## encode-lessons-as-checks

**Rule:** When a mistake recurs, add a check, not more prompt text.

Prompts drift; scripts don't. A recurring failure becomes a new file in `checks/` that exits 1 on the bad pattern.

_Enforced by:_ The post-outcome playbook proposes check edits.
