# Neptune validation

Retrieval, final-answer quality, provenance, and boundary enforcement are separate
claims. Research-1 informs the methodology; its historical model results are not new
Neptune runtime passes.

## Acceptance checks — 2026-09-05

Windows, Python 3.13.1, Codex CLI 0.153.1. Cole revision:
`eba5e31bc628280c546d4828491051c308d550dc`.

`python -m neptune setup`: 683 Cole documents / 941 chunks; empty Laci index.
Actual Laci contains no example personal records; mutation tests use temporary fixtures.

`python -m unittest discover -s tests -v`: 27 tests passed, covering:

- Ten transferred Tiger checks: Q2 relationship evidence, Q4 explanation and
  19:21/1161-second provenance, Q5 unsupported control, Q6 voice evidence, bounded
  packets, and index rebuilding.
- Explicit overrides/conflicts, no accidental Cole query on Laci, empty-Laci behavior.
  Automatic LLM routing is a skill behavior, not proven by these checks.
- Authorized create/edit/delete, exact IDs, stale revision conflicts, locking, atomic
  write failure, Unicode, literal shell-looking content, metadata validation, indexing
  failure preservation, and missing/stale/corrupt index fallback.
- Note archive/restore/promotion and flashcard create/edit/review schedules.
- A real CLI subprocess journey in an isolated copy: save/search/promote a note,
  create/review a card, delete knowledge, and reject Cole mutation.
- Invalid video IDs/dates, unsafe schemes, and timestamp range checks.

`python scripts/verify_runtime_sandbox.py` passed on the host using the exact launcher
profile: Cole write denied, code write denied, Laci writable, generated writable, Cole
readable. Denied-write checks open without truncation or writing; no source contents
change. This verifies tested path access, not every possible sandbox escape.

Two Windows failures found and fixed: SQLite connections must close before replacing
their file, and CRLF Markdown must normalize for parsing while hashes retain original
bytes. An initial attempt to create a nested restricted Windows token failed; running
the host-side probe with a named permission profile succeeded.

## Runtime protocol

Use a fresh runtime task with skills and a raw question, excluding evaluator answers
and development history. Preserve the tool packet, final answer, visible model identity,
and tool trace. Score retrieval, answer, provenance, and boundary behavior independently.
An unsupported question must receive an honest insufficient-evidence answer. Video
citations retain dates and available timestamps. No web substitution or cross-KB fallback.

Fresh runtime results are recorded below after evaluation. Deterministic success alone
does not establish fresh model-answer quality or repeatability.
