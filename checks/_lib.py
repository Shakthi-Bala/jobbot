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

NUMBER_RE = re.compile(r"(?<![\w.])(?:(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d+)?|\.\d+)")
# Cardinal words use the same representation in sources and generated prose.
# Match valid compounds rather than adding unrelated adjacent words ("one two").
_SMALL = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_WORD_VALUES = {word: n for n, word in enumerate(_SMALL)}
_WORD_VALUES.update({word: 20 + 10 * n for n, word in enumerate(_TENS)})
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1000000, "billion": 1000000000}
_WORD_SEP = r"[\s\-‐‑–]+"
_units = "(?:" + "|".join(_SMALL[1:10]) + ")"
_under100 = ("(?:" + "|".join(_TENS) + ")" + rf"(?:{_WORD_SEP}{_units})?"
             + "|(?:" + "|".join(_SMALL) + ")")
_group = rf"(?:(?:{_units}|a){_WORD_SEP}hundred(?:{_WORD_SEP}(?:and{_WORD_SEP})?(?:{_under100}))?|{_under100})"
_word_number = _group
for _scale in ("thousand", "million", "billion"):
    _word_number = rf"(?:{_group}{_WORD_SEP}{_scale}(?:{_WORD_SEP}(?:and{_WORD_SEP})?{_word_number})?|{_word_number})"
_digit_words = "(?:" + "|".join(_SMALL[:10]) + ")"
_fraction = rf"point{_WORD_SEP}{_digit_words}(?:{_WORD_SEP}{_digit_words})*"
_WORD_NUMBER_RE = re.compile(
    rf"(?<!\w)(?:{_word_number}(?:{_WORD_SEP}{_fraction})?|{_fraction})(?!\w)", re.I)


_NUMBER_IDIOMS_RE = re.compile(
    r"\b(?:one\s+of|no\s+one(?:\s+else)?|(?:one|zero)[-‐‑– ](?:hot|shot)|zero[-‐‑– ]copy|one\s+at\s+a\s+time|one[-‐‑– ]stage)\b", re.I)


_MAGNITUDES = {'k': 1000, 'thousand': 1000, 'm': 1000000, 'million': 1000000,
               'b': 1000000000, 'billion': 1000000000, 'dozen': 12}
_MAGNITUDE_RE = re.compile(rf"({NUMBER_RE.pattern})[ \t]*(k|K|M|B|thousand|million|billion|dozen)\b")


def leading_count(text: str) -> str | None:
    if re.search(r'\b(?:mentored|supervised|managed|coached|hired)\s*$', text, re.I):
        return 'person'
    if re.search(r'\b(?:team|group|cohort)(?:\s+size)?\s+(?:of|was|is|included|totaled)\s*$', text, re.I):
        return 'person'
    return None


_ORDINALS = dict(zip('first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth'.split(), range(1, 21)))
_ORDINAL_RE = re.compile(r'\b(' + '|'.join(_ORDINALS) + rf')\b(?={_WORD_SEP}(?:place|prize|rank|position|finish|among)\b)', re.I)


def numeric_text(text: str, *, contextual: bool = False) -> str:
    """Normalize English cardinal numbers, including hyphenated compounds."""
    def convert(match):
        total = group = 0
        tokens = re.split(_WORD_SEP, match[0].lower())
        decimal = ''
        if 'point' in tokens:
            index = tokens.index('point')
            decimal = '.' + ''.join(str(_WORD_VALUES[w]) for w in tokens[index + 1:])
            tokens = tokens[:index]
        for word in tokens:
            if word == 'and':
                continue
            if word == 'hundred':
                group *= 100
            elif word in _SCALES:
                total += group * _SCALES[word]
                group = 0
            else:
                group += 1 if word == 'a' else _WORD_VALUES[word]
        if contextual:
            remainder = text[match.end():]
            prefix = text[:match.start()]
            unit = UNIT_RE.match(remainder)
            # Small words can be idiomatic; larger cardinals remain numerical
            # claims even when their count noun is omitted (e.g. a leaderboard).
            distributive = match[0].lower() == 'one' and re.match(
                r'(?:\s+[A-Za-z-]+){1,3}\s+per\b', remainder, re.I) and not unit
            if distributive or not (total + group >= 20 or decimal or unit or count_noun(remainder)
                    or leading_count(prefix) or re.search(r'\btop[\s\-‐‑–]*$', prefix, re.I)
                    or re.match(r'\s+dozen\b', remainder, re.I)):
                return match[0]
        return str(total + group) + decimal
    text = _NUMBER_IDIOMS_RE.sub(' ', text or '')
    text = re.sub(rf'\bdegrees?{_WORD_SEP}of{_WORD_SEP}freedom\b', 'DOF', text, flags=re.I)
    # A half-dozen is six, before the generic "a dozen" expansion runs.
    text = re.sub(rf'\bhalf{_WORD_SEP}(?:(?:of{_WORD_SEP})?a{_WORD_SEP})?dozen\b', '6', text, flags=re.I)
    # Ordinal digits and words share rank evidence in the same contexts.
    text = re.sub(r'\b(placed|ranked|finished|came)\s+(\d+)(?:st|nd|rd|th)\b',
                  r'\1 \2 rank', text, flags=re.I)
    text = re.sub(r'\b(\d+)(?:st|nd|rd|th)(?=\s+of\s+\d)', r'\1 rank', text, flags=re.I)
    text = re.sub(r'\b(' + '|'.join(_ORDINALS) + r')(?=\s+of\s+\d)',
                  lambda m: str(_ORDINALS[m[1].lower()]) + ' rank', text, flags=re.I)
    text = re.sub(r'\b(placed|ranked|finished|came)\s+(' + '|'.join(_ORDINALS) + r')\b',
                  lambda m: m[1] + ' ' + str(_ORDINALS[m[2].lower()]) + ' rank', text, flags=re.I)
    text = _ORDINAL_RE.sub(lambda m: str(_ORDINALS[m[1].lower()]), text)
    text = re.sub(rf'\b(\d+)(?:st|nd|rd|th)(?={_WORD_SEP}(?:place|prize|rank|position|finish|among)\b)', r'\1', text, flags=re.I)
    text = re.sub(r'\ba dozen\b', '12', text, flags=re.I)
    text = _WORD_NUMBER_RE.sub(convert, text)
    text = re.sub(r'\btop[\s\-‐‑–]+(\d+)\b(?![\d.]|\s*(?:%|percent\b))', r'\1 rank', text, flags=re.I)
    text = re.sub(r'\b(\d+)(?=\s+among\b)', r'\1 rank', text, flags=re.I)
    # Lowercase m is metres unless attached to an explicit currency amount.
    text = re.sub(r'([$£€]\s*\d+(?:\.\d+)?)m\b', r'\1M', text)
    return _MAGNITUDE_RE.sub(
        lambda m: format(float(m[1].replace(',', '')) * _MAGNITUDES[m[2].lower()], '.15g'), text)


MULTIPLIERS = {"doubled": 2, "doubling": 2, "twofold": 2, "tripled": 3,
               "tripling": 3, "threefold": 3, "quadrupled": 4, "fourfold": 4,
               "halved": 0.5, "halving": 0.5, "twice": 2, "thrice": 3,
               "fivefold": 5, "sixfold": 6, "sevenfold": 7, "eightfold": 8,
               "ninefold": 9, "tenfold": 10}
UNIT_RE = re.compile(
    r"[\s\-‐‑–]*(place\b|prize\b|rank\b|position\b|finish\b|dof\b|%|percent\b|percentage[\s\-‐‑–]+points?\b|fps\b|frames?[\s\-‐‑–]+per[\s\-‐‑–]+second\b|"
    r"ms\b|milliseconds?\b|[µμu]s\b|microseconds?\b|s\b|seconds?\b|"
    r"mins?\b|minutes?\b|hrs?\b|hours?\b|days?\b|weeks?\b|months?\b|years?\b|"
    r"khz\b|mhz\b|ghz\b|hz\b|hertz\b|kb\b|mb\b|gb\b|tb\b|"
    r"m/s\b|km/h\b|mm\b|cm\b|meters?\b|km\b|m\b|kg\b|g\b|"
    r"pixels?\b|px\b|db\b|degrees?\b|°|watts?\b|kw\b|w\b|"
    r"times\b|x\b|×)", re.I)
UNIT_ALIASES = {'place': 'rank', 'prize': 'rank', 'position': 'rank', 'finish': 'rank', 'hertz': 'hz', 'percent': '%', 'frame per second': 'fps', 'frames per second': 'fps',
                'millisecond': 'ms', 'microsecond': 'us', 'µs': 'us', 'μs': 'us',
                'second': 's', 'min': 'minute', 'hr': 'hour', 'meter': 'm',
                'pixel': 'px', 'degree': '°', 'watt': 'w',
                'x': 'factor', '×': 'factor', 'times': 'factor', 'time': 'factor'}


def count_noun(remainder: str) -> str | None:
    phrase = re.match(r'[\s\-‐‑–]*([A-Za-z]+(?:[\s\-]+[A-Za-z]+){0,2})', remainder)
    if not phrase:
        return None
    for word in re.split(r'[\s\-]+', phrase[1].lower()):
        if word in {'at', 'on', 'in', 'of', 'to', 'and', 'or', 'with', 'from', 'per', 'by', 'for', 'across', 'over'}:
            break
        if (word.endswith('s') and word not in {'as', 'is', 'was', 'this', 'has'}) or word in {
                'site', 'customer', 'scene', 'frame', 'user', 'engineer', 'attempt', 'sequence',
                'image', 'sample', 'camera', 'robot', 'object', 'trial', 'target', 'project', 'case'}:
            return word[:-3] + 'y' if word.endswith('ies') else word.removesuffix('s')
    return None


def quantities(text: str, *, contextual: bool = False) -> set[tuple[float, str]]:
    """Measured numbers keep their units; multiplicative prose is a claim too."""
    text = numeric_text(text, contextual=contextual)
    out = set()
    for match in NUMBER_RE.finditer(text):
        currency = re.search(r'([$£€])\s*$', text[:match.start()])
        if currency:
            out.add((float(match[0].replace(',', '')), {'$': 'usd', '£': 'gbp', '€': 'eur'}[currency[1]]))
            continue
        unit = UNIT_RE.match(text, match.end())
        if unit:
            name = re.sub(r'[\s\-‐‑–]+', ' ', unit[1].lower())
            name = name[:-1] if name.endswith('s') and name not in ('ms', 'us', 's', 'fps') else name
            out.add((float(match[0].replace(',', '')), UNIT_ALIASES.get(name, name)))
        else:
            # Preserve count nouns as well as physical units. Modifiers may vary
            # ("synthetic warehouse scenes" vs "scenes"); the counted noun must agree.
            noun = count_noun(text[match.end():]) or leading_count(text[:match.start()])
            if noun:
                out.add((float(match[0].replace(',', '')), 'count:' + noun))
    for word, value in MULTIPLIERS.items():
        if re.search(rf'\b{word}\b', text or '', re.I):
            out.add((value, 'factor'))
    for word, value in [('dozens', 12), ('hundreds', 100), ('thousands', 1000), ('millions', 1000000)]:
        if re.search(rf'\b{word} of\b', text, re.I):
            out.add((value, 'approximate count'))
    if re.search(r'\bby half\b', text, re.I):
        out.add((0.5, 'factor'))
    if re.search(r'\b(?:an? )?order of magnitude\b', text, re.I):
        out.add((10, 'factor'))
    return out


def diagnostic(message: str, **evidence) -> str:
    """Keep a code-owned instruction separate from all reflected source data."""
    return message + '\n' + core.untrusted('diagnostic_evidence', core.dumps(evidence))


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


def numbers(text: str, *, contextual: bool = False) -> set[float]:
    out = set()
    # Dimensional labels name a technical domain, not a measured result.
    # Keep quantities such as 45 FPS or 2 days subject to numerical provenance.
    text = re.sub(r"\b[234][dD]\b", "", numeric_text(text, contextual=contextual))
    for m in NUMBER_RE.findall(text):
        try:
            out.add(float(m.replace(",", "")))
        except ValueError:
            pass
    out.update(value for value, unit in quantities(text, contextual=contextual) if unit in ('factor', 'approximate count'))
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
