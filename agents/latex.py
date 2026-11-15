"""LaTeX resumes in the style of my_resume/main.tex.

    resume.json (written by tailor/master) -> resume.tex -> resume.pdf

The .tex is always written, so it can also be compiled on Overleaf. A PDF is built
only when a LaTeX engine is installed (tectonic, latexmk, pdflatex or xelatex).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, urlsplit

import jinja2

from . import core

TEMPLATE = "resume.tex.j2"
COVER_TEMPLATE = "cover_letter.tex.j2"
ENGINES = ("tectonic", "latexmk", "pdflatex", "xelatex")
# Category names that read badly on a page.
CATEGORY_LABELS = {"Project tools": "Tools"}
LINK_LABELS = {"github": "GitHub", "linkedin": "LinkedIn", "site": "Portfolio",
               "scholar": "Google Scholar", "repo": "Code", "writeup": "Write-up",
               "video": "Video", "paper": "Paper"}

_SPECIAL = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
            "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
            "\\": r"\textbackslash{}", "×": r"$\times$", "→": r"$\rightarrow$",
            "–": r"\textendash{}", "—": r"\textemdash{}",
            "’": r"\textquoteright{}", "‘": r"\textquoteleft{}",
            "“": r"\textquotedblleft{}", "”": r"\textquotedblright{}",
            "≈": r"$\approx$", "±": r"$\pm$", "≤": r"$\leq$", "≥": r"$\geq$", "°": r"$^\circ$"}
_SPECIAL_RE = re.compile("|".join(re.escape(k) for k in _SPECIAL))
# Metrics are bold in main.tex ("by \textbf{7\%}"); do the same for percentages.
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?\\%)")
_UNIT_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?) (m|cm|mm|g|kg|Hz|ms|s|FPS|px|dB)\b")


class Raw(str):
    """Already-LaTeX text (links, commands): not escaped."""


def escape(value, emphasis: bool = True) -> str:
    """emphasis=False for letter prose, where bold percentages would look like a flyer."""
    if value is None:
        return ""
    if isinstance(value, Raw):
        return str(value)
    text = _SPECIAL_RE.sub(lambda m: _SPECIAL[m.group(0)], str(value))
    if emphasis:
        text = _PERCENT_RE.sub(r"\\textbf{\1}", text)
    text = re.sub(r"\bROS ([12])\b", r"ROS~\1", text)
    return _UNIT_RE.sub(r"\1~\2", text)


def _href(url: str, label: str) -> Raw:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise core.JobbotError("Resume links must be absolute HTTP(S) URLs")
    # Braces/backslashes in a data URL must never become TeX commands.
    safe_url = quote(url, safe=":/?&=+#@._~%-").replace("%", r"\%").replace("#", r"\#")
    return Raw(rf"\href{{{safe_url}}}{{{escape(label)}}}")


def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(core.TEMPLATES)),
        block_start_string="((*", block_end_string="*))",
        variable_start_string="(((", variable_end_string=")))",
        comment_start_string="((#", comment_end_string="#))",
        trim_blocks=True, lstrip_blocks=True, autoescape=False,
        finalize=escape, undefined=jinja2.StrictUndefined)


def context(resume: dict, pages: int = 1, show_summary: bool = False) -> dict:
    """Map resume.json onto the template's fields."""
    person = resume["person"]
    layout = resume.get("layout", {})
    presentation = layout.get("presentation", "classic")
    if presentation not in ("classic", "research"):
        raise core.JobbotError("resume_presentation must be 'classic' or 'research'")
    font_family = layout.get("font_family", "charter")
    if font_family not in ("charter", "sans"):
        raise core.JobbotError("resume_font must be 'charter' or 'sans'")
    contact = [x for x in (person.get("location"), person.get("email"), person.get("phone")) if x]
    for key, url in (person.get("links") or {}).items():
        if isinstance(url, str) and url.startswith("http"):
            contact.append(_href(url, LINK_LABELS.get(key, key.title())))

    def first_link(links: dict) -> Raw | None:
        for key, url in (links or {}).items():
            if isinstance(url, str) and url.startswith("http"):
                return _href(url, LINK_LABELS.get(key, "Link"))
        return None

    experience = []
    previous_employer = None
    for x in resume.get("experience", []):
        employer = x.get("employer") or x["org"]
        experience.append({"title": x["title"], "org": x["org"], "employer": employer,
                           "team": x.get("team", ""), "dates": x["dates"],
                           "show_employer": employer != previous_employer,
                           "focus": x.get("focus"), "bullets": x["bullets"]})
        previous_employer = employer
    research = experience and all("research" in x["title"].lower() for x in experience)
    return {
        "name": person["name"],
        "contact": contact,
        "presentation": presentation,
        "compact_education": bool(layout.get("compact_education", False)),
        "courses_in_education": bool(layout.get("coursework_in_education", False)),
        "entry_gap_pt": 2 if presentation == 'research' else 4,
        "margin_cm": 1.8,
        "font_family": font_family,
        "skills_last": bool(layout.get("skills_last", False)),
        "summary": resume.get("summary") if show_summary else "",
        "education": [{"school": e["school"], "degree": e["degree"], "dates": e["dates"],
                       "gpa": e.get("gpa")} for e in resume.get("education", [])],
        "skills": [{"category": CATEGORY_LABELS.get(g["category"], g["category"]), "names": g["items"]}
                   for g in resume.get("skills", [])],
        "courses": resume.get("courses", []),
        "experience_title": (("Research Experience" if research else "Experience")
                             if presentation == "research" else
                             ("RESEARCH EXPERIENCE" if research else "EXPERIENCE")),
        "education_title": "Education" if presentation == "research" else "EDUCATION",
        "projects_title": "Selected Projects" if presentation == "research" else "PROJECTS",
        "skills_title": "Technical Skills" if presentation == "research" else "SKILLS",
        "experience": experience,
        "projects": [{"heading": p["heading"], "dates": p.get("dates", ""), "bullets": p["bullets"],
                      "tools": p.get("tools") or [], "link": first_link(p.get("links", {}))}
                     for p in resume.get("projects", [])],
    }


def render_tex(resume: dict, out: Path, pages: int = 1, show_summary: bool = False) -> Path:
    out.write_text(_env().get_template(TEMPLATE).render(**context(resume, pages, show_summary)))
    return out


def render_cover_tex(letter: dict, out: Path) -> Path:
    """cover_letter.json -> cover_letter.tex, with the resume's typeface and header."""
    person = letter["person"]
    layout = letter.get("layout", {})
    font_family = layout.get("font_family", "charter")
    if font_family not in ("charter", "sans"):
        raise core.JobbotError("resume_font must be 'charter' or 'sans'")
    contact = [x for x in (person.get("location"), person.get("email"), person.get("phone")) if x]
    for key, url in (person.get("links") or {}).items():
        if isinstance(url, str) and url.startswith("http"):
            contact.append(_href(url, LINK_LABELS.get(key, key.title())))
    out.write_text(_env().get_template(COVER_TEMPLATE).render(
        name=person["name"], contact=contact, font_family=font_family,
        date=_long_date(letter.get("date", "")), company=letter["company"],
        location=letter.get("location", ""), title=letter["title"],
        paragraphs=[Raw(escape(p, emphasis=False)) for p in letter["paragraphs"]]))
    return out


def _long_date(iso: str) -> str:
    parts = str(iso).split("-")
    if len(parts) == 3 and all(p.isdigit() for p in parts) and 1 <= int(parts[1]) <= 12:
        month = ("January February March April May June July August September October "
                 "November December").split()[int(parts[1]) - 1]
        return f"{month} {int(parts[2])}, {parts[0]}"
    return str(iso)


def engine() -> str | None:
    """First installed LaTeX engine, including a user-local ~/.local/bin/tectonic."""
    extra = os.pathsep.join([str(Path.home() / ".local" / "bin"), os.environ.get("PATH", "")])
    for name in ENGINES:
        path = shutil.which(name, path=extra)
        if path:
            return path
    return None


def compile_pdf(tex: Path) -> Path | None:
    """tex -> pdf next to it. None if no engine is installed."""
    exe = engine()
    if not exe:
        return None
    name = Path(exe).name
    cmd = {"tectonic": [exe, "--untrusted", "--keep-logs", tex.name],
           "latexmk": [exe, "-pdf", "-no-shell-escape", "-interaction=nonstopmode", tex.name]}.get(
        name, [exe, "-no-shell-escape", "-interaction=nonstopmode", tex.name])
    runs = 1 if name in ("tectonic", "latexmk") else 2  # pdflatex: twice for paracol
    for _ in range(runs):
        try:
            r = subprocess.run(cmd, cwd=tex.parent, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired as e:
            raise core.JobbotError(f"LaTeX timed out on {tex.name}") from e
        if r.returncode:
            break
    pdf = tex.with_suffix(".pdf")
    if r.returncode != 0 or not pdf.exists():
        raise core.JobbotError(f"LaTeX failed on {tex.name}:\n{(r.stdout + r.stderr)[-1500:]}")
    log = tex.with_suffix(".log")
    if log.exists() and re.search(r"Font shape [^\n]*undefined|Missing character:",
                                  log.read_text(errors="replace")):
        raise core.JobbotError(
            f"LaTeX substituted a font or lost characters in {tex.name}; inspect the font setup")
    return pdf
