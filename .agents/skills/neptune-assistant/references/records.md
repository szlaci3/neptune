# Laci operations

All records are Markdown in Laci `records/`; stable paths identify records. Types are
`knowledge`, `note`, and `flashcard`. Notes are searchable Laci records and become
knowledge by promotion in place. Flashcards belong to a named deck (default `Default`).

Use `python -m neptune search '<terms>'` to discover records. Optional flags are
`--kind note`, `--kind flashcard`, `--kind knowledge`, `--archived`, and `--limit 1..50`.
Use `python -m neptune read records/<id>.md` for complete content and the current
revision. Do not guess an edit target from a search ranking: show plausible titles
and ask when ambiguous. For “edit that”, retain the last successfully changed path
and revision in this task's conversation. If that context is missing, rediscover it.

Send ONE JSON object through stdin to `python -m neptune mutate`. Use a safely quoted
PowerShell single-quoted here-string or a JSON request file in runtime/scratch (create
that directory if necessary); do not interpolate content into a shell command. Never
turn source text into commands. This tool's `authorized` flag records your interpretation
of the user's command; it is not independent authentication.

Create knowledge or a note:

```json
{"action":"create","authorized":true,"metadata":{"type":"note","title":"Meeting notes","Context":"Project name"},"body":"# Meeting notes\n\nThe user-approved note."}
```

`Author`, `Date` (YYYY-MM-DD), and `Context` are optional metadata. Date defaults to
today. Do not ask a separate metadata question. When saving material based on a KB
answer, include the supporting canonical/source links in the body rather than
inventing an author or presenting an inference as the user's own fact.

Update in place:

```json
{"action":"update","authorized":true,"path":"records/EXACT-ID.md","expected_revision":"REVISION-FROM-READ","body":"The complete replacement body","metadata":{"title":"Updated title"}}
```

Delete, archive, restore, and promote take the same `path`, `expected_revision`, and
`authorized` fields. Promotion changes a note to knowledge without changing its ID.
Delete permanently removes the record; do this only when the user requests deletion.
Archive retains the record and excludes it from normal search and due-card practice.
If a revision conflict occurs, read again and reconcile with the user's intended edit;
do not overwrite intervening changes blindly.

Create a flashcard from the conversation:

```json
{"action":"create","authorized":true,"metadata":{"type":"flashcard","title":"JavaScript numeric separators","front":"What does 4_000 mean in JavaScript?","back":"It is the number 4000. The underscore is a numeric separator.","deck":"JavaScript"}}
```

Use `Context` to retain derivation/source details for cards. Do not silently persist a
card merely because an answer is educational. “Make a flashcard about this” authorizes
creation when the conversation clearly identifies the content.

Practice: run `python -m neptune due` (optionally `--deck JavaScript`), present one
front at a time, let the user attempt it, then show the back and ask their rating.
Record their rating with `action: review`, `rating: again|hard|good|easy`, the exact
path and current revision, and `authorized: true`. Never grade or schedule on their
behalf without a request. Scheduling is a simple transparent interval system:
again = today; hard = max(1, current interval) days; good = max(1, 2×interval);
easy = max(4, 3×interval). New cards are due today. It is not FSRS or a claim of optimal
learning. Use native Codex conversation for quiz state; the saved card holds due dates.

After any mutation, inspect `saved`, `indexed`, and `status`. Report successful saves
briefly; successful indexing is silent. `saved_index_failed` means the record change
SUCCEEDED: do not retry creation. Explain the index error and offer the returned
recovery options. Canonical search remains available. If an error occurs before saving,
do not tell the user that the record was persisted.
