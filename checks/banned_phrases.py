"""No phrase from preferences.banned_phrases in anything you would send."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, core, diagnostic, rendered_texts  # noqa: E402


def check(d: Path) -> list[str]:
    banned = core.load_profile().get("preferences", {}).get("banned_phrases", [])
    bad = []
    for name, text in rendered_texts(d).items():
        for phrase in banned:
            for m in re.finditer(rf"\b{re.escape(phrase)}\w*", text, re.I):
                ctx = text[max(0, m.start() - 40): m.end() + 40].replace("\n", " ")
                bad.append(diagnostic('banned phrase in document', document=name, phrase=m.group(0), excerpt=ctx))
    return bad


if __name__ == "__main__":
    cli(check, "banned_phrases")
