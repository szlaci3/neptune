# Neptune architecture

This describes implemented behavior and limits. Plans and TODO tracking stay in the task.

## Runtime

Neptune = Codex + project skills + deterministic tools + canonical knowledge. Python
does not call models, choose models, or own a conversation loop. `start` simply launches
native interactive Codex. Native integration uses [skills](https://learn.chatgpt.com/docs/build-skills)
and [permission profiles](https://learn.chatgpt.com/docs/permissions).

The launcher extends `:read-only`, adding write permission only to runtime/, Laci,
and generated/. Laci's .git metadata remains read-only. Approval escalation is disabled: 
`--ask-for-approval` is set to `never`, so it simply fails at operations beyond permissions.
Cole and code remain read-only. A differently configured desktop task does not inherit
these guarantees. Shell network access and web search are disabled; Codex retains its
own model transport, so there is network access but only for Codex to use OpenAI’s model service.
This profile does not independently constrain user-installed external connector tools; runtime 
instructions use local Neptune tools only.

## Routing and grounding

Codex selects one KB under the assistant skill's topic/perspective policy. Explicit
initial Ask Cole / Ask Laci overrides win. The query command rejects conflicting
overrides and returns needs_routing if no route is supplied. LLM judgment is not
misrepresented as a deterministic keyword classifier. Unclear perspectives require
user clarification; an empty result never silently switches KBs.

Cole uses Research-1's transferred Tiger packet workflow in place of Saturn's older
Pi/manual-navigation procedure. Laci supports adaptive searches and full-record reads.
Personal facts require Laci evidence; model assessments are distinguished from facts.
Cole-attributed claims use only supplied evidence, never unstated model knowledge.

## Cole retrieval and provenance

Tiger is copied into Neptune with local paths and no runtime dependency on sibling
projects. Its index is rebuilt from Neptune's Cole submodule, not copied from Research-1.
The initial local build indexes 683 documents into 941 chunks. Raw transcripts and
relationship-only sections are excluded. Up to eight canonical excerpts (3,500 characters
each, two per record) and eight sources form a packet. Every returned excerpt and
provenance field is reread from Markdown; FTS only locates candidates.

The port retains Research-1's lexical ranking and Q2/Q4 corrections. It additionally
validates index corpus identity, opens retrieval SQLite read-only, rejects index output
inside the corpus, checks real calendar dates, requires HTTPS video URLs, and rejects
minute/second values outside 0..59. Video IDs must have the allowed 11-character syntax
and match stored URLs. This is local validation, not online video-existence verification.

Video citation instructions retain Saturn's stricter rule: use supplied timestamps
when available and show the date immediately after every video link. Canonical records
and linked source records are also cited. Source presence alone does not establish
claim support; Codex must assess the actual excerpt.

Cole indexes require a developer rebuild after deliberate source updates. Lexical
relevance, source-edge selection, and stale-discovery limitations remain: returned
text is reread, but the whole Cole corpus is not fingerprinted for changed recall.
Missing/invalid indexes cause an error rather than improvised evidence.

## Laci mutations and discovery

Laci's SCHEMA.md defines the storage format. Knowledge, note, and flashcard records
share UUID-based stable Markdown paths. Date defaults to entry date; Author and Context
are optional. Notes promote to knowledge in place. Archive preserves content; delete
permanently removes it. No hidden backup of deleted private content is made.

The runtime supplies `authorized: true` only after explicit user intent. This is a tool
contract, not cryptographic authentication. The sandbox enforces Cole's write boundary;
the skill interprets consent. Mutations accept Laci only, reject unsafe identities,
serialize writers using an exclusive lock, require a SHA-256 revision for existing
records, and atomically replace files. External editors do not honor the lock: avoid
concurrent edits outside the tool during a runtime mutation. Follow-up record identity
stays in the Codex conversation, not a cross-session global last-record pointer.

Every successful mutation rebuilds the Laci FTS index through a temporary database and
atomic replacement. On failure, saved_index_failed preserves the change and reports
contextual recovery options. Search checks index identities/revisions against canonical
files and falls back to scanning when the index is absent, corrupt, or stale. This
correctness-first freshness check reads all Laci records and targets a personal collection,
not a large hosted database. A malformed canonical record is reported for repair.

## Study and coding

New cards are due today. User ratings set the next interval: again → today, hard → at
least one day with current interval, good → at least one day and double interval,
easy → at least four days and triple interval. Intervals cap at 36,500 days. This is
a transparent simple scheduler, not FSRS. Codex conducts the quiz and persists ratings
only on the user's action. Flashcard metadata and Markdown Front/Back stay synchronized.
Local study needs no external deck service; mobile synchronization is not implemented.

Coding uses Codex's existing capabilities with grounded Cole advice where relevant.
Actual code changes need a task rooted in the coding project with its permissions:
the assistant launcher cannot edit arbitrary projects. Voice may use the host's native
feature when available; Neptune adds no audio store, remote server, or always-on host.
