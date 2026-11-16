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

NUMBER_RE = re.compile(r"(?<![\w.])(?:\d[\d,]*(?:\.\d+)?|\.\d+)")
MULTIPLIERS = {"doubled": 2, "doubling": 2, "twofold": 2, "tripled": 3,
               "tripling": 3, "threefold": 3, "quadrupled": 4, "fourfold": 4,
               "halved": 0.5, "halving": 0.5}
UNIT_RE = re.compile(
    r"\s*(%|percent\b|percentage points?\b|fps\b|frames? per second\b|"
    r"ms\b|milliseconds?\b|[µμu]s\b|microseconds?\b|s\b|seconds?\b|"
    r"mins?\b|minutes?\b|hrs?\b|hours?\b|days?\b|weeks?\b|months?\b|years?\b|"
    r"khz\b|mhz\b|ghz\b|hz\b|kb\b|mb\b|gb\b|tb\b|"
    r"m/s\b|km/h\b|mm\b|cm\b|meters?\b|km\b|m\b|kg\b|g\b|"
    r"pixels?\b|px\b|db\b|degrees?\b|°|watts?\b|kw\b|w\b|"
    r"times\b|x\b|×)", re.I)
UNIT_ALIASES = {'percent': '%', 'frame per second': 'fps', 'frames per second': 'fps',
                'millisecond': 'ms', 'microsecond': 'us', 'µs': 'us', 'μs': 'us',
                'second': 's', 'min': 'minute', 'hr': 'hour', 'meter': 'm',
                'pixel': 'px', 'degree': '°', 'watt': 'w',
                'x': 'factor', '×': 'factor', 'times': 'factor', 'time': 'factor'}


def quantities(text: str) -> set[tuple[float, str]]:
    """Measured numbers keep their units; multiplicative prose is a claim too."""
    out = set()
    for match in NUMBER_RE.finditer(text or ''):
        unit = UNIT_RE.match(text, match.end())
        if unit:
            name = unit[1].lower()
            name = name[:-1] if name.endswith('s') and name not in ('ms', 'us', 's', 'fps') else name
            out.add((float(match[0].replace(',', '')), UNIT_ALIASES.get(name, name)))
    for word, value in MULTIPLIERS.items():
        if re.search(rf'\b{word}\b', text or '', re.I):
            out.add((value, 'factor'))
    return out


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
    # Dimensional labels name a technical domain, not a measured result.
    # Keep quantities such as 45 FPS or 2 days subject to numerical provenance.
    text = re.sub(r"\b[234][dD]\b", "", text or "")
    for m in NUMBER_RE.findall(text):
        try:
            out.add(float(m.replace(",", "")))
        except ValueError:
            pass
    out.update(value for value, unit in quantities(text) if unit == 'factor')
    return out


def pdf_text(pdf: Path) -> str:
    try:
        return subprocess.run(["pdftotext", "-layout", str(pdf), "-"], check=True,
                              capture_output=True, text=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        from pypdf import PdfReader
        # Layout extraction avoids spurious spaces from kerning ("PyT orch") and
        # follows the same convention as pdftotext -layout above.
        return "\n".join(p.extract_text(extraction_mode="layout") or ""
                         for p in PdfReader(str(pdf)).pages)


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
