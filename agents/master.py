"""Master resume: every fact written once as a recruiter-grade bullet, tagged by role family.

    python jobbot.py master --draft          (re)write data/master_resume.yaml (one AI step)
    python jobbot.py master                  full master resume, all bullets (multi-page)
    python jobbot.py master --family rl      instant one-page resume for a role family, no AI

The writing agent also starts from these bullets when tailoring to a specific job.
data/master_resume.yaml is gitignored (it's your CV).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from . import core, tailor
from .schemas import MasterResume

PATH = core.DATA / "master_resume.yaml"
FAMILIES = ("perception", "rl", "robotics_swe", "ml")
MAX_BULLETS = {"experience": 4, "projects": 2}


def load() -> dict | None:
    return yaml.safe_load(PATH.read_text()) if PATH.exists() else None


def draft() -> Path:
    profile = core.load_profile()
    result = core.llm_json(
        "writing", core.system_prompt("master"),
        "## Profile (the ONLY source of facts)\n" + core.dumps({
            k: profile.get(k) for k in
            ("person", "education", "experience", "projects", "skills", "facts", "targets")})
        + "\n\n## Preferences\n" + core.dumps(profile.get("preferences", {})),
        MasterResume, max_tokens=32000)
    data = enforce(result, profile)
    PATH.write_text("# Master resume: written by the master agent, checked against profile.yaml.\n"
                    "# Edit freely; every bullet must keep fact IDs from its own entry.\n"
                    + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))
    return PATH


def enforce(result: MasterResume, profile: dict) -> dict:
    """Same rule as tailoring: a bullet may only cite facts of the entry it sits under."""
    entries = {e["id"]: e for e in profile.get("experience", []) + profile.get("projects", [])}
    known = core.profile_ids(profile)
    out_entries = {}
    for e in result.entries:
        allowed = set(entries.get(e.ref_id, {}).get("facts", []))
        kept = [b.model_dump() for b in e.bullets if b.fact_ids and set(b.fact_ids) <= allowed]
        dropped = len(e.bullets) - len(kept)
        if dropped:
            core.log_decision("master", None, "dropped_bullets", f"{e.ref_id}: {dropped} uncited")
        if kept:
            out_entries[e.ref_id] = sorted(kept, key=lambda b: b["priority"])
    summaries = {s.family: {"text": s.text, "fact_ids": s.fact_ids}
                 for s in result.summaries if s.fact_ids and set(s.fact_ids) <= known}
    families = {f.family: {"label": f.label, "experience": [x for x in f.experience if x in out_entries],
                           "projects": [x for x in f.projects if x in out_entries],
                           "skill_categories": f.skill_categories} for f in result.families}
    return {"families": families, "summaries": summaries, "entries": out_entries}


def content_for(master: dict, profile: dict, family: str | None) -> dict:
    """Pick bullets from the master. family=None -> everything (the full master CV)."""
    entries = {e["id"]: e for e in profile.get("experience", []) + profile.get("projects", [])}
    exp_ids = [e["id"] for e in profile.get("experience", [])]
    proj_ids = [e["id"] for e in profile.get("projects", [])]
    plan = master["families"].get(family) if family else None
    if family and not plan:
        raise core.JobbotError(f"Unknown family {family!r}; choose from {list(master['families'])}")

    def pick(ids: list[str], kind: str) -> list[dict]:
        items = []
        for ref in ids:
            bullets = master["entries"].get(ref, [])
            if family:
                bullets = [b for b in bullets if family in b.get("families", [])]
                bullets = bullets[:MAX_BULLETS[kind]]
            if ref not in entries:
                continue
            # The profile may have changed since the master was written: keep only
            # bullets whose facts still belong to this entry.
            allowed = set(entries[ref].get("facts", []))
            bullets = [b for b in bullets if b["fact_ids"] and set(b["fact_ids"]) <= allowed]
            if bullets:
                items.append({"ref_id": ref, "bullets": [
                    {"text": b["text"], "fact_ids": b["fact_ids"]} for b in bullets]})
        return items

    experience = pick(plan["experience"] if plan else exp_ids, "experience")
    projects = pick(plan["projects"] if plan else proj_ids, "projects")
    cats = set(plan["skill_categories"]) if plan else None
    skills = [{"skill": s["skill"], "fact_ids": s["evidence"], "category": s.get("category", "Skills")}
              for s in profile.get("skills", [])
              if s.get("evidence") and s.get("level") in ("strong", "working")
              and (cats is None or s.get("category") in cats)]
    summary = master["summaries"].get(family) if family else (
        master["summaries"].get(next(iter(master["summaries"]), ""), None))
    return {"summary": summary, "experience": experience, "projects": projects,
            "skills": skills, "cover_letter": [], "answers": [],
            "rationale": f"Master resume ({family or 'full'})."}


def render(family: str | None = None) -> dict:
    import sys
    sys.path.insert(0, str(core.ROOT))
    from checks import banned_phrases, fact_ids, length_limits, numbers_match, ats_parse

    master, profile = load(), core.load_profile()
    if not master:
        raise core.JobbotError("No data/master_resume.yaml yet. Run: python jobbot.py master --draft")
    label = master["families"][family]["label"] if family else "Full master CV"
    job = {"id": f"Master_Resume_{family or 'full'}", "company": "(master)", "title": label,
           "req_id": None, "url": None, "location": ""}
    pages = 1 if family else 2
    d = tailor.write_packet(job, content_for(master, profile, family), profile, version=1,
                            pages=pages, pages_reason="family one-pager" if family else "full master CV")
    for name in ("answers.md", "answers.tagged.md", "changes.diff", "rationale.md"):
        (d / name).unlink(missing_ok=True)
    tailor.render(d)
    checks = {"fact_ids": fact_ids.check, "numbers_match": numbers_match.check,
              "banned_phrases": banned_phrases.check, "ats_parse": ats_parse.check}
    if family:  # the full master is allowed to run long
        checks["length_limits"] = length_limits.check
    results = {name: fn(d) for name, fn in checks.items()}
    return {"dir": d, "results": results}
