#!/usr/bin/env python3
"""Daily orchestrator: daily-discovery, then new-job-packet for the top N new shortlisted jobs.

    python run_daily.py [--top 3] [--no-web] [--no-alerts] [--no-packets]

Cron (7:40am weekdays):
    40 7 * * 1-5 cd ~/jobbot && .venv/bin/python run_daily.py >> data/run.log 2>&1
"""
from __future__ import annotations

import argparse

from agents import core, discover, fit, packet, tracker


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=3, help="packets to build per run")
    p.add_argument("--no-web", action="store_true")
    p.add_argument("--no-alerts", action="store_true")
    p.add_argument("--no-packets", action="store_true")
    a = p.parse_args(argv)

    print(f"=== jobbot daily run {core.now()} ===")
    new_ids = discover.run(web=not a.no_web, alerts=not a.no_alerts)
    print(f"discovered {len(new_ids)} new job(s)")
    scored = fit.run()
    print(f"scored {len(scored)} job(s)")

    packets = []
    if not a.no_packets and a.top > 0:
        conn = core.connect()
        top = conn.execute(
            "SELECT j.id FROM jobs j JOIN fit f ON f.job_id=j.id "
            "WHERE j.status='shortlisted' AND j.active=1 "
            "ORDER BY (j.deadline IS NULL), j.deadline, f.score DESC LIMIT ?", (a.top,)).fetchall()
        for row in top:
            try:
                r = packet.build(row["id"])
            except Exception as e:  # one bad packet must not stop the run
                core.log_decision("run_daily", row["id"], "packet_error", repr(e))
                r = {"job_id": row["id"], "status": "error", "reason": repr(e)}
            print(f"packet {r['job_id']}: {r['status']}")
            packets.append(r)

    print(tracker.daily_log(new_ids, packets))


if __name__ == "__main__":
    main()
