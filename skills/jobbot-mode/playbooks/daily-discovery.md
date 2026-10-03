# daily-discovery

1. Poll all boards in `companies.yaml`, parse alert emails, and run targeted web searches.
2. Parse each new posting into the schema, and drop exclusions.
3. Deduplicate and verify each posting is active.
4. Run the fit agent on new jobs.
5. Write `data/daily_log.md`: new shortlist, expiring deadlines, and follow-ups due.

Code: `agents/discover.py:run` (1-3), `agents/fit.py:run` (4), `agents/tracker.py:daily_log` (5).
