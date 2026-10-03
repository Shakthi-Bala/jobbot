#!/usr/bin/env python3
"""jobbot command line. Every command stops before anything irreversible.

    python jobbot.py init                      create the tracker DB, copy example data
    python jobbot.py discover [--no-web] [--no-alerts]
    python jobbot.py fit [JOB_ID ...]
    python jobbot.py add-jd FILE --company C --title T [--location L --url U --req-id R]
    python jobbot.py packet JOB_ID [--skip-review] [--offline]
    python jobbot.py checks JOB_ID [--offline] [--outreach]
    python jobbot.py outreach JOB_ID
    python jobbot.py mark-applied JOB_ID       you submitted it; records the resume hash
    python jobbot.py mark-sent CONTACT_ID      you sent the message; schedules a follow-up
    python jobbot.py outcome JOB_ID {responded,interview,rejected,offer,closed} [--note N]
    python jobbot.py followups [--draft]
    python jobbot.py jobs [--status S]
    python jobbot.py weekly
    python jobbot.py eval run LABEL | eval compare LABEL_A LABEL_B
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from agents import core


def cmd_init(_):
    core.connect().close()
    for name in ("profile", "answers_bank"):
        src, dst = core.DATA / f"{name}.example.yaml", core.DATA / f"{name}.yaml"
        if not dst.exists():
            shutil.copy(src, dst)
            print(f"created {dst.relative_to(core.ROOT)} from the example; fill it in")
    core.OUT.mkdir(exist_ok=True)
    print(f"tracker ready at {core.DB_PATH.relative_to(core.ROOT)}")


def cmd_discover(a):
    from agents import discover
    ids = discover.run(web=not a.no_web, alerts=not a.no_alerts)
    print(f"{len(ids)} new job(s)")
    for i in ids:
        print(" ", i)


def cmd_fit(a):
    from agents import fit
    for r in fit.run(a.job_ids or None):
        extra = f" blocked by: {'; '.join(r['blockers'])}" if r["blockers"] else ""
        print(f"{r['job_id']}  {r['score']:>3}  {r['decision']}{extra}")


def cmd_add_jd(a):
    from agents import discover, fit
    text = Path(a.file).read_text() if a.file != "-" else sys.stdin.read()
    job_id = discover.add_manual(a.company, a.title, text, a.location, a.url, a.req_id)
    conn = core.connect()
    r = fit.score_job(conn, job_id)
    print(f"added {job_id}: fit {r['score']} -> {r['decision']}")
    print(f"next: python jobbot.py packet {job_id}")


def cmd_packet(a):
    from agents import packet
    r = packet.build(a.job_id, skip_review=a.skip_review, offline=a.offline)
    print(f"{r['job_id']}: {r['status']}" + (f" ({r['reason']})" if r.get("reason") else ""))
    if r.get("dir"):
        print(f"review it in {r['dir']}/ (review.md first), then submit it yourself and run:")
        print(f"  python jobbot.py mark-applied {r['job_id']}")


def cmd_checks(a):
    sys.path.insert(0, str(core.ROOT))
    from checks import run_all
    results = run_all.run(core.OUT / a.job_id, outreach=a.outreach, offline=a.offline)
    for name, probs in results.items():
        print(f"{'ok  ' if not probs else 'FAIL'} {name}")
        for p in probs:
            print(f"     - {p}")
    sys.exit(1 if run_all.failures(results) else 0)


def cmd_outreach(a):
    from agents import outreach
    r = outreach.run(a.job_id)
    print(f"drafted {r['drafted']} message(s)")
    for c in r.get("contacts", []):
        print(f"  contact {c['id']}: {c['name']} -> {c['file']}")
    if r.get("contacts"):
        print("Send them yourself, then: python jobbot.py mark-sent CONTACT_ID")


def cmd_mark_applied(a):
    from agents import tracker
    tracker.mark_applied(a.job_id)
    print(f"{a.job_id}: applied (follow-up scheduled in 10 days)")


def cmd_mark_sent(a):
    from agents import outreach
    outreach.mark_sent(a.contact_id)
    print(f"contact {a.contact_id}: sent (follow-up scheduled)")


def cmd_outcome(a):
    from agents import tracker
    tracker.record_outcome(a.job_id, a.outcome, a.note)
    print(f"{a.job_id}: {a.outcome}")
    print("If this outcome repeats a pattern, run the post-outcome playbook "
          "(skills/jobbot-mode/playbooks/post-outcome.md).")


def cmd_followups(a):
    from agents import tracker
    conn = core.connect()
    for f in tracker.due_followups(conn):
        who = f" with {f['contact_name']}" if f["contact_name"] else ""
        print(f"[{f['id']}] {f['due']} {f['company'] or ''}{who}: {f['note']}")
    if a.draft:
        for p in tracker.draft_nudges():
            print("drafted", p)


def cmd_jobs(a):
    conn = core.connect()
    sql = ("SELECT j.id, j.status, j.company, j.title, f.score FROM jobs j "
           "LEFT JOIN fit f ON f.job_id=j.id")
    rows = conn.execute(sql + " WHERE j.status=? ORDER BY f.score DESC", (a.status,)).fetchall() \
        if a.status else conn.execute(sql + " ORDER BY j.first_seen DESC LIMIT 100").fetchall()
    for r in rows:
        print(f"{r['id']}  {r['status']:<16} {str(r['score'] or ''):>3}  {r['title']}, {r['company']}")


def cmd_weekly(_):
    from agents import tracker
    print(tracker.weekly_review())


def cmd_eval(a):
    from agents import evals
    if a.action == "run":
        evals.run(a.labels[0])
    else:
        print(evals.compare(a.labels[0], a.labels[1]))


def main(argv=None):
    p = argparse.ArgumentParser(prog="jobbot", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    s = sub.add_parser("discover"); s.set_defaults(fn=cmd_discover)
    s.add_argument("--no-web", action="store_true"); s.add_argument("--no-alerts", action="store_true")
    s = sub.add_parser("fit"); s.set_defaults(fn=cmd_fit); s.add_argument("job_ids", nargs="*")
    s = sub.add_parser("add-jd"); s.set_defaults(fn=cmd_add_jd)
    s.add_argument("file", help="text file with the job description, or - for stdin")
    s.add_argument("--company", required=True); s.add_argument("--title", required=True)
    s.add_argument("--location", default=""); s.add_argument("--url", default="")
    s.add_argument("--req-id", default="")
    s = sub.add_parser("packet"); s.set_defaults(fn=cmd_packet); s.add_argument("job_id")
    s.add_argument("--skip-review", action="store_true"); s.add_argument("--offline", action="store_true")
    s = sub.add_parser("checks"); s.set_defaults(fn=cmd_checks); s.add_argument("job_id")
    s.add_argument("--offline", action="store_true"); s.add_argument("--outreach", action="store_true")
    s = sub.add_parser("outreach"); s.set_defaults(fn=cmd_outreach); s.add_argument("job_id")
    s = sub.add_parser("mark-applied"); s.set_defaults(fn=cmd_mark_applied); s.add_argument("job_id")
    s = sub.add_parser("mark-sent"); s.set_defaults(fn=cmd_mark_sent)
    s.add_argument("contact_id", type=int)
    s = sub.add_parser("outcome"); s.set_defaults(fn=cmd_outcome); s.add_argument("job_id")
    s.add_argument("outcome", choices=["responded", "interview", "rejected", "offer", "closed"])
    s.add_argument("--note", default="")
    s = sub.add_parser("followups"); s.set_defaults(fn=cmd_followups)
    s.add_argument("--draft", action="store_true")
    s = sub.add_parser("jobs"); s.set_defaults(fn=cmd_jobs); s.add_argument("--status")
    sub.add_parser("weekly").set_defaults(fn=cmd_weekly)
    s = sub.add_parser("eval"); s.set_defaults(fn=cmd_eval)
    s.add_argument("action", choices=["run", "compare"]); s.add_argument("labels", nargs="+")

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except core.JobbotError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
