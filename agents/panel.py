"""Review panel: seven independent readers, then an editor, round after round.

  ats_gate         automated screening system: does a human ever see this?
  hiring_manager   interview, maybe, or no (reads the posting)
  team_lead        \\
  competing_applicant \\
  ceo               >  read the resume and cover letter alone
  senior_engineer  /
  recruiter       /
  editor           merges all reactions into one revision plan for the writer

packet.build() runs the panel after the checks and accuracy review pass, sends the
editor's revisions back to the writer, and repeats until the editor calls the resume
bulletproof or the round limit is hit. Every round is saved in panel.json / panel.md.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from . import ats, core
from .schemas import InterviewDecision, PersonaReview, RevisionPlan, ScreenDecision

READERS = {
    "team_lead": "team-lead.md",
    "competing_applicant": "competing-applicant.md",
    "ceo": "ceo.md",
    "senior_engineer": "senior-engineer.md",
    "recruiter": "recruiter.md",
}
LABELS = {"ats_gate": "ATS gate", "hiring_manager": "Hiring manager", "team_lead": "Team lead",
          "competing_applicant": "Competing applicant", "ceo": "CEO",
          "senior_engineer": "Senior engineer", "recruiter": "Recruiter"}
RUBRIC_WEIGHTS = {"ownership_depth": 30, "impact_validation": 30,
                  "role_focus": 20, "communication": 20}


def persona_prompt(file: str) -> str:
    base = core.strip_front_matter((core.SKILLS / "panel" / "SKILL.md").read_text())
    return base + "\n\n# Your role\n\n" + (core.SKILLS / "panel" / "personas" / file).read_text()


def _documents(d: Path) -> tuple[str, str]:
    sys.path.insert(0, str(core.ROOT))
    from checks._lib import pdf_text
    resume = pdf_text(d / "resume.pdf") if (d / "resume.pdf").exists() else ""
    letter = (d / "cover_letter.md").read_text() if (d / "cover_letter.md").exists() else "(no cover letter)"
    return resume, letter


def _gather(calls: dict) -> dict:
    """Run every call; in manual mode queue all tasks before stopping, so Claude can
    answer the whole panel at once instead of one persona per re-run."""
    out, pending = {}, None
    for name, fn in calls.items():
        try:
            out[name] = fn()
        except core.ManualTaskPending as e:
            pending = pending or e
    if pending:
        raise pending
    return out


def _editing_inventory(profile: dict) -> dict:
    """Useful source facts without contact details, referees or local evidence paths."""
    fields = {
        "education": ("id", "school", "degree", "start", "end", "gpa"),
        "experience": ("id", "title", "org", "start", "end", "facts"),
        "projects": ("id", "name", "start", "end", "facts"),
        "facts": ("id", "text"),
    }
    inventory = {key: [{field: entry[field] for field in wanted if field in entry}
                       for entry in profile.get(key, [])]
                 for key, wanted in fields.items()}
    inventory["disclosure_constraints"] = profile.get("preferences", {}).get(
        "resume_disclosure_constraints", [])
    prefs = profile.get('preferences', {})
    inventory['presentation_requirements'] = {key: prefs[key] for key in (
        'resume_min_projects', 'resume_min_project_bullets', 'resume_compact_education',
        'resume_coursework', 'resume_coursework_in_education') if key in prefs}
    return inventory


def run(conn, job_id: str, d: Path, round_no: int) -> dict:
    job = core.get_job(conn, job_id)
    resume, letter = _documents(d)
    keywords = ats.score_packet(conn, job_id, d)
    role = f"Role: {job['title']} at {job['company']}"
    digest = core.sha256_file(d / "resume.pdf")
    docs = ("## Review modality\nText-only review: no rendered page images are supplied. "
            "Assess wording and reading order; do not claim visual inspection or approve typography.\n\n"
            f"## Resume artifact SHA-256\n{digest}\n\n"
            f"## Resume (text as parsed from the PDF)\n{resume}\n\n## Cover letter\n{letter}")
    posting = core.untrusted("posting", job["raw_text"])

    calls = {
        "ats_gate": lambda: core.llm_json(
            "review_lead", persona_prompt("ats-gate.md"),
            f"{role}\n\n## Code-computed keyword match\n{core.dumps(keywords)}\n\n{docs}\n\n{posting}",
            ScreenDecision),
        "hiring_manager": lambda: core.llm_json(
            "review_lead", persona_prompt("hiring-manager.md"), f"{role}\n\n{docs}\n\n{posting}",
            InterviewDecision),
    }
    for name, file in READERS.items():
        calls[name] = (lambda f=file: core.llm_json(
            "review_lead", persona_prompt(f), f"{role}\n\n{docs}\n\n{posting}", PersonaReview))
    reviews = _gather(calls)

    profile = core.load_profile()
    plan = core.llm_json(
        "review_lead", persona_prompt("editor.md"),
        f"{role}\nRound {round_no}.\n\n{docs}\n\n{posting}\n\n"
        "## Candidate-supplied editing inventory\nUse these facts to identify supported edits, "
        "including useful omissions. They do not count as visible evidence on the current resume. "
        "Respect disclosure constraints.\n" + core.dumps(_editing_inventory(profile)) + "\n\n"
        "## Panel reviews\n" + core.dumps({k: v.model_dump() for k, v in reviews.items()}),
        RevisionPlan)

    prefs = profile.get("preferences", {})
    target = prefs.get("panel_min_score")
    result = summarize(reviews, plan, keywords, round_no, min_score=target,
                       strict_rubric=prefs.get("panel_strict_rubric", False))
    result["resume_sha256"] = digest
    result["review_inputs"] = {"resume_text": True, "posting": True,
                              "editor_fact_text": True, "page_images": False}
    save(d, result)
    core.log_decision("panel", job_id, f"round_{round_no}",
                      f"gate={result['gate']} hm={result['hiring_manager']} "
                      f"avg={result['reader_avg']} ats={keywords['score']} "
                      f"revisions={len(plan.revisions)} bulletproof={plan.bulletproof}")
    return result


def summarize(reviews: dict, plan: RevisionPlan, keywords: dict, round_no: int,
              min_score: float | None = None, strict_rubric: bool = False) -> dict:
    readers = {k: reviews[k] for k in READERS if k in reviews}
    scores = {k: r.score for k, r in readers.items()}
    if strict_rubric:
        for name, reader in readers.items():
            if reader.rubric is None:
                raise core.JobbotError(f"{name}: strict review requires rubric components")
            total = 0.0
            for key, maximum in RUBRIC_WEIGHTS.items():
                part = getattr(reader.rubric, key)
                if not math.isfinite(part.points) or not 0 <= part.points <= maximum or not part.reason.strip():
                    raise core.JobbotError(f"{name}: invalid or unexplained rubric component {key}")
                total += part.points
            scores[name] = total / 10
            if not math.isclose(reader.score, scores[name], abs_tol=0.001):
                raise core.JobbotError(f"{name}: score does not match rubric total; do not round to reach a target")
    avg = round(sum(scores.values()) / max(1, len(scores)), 1)
    gate, hm = reviews["ats_gate"], reviews["hiring_manager"]
    done = plan.bulletproof or not plan.revisions or (
        gate.decision == "pass_to_human" and hm.decision == "interview" and avg >= 8)
    lowest = min(scores.values(), default=0)
    if min_score is not None:
        try:
            min_score = float(min_score)
        except (TypeError, ValueError) as e:
            raise core.JobbotError("preferences.panel_min_score must be a number from 1 to 10") from e
        if not math.isfinite(min_score) or not 1 <= min_score <= 10:
            raise core.JobbotError("preferences.panel_min_score must be a number from 1 to 10")
        if any(not 1 <= r.score <= 10 for r in readers.values()):
            raise core.JobbotError("Panel reader score outside the 1-10 scale")
        # A high average or an editor flag cannot waive the candidate's target.
        done = (set(readers) == set(READERS) and lowest >= min_score
                and gate.decision == "pass_to_human" and hm.decision == "interview")
    return {
        "round": round_no, "gate": gate.decision, "gate_score": gate.score,
        "hiring_manager": hm.decision, "reader_avg": avg, "ats_keyword_score": keywords["score"],
        "ats_max_score": keywords["max_score"], "done": done,
        "reader_min": lowest, "reader_target": min_score,
        "rubric_version": 2 if strict_rubric else 1,
        "revisions": [f"{r.instruction} (raised by {', '.join(r.raised_by)}; facts {', '.join(r.fact_ids) or '-'})"
                      for r in plan.revisions],
        "reviews": {k: v.model_dump() for k, v in reviews.items()},
        "plan": plan.model_dump(),
    }


def save(d: Path, result: dict) -> None:
    path = d / "panel.json"
    history = json.loads(path.read_text()) if path.exists() else []
    history = [h for h in history if h["round"] != result["round"]] + [result]
    path.write_text(core.dumps(history))
    (d / "panel.md").write_text(render_md(history))


def render_md(history: list[dict]) -> str:
    lines = ["# Review panel", "",
             "| Round | ATS gate | ATS keywords | Hiring manager | Readers (avg /10) | Revisions |",
             "|---|---|---|---|---|---|"]
    for h in history:
        lines.append(f"| {h['round']} | {h['gate']} ({h['gate_score']}) | {h['ats_keyword_score']}% "
                     f"(max {h['ats_max_score']}%) | {h['hiring_manager']} | {h['reader_avg']} | "
                     f"{len(h['revisions'])} |")
    last = history[-1]
    if last.get("reader_target") is not None:
        lines += ["", f"**Reader target:** every reader >= {last['reader_target']:g}/10; "
                  f"lowest = {last['reader_min']:g}/10. Target met: {'yes' if last['done'] else 'no'}."]
    r = last["reviews"]
    lines += ["", f"## Latest round ({last['round']})", "",
              f"**ATS gate: {r['ats_gate']['decision']}** ({r['ats_gate']['score']}). {r['ats_gate']['reason']}"]
    if r["ats_gate"]["missing_keywords"]:
        lines.append(f"- Missing keywords: {', '.join(r['ats_gate']['missing_keywords'])}")
    for k in ("knockout_failures", "parsing_problems"):
        lines += [f"- {k.replace('_', ' ').capitalize()}: {x}" for x in r["ats_gate"][k]]
    hm = r["hiring_manager"]
    lines += ["", f"**Hiring manager: {hm['decision']}** (confidence {hm['confidence']})"]
    lines += [f"- For: {x}" for x in hm["reasons_for"]] + [f"- Against: {x}" for x in hm["reasons_against"]]
    lines += [f"- Would change my mind: {x}" for x in hm["what_would_change_my_mind"]]
    lines += ["", "| Reader | Verdict | Score | First impression |", "|---|---|---|---|"]
    for k in READERS:
        if k in r:
            lines.append(f"| {LABELS[k]} | {r[k]['verdict']} | {r[k]['score']} | {r[k]['first_impression']} |")
    plan = last["plan"]
    lines += ["", "## Editor's plan", ""] + [f"- Keep: {x}" for x in plan["keep"]]
    lines += [f"- Revise: {x}" for x in last["revisions"]]
    lines += [f"- Needs new evidence (gap): {x}" for x in plan["needs_new_evidence"]]
    lines += [f"- Conflict resolved: {x}" for x in plan["conflicts_resolved"]]
    lines += ["", f"**Bulletproof:** {'yes' if plan['bulletproof'] else 'not yet'}"]
    return "\n".join(lines) + "\n"
