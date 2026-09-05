"""Build and query tiger's disposable discovery index.

The index only locates candidates.  Every excerpt and provenance field returned
by :func:`retrieve_packet` is re-read from canonical Markdown at query time.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = PACKAGE_ROOT / "knowledge" / "cole-medin-knowledge-base"
DEFAULT_INDEX = PACKAGE_ROOT / "generated" / "tiger.sqlite"
# Ported from Research-1. These bounds constrain discovery, not authority.
MAX_RETRIEVED_CHUNKS = 8
DEFAULT_RETRIEVED_CHUNKS = 8
MAX_CHUNK_CHARS = 3_500
MAX_SOURCE_RECORDS = 8
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+[^)]*)?\)")
TIMESTAMP_RE = re.compile(r"\[(\d{1,2}:\d{2}:\d{2})\]")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "cole", "does", "for", "how",
    "in", "is", "it", "of", "on", "or", "related", "the", "to", "what",
    "when", "why", "with",
}
NON_EVIDENCE_HEADINGS = {
    "builds on", "concepts covered", "contrasts with", "entities", "implemented by",
    "part of", "prerequisites", "related", "sources", "tools", "transcript", "works with",
}


class TigerError(RuntimeError):
    """A deterministic tiger input, build, or provenance error."""


@dataclass(frozen=True)
class Section:
    heading: str
    level: int
    ordinal: int
    text: str


@dataclass(frozen=True)
class Chunk:
    """A paragraph-aware bounded excerpt from one canonical Markdown section."""

    heading: str
    section_ordinal: int
    chunk_ordinal: int
    text: str


@dataclass(frozen=True)
class Document:
    path: str
    frontmatter: dict[str, str]
    body: str
    sections: tuple[Section, ...]

    @property
    def type(self) -> str:
        return self.frontmatter.get("type", "")

    @property
    def title(self) -> str:
        return self.frontmatter.get("title", self.sections[0].heading if self.sections else self.path)


def _canonical_files(corpus: Path) -> Iterable[Path]:
    for directory in ("concepts", "entities", "sources"):
        base = corpus / directory
        if base.is_dir():
            yield from sorted(path for path in base.rglob("*.md") if path.name != "index.md")


def _frontmatter_and_body(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    frontmatter: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$", line)
        if match:
            frontmatter[match.group(1)] = match.group(2).strip('"\'')
    return frontmatter, text[end + 4 :].lstrip("\r\n")


def _sections(body: str, fallback_heading: str) -> tuple[Section, ...]:
    matches = list(HEADING_RE.finditer(body))
    if not matches:
        clean = body.strip()
        return (Section(fallback_heading, 1, 0, clean),) if clean else ()
    result: list[Section] = []
    preamble = body[: matches[0].start()].strip()
    if preamble:
        result.append(Section("Overview", 1, -1, preamble))
    for ordinal, match in enumerate(matches):
        next_start = matches[ordinal + 1].start() if ordinal + 1 < len(matches) else len(body)
        text = body[match.end() : next_start].strip()
        if text:
            result.append(Section(match.group(2).strip(), len(match.group(1)), ordinal, text))
    return tuple(result)


def load_document(corpus: Path, path: str) -> Document:
    corpus = corpus.resolve()
    target = (corpus / path).resolve()
    try:
        relative = target.relative_to(corpus)
    except ValueError as exc:
        raise TigerError(f"path escapes corpus: {path}") from exc
    if target.suffix != ".md" or not target.is_file():
        raise TigerError(f"canonical record not found: {path}")
    frontmatter, body = _frontmatter_and_body(target.read_text(encoding="utf-8"))
    return Document(relative.as_posix(), frontmatter, body, _sections(body, target.stem))


def _split_text(text: str, maximum: int) -> tuple[str, ...]:
    """Split at paragraph boundaries first, then at a word boundary if needed."""
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > maximum:
            if current:
                chunks.append(current)
                current = ""
            remaining = paragraph
            while len(remaining) > maximum:
                cut = remaining.rfind(" ", 0, maximum)
                cut = cut if cut > 0 else maximum
                chunks.append(remaining[:cut].strip())
                remaining = remaining[cut:].strip()
            if remaining:
                current = remaining
            continue
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if len(candidate) > maximum:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return tuple(chunks)


def document_chunks(document: Document) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    for section in document.sections:
        if section.heading.lower() in NON_EVIDENCE_HEADINGS or section.text.count("](") >= 4:
            continue
        for chunk_ordinal, text in enumerate(_split_text(section.text, MAX_CHUNK_CHARS)):
            chunks.append(Chunk(section.heading, section.ordinal, chunk_ordinal, text))
    return tuple(chunks)


def build_index(corpus: Path = DEFAULT_CORPUS, index: Path = DEFAULT_INDEX) -> dict[str, int]:
    """Recreate tiger's FTS index exclusively from the canonical Cole corpus."""
    corpus = corpus.resolve()
    if not corpus.is_dir():
        raise TigerError(f"corpus directory not found: {corpus}")
    if index.resolve().is_relative_to(corpus):
        raise TigerError("generated index must be outside the read-only corpus")
    index.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="tiger-", suffix=".sqlite", dir=index.parent)
    os.close(fd)
    temporary = Path(name)
    connection = sqlite3.connect(temporary)
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE chunks USING fts5("
            "path UNINDEXED, type UNINDEXED, heading UNINDEXED, section_ordinal UNINDEXED, "
            "chunk_ordinal UNINDEXED, text)"
        )
        document_count = 0
        chunk_count = 0
        for file_path in _canonical_files(corpus):
            document = load_document(corpus, file_path.relative_to(corpus).as_posix())
            if document.type not in {"concept", "entity", "source"}:
                continue
            document_count += 1
            for chunk in document_chunks(document):
                searchable = "\n".join(
                    part for part in (document.title, document.frontmatter.get("description", ""), chunk.heading, chunk.text) if part
                )
                connection.execute(
                    "INSERT INTO chunks(path, type, heading, section_ordinal, chunk_ordinal, text) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (document.path, document.type, chunk.heading, str(chunk.section_ordinal), str(chunk.chunk_ordinal), searchable),
                )
                chunk_count += 1
        connection.execute("CREATE TABLE build_info (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO build_info VALUES (?, ?)", ("corpus", str(corpus)))
        connection.execute("INSERT INTO build_info VALUES (?, ?)", ("format", "tiger-1"))
        connection.commit()
    finally:
        connection.close()
    temporary.replace(index)
    return {"documents": document_count, "chunks": chunk_count}


def _text_terms(text: str) -> list[str]:
    """Read all significant terms; evidence must not inherit the query's cap."""
    terms = []
    for term in WORD_RE.findall(text.lower()):
        if len(term) > 1 and term not in STOP_WORDS and term not in terms:
            terms.append(term)
    return terms


def _query_terms(question: str) -> list[str]:
    terms = _text_terms(question)
    if not terms:
        raise TigerError("question has no searchable terms")
    return terms[:8]


def _match_term(term: str) -> str:
    """Use a deliberately small normalization only for deterministic re-ranking."""
    if term.endswith("bases"):
        return term[:-1]
    if term.endswith("ies") and len(term) > 3:
        return term[:-3] + "y"
    if term.endswith("s") and len(term) > 3 and not term.endswith("ss"):
        return term[:-1]
    return term


def _fts_expression(question: str) -> str:
    # Terms come from a restrictive word tokenizer, never directly from FTS syntax.
    return " OR ".join(f'"{term}"' for term in _query_terms(question))


def _resolve_link(corpus: Path, record_path: str, href: str) -> str | None:
    href = href.split("#", 1)[0]
    if not href or "://" in href or not href.endswith(".md"):
        return None
    target = (corpus / Path(record_path).parent / href).resolve()
    try:
        return target.relative_to(corpus.resolve()).as_posix()
    except ValueError:
        return None


def _source_edges(document: Document, corpus: Path) -> list[dict[str, Any]]:
    sources_section = next((section for section in document.sections if section.heading.lower() == "sources"), None)
    if not sources_section:
        return []
    edges = []
    for line in sources_section.text.splitlines():
        match = LINK_RE.search(line)
        if not match:
            continue
        path = _resolve_link(corpus, document.path, match.group(2))
        if not path or not path.startswith("sources/"):
            continue
        timestamps = []
        for timestamp in TIMESTAMP_RE.findall(line):
            timestamps.append({"timestamp": timestamp, "seconds": timestamp_seconds(timestamp)})
        edges.append({"path": path, "label": match.group(1), "claim": line.lstrip("- ").strip(), "timestamps": timestamps})
    return edges


def _valid_video_url(url: str, video_id: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = parsed.netloc.lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        return parse_qs(parsed.query).get("v", [None])[0] == video_id
    return host == "youtu.be" and parsed.path.strip("/") == video_id


def timestamp_seconds(timestamp: str) -> int:
    if not re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", timestamp):
        raise TigerError(f"invalid timestamp: {timestamp}")
    hour, minute, second = map(int, timestamp.split(":"))
    if minute > 59 or second > 59:
        raise TigerError(f"invalid timestamp: {timestamp}")
    return hour * 3600 + minute * 60 + second


def _timestamp_url(video_url: str, seconds: int) -> str:
    """Return the validated source URL with an unambiguous seek position."""
    parsed = urlparse(video_url)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "t"]
    query.append(("t", str(seconds)))
    return urlunparse(parsed._replace(query=urlencode(query)))


def _rendered_timestamps(
    timestamps: list[dict[str, Any]], video_url: str, title: str, published: str
) -> list[dict[str, Any]]:
    """Add a ready-to-paste Markdown citation to each canonical timestamp."""
    rendered = []
    for timestamp in timestamps:
        timestamp_url = _timestamp_url(video_url, int(timestamp["seconds"]))
        rendered.append(
            {
                **timestamp,
                "url": timestamp_url,
                "citation": f"[{title}]({timestamp_url}) (published {published}; {timestamp['timestamp']})",
            }
        )
    return rendered


def _source_packet(corpus: Path, path: str, claims: list[dict[str, Any]]) -> dict[str, Any]:
    source = load_document(corpus, path)
    if source.type != "source":
        raise TigerError(f"linked provenance record is not a source: {path}")
    video_id = source.frontmatter.get("youtube_id", "")
    url = source.frontmatter.get("url", "")
    published = source.frontmatter.get("published", "")
    if not VIDEO_ID_RE.fullmatch(video_id):
        raise TigerError(f"invalid video ID in {path}: {video_id!r}")
    if not _valid_video_url(url, video_id):
        raise TigerError(f"video URL does not validate against ID in {path}")
    try:
        date.fromisoformat(published)
    except ValueError as exc:
        raise TigerError(f"invalid publication date in {path}: {published!r}") from exc
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
        raise TigerError(f"invalid publication date in {path}: {published!r}")
    rendered_claims = [
        {
            **claim,
            "timestamps": _rendered_timestamps(claim["timestamps"], url, source.title, published),
        }
        for claim in claims
    ]
    return {
        "path": source.path,
        "title": source.title,
        "published": published,
        "video": {"id": video_id, "url": url},
        "claims": rendered_claims,
    }


def retrieve_packet(
    question: str,
    corpus: Path = DEFAULT_CORPUS,
    index: Path = DEFAULT_INDEX,
    *,
    limit: int = DEFAULT_RETRIEVED_CHUNKS,
) -> dict[str, Any]:
    """Return a bounded, canonical-Markdown-derived evidence packet."""
    if not question.strip():
        raise TigerError("question must not be empty")
    if not index.is_file():
        raise TigerError(f"generated index not found: {index}; run tiger build")
    if not 1 <= limit <= MAX_RETRIEVED_CHUNKS:
        raise TigerError(f"limit must be between 1 and {MAX_RETRIEVED_CHUNKS}")

    connection = sqlite3.connect(index.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        info = dict(connection.execute("SELECT key, value FROM build_info"))
        if info.get("format") != "tiger-1" or Path(info.get("corpus", "")).resolve() != corpus.resolve():
            raise TigerError("generated index belongs to a different corpus; rebuild locally")
        rows = connection.execute(
            "SELECT path, type, heading, section_ordinal, chunk_ordinal, -bm25(chunks) AS score FROM chunks "
            "WHERE chunks MATCH ? AND type IN ('concept', 'entity', 'source') "
            "ORDER BY score DESC, path, CAST(section_ordinal AS INTEGER), CAST(chunk_ordinal AS INTEGER) LIMIT 200",
            (_fts_expression(question),),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise TigerError(f"invalid generated index: {exc}") from exc
    finally:
        connection.close()

    terms = {_match_term(term) for term in _query_terms(question)}
    minimum_matches = 2 if len(terms) >= 2 else 1
    candidates: list[tuple[Document, Chunk, float, int, int]] = []
    for path, _type, heading, section_ordinal, chunk_ordinal, score in rows:
        try:
            document = load_document(corpus, path)
        except TigerError:
            continue  # A stale discovery index must not make stale text authoritative.
        chunk = next(
            (
                item
                for item in document_chunks(document)
                if item.section_ordinal == int(section_ordinal)
                and item.chunk_ordinal == int(chunk_ordinal)
                and item.heading == heading
            ),
            None,
        )
        if not chunk:
            continue
        record_words = {
            _match_term(term)
            for term in _text_terms(" ".join((document.title, document.frontmatter.get("description", ""), chunk.text)))
        }
        matched_terms = len(terms.intersection(record_words))
        title_words = {_match_term(term) for term in _text_terms(document.title)}
        title_matches = len(terms.intersection(title_words))
        # A record named by the question is a valid direct route even when the
        # question joins two records (for example, Chunking + Knowledge Bases).
        # A body-only hit still needs multi-term coverage to avoid lexical noise.
        if matched_terms < minimum_matches and not title_matches:
            continue
        candidates.append((document, chunk, float(score), matched_terms, title_matches))
    # Title matches add weight without taking unconditional priority over body coverage.
    candidates.sort(key=lambda item: (-(item[3] + item[4]), -item[3], -item[2], item[0].path, item[1].section_ordinal, item[1].chunk_ordinal))

    selected: list[tuple[Document, Chunk, float]] = []
    selected_chunk_ids: set[tuple[str, int, int]] = set()
    per_record_count: dict[str, int] = {}
    for document, chunk, score, _, _ in candidates:
        chunk_id = (document.path, chunk.section_ordinal, chunk.chunk_ordinal)
        if chunk_id in selected_chunk_ids or per_record_count.get(document.path, 0) >= 2:
            continue
        selected.append((document, chunk, float(score)))
        selected_chunk_ids.add(chunk_id)
        per_record_count[document.path] = per_record_count.get(document.path, 0) + 1
        if len(selected) == limit:
            break

    if not selected:
        return {
            "format": "tiger-1",
            "question": question,
            "status": "insufficient_coverage",
            "reason": "No canonical concept or entity record matched the question.",
            "excerpts": [],
            "sources": [],
        }

    source_claims: dict[str, list[dict[str, Any]]] = {}
    for document, chunk, _ in selected:
        if document.type == "source":
            if len(source_claims) >= MAX_SOURCE_RECORDS and document.path not in source_claims:
                continue
            timestamps = []
            for timestamp in TIMESTAMP_RE.findall(chunk.text):
                timestamps.append({"timestamp": timestamp, "seconds": timestamp_seconds(timestamp)})
            source_claims.setdefault(document.path, []).append(
                {
                    "canonical_path": document.path,
                    "canonical_heading": chunk.heading,
                    "excerpt_ref": {"path": document.path, "heading": chunk.heading},
                    "timestamps": timestamps,
                }
            )
            continue
        edges = _source_edges(document, corpus)
        if not edges:
            raise TigerError(f"missing linked source provenance for {document.path}")
        edges.sort(
            key=lambda edge: (
                -int(bool(edge["timestamps"])),
                -len(terms.intersection({_match_term(term) for term in _text_terms(edge["claim"])})),
                edge["path"],
            )
        )
        # One linked source record per concept/entity chunk keeps every claim
        # traceable while leaving capacity for directly retrieved source chunks.
        for edge in edges[:1]:
            if len(source_claims) >= MAX_SOURCE_RECORDS and edge["path"] not in source_claims:
                break
            source_claims.setdefault(edge["path"], []).append(
                {
                    "canonical_path": document.path,
                    "canonical_heading": "Sources",
                    "text": edge["claim"],
                    "timestamps": edge["timestamps"],
                }
            )

    packet_sources = [_source_packet(corpus, path, claims) for path, claims in sorted(source_claims.items())]
    return {
        "format": "tiger-1",
        "question": question,
        "status": "ok",
        "excerpts": [
            {
                "path": document.path,
                "heading": chunk.heading,
                "text": chunk.text,
                "score": round(score, 6),
            }
            for document, chunk, score in selected
        ],
        "sources": packet_sources,
    }


def packet_prompt(packet: dict[str, Any]) -> str:
    """Produce the fixed context that a caller supplies to exactly one Codex response."""
    return (
        "You are Neptune. Answer only from this tiger evidence packet. "
        "Do not claim coverage when status is insufficient_coverage. Cite only the supplied "
        "canonical paths and source metadata. A supplied video timestamp citation is available "
        "when it helps the reader verify a claim; retain the publication date when citing a video.\n\n"
        + json.dumps(packet, ensure_ascii=False, indent=2)
    )
