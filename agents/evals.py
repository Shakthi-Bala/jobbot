"""Evaluate prompt/skill changes on saved job descriptions (README: Development).

    data/evals/<case>/posting.txt   the job description
    data/evals/<case>/meta.yaml     company, title (location, req_id optional)
    data/evals/<case>/notes.md      what a good packet looks like (for the judge)

`run` builds packets for every case into out/evals/<label>/ using a separate DB.
`compare` judges two labels blind and reports wins plus check pass rates.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from . import core
from .schemas import BlindVerdict

EVALS = core.DATA / "evals"


def cases() -> list[Path]:
    return sorted(p for p in EVALS.iterdir() if (p / "posting.txt").exists()) \
        if EVALS.exists() else []


def run(label: str) -> dict:
    import sys
    sys.path.insert(0, str(core.ROOT))
    from checks import run_all
    from . import discover, tailor

    root = core.OUT / "evals" / label
    root.mkdir(parents=True, exist_ok=True)
    saved = core.DB_PATH, core.OUT
    core.DB_PATH, core.OUT = root / "eval.db", root
    summary = {}
    try:
        conn = core.connect()
        for case in cases():
            meta = core.load_yaml(case / "meta.yaml", default={})
            job_id = discover.add_manual(meta.get("company", case.name), meta.get("title", ""),
                                         (case / "posting.txt").read_text(),
                                         meta.get("location", ""), "", meta.get("req_id", ""))
            try:
                d = tailor.build(conn, job_id)
                results = run_all.run(d, offline=True)
                summary[case.name] = {"job_id": job_id, "failures": run_all.failures(results)}
            except core.JobbotError as e:
                summary[case.name] = {"job_id": job_id, "failures": [f"build failed: {e}"]}
            print(f"{case.name}: {len(summary[case.name]['failures'])} check failure(s)")
    finally:
        core.DB_PATH, core.OUT = saved
    (root / "summary.json").write_text(core.dumps(summary))
    return summary


def _packet_text(d: Path) -> str:
    parts = []
    if (d / "resume.json").exists():
        parts.append("RESUME\n" + (d / "resume.json").read_text())
    for name in ("cover_letter.md", "answers.md"):
        if (d / name).exists():
            parts.append(name.upper() + "\n" + (d / name).read_text())
    return "\n\n".join(parts)


def compare(label_a: str, label_b: str, seed: int = 0) -> str:
    rng = random.Random(seed)
    root = core.OUT / "evals"
    sa = json.loads((root / label_a / "summary.json").read_text())
    sb = json.loads((root / label_b / "summary.json").read_text())
    wins = {label_a: 0, label_b: 0, "tie": 0}
    rows = []
    for case in cases():
        if case.name not in sa or case.name not in sb:
            continue
        da = root / label_a / sa[case.name]["job_id"]
        db = root / label_b / sb[case.name]["job_id"]
        pair = [(label_a, da), (label_b, db)]
        rng.shuffle(pair)  # strip labels: the judge sees only A and B
        notes = (case / "notes.md").read_text() if (case / "notes.md").exists() else "n/a"
        verdict = core.llm_json(
            "review_lead",
            "You compare two application packets for the same job, blind. Prefer the one that is "
            "more truthful, more specific to the job, and closer to the notes on what good looks "
            "like. Overclaiming loses outright.",
            f"## What good looks like\n{notes}\n\n"
            + core.untrusted("posting", (case / "posting.txt").read_text())
            + f"\n\n## Packet A\n{_packet_text(pair[0][1])}\n\n## Packet B\n{_packet_text(pair[1][1])}",
            BlindVerdict, max_tokens=4000)
        winner = "tie" if verdict.winner == "tie" else pair[0 if verdict.winner == "A" else 1][0]
        wins[winner] += 1
        rows.append(f"| {case.name} | {winner} | {verdict.reason[:140]} |")

    def pass_rate(s):
        return sum(1 for v in s.values() if not v["failures"]) / max(1, len(s))

    report = "\n".join([
        f"# Eval: {label_a} vs {label_b}", "",
        f"Wins: {label_a} {wins[label_a]}, {label_b} {wins[label_b]}, ties {wins['tie']}", "",
        f"All-checks-pass rate: {label_a} {pass_rate(sa):.0%}, {label_b} {pass_rate(sb):.0%}", "",
        "Keep the change only if it wins and all checks still pass.", "",
        "| Case | Winner | Judge's reason |", "|---|---|---|", *rows]) + "\n"
    (root / f"compare_{label_a}_vs_{label_b}.md").write_text(report)
    return report
