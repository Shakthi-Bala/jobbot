"""Every number in the output appears in the facts it cites. A null metric means no number."""
import sys
import re
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import UNIT_RE, count_noun, numeric_text, diagnostic, claim_lines, cli, core, json_strings, meta, numbers, quantities, tagged_files  # noqa: E402


def source_texts(profile: dict) -> dict[str, str]:
    out = {}
    for f in profile.get("facts", []):
        metrics = {k: v for k, v in (f.get("metrics") or {}).items() if v is not None}
        out[f["id"]] = f.get("text", "") + " " + json_strings(metrics)
    for key in ("education", "experience", "projects"):
        for e in profile.get(key, []) or []:
            excluded = ('facts', 'start', 'end', 'dates')
            scalars = {k: v for k, v in e.items() if k not in excluded}
            out[e["id"]] = json_strings(scalars)
    return out


def source_numbers(profile: dict) -> dict[str, set[float]]:
    return {key: numbers(text) for key, text in source_texts(profile).items()}


TOOLS = ('Python', 'OpenCV', 'CUDA', 'ROS', 'PyTorch', 'TensorFlow', 'TensorRT', 'NumPy', 'Ubuntu', 'C++')


def version_metric_suffix(after: str) -> bool:
    if UNIT_RE.match(after):
        return True
    # In "ROS 2 camera processing", camera modifies an uncountable technical
    # activity. In "ROS 2 cameras" or "ROS 2 robot deployments", it is a count.
    if re.match(r'\s+(?:camera|robot|frame|image|sensor)\s+(?:processing|calibration|perception|mapping|localization|software|firmware|tooling)\b', after, re.I):
        return False
    return bool(count_noun(after))


def documented_versions(profile: dict, sources: list[str]) -> set[tuple[str, str]]:
    labels = set()
    for text in sources + [s.get('skill', '') for s in profile.get('skills', [])]:
        for tool in TOOLS:
            for match in re.finditer(rf'(?<!\w){re.escape(tool)}\s*v?\s*(\d+(?:\.\d+)*)(?!\w|\.\d)', text, re.I):
                after = text[match.end():]
                if not version_metric_suffix(after):
                    labels.add((tool.casefold(), match[1]))
    return labels


def without_versions(text: str, labels: set[tuple[str, str]], *, claim: bool) -> str:
    for tool in TOOLS:
        def replace(match):
            after = text[match.end():]
            measured = version_metric_suffix(after) if claim else UNIT_RE.match(after)
            return '' if (tool.casefold(), match[1]) in labels and not measured else match[0]
        text = re.sub(rf'(?<!\w){re.escape(tool)}\s*v?\s*(\d+(?:\.\d+)*)(?!\w|\.\d)', replace, text, flags=re.I)
    return text


def claim_prose(prose: str, profile: dict, cited: list[str], sources: list[str], project_count: int) -> str:
    """Exclude documented version/date labels, never their trailing quantities."""
    prose = without_versions(prose, documented_versions(profile, sources), claim=True)
    months = ('January February March April May June July August September October November December').split()
    for entry in profile.get('education', []):
        if entry['id'] not in cited:
            continue
        for key in ('start', 'end'):
            value = str(entry.get(key) or '')
            match = re.match(r'^(\d{4})-(\d{2})(?:-|$)', value)
            if not match or not 1 <= int(match[2]) <= 12:
                continue
            month, year = months[int(match[2]) - 1], match[1]
            pattern = rf'\b(?:{month}|{month[:3]}\.?)\s+{year}\b'
            def calendar_label(found):
                after = prose[found.end():]
                return found[0] if UNIT_RE.match(after) or count_noun(after) else ''
            prose = re.sub(pattern, calendar_label, prose, flags=re.I)
            if key == 'end':
                pattern = (rf'\b(?:graduating|graduation|graduate|expected|finishing|completing)'
                           rf'(?:\s+(?:my|the|a|degree|m\.s\.|b\.s\.|in|by|on|of)){{0,5}}\s+{year}\b')
                prose = re.sub(pattern, calendar_label, prose, flags=re.I)
    prose = numeric_text(prose, contextual=True)
    def document_count(match):
        return '' if 0 < int(match[1]) <= project_count else match[0]
    return re.sub(r'\b(\d+) projects? (?:show|illustrate|demonstrate|highlight)\b', document_count, prose, flags=re.I)


def check(d: Path) -> list[str]:
    profile = core.load_profile()
    bank = core.load_answers_bank()
    from agents.tailor import _bank_get
    src = source_texts(profile)
    m = meta(d)
    # Numbers that are part of names, never claims: job title, company, req ID, skill names.
    names = [str(m.get(k) or '') for k in ('company', 'title', 'req_id')]
    names += [s.get('skill', '') for s in profile.get('skills', [])]
    from agents.tailor import dates
    education_headers = {}
    for entry in profile.get('education', []):
        header = f"{entry['degree']}, {entry['school']}, {dates(entry)}"
        if entry.get('gpa'):
            header += f", GPA {entry['gpa']}"
        education_headers[header + f" [{entry['id']}]"] = dates(entry)
    posting = ''
    if m.get('job_id') and core.DB_PATH.exists():
        conn = core.connect()
        try:
            posting = core.get_job(conn, m['job_id'])['raw_text'] or ''
        except core.JobbotError:
            pass  # A detached packet still receives strict numerical checks.
        finally:
            conn.close()
    resume = d / 'resume.json'
    project_count = len(json.loads(resume.read_text()).get('projects', [])) if resume.exists() else len(profile.get('projects', []))
    bad = []
    for path in tagged_files(d):
        claims = list(claim_lines(path))
        # Question labels are visible prose too. An exact posting question is
        # quoted input; invented numerical assertions in a label are not exempt.
        if path.name == 'answers.tagged.md':
            for n, label in enumerate(path.read_text().splitlines(), 1):
                if label.startswith('## Q: '):
                    question = label[len('## Q: '):]
                    if not core.quote_in_text(question, posting):
                        claims.append((n, question))
        for n, line in claims:
            if core.NEED_INPUT_RE.fullmatch(line):
                continue  # a question for you, not a claim
            sources = []
            for t in core.FACT_TAG_RE.findall(line):
                sources.append(src.get(t, ''))
            for k in core.ANSWER_TAG_RE.findall(line):
                sources.append(json_strings(_bank_get(bank, k)))
            if path.name == 'resume.tagged.md' and line in education_headers:
                sources.append(education_headers[line])
            prose = claim_prose(core.strip_tags(line), profile, core.FACT_TAG_RE.findall(line), sources, project_count)
            # A number in a product name permits that name, not an unrelated metric.
            for name in sorted(filter(None, names), key=len, reverse=True):
                def known_name(match):
                    after = prose[match.end():]
                    if quantities(match[0]) or (numbers(match[0]) and version_metric_suffix(after)):
                        return match[0]
                    return ''
                prose = re.sub(rf'(?<!\w){re.escape(name)}(?!\w)', known_name, prose, flags=re.I)
            labels = documented_versions(profile, sources)
            metric_sources = [without_versions(s, labels, claim=False) for s in sources]
            allowed = set().union(*(numbers(s) for s in metric_sources))
            extra = numbers(prose, contextual=True) - allowed
            if extra:
                shown = ", ".join(f"{x:g}" for x in sorted(extra))
                bad.append(diagnostic(f"{path.name}:{n} numbers not in cited facts ({shown})", claim=line[:120]))
            allowed_units = set().union(*(quantities(s) for s in metric_sources))
            unsupported = quantities(prose, contextual=True) - allowed_units
            if unsupported:
                shown = ', '.join(f'{value:g} {unit}' for value, unit in sorted(unsupported))
                bad.append(diagnostic(f"{path.name}:{n} quantities not in cited facts ({shown})", claim=line[:120]))
    return bad


if __name__ == "__main__":
    cli(check, "numbers_match")
