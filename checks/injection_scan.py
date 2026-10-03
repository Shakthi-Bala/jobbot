"""Flags posting text that addresses an AI ("ignore previous instructions", hidden
white text) and generated documents that echo such text."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, db, meta, rendered_texts  # noqa: E402

PATTERNS = [
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) (?:instructions|prompts?)",
    r"disregard (?:all |any )?(?:the )?(?:previous|prior|above) ",
    r"\bif you are an? (?:ai|llm|language model|bot|assistant)\b",
    r"\b(?:ai|llm|chatgpt|claude|gpt)[- ]?(?:generated )?(?:applicants?|assistants?|models?),? (?:must|should|please)\b",
    r"\bsystem prompt\b",
    r"\byou are (?:now )?(?:an? )?(?:ai|chatgpt|large language model|assistant)\b",
    r"\binclude the (?:word|phrase|code)\b",
    r"\bnew instructions\b",
]
PATTERN_RE = re.compile("|".join(PATTERNS), re.I)


def scan(text: str) -> list[str]:
    return [m.group(0) for m in PATTERN_RE.finditer(text or "")]


def check(d: Path) -> list[str]:
    job_id = meta(d).get("job_id")
    bad = []
    job = db().execute("SELECT raw_text, parsed_json FROM jobs WHERE id=?", (job_id,)).fetchone()
    if job:
        bad += [f"posting addresses an AI: \"{h}\"" for h in scan(job["raw_text"])]
        flags = json.loads(job["parsed_json"] or "{}").get("injection_flags", [])
        bad += [f"posting flag: {f}" for f in flags]
    for name, text in rendered_texts(d).items():
        bad += [f"{name} echoes injection text: \"{h}\"" for h in scan(text)]
    return bad


if __name__ == "__main__":
    cli(check, "injection_scan")
