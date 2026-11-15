"""Resume page count and cover letter / outreach word counts are within limits."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, core, pdf_pages  # noqa: E402


def words(text: str) -> int:
    return len(text.split())


def outreach_body(text: str) -> str:
    """Drop the 'Subject:' line; the limit applies to the message body."""
    return "\n".join(l for l in text.splitlines() if not l.lower().startswith("subject:"))


def check(d: Path) -> list[str]:
    prefs = core.load_profile().get("preferences", {})
    bad = []
    pdf = d / "resume.pdf"
    if pdf.exists():
        meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
        limit = meta.get("pages") or prefs.get("resume_pages", 1)
        limit = 1 if str(limit) == "auto" else int(limit)
        pages = pdf_pages(pdf)
        if pages > limit:
            from pypdf import PdfReader
            spill = sum(1 for page in PdfReader(str(pdf)).pages[limit:]
                        for line in (page.extract_text() or "").splitlines() if line.strip())
            bad.append(f"resume is {pages} pages; limit {limit}. About {spill} line(s) spill past "
                       f"page {limit}: cut at least that many rendered lines (shorten two-line "
                       "bullets to one, drop the weakest bullet or a skills row); keep type size")
    cl = d / "cover_letter.md"
    if cl.exists():
        n, limit = words(cl.read_text()), prefs.get("cover_letter_max_words", 300)
        if n > limit:
            bad.append(f"cover letter is {n} words; limit {limit}")
        floor = int(prefs.get("cover_letter_min_words", 0))
        if n < floor:
            bad.append(f"cover letter is {n} words; a letter under {floor} reads as a form note. "
                       "Add a supported, posting-specific paragraph")
        letter_pdf = d / "cover_letter.pdf"
        if letter_pdf.exists() and pdf_pages(letter_pdf) > 1:
            bad.append(f"cover letter is {pdf_pages(letter_pdf)} pages; limit 1")
    limit = prefs.get("outreach_max_words", 120)
    for p in sorted(d.glob("outreach/*.md")):
        if p.name.endswith(".tagged.md"):
            continue
        n = words(outreach_body(p.read_text()))
        if n > limit:
            bad.append(f"outreach/{p.name} is {n} words; limit {limit}")
    return bad


if __name__ == "__main__":
    cli(check, "length_limits")
