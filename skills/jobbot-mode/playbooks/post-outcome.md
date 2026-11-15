# post-outcome

1. Record the outcome: `python jobbot.py outcome JOB_ID {responded|interview|rejected|offer} --note "..."`.
2. Note what worked or didn't: which resume version (see `actions` and the document hash),
   which source, fit score, whether there was a referral.
3. Look for a repeat: has the same failure happened at least twice
   (`data/decisions.tsv`, `data/weekly_review.md`)?
4. If yes, propose one change: a new or stricter check in `checks/` (preferred,
   see `encode-lessons-as-checks`) or a skill edit. Skill edits must pass the eval
   loop in the README's Development section before they're kept.
5. Stop. You approve the change.
