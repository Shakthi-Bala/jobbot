#!/usr/bin/env python3
"""jobbot command line. Every command stops before anything irreversible.

    python jobbot.py init                      create the tracker DB, copy example data
    python jobbot.py discover [--no-web] [--no-alerts]
    python jobbot.py fit [JOB_ID ...]
    python jobbot.py add-jd FILE --company C --title T [--location L --url U --req-id R]
    python jobbot.py packet JOB_ID [--skip-review] [--offline] [--force]
    python jobbot.py approve JOB_ID            keep this packet's bullet wording for later jobs
    python jobbot.py checks JOB_ID [--offline] [--outreach]
    python jobbot.py outreach JOB_ID
    python jobbot.py mark-applied JOB_ID       you submitted it; records the resume hash
    python jobbot.py mark-sent CONTACT_ID      you sent the message; schedules a follow-up
    python jobbot.py outcome JOB_ID {responded,interview,rejected,offer,closed} [--note N]
    python jobbot.py followups [--draft]
    python jobbot.py jobs [--status S]
    python jobbot.py weekly
    python jobbot.py eval run LABEL | eval compare LABEL_A LABEL_B
    python jobbot.py gaps [JOB_ID ...] [--top N] [--summary]   what you're missing, highest pay first
    python jobbot.py ingest URL [URL ...]       add postings by ATS URL (manual-mode web search)
    python jobbot.py tasks [--check]           manual mode: pending assistant tasks
    python jobbot.py master [--draft] [--family F]   master resume; F = perception|rl|robotics_swe|ml
    python jobbot.py sheet                     refresh data/applications.xlsx (keeps your Applied?/Notes)
    python jobbot.py privacy [--install-hook]  refuse to push if tracked files contain your personal details

Manual mode (models.yaml `mode: manual`) uses no API key: each AI step is written to
out/tasks/<key>.task.md, your coding assistant writes <key>.answer.json, and you
re-run the same command to continue.
"""
from __future__ import annotations

import argparse
import shlex
import shutil
import sys
from pathlib import Path

from agents import core


def cmd_init(_):
    core.connect().close()
    models = core.ROOT / 'models.yaml'
    if not models.exists():
        shutil.copy(core.ROOT / 'models.example.yaml', models)
    for name in ("profile", "answers_bank"):
        src, dst = core.DATA / f"{name}.example.yaml", core.DATA / f"{name}.yaml"
        if not dst.exists():
            shutil.copy(src, dst)
            print(f"created {dst.relative_to(core.ROOT)} from the example; fill it in")
    core.OUT.mkdir(exist_ok=True)
    print(f"tracker ready at {core.DB_PATH.relative_to(core.ROOT)}")


def cmd_demo(_):
    from agents import demo
    demo.run()


def cmd_discover(a):
    from agents import discover
    ids = discover.run(web=not a.no_web, alerts=not a.no_alerts)
    print(f"{len(ids)} new job(s), highest pay first")
    _print_jobs(ids)
    _pending_note()


def cmd_gmail_auth(_):
    from agents import discover
    if discover.gmail_credentials(interactive=True) is None:
        raise core.JobbotError('Add your read-only OAuth client to data/credentials.json first')
    print('Gmail authorization saved; discovery can now read existing job alerts')


def cmd_fit(a):
    from agents import fit
    for r in fit.run(a.job_ids or None):
        extra = f" blocked by: {'; '.join(r['blockers'])}" if r["blockers"] else ""
        print(f"{r['job_id']}  {r['pay']:<15} {r['score']:>3}  {r['decision']}{extra}")
    _pending_note()


def cmd_add_jd(a):
    from agents import discover, fit
    text = Path(a.file).read_text() if a.file != "-" else sys.stdin.read()
    job_id = discover.add_manual(a.company, a.title, text, a.location, a.url, a.req_id)
    conn = core.connect()
    r = fit.score_job(conn, job_id)
    print(f"added {job_id}: fit {r['score']} -> {r['decision']}")
    print(f"next: python jobbot.py packet {job_id}"
          + ("" if r["decision"] == "shortlist" else " --force   (fit said "
             f"{r['decision']}; --force builds it anyway unless it is blocked)"))


def cmd_packet(a):
    from agents import packet
    r = packet.build(a.job_id, skip_review=a.skip_review, offline=a.offline,
                     skip_panel=a.no_panel, force=a.force)
    print(f"{r['job_id']}: {r['status']}" + (f" ({r['reason']})" if r.get("reason") else ""))
    if r.get("dir"):
        print(f"review it in {r['dir']}/ (wording.md and review.md first).")
        print(f"happy with the wording?  python jobbot.py approve {r['job_id']}   (reused for later jobs)")
        print(f"submitted it yourself?   python jobbot.py mark-applied {r['job_id']}")


def cmd_checks(a):
    sys.path.insert(0, str(core.ROOT))
    from checks import run_all
    results = run_all.run(core.job_dir(a.job_id), outreach=a.outreach, offline=a.offline)
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


def cmd_approve(a):
    from agents import bank
    r = bank.promote(a.job_id)
    print(f"{a.job_id}: {r['added']} bullet(s) added to {r['path'].relative_to(core.ROOT)}, "
          f"{r['already_present']} already there. New drafts start from this wording.")


def cmd_mark_applied(a):
    from agents import bank, tracker
    tracker.mark_applied(a.job_id)
    if (core.job_dir(a.job_id) / "resume.tagged.md").exists():
        bank.promote(a.job_id)  # what you sent is wording you approved
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
    where = "WHERE j.status=?" if a.status else ""
    rows = conn.execute(
        "SELECT j.id FROM jobs j LEFT JOIN fit f ON f.job_id=j.id "
        f"{where} ORDER BY {core.PAY_ORDER_SQL}, f.score DESC LIMIT 200",
        (a.status,) if a.status else ()).fetchall()
    _print_jobs([r["id"] for r in rows])


def _print_jobs(ids):
    conn = core.connect()
    for jid in ids:
        r = conn.execute("SELECT j.*, f.score FROM jobs j LEFT JOIN fit f ON f.job_id=j.id "
                         "WHERE j.id=?", (jid,)).fetchone()
        if r['comp_max'] is not None:
            pay = (f"${r['comp_min'] // 1000}-{r['comp_max'] // 1000}K"
                   if r['comp_min'] is not None else f"up to ${r['comp_max'] // 1000}K")
        else:
            pay = "pay n/a"
        print(f"{r['id']}  {pay:<13} {r['status']:<16} {str(r['score'] or ''):>3}  "
              f"{r['title']}, {r['company']}")


def _pending_note():
    n = len(core.pending_tasks())
    if n:
        print(f"\n{n} AI step(s) waiting for your coding assistant in out/tasks/ "
              "(answer them with your coding assistant, then re-run this command)")


def cmd_gaps(a):
    from agents import gaps
    if a.summary:
        print(gaps.summary())
        return
    r = gaps.run(a.job_ids or None, top=a.top)
    print(f"analyzed {len(r['analyzed'])} job(s)")
    for jid in r["analyzed"]:
        print(f"  out/{core.job_dir(jid).name}/gaps.md")
    if r["analyzed"]:
        print("summary: out/gaps/summary.md")
    _pending_note()


def cmd_ingest(a):
    from agents import discover
    profile = core.load_profile()
    ids = discover.ingest_urls(core.connect(), a.urls, profile.get("targets", {}), "web",
                               core.min_salary(profile))
    print(f"{len(ids)} new job(s)")
    _print_jobs(discover.sort_by_pay(core.connect(), ids))
    _pending_note()


def cmd_master(a):
    from agents import master
    if a.draft:
        print(f"wrote {master.draft().relative_to(core.ROOT)}")
    families = list(master.FAMILIES) if a.family == "all" else [a.family]
    for fam in families:
        r = master.render(None if fam == "full" else fam)
        bad = [f"{k}: {p}" for k, v in r["results"].items() for p in v]
        print(f"{r['dir'].name}/resume.pdf  " + ("all checks pass" if not bad else f"{len(bad)} problem(s)"))
        for b in bad:
            print("   -", b)


def cmd_sheet(_):
    from agents import sheet
    r = sheet.build()
    print(f"{r['rows']} job(s) -> {r['path'].relative_to(core.ROOT)}")
    for jid in r["recorded_applied"]:
        print(f"  recorded as applied (from the sheet): {jid}")


def cmd_privacy(a):
    from agents import privacy
    if a.install_hook:
        print(f"installed {privacy.install_hook()}: every `git push` now runs the scan")
    problems = privacy.scan_push(sys.stdin.read()) if a.push else privacy.run()
    for p in problems:
        print("  -", p)
    print("no personal details in tracked files" if not problems
          else f"{len(problems)} line(s) to clean before pushing")
    sys.exit(1 if problems else 0)


def cmd_tasks(a):
    from agents import schemas
    d = core.tasks_dir()
    if a.check:
        bad = 0
        for ans in sorted(d.glob("*.answer.json")) if d.exists() else []:
            task = d / ans.name.replace(".answer.json", ".task.md")
            name = task.read_text().split("-> ", 1)[1].split("\n", 1)[0].strip() \
                if task.exists() else None
            try:
                getattr(schemas, name).model_validate_json(ans.read_text())
            except Exception as e:
                bad += 1
                print(f"INVALID {ans.name}: {str(e)[:300]}")
        print("all answers valid" if not bad else f"{bad} invalid answer(s)")
        sys.exit(1 if bad else 0)
    pending = core.pending_tasks()
    if not pending:
        print("no pending tasks")
    for t in pending:
        print(f"{t.relative_to(core.ROOT)}  {t.read_text().splitlines()[0][2:]}")


def cmd_weekly(_):
    from agents import tracker
    print(tracker.weekly_review())


def cmd_eval(a):
    from agents import evals
    expected = 1 if a.action == 'run' else 2
    if len(a.labels) != expected:
        raise core.JobbotError(f'eval {a.action} expects {expected} label(s)')
    if a.action == "run":
        evals.run(a.labels[0])
    else:
        print(evals.compare(a.labels[0], a.labels[1]))


def main(argv=None):
    p = argparse.ArgumentParser(prog="jobbot", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser('demo', help='run an isolated offline example with recorded fixture answers').set_defaults(fn=cmd_demo)
    sub.add_parser('gmail-auth', help='authorize Gmail interactively before scheduled discovery').set_defaults(fn=cmd_gmail_auth)
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
    s.add_argument("--no-panel", action="store_true", help="skip the 7-reader review panel")
    s.add_argument("--force", action="store_true",
                   help="build even if the fit agent said skip (never overrides a blocked posting)")
    s = sub.add_parser("approve"); s.set_defaults(fn=cmd_approve); s.add_argument("job_id")
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
    s = sub.add_parser("gaps"); s.set_defaults(fn=cmd_gaps); s.add_argument("job_ids", nargs="*")
    s.add_argument("--top", type=int, default=10); s.add_argument("--summary", action="store_true")
    s = sub.add_parser("ingest"); s.set_defaults(fn=cmd_ingest); s.add_argument("urls", nargs="+")
    sub.add_parser("sheet").set_defaults(fn=cmd_sheet)
    s = sub.add_parser("master"); s.set_defaults(fn=cmd_master)
    s.add_argument("--draft", action="store_true", help="(re)write data/master_resume.yaml")
    s.add_argument("--family", default="full",
                   choices=["full", "all", "perception", "rl", "robotics_swe", "ml"])
    s = sub.add_parser("privacy"); s.set_defaults(fn=cmd_privacy)
    s.add_argument("--install-hook", action="store_true", help="scan before every git push")
    s.add_argument('--push', action='store_true', help='scan outgoing commits from pre-push stdin')
    s = sub.add_parser("tasks"); s.set_defaults(fn=cmd_tasks)
    s.add_argument("--check", action="store_true")

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except core.ManualTaskPending as e:
        command = shlex.join(['python', 'jobbot.py', *(sys.argv[1:] if argv is None else argv)])
        print(f"{e}\nAnswer the pending tasks in out/tasks with your coding assistant, "
              f"then re-run: {command}")
        _pending_note()
        sys.exit(3)
    except core.JobbotError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
