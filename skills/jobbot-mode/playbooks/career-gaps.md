# career-gaps

1. Start at the highest pay band ($200K+) and work down band by band to the
   $80K minimum (`targets.min_base_salary_usd`). Unlisted pay comes last.
2. For each job, run the gap coach: requirements met/partial/missing, resume
   improvements from existing work, remaining gaps, 1-3 grad-level projects, how to
   get the job, interview topics.
3. Write `out/<job_id>/gaps.md` for each job.
4. Aggregate into `out/gaps/summary.md`: jobs by pay band, the most common missing
   requirements (weighted toward higher pay), and the projects that close gaps across
   the most jobs.
5. Stop. You choose which projects to do. A project goes into `profile.yaml` only
   after it is done and measured.

Code: `python jobbot.py gaps [--top N]`, then `python jobbot.py gaps --summary`.
