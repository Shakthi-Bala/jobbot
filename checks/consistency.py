"""Names, dates, titles and the target company agree across resume, letter and answers."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, core, json_strings, meta, rendered_texts  # noqa: E402

YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")


def check(d: Path) -> list[str]:
    profile = core.load_profile()
    person = profile.get("person", {})
    m = meta(d)
    bad = []
    if (d / "resume.json").exists():
        r = json.loads((d / "resume.json").read_text())
        for k in ("name", "email", "phone"):
            if (r["person"].get(k) or "") != (person.get(k) or ""):
                bad.append(f"resume {k} {r['person'].get(k)!r} != profile {person.get(k)!r}")
    if (d / "cover_letter.json").exists():
        c = json.loads((d / "cover_letter.json").read_text())
        for k in ("company", "title"):
            if c.get(k) != m.get(k):
                bad.append(f"cover letter {k} {c.get(k)!r} != job {m.get(k)!r}")
        if c["person"].get("name") != person.get("name"):
            bad.append("cover letter signature name differs from profile")

    # Any year mentioned in prose must exist somewhere in the profile or bank.
    known_years = set(YEAR_RE.findall(json_strings(profile) + json_strings(core.load_answers_bank())))
    for name, text in rendered_texts(d).items():
        if name == "resume":
            continue
        for y in sorted(set(YEAR_RE.findall(text)) - known_years):
            bad.append(f"{name} mentions year {y}, which is not in your profile")

    # A different job title for this role should not appear in the letter.
    letter = rendered_texts(d).get("cover_letter.md", "")
    for t in profile.get("targets", {}).get("titles", []):
        if t.lower() != (m.get("title") or "").lower() and t.lower() in letter.lower() \
                and t.lower() not in (m.get("title") or "").lower():
            bad.append(f"cover letter names a different role title: {t!r}")
    return bad


if __name__ == "__main__":
    cli(check, "consistency")
