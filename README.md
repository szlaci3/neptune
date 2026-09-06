# Neptune

Neptune is a personal assistant operated by **Codex**, with two local knowledge
bases, notes, and flashcards. Codex is the runtime: no Pi dependency, second agent
loop, model API wrapper, or background service.

Cole contains AI engineering knowledge. Laci holds your explicitly saved personal
knowledge, notes, and study cards. Ask naturally in a dedicated Neptune task.

## Start

Requirements: Python 3.11+ with SQLite FTS5, an installed/authenticated Codex CLI,
and both knowledge submodules checked out. The tools use Python's standard library
only. This build was checked with Python 3.13.1 and Codex CLI 0.153.1.

From this directory:

```powershell
python -X utf8 -m neptune setup
python -X utf8 -m neptune start
```

The launcher checks PATH, then the Windows Codex desktop installation. You do not
need to modify PATH when using that installation. To select a specific executable,
use `python -m neptune start --codex 'C:/path/to/codex.exe'` or set
`NEPTUNE_CODEX_PATH`. Use `start --show-command` to inspect discovery without starting
a model session.

`setup` builds disposable search indexes without model calls or sample personal data.
`start` opens native interactive Codex with Neptune's skill and permission profile.
It inherits your model choice and authentication. Writes are limited to runtime
working space, Laci, and generated data; Cole and code remain read-only. Shell network
access and web search are disabled. Codex handles its own model communication.
The launcher also disables the inherited `node_repl` MCP server for this session;
Neptune's Python tools do not require it. Your global Codex configuration is unchanged.

In the Codex desktop app, open Neptune and start a fresh task with “Operate as Neptune
using the neptune-assistant skill.” The app's chosen permissions control access; the
CLI launcher's enforced profile is not automatically applied to desktop tasks. Use
the launcher when you need the tested write boundary.

## Try it

- “Ask Cole: What does Cole mean by the dumb zone?”
- “Ask Laci: What do you know about my cycling?”
- “Save a note: JavaScript accepts 4_000 as the number 4000.”
- “Edit that note to explain why separators help readability.”
- “Promote that note into knowledge.”
- “Make a flashcard about this in my JavaScript deck.”
- “Quiz me on my due JavaScript cards.”

Author, Date, and Context are optional. Saves require your command or approval;
ambiguous edits require identifying the intended record. Edits preserve record paths,
and stale revisions are rejected. Notes are searchable Laci records, archive hides
them without deletion, and promotion changes type in place. Flashcards have named
decks and a transparent daily review schedule, stored locally without mobile sync.

## Tools and verification

```powershell
python -m neptune --help
python -m neptune query 'Ask Cole: Why does chunking matter in RAG?'
python -m neptune search --kind note
python -m neptune due --deck JavaScript
python -m unittest discover -s tests -v
python scripts/verify_runtime_sandbox.py
```

Run the last command from the host, not inside another restricted Windows token.
It checks actual access without writing Cole or application-code bytes.

See [architecture](docs/ARCHITECTURE.md), [validation](docs/VALIDATION.md), the
[record workflow](.agents/skills/neptune-assistant/references/records.md), and the
[Laci schema](knowledge/laci-knowledge-base/SCHEMA.md). The
[token-efficiency report](docs/TOKEN-EFFICIENCY-TEST.md) records the user's five-question
usage comparison, startup figures, and limits of the available measurements.

Research-1 supplied Tiger and regression cases. Saturn supplied capability requirements.
Both reference projects remain unchanged. Mobile hosting and dedicated voice/replay
storage are outside the user-confirmed priority. Existing Codex voice and coding
features remain host capabilities, not separately implemented Neptune features.
