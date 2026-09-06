# Neptune

Neptune is Codex operating with this project's resources. Codex supplies reasoning,
sessions, tools, and coding. Do not introduce a second agent loop or a Pi dependency.

For personal-assistant requests, load `.agents/skills/neptune-assistant/SKILL.md`.
For development of Neptune, read README and the relevant docs, inspect code and Git
state, preserve user changes, and run the deterministic tests. Do not mix evaluation
answers or sibling-project history into a runtime task.

Cole (`knowledge/cole-medin-knowledge-base/`) is strictly read-only, including during
development. Laci persistence requires explicit user intent. Use the mutation tool;
do not bypass revision checks by directly editing runtime records.

Keep implementation plans and TODO tracking in the task, never repository files.
Documentation describes implemented behavior, usage, and verified limitations.
Do not publish, push, or commit private Laci records as a side effect of runtime use.
