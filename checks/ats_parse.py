"""The real PDF, read by pdftotext, contains every section, the contact info and the
job's keywords that the resume uses, in reading order."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, core, db, json_strings, meta, pdf_text  # noqa: E402


def check(d: Path) -> list[str]:
    pdf, data_path = d / "resume.pdf", d / "resume.json"
    if not pdf.exists():
        return ["resume.pdf missing: render failed or never ran"]
    data = json.loads(data_path.read_text())
    text = core.normalize(pdf_text(pdf))
    bad = []

    sections = [s for s in ("education", "experience", "projects", "skills") if data.get(s)]
    positions = []
    for s in sections:
        pos = text.find(s)
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
