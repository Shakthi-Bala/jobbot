"""Every number in the output appears in the facts it cites. A null metric means no number."""
import sys
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import claim_lines, cli, core, json_strings, meta, numbers, quantities, tagged_files  # noqa: E402


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
            prose = core.strip_tags(line)
            # A number in a product name permits that name, not an unrelated metric.
            for name in sorted(filter(None, names), key=len, reverse=True):
                prose = re.sub(rf'(?<!\w){re.escape(name)}(?!\w)', '', prose, flags=re.I)
            allowed = set().union(*(numbers(s) for s in sources))
            extra = numbers(prose) - allowed
            if extra:
                shown = ", ".join(f"{x:g}" for x in sorted(extra))
                bad.append(f"{path.name}:{n} numbers not in cited facts ({shown}): {line[:120]}")
            allowed_units = set().union(*(quantities(s) for s in sources))
            unsupported = quantities(prose) - allowed_units
            if unsupported:
                shown = ', '.join(f'{value:g} {unit}' for value, unit in sorted(unsupported))
                bad.append(f"{path.name}:{n} quantities not in cited facts ({shown}): {line[:120]}")
    return bad


if __name__ == "__main__":
    cli(check, "numbers_match")
