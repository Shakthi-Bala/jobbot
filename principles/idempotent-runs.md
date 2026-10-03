## idempotent-runs

**Rule:** Re-running any step converges to the same state with no duplicates.

Jobs are keyed by hash(company, title, location); contacts by (company, name); document versions by hash. Running discovery twice adds nothing new.

_Enforced by:_ `agents/discover.py:upsert_jobs`, `core.record_document`.
