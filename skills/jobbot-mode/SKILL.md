---
name: jobbot-mode
description: Router. Match a job-search task to exactly one playbook and run its steps in order.
---

# jobbot mode

Read `principles/` first. Then pick the playbook that matches the task, copy its
steps into a todo list **verbatim**, and do them in order. Don't skip, merge or
reorder steps. If a step says stop, stop and log why.

| Task | Playbook | Command |
|---|---|---|
| Find and score new roles | `playbooks/daily-discovery.md` | `python run_daily.py --no-packets` |
| Build an application packet for one job | `playbooks/new-job-packet.md` | `python jobbot.py packet JOB_ID` |
| Find people and draft messages for one job | `playbooks/outreach.md` | `python jobbot.py outreach JOB_ID` |
| Nudge people who haven't replied | `playbooks/follow-up.md` | `python jobbot.py followups --draft` |
| Record a rejection, interview or offer | `playbooks/post-outcome.md` | `python jobbot.py outcome JOB_ID ...` |
| Weekly funnel and tuning | `playbooks/weekly-review.md` | `python jobbot.py weekly` |

If no playbook fits, say so and ask. Do not improvise a new pipeline.
