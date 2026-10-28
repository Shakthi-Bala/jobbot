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

import jinja2

from . import core

TEMPLATE = "resume.tex.j2"
ENGINES = ("tectonic", "latexmk", "pdflatex", "xelatex")
# Category names that read badly on a page.
CATEGORY_LABELS = {"Project tools": "Tools"}
LINK_LABELS = {"github": "GitHub", "linkedin": "LinkedIn", "site": "Portfolio",
               "scholar": "Google Scholar", "repo": "Code", "writeup": "Write-up",
               "video": "Video", "paper": "Paper"}

_SPECIAL = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
            "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
            "\\": r"\textbackslash{}", "×": r"$\times$", "→": r"$\rightarrow$",
            "≈": r"$\approx$", "±": r"$\pm$", "≤": r"$\leq$", "≥": r"$\geq$", "°": r"$^\circ$"}
_SPECIAL_RE = re.compile("|".join(re.escape(k) for k in _SPECIAL))
# Metrics are bold in main.tex ("by \textbf{7\%}"); do the same for percentages.
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?\\%)")


class Raw(str):
    """Already-LaTeX text (links, commands): not escaped."""


def escape(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Raw):
        return str(value)
    text = _SPECIAL_RE.sub(lambda m: _SPECIAL[m.group(0)], str(value))
    return _PERCENT_RE.sub(r"\\textbf{\1}", text)


def _href(url: str, label: str) -> Raw:
    safe_url = url.replace("%", r"\%").replace("#", r"\#")
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
    contact = [x for x in (person.get("location"), person.get("email"), person.get("phone")) if x]
    for key, url in (person.get("links") or {}).items():
        if isinstance(url, str) and url.startswith("http"):
            contact.append(_href(url, LINK_LABELS.get(key, key.title())))

    def first_link(links: dict) -> Raw | None:
        for key, url in (links or {}).items():
            if isinstance(url, str) and url.startswith("http"):
                return _href(url, LINK_LABELS.get(key, "Link"))
        return None

    experience = [{"title": x["title"], "org": x["org"], "dates": x["dates"],
                   "focus": x.get("focus"), "bullets": x["bullets"]}
                  for x in resume.get("experience", [])]
    research = experience and all("research" in x["title"].lower() for x in experience)
    return {
        "name": person["name"],
        "contact": contact,
        "margin_cm": 2.0 if pages == 1 else 1.8,
        "summary": resume.get("summary") if show_summary else "",
        "education": [{"school": e["school"], "degree": e["degree"], "dates": e["dates"],
                       "gpa": e.get("gpa")} for e in resume.get("education", [])],
        "skills": [{"category": CATEGORY_LABELS.get(g["category"], g["category"]), "names": g["items"]}
                   for g in resume.get("skills", [])],
        "courses": resume.get("courses", []),
        "experience_title": "RESEARCH EXPERIENCE" if research else "EXPERIENCE",
        "experience": experience,
        "projects": [{"heading": p["heading"], "dates": p.get("dates", ""), "bullets": p["bullets"],
                      "tools": p.get("tools") or [], "link": first_link(p.get("links", {}))}
                     for p in resume.get("projects", [])],
    }


def render_tex(resume: dict, out: Path, pages: int = 1, show_summary: bool = False) -> Path:
    out.write_text(_env().get_template(TEMPLATE).render(**context(resume, pages, show_summary)))
    return out


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
    cmd = {"tectonic": [exe, "--keep-logs", tex.name],
           "latexmk": [exe, "-pdf", "-interaction=nonstopmode", tex.name]}.get(
        name, [exe, "-interaction=nonstopmode", tex.name])
    runs = 1 if name in ("tectonic", "latexmk") else 2  # pdflatex: twice for paracol
    for _ in range(runs):
        r = subprocess.run(cmd, cwd=tex.parent, capture_output=True, text=True)
    pdf = tex.with_suffix(".pdf")
    if r.returncode != 0 or not pdf.exists():
        raise core.JobbotError(f"LaTeX failed on {tex.name}:\n{(r.stdout + r.stderr)[-1500:]}")
    return pdf
