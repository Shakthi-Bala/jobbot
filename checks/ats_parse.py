"""The real PDF, read by pdftotext, contains every section, the contact info and the
job's keywords that the resume uses, in reading order."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, core, db, json_strings, meta, pdf_text  # noqa: E402


def check(d: Path) -> list[str]:
    pdf, data_path = d / "resume.pdf", d / "resume.json"
    if not pdf.exists():
        return ["resume.pdf missing: render failed or never ran"]
    data = json.loads(data_path.read_text())
    raw = pdf_text(pdf)
    text = core.normalize(raw)
    bad = []
    for leak in ("=>", "#let", "#for", ".filter(", ".join(", "d.person"):
        if leak in raw:
            bad.append(f"template code leaked into the PDF: {leak!r}")

    order = data.get("sections") or ["education", "experience", "projects", "skills"]
    sections = [s for s in order if data.get(s)]
    positions = []
    for s in sections:
        # A heading is a line of its own ("SKILLS"), not the word inside a bullet.
        heading = data.get("section_headings", {}).get(s, s)
        pattern = r"[ \t]+".join(re.escape(word) for word in heading.split())
        m = re.search(rf"^[ \t]*{pattern}[ \t]*$", raw, re.I | re.M)
        pos = m.start() if m else -1
        if pos < 0:
            bad.append(f"section header missing in parsed PDF: {s}")
        positions.append(pos)
    found = [p for p in positions if p >= 0]
    if found != sorted(found):
        bad.append(f"sections out of reading order: {sections}")

    person = data["person"]
    for field in ("name", "email"):
        if person.get(field) and core.normalize(person[field]) not in text:
            bad.append(f"{field} not found in parsed PDF: {person[field]}")

    job = db().execute("SELECT parsed_json FROM jobs WHERE id=?", (meta(d).get("job_id"),)).fetchone()
    keywords = json.loads((job and job["parsed_json"]) or "{}").get("keywords", [])[:15]
    source = core.normalize(json_strings(data))
    for kw in keywords:
        k = core.normalize(kw)
        if k and k in source and k not in text:
            bad.append(f"keyword lost in rendering: {kw}")
    return bad


if __name__ == "__main__":
    cli(check, "ats_parse")
