"""Review agent: run checks, send the same packet + rubric to several models, then
have a lead model bucket the findings. Never edits documents."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import core
from .schemas import LeadJudgment, ReviewerReport

SKILL = "interrogate-packet"


def _cited_facts(texts: list[str], profile: dict) -> dict:
    ids = set()
    for t in texts:
        ids |= set(core.FACT_TAG_RE.findall(t))
    lookup = {f["id"]: f for f in profile.get("facts", [])}
    for key in ("education", "experience", "projects"):
        for e in profile.get(key, []) or []:
            lookup[e["id"]] = {k: v for k, v in e.items() if k != "facts"}
    return {i: lookup[i] for i in sorted(ids) if i in lookup}


def intent(job, parsed: dict) -> str:
    top = ", ".join(parsed.get("must_have", [])[:3]) or "the stated requirements"
    return (f"Application for {job['title']} at {job['company']}, req {job['req_id'] or 'n/a'}; "
            f"emphasize {top}.")


def packet_bundle(d: Path, outreach: bool = False) -> dict[str, str]:
    if outreach:
        files = sorted(d.glob("outreach/*.tagged.md"))
    else:
        files = [d / n for n in ("resume.tagged.md", "cover_letter.tagged.md",
                                 "answers.tagged.md") if (d / n).exists()]
    return {str(p.relative_to(d)): p.read_text() for p in files}


def review(conn, job_id: str, d: Path, check_results: dict[str, list[str]],
           outreach: bool = False) -> LeadJudgment:
    profile = core.load_profile()
    job = core.get_job(conn, job_id)
    parsed = json.loads(job["parsed_json"] or "{}")
    bundle = packet_bundle(d, outreach)
    facts = _cited_facts(list(bundle.values()), profile)
    extra = ""
    if outreach:
        extra = "\n\n## Contacts (with sources)\n" + core.dumps(
            [json.loads(p.read_text()) for p in sorted(d.glob("outreach/*.json"))
             if p.name != "checks.json"])

    rubric = core.read_skill_ref(SKILL, "rubric.md")
    reviewer_system = (core.system_prompt(SKILL) + "\n\n" + rubric + "\n\n"
                       + core.read_skill_ref(SKILL, "reviewer-prompt.md"))
    user = (
        f"## Intent\n{intent(job, parsed)}\n\n"
        "## Packet (tagged: [Fxxx] etc. are citations into the facts below)\n"
        + "\n\n".join(f"### {name}\n```\n{text}\n```" for name, text in bundle.items())
        + "\n\n## Cited facts from profile.yaml\n" + core.dumps(facts)
        + "\n\n## Candidate authorization\n" + core.dumps(profile.get("authorization", {}))
        + extra + "\n\n" + core.untrusted("posting", job["raw_text"])
    )

    reviewers = []
    for cfg in core.reviewer_models():
        if not cfg["model"].startswith("claude-"):
            core.warn(f"reviewer {cfg['model']} skipped: only Anthropic models are wired up")
            continue
        reviewers.append(cfg)
    if not reviewers:
        raise core.JobbotError("No usable reviewers in models.yaml")

    def run_one(i_cfg):
        i, cfg = i_cfg
        label = f"R{i + 1}:{cfg['model']}"
        try:
            return label, core.llm_json(cfg, reviewer_system, user, ReviewerReport)
        except Exception as e:  # one failed reviewer should not sink the review
            core.warn(f"{label} failed: {e}")
            return label, None

    with ThreadPoolExecutor(max_workers=len(reviewers)) as pool:
        reports = [r for r in pool.map(run_one, enumerate(reviewers)) if r[1] is not None]
    if not reports:
        raise core.JobbotError("Every reviewer failed")

    findings_text = "\n\n".join(
        f"### {label}\n" + core.dumps([f.model_dump() for f in rep.findings])
        for label, rep in reports)
    failed_checks = {k: v for k, v in check_results.items() if v}
    lead_user = (
        user + "\n\n## Reviewer findings\n" + findings_text
        + "\n\n## Check failures (rules as code; these are facts, not opinions)\n"
        + (core.dumps(failed_checks) if failed_checks else "none")
    )
    lead_system = (core.system_prompt(SKILL) + "\n\n" + rubric + "\n\n"
                   + core.read_skill_ref(SKILL, "lead-judgment.md"))
    judgment = core.llm_json("review_lead", lead_system, lead_user, LeadJudgment)

    write_review(d, job, parsed, judgment, reports, check_results, outreach)
    return judgment


def write_review(d: Path, job, parsed: dict, judgment: LeadJudgment, reports,
                 check_results: dict, outreach: bool) -> Path:
    labels = [label for label, _ in reports]
    buckets = {"act_on": "Act on", "consider": "Consider", "noted": "Noted",
               "dismissed": "Dismissed"}
    lines = [f"# Review: {job['title']} at {job['company']}", "",
             f"**Intent:** {intent(job, parsed)}", "",
             f"**Reviewers:** {', '.join(labels)}", "", f"**Overall:** {judgment.overall}", "",
             "## Checks", ""]
    for name, probs in check_results.items():
        lines.append(f"- {'PASS' if not probs else 'FAIL'} `{name}`")
        lines += [f"  - {p}" for p in probs]
    for key, title in buckets.items():
        items = [f for f in judgment.findings if f.bucket == key]
        lines += ["", f"## {title} ({len(items)})", ""]
        for f in items:
            conf = "high confidence" if len(f.raised_by) >= 2 else "single reviewer"
            lines.append(f"- **{f.summary}** ({f.location}; {conf})")
            lines.append(f"  - Why: {f.reason}")
            if f.fix_instruction and key in ("act_on", "consider"):
                lines.append(f"  - Fix: {f.fix_instruction}")
    lines += ["", "## Agreement map", "",
              "| Finding | " + " | ".join(f"R{i + 1}" for i in range(len(labels))) + " |",
              "|---|" + "---|" * len(labels)]
    for f in judgment.findings:
        marks = ["x" if any(lbl.startswith(f"R{i + 1}") or lbl == labels[i]
                            for lbl in f.raised_by) else "" for i in range(len(labels))]
        lines.append(f"| {f.summary[:80]} | " + " | ".join(marks) + " |")
    path = d / ("outreach/review.md" if outreach else "review.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def act_on(judgment: LeadJudgment) -> list[str]:
    return [f"{f.summary} ({f.location}). Fix: {f.fix_instruction or f.reason}"
            for f in judgment.findings if f.bucket == "act_on"]
