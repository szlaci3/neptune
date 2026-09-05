"""Canonical Markdown storage, optimistic mutations, and disposable discovery."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
LACI = ROOT / 'knowledge' / 'laci-knowledge-base'
KINDS = {'knowledge', 'note', 'flashcard'}


class StoreError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.neptune-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class Store:
    def __init__(self, root: Path = LACI, index: Path | None = None):
        self.root = root.resolve()
        if self.root.name == 'cole-medin-knowledge-base':
            raise StoreError('Cole is read-only')
        self.index = index or ROOT / 'generated' / 'laci.sqlite'

    def path(self, identity: str) -> Path:
        if not re.fullmatch(r'records/[a-z0-9][a-z0-9-]*\.md', identity):
            raise StoreError('Expected an exact records/<id>.md identity')
        path = self.root / identity
        if path.resolve().parent != self.root / 'records' or path.is_symlink():
            raise StoreError('Record path escapes the canonical records directory')
        return path

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / '.neptune-write.lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise StoreError('Another write is active. Retry; if a process crashed, inspect .neptune-write.lock before removing it.') from exc
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(str(os.getpid()))
            yield
        finally:
            lock.unlink()

    def read(self, identity: str) -> dict:
        path = self.path(identity)
        try:
            data = path.read_bytes()
        except FileNotFoundError as exc:
            raise StoreError(f'Record not found: {identity}') from exc
        text = data.decode('utf-8-sig').replace('\r\n', '\n')
        if not text.startswith('---\n') or '\n---\n' not in text[4:]:
            raise StoreError(f'Invalid OKF frontmatter: {identity}')
        header, body = text[4:].split('\n---\n', 1)
        try:
            metadata = {key: json.loads(value) for key, value in
                        (line.split(': ', 1) for line in header.splitlines())}
        except (ValueError, TypeError) as exc:
            raise StoreError(f'Invalid Neptune metadata: {identity}') from exc
        self.validate(metadata, body)
        return {'path': identity, 'revision': digest(data), 'metadata': metadata, 'body': body.strip()}

    @staticmethod
    def validate(metadata: dict, body: str):
        if not isinstance(body, str):
            raise StoreError('body must be text')
        if metadata.get('type') not in KINDS:
            raise StoreError('type must be knowledge, note, or flashcard')
        if not isinstance(metadata.get('title'), str) or not metadata['title'].strip():
            raise StoreError('title is required')
        if not body.strip():
            raise StoreError('body is required')
        if metadata.get('status') not in {'active', 'archived'}:
            raise StoreError('status must be active or archived')
        for key in ('Date', 'created', 'updated', 'due'):
            if key in ('created', 'updated') and key not in metadata:
                raise StoreError(f'{key} is required')
            if key in metadata:
                try:
                    date.fromisoformat(metadata[key])
                except (TypeError, ValueError) as exc:
                    raise StoreError(f'{key} must be an ISO calendar date') from exc
        for key in ('Author', 'Context'):
            if key in metadata and not isinstance(metadata[key], str):
                raise StoreError(f'{key} must be text')
        if metadata['type'] == 'flashcard':
            for key in ('front', 'back', 'deck', 'due'):
                if not isinstance(metadata.get(key), str) or not metadata[key].strip():
                    raise StoreError(f'flashcard {key} is required')
            if type(metadata.get('interval')) is not int or not 0 <= metadata['interval'] <= 36500:
                raise StoreError('Invalid review interval')

    def records(self):
        for path in sorted((self.root / 'records').glob('*.md')):
            yield self.read('records/' + path.name)

    def write_record(self, identity: str, metadata: dict, body: str):
        self.validate(metadata, body)
        text = '---\n' + '\n'.join(f'{k}: {json.dumps(v, ensure_ascii=False)}' for k, v in metadata.items())
        atomic_write(self.path(identity), (text + '\n---\n\n' + body.strip() + '\n').encode('utf-8'))

    def reindex(self) -> dict:
        """Caller holds the write lock. Readers never need to create an index."""
        records = list(self.records())
        self.index.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='laci-', suffix='.sqlite', dir=self.index.parent)
        os.close(fd)
        try:
            with closing(sqlite3.connect(name)) as db:
                db.execute('CREATE VIRTUAL TABLE records USING fts5(path UNINDEXED, revision UNINDEXED, text)')
                db.executemany('INSERT INTO records VALUES (?, ?, ?)',
                               [(r['path'], r['revision'], r['metadata']['title'] + '\n' + r['body']) for r in records])
                db.commit()
            os.replace(name, self.index)
        finally:
            Path(name).unlink(missing_ok=True)
        return {'status': 'ok', 'records': len(records)}

    def after_write(self, identity: str, action: str) -> dict:
        result = {'status': 'ok', 'action': action, 'path': identity, 'saved': True}
        if action != 'delete':
            result['record'] = self.read(identity)
        try:
            self.reindex()
            result['indexed'] = True
        except (OSError, sqlite3.Error, StoreError) as exc:
            result.update(status='saved_index_failed', indexed=False, error=str(exc),
                          recovery=['Use canonical search now; it does not require an index.',
                                    'Fix the reported indexing problem, then run python -m neptune reindex.'])
        return result

    def mutate(self, request: dict) -> dict:
        """The runtime supplies explicit user intent; this flag is not authentication."""
        if request.get('authorized') is not True:
            raise StoreError('Persistence requires an explicit user command or approval')
        if request.get('kb', 'laci') != 'laci':
            raise StoreError('Only Laci may be mutated; Cole is read-only')
        if not isinstance(request.get('metadata', {}), dict):
            raise StoreError('metadata must be an object')
        action = request.get('action')
        if action not in {'create', 'update', 'delete', 'archive', 'restore', 'promote', 'review'}:
            raise StoreError('Unknown mutation action')
        with self.locked():
            today = date.today().isoformat()
            if action == 'create':
                metadata = dict(request.get('metadata', {}))
                if set(metadata) - {'type', 'title', 'Author', 'Date', 'Context', 'front', 'back', 'deck'}:
                    raise StoreError('Unsupported create metadata')
                metadata.setdefault('type', 'knowledge')
                metadata.setdefault('Date', today)
                metadata.update(created=today, updated=today, status='active')
                body = request.get('body', '')
                if metadata['type'] == 'flashcard':
                    metadata.setdefault('deck', 'Default')
                    metadata.update(due=today, interval=0)
                    body = f"# {metadata.get('title', '')}\n\n## Front\n\n{metadata.get('front', '')}\n\n## Back\n\n{metadata.get('back', '')}"
                identity = f'records/{uuid.uuid4().hex}.md'
            else:
                identity = request.get('path', '')
                old = self.read(identity)
                if request.get('expected_revision') != old['revision']:
                    raise StoreError('Revision conflict: read the exact record again before changing it')
                metadata, body = dict(old['metadata']), old['body']
                if action == 'delete':
                    self.path(identity).unlink()
                    return self.after_write(identity, action)
                if action == 'update':
                    changes = request.get('metadata', {})
                    if set(changes) - {'title', 'Author', 'Date', 'Context', 'front', 'back', 'deck'}:
                        raise StoreError('Only content and optional metadata may be edited')
                    metadata.update(changes)
                    body = request.get('body', body)
                    if metadata['type'] == 'flashcard':
                        body = f"# {metadata['title']}\n\n## Front\n\n{metadata['front']}\n\n## Back\n\n{metadata['back']}"
                elif action in {'archive', 'restore'}:
                    metadata['status'] = 'archived' if action == 'archive' else 'active'
                elif action == 'promote':
                    if metadata['type'] != 'note':
                        raise StoreError('Only notes can be promoted to knowledge')
                    metadata['type'] = 'knowledge'
                elif action == 'review':
                    if metadata['type'] != 'flashcard' or metadata['status'] != 'active':
                        raise StoreError('Review requires an active flashcard')
                    rating = request.get('rating')
                    interval = metadata['interval']
                    if rating not in {'again', 'hard', 'good', 'easy'}:
                        raise StoreError('rating must be again, hard, good, or easy')
                    interval = {'again': 0, 'hard': max(1, interval),
                                'good': max(1, interval * 2), 'easy': max(4, interval * 3)}[rating]
                    interval = min(36500, interval)
                    metadata.update(interval=interval, due=(date.today() + timedelta(days=interval)).isoformat(), last_review=today)
                metadata['updated'] = today
            self.write_record(identity, metadata, body)
            return self.after_write(identity, action)

    def search(self, question: str = '', *, kind: str | None = None, archived=False, limit=8) -> dict:
        if kind and kind not in KINDS:
            raise StoreError('Unknown record kind')
        if not 1 <= limit <= 50:
            raise StoreError('limit must be 1..50')
        # Canonical scanning is also the reliable fallback for missing/stale indexes.
        records = list(self.records())
        words = list(dict.fromkeys(re.findall(r'\w+', question.casefold())))[:16]
        ignored = {'what', 'does', 'the', 'about', 'know', 'laci', 'ask', 'my', 'is', 'a', 'i', 'and', 'for'}
        words = [word for word in words if word not in ignored]
        discovery = 'canonical'
        indexed_paths = None
        if words and self.index.is_file():
            try:
                with closing(sqlite3.connect(self.index.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                    fingerprints = dict(db.execute('SELECT path, revision FROM records'))
                    if fingerprints == {r['path']: r['revision'] for r in records}:
                        expression = ' OR '.join('"' + w + '"*' for w in words)
                        indexed_paths = {row[0] for row in db.execute('SELECT path FROM records WHERE records MATCH ?', (expression,))}
                        discovery = 'fts5'
            except (sqlite3.Error, OSError):
                pass  # Canonical files are usable during index recovery.
        matches = []
        for record in records:
            if indexed_paths is not None and record['path'] not in indexed_paths:
                continue
            metadata = record['metadata']
            if (kind and metadata['type'] != kind) or (not archived and metadata['status'] == 'archived'):
                continue
            title = metadata['title'].casefold()
            content = (title + '\n' + record['body']).casefold()
            score = sum(1 + int(word in title) for word in words if word in content)
            if words and not score:
                continue
            matches.append((score, record))
        matches.sort(key=lambda item: (-item[0], item[1]['path']))
        return {'format': 'neptune-laci-1', 'kb': 'laci', 'status': 'ok' if matches else 'insufficient_coverage',
                'discovery': discovery, 'total': len(matches),
                'records': [{**r, 'body': r['body'][:3500], 'truncated': len(r['body']) > 3500} for _, r in matches[:limit]]}

    def due(self, deck: str | None = None) -> dict:
        today = date.today().isoformat()
        cards = [r for r in self.records() if r['metadata']['type'] == 'flashcard'
                 and r['metadata']['status'] == 'active' and r['metadata']['due'] <= today
                 and (deck is None or r['metadata']['deck'] == deck)]
        cards.sort(key=lambda r: (r['metadata']['due'], r['path']))
        return {'status': 'ok', 'total': len(cards), 'cards': cards[:50]}
