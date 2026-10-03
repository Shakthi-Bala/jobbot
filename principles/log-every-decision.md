## log-every-decision

**Rule:** Append agent, decision, reason, and sources to `decisions.tsv`.

Every shortlist, skip, block, dropped claim, dropped contact and stopped packet is logged with its reason, so any outcome can be audited.

_Enforced by:_ `agents/core.py:log_decision`.
