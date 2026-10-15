"""ATS keyword scoring, as code (no AI).

Each posting keyword lands in one of three buckets:
  in_resume        the rendered PDF contains it (what an ATS matches on)
  fixable          your profile proves it, but the resume doesn't say it -> add it
  gap              nothing in your profile backs it -> a real gap, never claimed

score     = in_resume / total            (what this resume scores now)
max_score = (in_resume + fixable) / total (the honest ceiling with your evidence)
"""
from __future__ import annotations

import json
import re

from . import core

# Spelling variants an ATS (or a recruiter's search) treats as the same thing.
SYNONYMS = {
    "sim to real": ["sim2real", "sim-to-real", "simulation to real"],
    "reinforcement learning": ["rl"],
    "isaac lab": ["isaaclab", "isaac sim"],
    "ros 2": ["ros2"],
    "computer vision": ["cv"],
    "machine learning": ["ml"],
    "3d vision": ["3d perception", "depth estimation"],
}


def _norm(text: str) -> str:
    return " " + core.normalize(text) + " "


def mentions(keyword: str, text: str) -> bool:
    """Whole-word, punctuation-insensitive match, with symbol-safe handling of C++/C#."""
    kw = keyword.strip()
    if not kw:
        return False
    if re.search(r"[+#]", kw):  # "C++" would normalize to "c" and match everything
        return re.search(rf"(?<![\w+#]){re.escape(kw.lower())}(?![\w+#])", text.lower()) is not None
    hay, hay_compact = _norm(text), _norm(text).replace(" ", "")
    for variant in [kw] + SYNONYMS.get(core.normalize(kw), []):
        v = core.normalize(variant)
        if v and (f" {v} " in hay or (len(v) > 4 and v.replace(" ", "") in hay_compact)):
            return True
    return False


def profile_text(profile: dict) -> str:
    parts = [f.get("text", "") for f in profile.get("facts", [])]
    parts += [s["skill"] for s in profile.get("skills", []) if s.get("evidence")]
    for e in profile.get("education", []):
        parts += [e.get("degree", ""), json.dumps(e.get("thesis", {})), " ".join(e.get("coursework", []))]
    for e in profile.get("experience", []) + profile.get("projects", []):
        parts.append(e.get("title") or e.get("name") or "")
    return "\n".join(parts)


def posting_keywords(job) -> list[str]:
    parsed = json.loads(job["parsed_json"] or "{}")
    seen, out = set(), []
    for k in parsed.get("keywords", []):
        n = core.normalize(k)
        if n and n not in seen:
            seen.add(n)
            out.append(k)
    return out


def classify(keywords: list[str], profile: dict, resume_text: str | None) -> dict:
    ptext = profile_text(profile)
    buckets = {"in_resume": [], "fixable": [], "gap": []}
    for k in keywords:
        if resume_text is not None and mentions(k, resume_text):
            buckets["in_resume"].append(k)
        elif mentions(k, ptext):
            buckets["fixable"].append(k)
        else:
            buckets["gap"].append(k)
    total = max(1, len(keywords))
    buckets["score"] = round(100 * len(buckets["in_resume"]) / total)
    buckets["max_score"] = round(100 * (len(buckets["in_resume"]) + len(buckets["fixable"])) / total)
    buckets["total"] = len(keywords)
    return buckets


def score_packet(conn, job_id: str, d) -> dict:
    """Score the rendered resume PDF in packet folder d; writes d/ats.json."""
    import sys
    sys.path.insert(0, str(core.ROOT))
    from checks._lib import pdf_text
    job = core.get_job(conn, job_id)
    text = pdf_text(d / "resume.pdf") if (d / "resume.pdf").exists() else ""
    result = classify(posting_keywords(job), core.load_profile(), text)
    (d / "ats.json").write_text(core.dumps(result))
    return result
