"""Application writing agent: choose, order and reword verified facts for one job.

The model proposes; code disposes. Every bullet must cite fact IDs that belong to
the entry it sits under, or it is deleted. Output is written twice: a tagged
version that checks/ read, and a clean rendered version you send.
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import core
from .schemas import ParagraphList, TailoredPacket

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def fmt_month(value) -> str:
    s = str(value or "").strip()
    if s.lower() == "present" or not s:
        return s.capitalize() if s else ""
    parts = s.split("-")
    if len(parts) >= 2 and parts[1].isdigit() and 1 <= int(parts[1]) <= 12:
        return f"{MONTHS[int(parts[1]) - 1]} {parts[0]}"
    return s


def dates(entry: dict) -> str:
    start, end = fmt_month(entry.get("start")), fmt_month(entry.get("end"))
    return f"{start} – {end}" if start and end else start or end or str(entry.get("dates", ""))


RESEARCH_TITLE_RE = re.compile(r"\b(research|researcher|scientist|ph\.?d)\b", re.I)
RESEARCH_ASK_RE = re.compile(r"\b(publications?|publication record|ph\.?\s?d|first[- ]author|peer[- ]reviewed)\b", re.I)


def decide_pages(job, parsed: dict, profile: dict) -> tuple[int, str]:
    """1 or 2 pages for this job, and why. preferences.resume_pages: auto | 1 | 2."""
    pref = profile.get("preferences", {}).get("resume_pages", "auto")
    if str(pref) in ("1", "2"):
        return int(pref), f"fixed by preferences.resume_pages = {pref}"
    if RESEARCH_TITLE_RE.search(job["title"] or ""):
        return 2, "research-titled role: two pages let publications and research depth show"
    if RESEARCH_ASK_RE.search(job["raw_text"] or ""):
        return 2, "posting asks for publications or a PhD: two pages"
    return 1, "engineering role for a new grad: one page"


def resume_format(profile: dict) -> str:
    """preferences.resume_format: latex (my_resume/main.tex style) | typst."""
    return profile.get("preferences", {}).get("resume_format", "typst")


def packet_dir(job_id: str) -> Path:
    return core.job_dir(job_id)


# ------------------------------------------------------------- drafting

def draft(conn, job_id: str, feedback: list[str] | None = None) -> TailoredPacket:
    profile = core.load_profile()
    job = core.get_job(conn, job_id)
    fit = conn.execute("SELECT * FROM fit WHERE job_id=?", (job_id,)).fetchone()
    parsed = json.loads(job["parsed_json"] or "{}")
    prefs = profile.get("preferences", {})

    user = (
        "## Profile (the ONLY source of facts)\n" + core.dumps({
            k: profile.get(k) for k in
            ("person", "education", "experience", "projects", "skills", "facts")
        })
        + "\n\n## Answers bank (approved by the candidate; cite as answer_bank_keys)\n"
        + core.dumps(core.load_answers_bank())
        + "\n\n## Preferences\n" + core.dumps(prefs)
        + f"\n\n## Job\nCompany: {job['company']}\nTitle: {job['title']}\n"
        f"Req ID: {job['req_id']}\nParsed: {core.dumps(parsed)}\n"
        + (f"Fit analysis: strengths={fit['strengths_json']} gaps={fit['gaps_json']}\n"
           if fit else "")
        + f"Cover letter requested: {parsed.get('cover_letter_requested', False)}\n"
        f"Application questions: {core.dumps(parsed.get('application_questions', []))}\n\n"
        + core.untrusted("posting", job["raw_text"])
    )
    from . import ats, master
    pages, why = decide_pages(job, parsed, profile)
    user += (f"\n\n## Page budget: {pages} page(s) ({why}). "
             + ((f"Include at least {prefs['resume_min_projects']} distinct relevant projects; "
                 "balance their detail with experience and the requested skills/coursework."
                 if prefs.get('resume_min_projects') else
                 "Choose the strongest relevant entries and keep bullets to one or two lines.")
                if pages == 1 else
                "Use the room for depth: more research entries, projects and results, "
                "but every line must still earn its place."))
    kw = ats.classify(ats.posting_keywords(job), profile, None)
    user += ("\n\n## Supported posting terminology (diagnostic, not a coverage target)\n"
             "Use a term only where it accurately explains a selected contribution. "
             "Do not force exact spellings into every section, add a disabled summary, "
             "or replace distinctive engineering context with keyword lists.\n"
             + ", ".join(kw["fixable"])
             + "\n\n## Posting keywords with NO evidence in the profile (never claim these)\n"
             + (", ".join(kw["gap"]) or "none"))
    m = master.load()
    if m:
        user += ("\n\n## Master resume: candidate-approved source material, not a quality verdict. "
                 "Reassess selection and wording against the facts and posting. Restore useful "
                 "problem context or differentiators omitted by earlier drafts; keep evidence exact.\n"
                 + core.dumps(m))
    if feedback:
        user += ("\n\n## Fix these problems from the previous draft\n"
                 + "\n".join(f"- {f}" for f in feedback))
    return core.llm_json("writing", core.system_prompt("tailor"), user, TailoredPacket,
                         max_tokens=32000)


def unslop(paragraphs: list[dict], profile: dict) -> list[dict]:
    """Remove filler and AI-sounding phrasing. Keeps each paragraph's fact IDs."""
    if not paragraphs:
        return paragraphs
    banned = profile.get("preferences", {}).get("banned_phrases", [])
    result = core.llm_json(
        "writing", core.system_prompt("unslop"),
        f"Banned phrases: {banned}\n\nParagraphs:\n" + core.dumps(paragraphs),
        ParagraphList, max_tokens=8000,
    )
    out = []
    for before, after in zip(paragraphs, result.paragraphs):
        # The rewrite may not add sources. Fall back to the original if it did.
        if set(after.fact_ids) <= set(before["fact_ids"]) and after.fact_ids:
            out.append(after.model_dump())
        else:
            out.append(before)
    return out + paragraphs[len(result.paragraphs):]


# ------------------------------------------------------------ validation

def select_skills(chosen: list[str], profile: dict, must_have: list[str],
                  posting_text: str = "") -> list[dict]:
    """Evidence-backed writer picks, with optional automatic posting matches.
    Familiar skills are included only when required."""
    from . import ats
    required = " ".join(must_have)
    picked = {c.lower() for c in chosen}
    auto_add = profile.get("preferences", {}).get("resume_auto_add_skills", False)
    out = []
    for s in profile.get("skills", []):
        if not s.get("evidence"):
            continue
        wanted = s["skill"].lower() in picked or (
            auto_add and posting_text and ats.mentions(s["skill"], posting_text))
        if not wanted:
            continue
        if s.get("level") in ("strong", "working"):
            out.append({"skill": s["skill"], "fact_ids": s["evidence"],
                        "category": s.get("category", "Skills")})
        elif s.get("level") == "familiar" and ats.mentions(s["skill"], required):
            out.append({"skill": f"{s['skill']} (familiar)", "fact_ids": s["evidence"],
                        "category": s.get("category", "Skills")})
    return out


def enforce(packet: TailoredPacket, profile: dict, job_id: str,
            must_have: list[str], posting_text: str = "") -> dict:
    """Apply no-unsourced-claims in code. Returns a plain dict ready to render."""
    known = core.profile_ids(profile)
    entries = {e["id"]: e for e in profile.get("experience", []) + profile.get("projects", [])}
    bank = core.load_answers_bank()

    def keep_entry(entry) -> dict | None:
        src = entries.get(entry.ref_id)
        if not src:
            core.log_decision("tailor", job_id, "dropped_entry", f"unknown ref {entry.ref_id}")
            return None
        allowed = set(src.get("facts", []))
        bullets = []
        for b in entry.bullets:
            if b.fact_ids and set(b.fact_ids) <= allowed:
                bullets.append({"text": b.text.strip(), "fact_ids": b.fact_ids})
            else:
                core.log_decision("tailor", job_id, "dropped_bullet",
                                  f"{entry.ref_id}: ids {b.fact_ids} not in {sorted(allowed)}: "
                                  f"{b.text[:100]}")
        return {"ref_id": entry.ref_id, "bullets": bullets} if bullets else None

    skills = select_skills(packet.skills, profile, must_have, posting_text)

    summary = None
    if packet.summary.fact_ids and set(packet.summary.fact_ids) <= known:
        summary = packet.summary.model_dump()
    else:
        core.log_decision("tailor", job_id, "dropped_summary",
                          f"uncited or unknown ids {packet.summary.fact_ids}")

    paragraphs = [p.model_dump() for p in packet.cover_letter
                  if p.fact_ids and set(p.fact_ids) <= known]

    answers = []
    for a in packet.answers:
        keys = [k for k in a.answer_bank_keys
                if isinstance(_bank_get(bank, k), (str, bool, int, float))]
        ids = [f for f in a.fact_ids if f in known]
        invalid = len(keys) != len(a.answer_bank_keys) or len(ids) != len(a.fact_ids)
        if a.need_input or invalid or not (keys or ids):
            answers.append({"question": a.question, "answer": "", "fact_ids": [],
                            "keys": [], "need_input": a.need_input or "no supporting fact"})
        else:
            answer = a.answer.strip()
            # An answer-bank citation is not permission to reverse the approved
            # answer (especially self-identification). Use the stored value.
            if keys and (not ids or any(k.startswith("self_identification.") for k in keys)):
                answer = "\n".join(str(_bank_get(bank, k)) for k in keys)
            answers.append({"question": a.question, "answer": answer,
                            "fact_ids": ids, "keys": keys, "need_input": None})

    return {
        "summary": summary,
        "experience": [e for e in map(keep_entry, packet.experience) if e],
        "projects": [e for e in map(keep_entry, packet.projects) if e],
        "skills": skills,
        "cover_letter": paragraphs,
        "answers": answers,
        "rationale": packet.rationale,
    }


def _bank_get(bank: dict, dotted: str):
    node = bank
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


# -------------------------------------------------------------- writing

def tags(ids: list[str], keys: list[str] = ()) -> str:
    return "".join(f"[{i}]" for i in ids) + "".join(f"[A:{k}]" for k in keys)


def write_packet(job, content: dict, profile: dict, version: int, pages: int = 1,
                 pages_reason: str = "") -> Path:
    d = packet_dir(job["id"])
    d.mkdir(parents=True, exist_ok=True)
    person = profile.get("person", {})
    entries = {e["id"]: e for e in profile.get("experience", []) + profile.get("projects", [])}

    meta = {"job_id": job["id"], "company": job["company"], "title": job["title"],
            "req_id": job["req_id"], "url": job["url"], "location": job["location"],
            "version": version, "created_at": core.now(),
            "pages": pages, "pages_reason": pages_reason, "format": resume_format(profile),
            "show_summary": bool(profile.get("preferences", {}).get("resume_summary", False))}
    meta['min_projects'] = int(profile.get('preferences', {}).get('resume_min_projects', 0))
    (d / "meta.json").write_text(core.dumps(meta))

    # --- resume: tagged markdown (for checks) + json (for Typst) ----------
    lines = [f"# {person.get('name', '')} | {person.get('email', '')} | "
             f"{person.get('phone', '')} | {person.get('location', '')}", ""]
    summary = content.get("summary")
    if summary:
        lines += ["## Summary", f"{summary['text']} {tags(summary['fact_ids'])}", ""]
    lines.append("## Education")
    edu_json = []
    for i, e in enumerate(profile.get("education", [])):
        lines.append(f"{e['degree']}, {e['school']}, {dates(e)}"
                     + (f", GPA {e['gpa']}" if e.get("gpa") else "") + f" [{e['id']}]")
        details = []
        if e.get("thesis", {}).get("title"):
            details.append(f"Thesis: {e['thesis']['title']}")
        if e.get("coursework") and i == 0:  # coursework only for the current degree
            details.append("Relevant coursework: " + ", ".join(e["coursework"][:6]))
        lines += [f"- {x} [{e['id']}]" for x in details]
        shown_dates = dates(e)
        if profile.get("preferences", {}).get("resume_graduation_only") and e.get("end"):
            shown_dates = fmt_month(e["end"])
            if str(e["end"]) > core.today():
                shown_dates = "Expected " + shown_dates
        edu_json.append({"degree": e["degree"], "school": e["school"], "dates": shown_dates,
                         "location": e.get("location", ""), "gpa": str(e.get("gpa") or ""),
                         "details": details})

    def section(title: str, items: list[dict], kind: str) -> list[dict]:
        out = []
        if items:
            lines.extend(["", f"## {title}"])
        for item in items:
            src = entries[item["ref_id"]]
            heading = (f"{src['title']}, {src['org']}" if kind == "experience"
                       else src["name"])
            lines.append(f"### {heading}, {dates(src)} [{src['id']}]")
            lines.extend(f"- {b['text']} {tags(b['fact_ids'])}" for b in item["bullets"])
            out.append({"ref_id": item['ref_id'], "heading": heading, "title": src.get("title", src.get("name", "")),
                        "org": src.get("org", ""), "location": src.get("location", ""),
                        "employer": src.get("employer", src.get("org", "")),
                        "team": src.get("team", ""),
                        "dates": dates(src), "links": src.get("links", {}) or {},
                        "focus": src.get("focus"), "tools": src.get("tools") or [],
                        "bullets": [b["text"] for b in item["bullets"]]})
        return out

    exp_json = section("Experience", content["experience"], "experience")
    proj_json = section("Projects", content["projects"], "project")
    groups: dict[str, list[dict]] = {}
    display_groups = profile.get('preferences', {}).get('resume_skill_groups', {})
    category_for_skill = {name: category for category, names in display_groups.items() for name in names}
    for sk in content["skills"]:
        category = category_for_skill.get(sk['skill'], sk.get('category', 'Skills'))
        groups.setdefault(category, []).append(sk)
    if groups:
        lines.extend(["", "## Skills"])
        for cat, items in groups.items():
            ids = sorted({i for sk in items for i in sk["fact_ids"]})
            lines.append(f"- {cat}: {', '.join(sk['skill'] for sk in items)} {tags(ids)}")
    (d / "resume.tagged.md").write_text("\n".join(lines) + "\n")

    resume_json = {
        "layout": {"font_family": profile.get("preferences", {}).get("resume_font", "charter"),
                   "presentation": profile.get("preferences", {}).get("resume_presentation", "classic"),
                   "compact_education": bool(profile.get("preferences", {}).get("resume_compact_education", False)),
                   "coursework_in_education": bool(profile.get("preferences", {}).get("resume_coursework_in_education", False)),
                   "skills_last": bool(profile.get("preferences", {}).get("resume_skills_last", False))},
        "person": {k: person.get(k, "") for k in ("name", "email", "phone", "location")}
        | {"links": person.get("links", {}) or {}},
        "summary": summary["text"] if summary else "",
        "courses": ((profile.get("education") or [{}])[0].get("coursework", []) or [])
        if profile.get("preferences", {}).get("resume_coursework", True) else [],
        "sections": ["summary", "skills", "experience", "projects", "education"],
        "education": edu_json, "experience": exp_json, "projects": proj_json,
        "skills": [{"category": c, "items": [sk["skill"] for sk in items]}
                   for c, items in groups.items()],
    }
    (d / "resume.json").write_text(core.dumps(resume_json))
    shutil.copy(core.TEMPLATES / "resume.typ", d / "resume.typ")

    # --- cover letter --------------------------------------------------
    for p in ("cover_letter.tagged.md", "cover_letter.md", "cover_letter.json",
              "cover_letter.typ", "cover_letter.pdf"):
        (d / p).unlink(missing_ok=True)
    if content["cover_letter"]:
        tagged = [f"# Cover letter: {job['title']}, {job['company']}", ""]
        tagged += [f"{p['text']} {tags(p['fact_ids'])}\n" for p in content["cover_letter"]]
        (d / "cover_letter.tagged.md").write_text("\n".join(tagged))
        clean = [p["text"] for p in content["cover_letter"]]
        (d / "cover_letter.md").write_text("\n\n".join(clean) + "\n")
        (d / "cover_letter.json").write_text(core.dumps({
            "person": resume_json["person"], "company": job["company"],
            "title": job["title"], "date": core.today(), "paragraphs": clean}))
        shutil.copy(core.TEMPLATES / "cover_letter.typ", d / "cover_letter.typ")

    # --- answers -------------------------------------------------------
    tagged, clean = [f"# Application answers: {job['title']}, {job['company']}", ""], []
    for a in content["answers"]:
        tagged.append(f"## Q: {a['question']}")
        clean.append(f"**{a['question']}**\n")
        if a["need_input"]:
            tagged.append(f"[NEED INPUT: {a['need_input']}]")
            clean.append(f"[NEED INPUT: {a['need_input']}]\n")
        else:
            tagged.append(f"{a['answer']} {tags(a['fact_ids'], a['keys'])}")
            clean.append(a["answer"] + "\n")
        tagged.append("")
    (d / "answers.tagged.md").write_text("\n".join(tagged))
    (d / "answers.md").write_text("\n".join(clean))

    # --- diff vs master ------------------------------------------------
    facts = core.facts_by_id(profile)
    master, tailored = [], []
    for e in profile.get("experience", []) + profile.get("projects", []):
        master.append(f"### {e['id']} {e.get('title') or e.get('name')}")
        master += [f"- {facts[f]['text']}" for f in e.get("facts", []) if f in facts]
    for item in content["experience"] + content["projects"]:
        src = entries[item["ref_id"]]
        tailored.append(f"### {src['id']} {src.get('title') or src.get('name')}")
        tailored += [f"- {b['text']}" for b in item["bullets"]]
    diff = difflib.unified_diff(master, tailored, "master (profile.yaml)", "tailored", lineterm="")
    (d / "changes.diff").write_text("\n".join(diff) + "\n")
    (d / "rationale.md").write_text(content["rationale"] + "\n")
    return d


def compile_typst(src: Path) -> Path:
    pdf = src.with_suffix(".pdf")
    if shutil.which("typst"):
        subprocess.run(["typst", "compile", str(src), str(pdf)], check=True,
                       capture_output=True, text=True)
    else:
        import typst
        typst.compile(str(src), output=str(pdf))
    return pdf


def render(d: Path) -> list[Path]:
    pdfs = []
    meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
    note = d / "LATEX_NOTE.md"
    note.unlink(missing_ok=True)
    # A failed rebuild must never leave a previous version's PDF looking current.
    for name in ("resume.pdf", "cover_letter.pdf"):
        (d / name).unlink(missing_ok=True)
    if meta.get("format") == "latex" and (d / "resume.json").exists():
        from . import latex
        show_summary = meta.get("show_summary", False)
        tex = latex.render_tex(json.loads((d / "resume.json").read_text()), d / "resume.tex",
                               pages=meta.get("pages", 1), show_summary=show_summary)
        pdf = latex.compile_pdf(tex)
        if pdf:
            pdfs.append(pdf)
            (d / "resume.typ").unlink(missing_ok=True)  # the LaTeX PDF is the resume
            data = json.loads((d / "resume.json").read_text())
            ctx = latex.context(data)
            data["sections"] = (["education", "experience", "projects", "skills"]
                                if data.get("layout", {}).get("skills_last") else
                                ["education", "skills", "experience", "projects"])
            if show_summary and data.get("summary"):
                data["sections"].insert(0, "summary")
            data["section_headings"] = {name: ctx[f"{name}_title"]
                                        for name in ("education", "experience", "projects", "skills")}
            # Keep the render description in sync with what the PDF includes.
            if not show_summary:
                data["summary"] = ""
            for e in data["education"]:
                e["details"] = []
            (d / "resume.json").write_text(core.dumps(data))
        else:
            note.write_text("No LaTeX engine is installed, so resume.pdf is the Typst fallback "
                            "(used for checks). Compile resume.tex on Overleaf, or install "
                            "tectonic / texlive, then re-run the packet.\n")
    for name in ("resume.typ", "cover_letter.typ"):
        if (d / name).exists():
            try:
                pdfs.append(compile_typst(d / name))
            except (subprocess.CalledProcessError, RuntimeError, ImportError) as e:
                detail = getattr(e, "stderr", "") or str(e)
                raise core.JobbotError(f"Typst failed on {name}: {detail}") from e
    return pdfs


def build(conn, job_id: str, feedback: list[str] | None = None, version: int = 1) -> Path:
    profile = core.load_profile()
    job = core.get_job(conn, job_id)
    parsed = json.loads(job["parsed_json"] or "{}")
    packet = draft(conn, job_id, feedback)
    content = enforce(packet, profile, job_id, parsed.get("must_have", []),
                      job["raw_text"] + " " + " ".join(parsed.get("keywords", [])))
    content["cover_letter"] = unslop(content["cover_letter"], profile)
    pages, why = decide_pages(job, parsed, profile)
    d = write_packet(job, content, profile, version, pages, why)
    render(d)
    core.log_decision("tailor", job_id, f"packet_v{version}",
                      f"{pages} page(s): {why}. {content['rationale'][:250]}")
    return d
