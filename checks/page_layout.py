"""The rendered page looks like the approved one: the LaTeX build (not the Typst
fallback), and a one-page resume that actually uses its page.

A resume that stops two thirds of the way down reads as thin; one that needs smaller
type to fit was over-written. Both are content problems, so the message tells the
writer roughly how many lines to add. The limit is preferences.resume_max_bottom_blank_in
(inches of empty page above the bottom edge, margin included); unset = not checked.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, core, meta, pdf_pages  # noqa: E402

LINE_PT = 13.6          # one 11 pt body line
BOTTOM_MARGIN_IN = 0.71  # templates/resume.tex.j2 uses 1.8 cm


def bottom_blank_in(pdf: Path) -> float:
    """Inches between the lowest text baseline on the last page and the page bottom."""
    from pypdf import PdfReader
    ys = []

    def visitor(text, cm, tm, font, size):
        if text.strip():
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            if y > 0:
                ys.append(y)

    PdfReader(str(pdf)).pages[-1].extract_text(visitor_text=visitor)
    if not ys:
        raise ValueError("no text positions found on the page")
    return round(min(ys) / 72, 2)


def check(d: Path) -> list[str]:
    info, bad = meta(d), []
    if info.get("format") == "latex" and (d / "LATEX_NOTE.md").exists():
        bad.append("resume.pdf is the Typst fallback, not the LaTeX layout: no LaTeX engine was "
                   "found. Install tectonic (~/.local/bin/tectonic) and rebuild")
    if info.get("format") == "latex" and (d / "cover_letter.typ").exists():
        bad.append("cover_letter.pdf is the Typst fallback; it will not match the resume's typeface")
    pdf = d / "resume.pdf"
    limit = core.load_profile().get("preferences", {}).get("resume_max_bottom_blank_in")
    if limit is None or not pdf.exists() or int(info.get("pages") or 1) != 1 or pdf_pages(pdf) != 1:
        return bad
    blank = bottom_blank_in(pdf)
    if blank > float(limit):
        lines = max(1, int((blank - BOTTOM_MARGIN_IN) * 72 // LINE_PT))
        bad.append(f"resume leaves {blank:.2f} in empty at the bottom of the page (limit {float(limit):g}): "
                   f"about {lines} more line(s) fit. Add supported detail to the most relevant "
                   "entries or one more relevant project; do not pad, enlarge type or add a summary")
    return bad


if __name__ == "__main__":
    cli(check, "page_layout")
