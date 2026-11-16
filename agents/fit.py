"""Fit and eligibility agent: score 0-100, separate explicit restrictions from unknowns.

The model scores and finds evidence. Code decides what blocks: a restriction
counts only if its quote is verbatim in the posting, and whether it blocks you
is computed from profile.authorization, never from the model's opinion.
"""
from __future__ import annotations

import json
import re
import html

from . import core
from .schemas import FitResult, FitRestriction


def _yes(v) -> bool:
    return v is True or str(v).lower() in ("yes", "true")


def _no(v) -> bool:
    return v is False or str(v).lower() in ("no", "false")


def restriction_effect(r: FitRestriction, auth: dict) -> str:
    """'blocks' | 'question' | 'ok'. 'unsure' is never a block (unknown-is-not-no)."""
    t = r.type
    if t == "sponsorship":
        # A sponsorship *mention* can describe support being available. Only a
        # clear negative statement is a blocking restriction; ambiguous text asks.
        denied = re.search(
            r"(?:\bno\b|\bnot\b|cannot|can't|unable|without|unavailable|ineligible)"
            r".{0,80}sponsor|sponsor.{0,80}(?:\bnot\b|unavailable|ineligible)",
            r.quote, re.I)
        if not denied:
            return "question"
        if _yes(auth.get("needs_sponsorship_now")):
            return "blocks"
        if _yes(auth.get("needs_sponsorship_future")):
            # "will not sponsor" postings block future sponsorship needs too
            return "blocks" if "future" in r.quote.lower() or "now or in the future" \
                in r.quote.lower() else "question"
        return "ok" if _no(auth.get("needs_sponsorship_now")) and \
            _no(auth.get("needs_sponsorship_future")) else "question"
    if t in ("citizenship", "export_control"):
        # Citizenship and export-control eligibility are separate user answers.
        key = "citizenship_eligible" if t == "citizenship" else "export_control_eligible"
        v = auth.get(key)
        return "blocks" if _no(v) else "ok" if _yes(v) else "question"
    if t == "clearance":
        v = auth.get("clearance_eligible")
        return "blocks" if _no(v) else "ok" if _yes(v) else "question"
    return "question"


def dealbreaker_hits(job, profile: dict) -> list[str]:
    db = profile.get("dealbreakers", {}) or {}
    text = core.normalize(f"{job['title']} {job['raw_text']}")
    hits = [f"excluded term: {t}" for t in db.get("excluded_terms", [])
            if core.normalize(t) and re.search(rf"(?<!\w){re.escape(core.normalize(t))}(?!\w)", text)]
    parsed = json.loads(job["parsed_json"] or "{}")
    allowed = [e.lower() for e in db.get("employment_types", [])]
    et = (parsed.get("employment_type") or "").lower()
    if allowed and et and not any(a in et for a in allowed):
        hits.append(f"employment type {et!r} not in {allowed}")
    return hits


def score_job(conn, job_id: str, profile: dict | None = None) -> dict:
    profile = profile or core.load_profile()
    job = core.get_job(conn, job_id)
    if job["parsed_json"] is None:  # manual mode: discovery queued the parse as a task
        from . import discover
        parsed = discover.parse_posting(dict(job))
        if not discover.apply_parse(conn, job_id, job["raw_text"], parsed, job["raw_html"] or "",
                                    profile.get("targets", {})):
            return {"job_id": job_id, "score": 0, "decision": "skip", "blockers": [],
                    "pay": core.pay_band(job["comp_max"])}
        job = core.get_job(conn, job_id)
    known_ids = core.profile_ids(profile)

    user = (
        "## Candidate profile (verified facts)\n" + core.dumps({
            k: profile.get(k) for k in
            ("authorization", "education", "experience", "projects", "skills", "facts",
             "targets", "dealbreakers")
        })
        + "\n\n" + core.untrusted("job_metadata", core.dumps({
            k: job[k] for k in ("company", "title", "location")}))
        + "\n" + core.untrusted("parsed_posting", job['parsed_json'] or '{}') + "\n"
        + core.untrusted("posting", job["raw_text"])
    )
    result = core.llm_json("fit", core.system_prompt("fit"), user, FitResult)

    # --- rules as code -------------------------------------------------
    restrictions, blockers = [], []
    parsed_restrictions = json.loads(job["parsed_json"] or "{}").get("restrictions", [])
    candidates = list(result.restrictions) + [FitRestriction(**r, note="From posting parse")
                                            for r in parsed_restrictions]
    seen = set()
    for r in candidates:
        r.quote = html.unescape(r.quote)
        key = (r.type, " ".join(r.quote.split()).casefold())
        if key in seen:
            continue
        seen.add(key)
        if not core.quote_in_text(r.quote, job["raw_text"]):
            core.log_decision("fit", job_id, "dropped_restriction",
                              f"quote not verbatim in posting: {r.quote[:120]}")
            continue
        effect = restriction_effect(r, profile.get("authorization", {}))
        restrictions.append({**r.model_dump(), "effect": effect})
        if effect == "blocks":
            blockers.append(f"{r.type}: \"{r.quote}\"")
        elif effect == "question":
            result.questions.append(f"Posting says \"{r.quote}\". Does this apply to you?")

    strengths = []
    for s in result.strengths:
        bad = [f for f in s.fact_ids if f not in known_ids]
        if bad or not s.fact_ids:
            core.log_decision("fit", job_id, "dropped_strength",
                              f"uncited or unknown ids {bad}: {s.text[:100]}")
            continue
        strengths.append(s.model_dump())

    score = max(0, min(100, result.score))
    deal = dealbreaker_hits(job, profile)
    threshold = profile.get("targets", {}).get("min_fit_score", 70)
    if blockers:
        decision, status = "blocked", "blocked"
    elif deal:
        decision, status = "skip", "skipped"
    elif score >= threshold:
        decision, status = "shortlist", "shortlisted"
    else:
        decision, status = "skip", "skipped"

    conn.execute(
        "INSERT OR REPLACE INTO fit (job_id, score, strengths_json, gaps_json, restrictions_json, "
        "unknowns_json, questions_json, decision, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (job_id, score, core.dumps(strengths), core.dumps(result.gaps), core.dumps(restrictions),
         core.dumps(result.unknowns), core.dumps(result.questions), decision, core.now()),
    )
    conn.commit()
    if job["status"] not in ("applied", "responded", "interview", "rejected", "offer", "closed"):
        core.set_status(conn, job_id, status)
    reason = f"score {score} (threshold {threshold}); " + "; ".join(blockers + deal) \
        if blockers or deal else f"score {score} (threshold {threshold}). {result.summary}"
    core.log_decision("fit", job_id, decision, reason, [job["url"] or ""])
    return {"job_id": job_id, "score": score, "decision": decision, "blockers": blockers + deal,
            "pay": core.pay_band(job["comp_max"])}


def run(job_ids: list[str] | None = None) -> list[dict]:
    """Score the given jobs, or every active job still at 'discovered', highest pay first.
    In manual mode, jobs waiting on a task are skipped; re-run after answering."""
    conn = core.connect()
    profile = core.load_profile()
    if job_ids is None:
        job_ids = [r["id"] for r in conn.execute(
            "SELECT j.id FROM jobs j WHERE j.status='discovered' AND j.active=1 "
            f"ORDER BY {core.PAY_ORDER_SQL}").fetchall()]
    results = []
    for jid in job_ids:
        try:
            results.append(score_job(conn, jid, profile))
        except core.ManualTaskPending:
            continue
        except core.JobbotError as e:
            core.warn(f"fit {jid}: {e}")
            core.log_decision("fit", jid, "error", str(e))
    return results
