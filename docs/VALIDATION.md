# Neptune validation

Retrieval, final-answer quality, provenance, and boundary enforcement are separate
claims. Research-1 informs the methodology; its historical model results are not new
Neptune runtime passes.

The separate [token-efficiency report](TOKEN-EFFICIENCY-REPORT.md) records a user-performed
five-question workload comparison. It preserves reported usage and startup figures.

## Acceptance checks — 2026-09-05

Windows, Python 3.13.1, Codex CLI 0.153.1. Cole revision:
`eba5e31bc628280c546d4828491051c308d550dc`.

`python -m neptune setup`: 683 Cole documents / 941 chunks; empty Laci index.
Actual Laci contains no example personal records; mutation tests use temporary fixtures.

`python -m unittest discover -s tests -v`: 32 tests passed, covering:

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
- Rejection of indexes from another corpus and index output inside read-only Cole.

Both project skills passed the supplied Skill Creator `quick_validate.py` validator.
PyYAML was installed only into ignored generated/validation-deps for that developer
check; it is not a Neptune runtime dependency.

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

Deterministic success alone does not establish fresh model-answer quality or repeatability.

## Two authorized fresh runtime evaluations — 2026-09-05

Two fresh Codex subagent tasks received only the project skill location, runtime
boundaries, and one raw question. No development history or expected answer was forked.
They used the inherited Codex model with no override; usage counters were not returned.
These were fresh skill evaluations, not CLI-launched permission-profile sessions:
boundary enforcement was checked separately by the host sandbox probe above. The
observable ledgers below were returned by the runtime agents, not a complete audit log.

**Cole explanation:** `Ask Cole: What does Cole mean when he says an LLM gets into
the dumb zone?` The runtime read the assistant and Cole skills, then invoked
`python -m neptune query 'Ask Cole: What does Cole mean when he says an LLM gets into the dumb zone?' --kb cole`
once. Result: `ok`. Its answer explained context overload, bounded attention, declining
reliability before the context limit, and compaction/handoff as the practical response.
It cited the canonical Context Rot record, its source record, and the validated video
link with `t=1161`, publication date 2025-12-17, and 0:19:21. The returned explanation
and practical takeaway are supported by the canonical context-rot excerpt. Retrieval,
answer, and provenance: **PASS for this run**. Its ledger reported no writes or network
use; no forbidden reads were reported.

**Unsupported control:** `Ask Cole: What does Cole recommend for Kubernetes cluster
autoscaling?` The runtime read the same two skills and invoked the corresponding
`neptune query ... --kb cole` command once. Result: `insufficient_coverage`.
Final answer: “The supplied Cole evidence doesn’t cover Kubernetes cluster autoscaling,
so I can’t attribute a recommendation to Cole. This retrieval limit doesn’t establish
that the topic is absent from the entire corpus.” Retrieval/answer: **PASS for this
run**. It fabricated no citations and did not substitute general advice. Its ledger
reported only the two skill reads and one retrieval command.

These two observations establish the tested fresh workflows, not repeated-run reliability,
automatic routing judgment across topics, or all conversational mutation behaviors.
