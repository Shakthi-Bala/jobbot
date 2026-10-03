# follow-up

1. List follow-ups due today or earlier (`python jobbot.py followups`).
2. For each contact follow-up, draft a 2-3 sentence nudge that adds no new claims
   (`python jobbot.py followups --draft`, written to `out/<job_id>/outreach/<name>.followup.md`).
3. Stop. You send. Mark the follow-up done in the dashboard.

Send at most one follow-up per person. After that, set the contact to `no_reply`.
