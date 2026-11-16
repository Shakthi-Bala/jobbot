#!/usr/bin/env python3
"""Daily orchestrator: daily-discovery, then new-job-packet for the top N shortlisted jobs,
highest pay first. In manual mode, run it during your coding-assistant session: AI steps
become tasks in out/tasks/, and re-running continues where it stopped.

    python run_daily.py [--top 3] [--no-web] [--no-alerts] [--no-packets]

Run it while you're at the computer. Nothing is ever submitted or sent.
"""
from __future__ import annotations

import argparse

from agents import core, discover, fit, packet, tracker


def run_stage(name, action):
    """Keep already stored work usable when an expected provider/source error occurs."""
    try:
        return action()
    except core.JobbotError as e:
        core.log_decision('run_daily', None, f'{name}_error', str(e))
        core.warn(f'{name} paused: {e}')
        return []


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=3, help="packets to build per run")
    p.add_argument("--no-web", action="store_true")
    p.add_argument("--no-alerts", action="store_true")
    p.add_argument("--no-packets", action="store_true")
    a = p.parse_args(argv)

    print(f"=== jobbot daily run {core.now()} ===")
    new_ids = run_stage('discovery', lambda: discover.run(web=not a.no_web, alerts=not a.no_alerts))
    print(f"discovered {len(new_ids)} new job(s)")
    scored = run_stage('fit', fit.run)
    print(f"scored {len(scored)} job(s)")

    packets = []
    if not a.no_packets and a.top > 0:
        conn = core.connect()
        top = conn.execute(
            "SELECT j.id FROM jobs j JOIN fit f ON f.job_id=j.id "
            "WHERE j.status IN ('shortlisted','packet_drafted','reviewed') AND j.active=1 "
            f"ORDER BY {core.PAY_ORDER_SQL}, f.score DESC LIMIT ?", (a.top,)).fetchall()
        for row in top:
            try:
                r = packet.build(row["id"])
            except core.ManualTaskPending as e:
                r = {"job_id": row["id"], "status": "waiting_for_claude", "reason": str(e)}
            except Exception as e:  # one bad packet must not stop the run
                core.log_decision("run_daily", row["id"], "packet_error", repr(e))
                r = {"job_id": row["id"], "status": "error", "reason": repr(e)}
            print(f"packet {r['job_id']}: {r['status']}")
            packets.append(r)

    print(tracker.daily_log(new_ids, packets))
    pending = core.pending_tasks()
    if pending:
        print(f"{len(pending)} AI step(s) waiting for your coding assistant in out/tasks/; "
              "answer them with your coding assistant, then re-run run_daily.py")


if __name__ == "__main__":
    main()
