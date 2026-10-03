## no-unsourced-claims

**Rule:** Every factual line cites a fact ID.

Every line that states something about the candidate carries one or more IDs from `profile.yaml` (`[F012]`, `[X001]`, `[E001]`, `[P003]`) or an answers-bank key (`[A:why_field]`). A line that can't be cited is deleted, not softened. "Familiar with" is still a claim.

_Enforced by:_ `checks/fact_ids.py`; `agents/tailor.py:enforce` drops uncited bullets before rendering.
