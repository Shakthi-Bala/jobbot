"""Helpers shared by the check scripts."""
from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents import core  # noqa: E402

NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def meta(d: Path) -> dict:
    p = d / "meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


def tagged_files(d: Path) -> list[Path]:
    return sorted(d.glob("*.tagged.md")) + sorted(d.glob("outreach/*.tagged.md"))


def rendered_texts(d: Path) -> dict[str, str]:
    """The human-facing text of every document in the packet."""
    out = {}
    if (d / "resume.json").exists():
        out["resume"] = json_strings(json.loads((d / "resume.json").read_text()))
    for name in ("cover_letter.md", "answers.md"):
        if (d / name).exists():
            out[name] = (d / name).read_text()
    for p in sorted(d.glob("outreach/*.md")):
        if not p.name.endswith(".tagged.md"):
            out[f"outreach/{p.name}"] = p.read_text()
    return out


def json_strings(node) -> str:
    if isinstance(node, dict):
        return "\n".join(json_strings(v) for v in node.values())
    if isinstance(node, list):
        return "\n".join(json_strings(v) for v in node)
    return str(node) if node is not None else ""


def claim_lines(path: Path):
    """(line_no, line) for every line that makes a claim. Headings ('#'),
    template markers ('=') and non-claim lines ('//') are skipped."""
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if s and not s.startswith(("#", "=", "//")):
            yield i, s


def numbers(text: str) -> set[float]:
    out = set()
    for m in NUMBER_RE.findall(text or ""):
        try:
            out.add(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def pdf_text(pdf: Path) -> str:
    try:
        return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                              capture_output=True, text=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)


def pdf_pages(pdf: Path) -> int:
    from pypdf import PdfReader
    return len(PdfReader(str(pdf)).pages)


def db() -> sqlite3.Connection:
    return core.connect()


def cli(check: Callable[[Path], list[str]], name: str) -> None:
    if len(sys.argv) != 2:
        print(f"usage: python checks/{name}.py out/<Company>_<Role>")
        sys.exit(2)
    problems = check(Path(sys.argv[1]))
    if problems:
        print(f"FAIL {name}:\n" + "\n".join(f"  - {p}" for p in problems))
        sys.exit(1)
    print(f"ok   {name}")
