from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tiger.core import DEFAULT_CORPUS, TigerError, build_index, packet_prompt, retrieve_packet


class TigerPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.work = Path(tempfile.mkdtemp(prefix="research-1-tiger-"))
        cls.index = cls.work / "tiger.sqlite"
        cls.stats = build_index(DEFAULT_CORPUS, cls.index)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.work)

    def test_builds_canonical_discovery_index(self) -> None:
        self.assertGreater(self.stats["documents"], 100)
        self.assertGreater(self.stats["chunks"], self.stats["documents"])

    def test_q2_packet_is_bounded_and_complete(self) -> None:
        packet = retrieve_packet("How are chunking and a knowledge base related?", DEFAULT_CORPUS, self.index)
        self.assertEqual(packet["status"], "ok")
        self.assertLessEqual(len(packet["excerpts"]), 8)
        self.assertTrue(any(item["path"] == "concepts/chunking.md" for item in packet["excerpts"]))
        self.assertTrue(any(item["path"] == "concepts/knowledge-bases.md" for item in packet["excerpts"]))
        self.assertTrue(packet["sources"])
        for source in packet["sources"]:
            self.assertRegex(source["published"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertRegex(source["video"]["id"], r"^[A-Za-z0-9_-]{11}$")
            self.assertIn(source["video"]["id"], source["video"]["url"])
            self.assertTrue(source["claims"])
        # Direct source prose may have no timestamp. The two canonical concepts
        # must still have linked, timestamped claim evidence for this synthesis.
        for path in ("concepts/chunking.md", "concepts/knowledge-bases.md"):
            claims = [claim for source in packet["sources"] for claim in source["claims"]
                      if claim["canonical_path"] == path]
            self.assertTrue(claims, f"Missing linked provenance for {path}")
            self.assertTrue(any(claim["timestamps"] for claim in claims))

    def test_q2_contains_supported_relationship_and_linked_source_claim(self) -> None:
        packet = retrieve_packet("How are chunking and a knowledge base related?", DEFAULT_CORPUS, self.index)
        excerpts = {item["path"]: item["text"].lower() for item in packet["excerpts"]}
        self.assertIn("concepts/chunking.md", excerpts)
        self.assertIn("concepts/knowledge-bases.md", excerpts)
        self.assertTrue(any(phrase in excerpts["concepts/chunking.md"] for phrase in (
            "specific knowledge it needs", "embedding precision", "splitting fixes"
        )))
        self.assertIn("curated, private store", excerpts["concepts/knowledge-bases.md"])
        self.assertIn("separate from the model's frozen weights", excerpts["concepts/knowledge-bases.md"])

        source = next(
            source for source in packet["sources"]
            if source["path"] == "sources/your-ultimate-n8n-rag-ai-agent-template-just-got-a-massive-upgrade.md"
        )
        claims = [claim for claim in source["claims"] if claim["canonical_path"] == "concepts/knowledge-bases.md"]
        self.assertTrue(claims)
        self.assertTrue(any(
            "chunking and curating" in claim["text"].lower()
            and any(timestamp["timestamp"] == "0:01:52" and timestamp["seconds"] == 112
                    for timestamp in claim["timestamps"])
            for claim in claims
        ))
        self.assertTrue(all(
            claim["text"] in (DEFAULT_CORPUS / "concepts/knowledge-bases.md").read_text(encoding="utf-8")
            for claim in claims
        ))

    def test_q5_preserves_unsupported_boundary(self) -> None:
        packet = retrieve_packet("What does Cole recommend for Kubernetes cluster autoscaling?", DEFAULT_CORPUS, self.index)
        self.assertEqual(packet["status"], "insufficient_coverage")
        self.assertEqual(packet["excerpts"], [])
        self.assertEqual(packet["sources"], [])

    def test_q6_returns_voice_evidence_and_provenance(self) -> None:
        packet = retrieve_packet("What does Cole recommend for voice agents?", DEFAULT_CORPUS, self.index)
        self.assertEqual(packet["status"], "ok")
        self.assertTrue(any(item["path"].startswith("concepts/voice-") for item in packet["excerpts"]))
        self.assertTrue(any(item["path"] == "sources/build-your-first-voice-ai-agent-in-20-minutes-with-livekit-open-source.md" for item in packet["excerpts"]))
        self.assertTrue(any(item["heading"] == "Overview" and "LiveKit" in item["text"] for item in packet["excerpts"]))
        self.assertTrue(all(len(item["text"]) <= 3500 and not item["text"].endswith("…") for item in packet["excerpts"]))
        self.assertTrue(packet["sources"])
        self.assertTrue(any(claim["timestamps"] for source in packet["sources"] for claim in source["claims"]))

    def test_timestamped_video_evidence_has_a_ready_to_cite_seek_url(self) -> None:
        packet = retrieve_packet("What does Cole mean when he says an LLM gets into the dumb zone?", DEFAULT_CORPUS, self.index)
        timestamps = [
            timestamp
            for source in packet["sources"]
            for claim in source["claims"]
            for timestamp in claim["timestamps"]
        ]
        self.assertTrue(timestamps)
        for timestamp in timestamps:
            parsed = urlparse(timestamp["url"])
            self.assertEqual(parse_qs(parsed.query).get("t"), [str(timestamp["seconds"])])
            self.assertIn(timestamp["url"], timestamp["citation"])
            self.assertIn("published", timestamp["citation"])
        self.assertIn("when it helps the reader verify a claim", packet_prompt(packet))

    def test_q4_returns_context_rot_explanation_and_matching_source(self) -> None:
        question = 'What does Cole mean when he says an LLM gets into “the dumb zone”?'
        cases = [(wording, limit)
                 for wording in (question, question.replace('“', '"').replace('”', '"'), question.replace('“', '').replace('”', ''))
                 for limit in (1, 8)]
        for wording, limit in cases:
            with self.subTest(question=wording, limit=limit):
                packet = retrieve_packet(wording, DEFAULT_CORPUS, self.index, limit=limit)
                self.assertEqual(packet["status"], "ok")
                concept = [item for item in packet["excerpts"] if item["path"] == "concepts/context-rot.md"]
                self.assertTrue(concept, "Q4 must retrieve the canonical context-rot explanation")
                explanation = "\n".join(item["text"] for item in concept).lower()
                for phrase in ("bounded attention", "dumb zone", "irrelevant information", "not a hard cliff"):
                    self.assertIn(phrase, explanation)
                canonical_text = (DEFAULT_CORPUS / "concepts/context-rot.md").read_text(encoding="utf-8")
                self.assertTrue(all(item["text"] in canonical_text for item in concept))
                sources = [source for source in packet["sources"] if source["path"] == "sources/are-agent-harnesses-bringing-back-vibe-coding.md"]
                self.assertEqual(len(sources), 1)
                source = sources[0]
                self.assertEqual(source["video"]["id"], "13HP_bSeNjU")
                self.assertEqual(source["published"], "2025-12-17")
                claims = [claim for claim in source["claims"] if claim["canonical_path"] == "concepts/context-rot.md"]
                self.assertTrue(claims, "The source must be linked to the retrieved context-rot claim")
                self.assertTrue(any("bounded attention" in claim["text"] and "dumb zone" in claim["text"] for claim in claims))
                self.assertTrue(all(claim["text"] in canonical_text for claim in claims))
                timestamps = [timestamp for claim in claims for timestamp in claim["timestamps"]]
                self.assertTrue(any(timestamp["timestamp"] == "0:19:21" and timestamp["seconds"] == 1161
                                    and parse_qs(urlparse(timestamp["url"]).query).get("t") == ["1161"]
                                    for timestamp in timestamps))
                self.assertLessEqual(len(packet["excerpts"]), limit)
                self.assertTrue(all(len(item["text"]) <= 3500 for item in packet["excerpts"]))

    def test_rejects_invalid_bounds(self) -> None:
        with self.assertRaisesRegex(TigerError, "limit must be"):
            retrieve_packet("chunking", DEFAULT_CORPUS, self.index, limit=9)

    def test_rejects_index_from_another_corpus(self) -> None:
        with self.assertRaisesRegex(TigerError, 'different corpus'):
            retrieve_packet('chunking', self.work / 'different-corpus', self.index)

    def test_cannot_build_generated_data_inside_read_only_corpus(self) -> None:
        with self.assertRaisesRegex(TigerError, 'outside the read-only corpus'):
            build_index(DEFAULT_CORPUS, DEFAULT_CORPUS / 'forbidden-index.sqlite')

    def test_deleted_index_only_requires_a_rebuild(self) -> None:
        rebuilt = self.work / "rebuilt.sqlite"
        build_index(DEFAULT_CORPUS, rebuilt)
        rebuilt.unlink()
        build_index(DEFAULT_CORPUS, rebuilt)
        self.assertEqual(retrieve_packet("Why does chunking matter in RAG?", DEFAULT_CORPUS, rebuilt)["status"], "ok")

    def test_package_has_no_venus_dependency(self) -> None:
        package = Path(__file__).parents[1] / "tiger"
        implementation = "\n".join(path.read_text(encoding="utf-8").lower() for path in package.glob("*.py"))
        self.assertNotIn("from venus", implementation)
        self.assertNotIn("import venus", implementation)
        self.assertNotIn(".venus/", implementation)


if __name__ == "__main__":
    unittest.main()
