## human-does-irreversible

**Rule:** Agents never submit, send, or accept anything.

No agent has a submit or send tool. The pipeline ends at `ready_for_review`. The candidate submits, sends, and then records it (`mark-applied`, `mark-sent`).

_Enforced by:_ By construction: no such tool exists anywhere in `agents/`.
