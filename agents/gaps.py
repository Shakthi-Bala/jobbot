"""Gap coach: for each job, highest pay first, what's missing and how to close it.

Per job it writes out/<Company>_<Role>/gaps.md (+ gaps.json). The summary aggregates every
report into out/gaps/summary.md: jobs by pay band, the most common missing
requirements, and the projects that would close gaps across the most jobs.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz

from . import core
from .schemas import GapReport

VERDICT_LABEL = {"apply_now": "Apply now", "apply_after_quick_fixes": "Apply after quick fixes",
                 "stretch": "Stretch", "not_a_fit": "Not a fit"}


def candidates(conn, top: int | None, min_pay: int) -> list[str]:
    """Active, unblocked jobs at or above the pay floor, highest pay first."""
    rows = conn.execute(
        "SELECT j.id FROM jobs j WHERE j.active=1 AND j.status NOT IN "
        "('blocked','closed','applied','rejected','offer') "
        "AND (j.comp_max IS NULL OR j.comp_max >= ?) "
        f"ORDER BY {core.PAY_ORDER_SQL}", (min_pay,)).fetchall()
    ids = [r["id"] for r in rows]
    return ids[:top] if top else ids


def analyze(conn, job_id: str, profile: dict | None = None) -> GapReport:
    profile = profile or core.load_profile()
    job = core.get_job(conn, job_id)
    fit = conn.execute("SELECT score, gaps_json FROM fit WHERE job_id=?", (job_id,)).fetchone()
    user = (
        "## Candidate profile (verified facts only)\n" + core.dumps({
            k: profile.get(k) for k in ("education", "experience", "projects", "skills",
                                        "facts", "authorization")})
        + '\n\n' + core.untrusted('job_metadata', core.dumps({
            k: job[k] for k in ('company', 'title', 'location', 'comp_text', 'comp_max')}))
        + '\n' + core.untrusted('parsed_posting', job['parsed_json'] or '{}')
        + (core.untrusted('fit_analysis', f"Fit score: {fit['score']}; fit gaps: {fit['gaps_json']}") if fit else '')
        + "\n" + core.untrusted("posting", job["raw_text"])
    )
    report = core.llm_json("writing", core.system_prompt("gap-coach"), user, GapReport)
    return enforce(report, profile, job_id)


def enforce(report: GapReport, profile: dict, job_id: str) -> GapReport:
    """Rules as code: 'met' needs real fact IDs; unknown IDs are removed."""
    known = core.profile_ids(profile)
    for r in report.requirements:
        r.fact_ids = [f for f in r.fact_ids if f in known]
        if r.status in ("met", "partial") and not r.fact_ids:
            core.log_decision("gaps", job_id, "downgraded",
                              f"{r.requirement!r} marked {r.status} without valid evidence")
            r.status = "missing"
    for i in report.resume_improvements:
        i.fact_ids = [f for f in i.fact_ids if f in known]
    for p in report.projects:
        p.builds_on = [f for f in p.builds_on if f in known]
    report.readiness = max(0, min(100, report.readiness))
    return report


def write(job, report: GapReport) -> Path:
    d = core.job_dir(job["id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "gaps.json").write_text(core.dumps(
        report.model_dump() | {"job_id": job["id"], "company": job["company"],
                               "title": job["title"], "comp_max": job["comp_max"],
                               "comp_text": job["comp_text"], "url": job["url"]}))
    icon = {"met": "✅", "partial": "🟡", "missing": "❌"}
    lines = [
        f"# Gaps: {job['title']} at {job['company']}", "",
        f"**Pay:** {job['comp_text'] or core.pay_band(job['comp_max'])} · "
        f"**Verdict:** {VERDICT_LABEL[report.verdict]} · **Readiness:** {report.readiness}/100"
        + (f" · [posting]({job['url']})" if job["url"] else ""), "",
        report.summary, "", "## Requirements", "",
        "| | Requirement | Type | Evidence | Note |", "|---|---|---|---|---|",
    ]
    order = {"missing": 0, "partial": 1, "met": 2}
    for r in sorted(report.requirements, key=lambda r: (order[r.status], r.kind)):
        lines.append(f"| {icon[r.status]} | {r.requirement} | {r.kind.replace('_', ' ')} | "
                     f"{', '.join(r.fact_ids) or '-'} | {r.note} |")
    lines += ["", "## Fix on your resume now (existing work)", ""]
    lines += [f"- {i.change} ({', '.join(i.fact_ids) or 'no facts'}). _{i.why}_"
              for i in report.resume_improvements] or ["- Nothing to change."]
    lines += ["", "## Gaps", ""]
    lines += [f"- **[{g.importance}] {g.gap}**: {g.how_to_close} (~{g.weeks} wk)"
              for g in report.gaps] or ["- None."]
    lines += ["", "## Projects that would close these gaps", ""]
    for p in report.projects:
        lines += [f"### {p.title} (~{p.weeks} weeks)", "",
                  p.description, "",
                  f"- **Closes:** {'; '.join(p.closes)}",
                  f"- **Builds on:** {', '.join(p.builds_on) or 'new work'}",
                  f"- **Stack:** {', '.join(p.stack)}",
                  f"- **Deliverables:** {'; '.join(p.deliverables)}",
                  f"- **Resume metric once done:** {p.success_metric}", ""]
    lines += ["## How to get this job", ""] + [f"- {t}" for t in report.how_to_get_it]
    lines += ["", "## Likely interview topics", ""] + [f"- {t}" for t in report.interview_topics]
    path = d / "gaps.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def run(job_ids: list[str] | None = None, top: int | None = 10) -> dict:
    conn = core.connect()
    profile = core.load_profile()
    ids = job_ids or candidates(conn, top, core.min_salary(profile))
    done, pending = [], 0
    for jid in ids:
        try:
            report = analyze(conn, jid, profile)
        except core.ManualTaskPending:
            pending += 1
            continue
        job = core.get_job(conn, jid)
        write(job, report)
        core.log_decision("gaps", jid, report.verdict,
                          f"readiness {report.readiness}; {len(report.gaps)} gaps; "
                          f"pay {core.pay_band(job['comp_max'])}")
        done.append(jid)
    if done:
        summary()
    return {"analyzed": done, "pending": pending}


# --------------------------------------------------------------- summary

def _load_reports() -> list[dict]:
    reports = []
    for p in core.OUT.glob("*/gaps.json"):
        reports.append(json.loads(p.read_text()))
    return sorted(reports, key=lambda r: (r["comp_max"] is None, -(r["comp_max"] or 0)))


def _weight(comp_max: int | None) -> float:
    """Higher-paying jobs count more; unlisted pay counts like the floor."""
    return max(1.0, (comp_max or 80_000) / 100_000)


def _cluster(items: list[tuple[str, dict]], threshold: int = 80) -> list[list[tuple[str, dict]]]:
    clusters: list[list[tuple[str, dict]]] = []
    for text, meta in items:
        for c in clusters:
            if fuzz.token_set_ratio(core.normalize(text), core.normalize(c[0][0])) >= threshold:
                c.append((text, meta))
                break
        else:
            clusters.append([(text, meta)])
    return clusters


def summary() -> str:
    reports = _load_reports()
    out = core.OUT / "gaps"
    out.mkdir(parents=True, exist_ok=True)
    lines = [f"# Gap summary ({core.today()})", "",
             f"{len(reports)} job(s) analyzed, highest pay first.", ""]

    by_band: dict[str, list[dict]] = defaultdict(list)
    for r in reports:
        by_band[core.pay_band(r["comp_max"])].append(r)
    bands = [label for _, label in core.PAY_BANDS] + ["pay not listed"]
    lines += ["## Jobs by pay band", ""]
    for band in bands:
        if not by_band.get(band):
            continue
        lines += [f"### {band}", "", "| Job | Pay | Verdict | Readiness | Report |",
                  "|---|---|---|---|---|"]
        for r in by_band[band]:
            lines.append(f"| {r['title']}, {r['company']} | {r['comp_text'] or '-'} | "
                         f"{VERDICT_LABEL[r['verdict']]} | {r['readiness']} | "
                         f"out/{core.job_dir(r['job_id']).name}/gaps.md |")
        lines.append("")

    missing = [(q["requirement"], r) for r in reports for q in r["requirements"]
               if q["status"] != "met" and q["kind"] == "must_have"]
    clusters = sorted(_cluster(missing), key=lambda c: -sum(_weight(m["comp_max"]) for _, m in c))
    lines += ["## Most common unmet must-haves: missing or partial (weighted toward higher pay)", "",
              "| Requirement | Jobs | Highest pay |", "|---|---|---|"]
    for c in clusters[:15]:
        jobs = {m["job_id"]: m for _, m in c}
        top = max((m["comp_max"] or 0) for m in jobs.values())
        lines.append(f"| {c[0][0]} | {len(jobs)} | {core.pay_band(top or None)} |")

    projects = [(p["title"], {"p": p, **r}) for r in reports for p in r["projects"]]
    pclusters = sorted(_cluster(projects, threshold=70),
                       key=lambda c: -sum(_weight(m["comp_max"]) for _, m in c))
    lines += ["", "## Projects ranked by how many jobs they help", ""]
    for i, c in enumerate(pclusters[:8], 1):
        p = c[0][1]["p"]
        jobs = sorted({f"{m['title']} ({m['company']})" for _, m in c})
        lines += [f"### {i}. {p['title']} (~{p['weeks']} weeks, helps {len(jobs)} job(s))", "",
                  p["description"], "",
                  f"- **Closes:** {'; '.join(sorted({x for _, m in c for x in m['p']['closes']}))}",
                  f"- **Resume metric once done:** {p['success_metric']}",
                  f"- **Jobs:** {'; '.join(jobs)}", ""]
    text = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(text)
    return text
