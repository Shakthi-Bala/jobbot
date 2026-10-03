"""Every number in the output appears in the facts it cites. A null metric means no number."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import claim_lines, cli, core, json_strings, meta, numbers, tagged_files  # noqa: E402


def source_numbers(profile: dict) -> dict[str, set[float]]:
    out = {}
    for f in profile.get("facts", []):
        metrics = {k: v for k, v in (f.get("metrics") or {}).items() if v is not None}
        out[f["id"]] = numbers(f.get("text", "") + " " + json_strings(metrics))
    for key in ("education", "experience", "projects"):
        for e in profile.get(key, []) or []:
            scalars = {k: v for k, v in e.items() if k not in ("facts",)}
            out[e["id"]] = numbers(json_strings(scalars))
    return out


def check(d: Path) -> list[str]:
    profile = core.load_profile()
    bank = core.load_answers_bank()
    from agents.tailor import _bank_get
    src = source_numbers(profile)
    m = meta(d)
    # Numbers that are part of names, never claims: job title, company, req ID, skill names.
    always_ok = numbers(" ".join(str(m.get(k, "")) for k in ("company", "title", "req_id")))
    always_ok |= numbers(" ".join(s.get("skill", "") for s in profile.get("skills", [])))
    bad = []
    for path in tagged_files(d):
        for n, line in claim_lines(path):
            allowed = set(always_ok)
            for t in core.FACT_TAG_RE.findall(line):
                allowed |= src.get(t, set())
            for k in core.ANSWER_TAG_RE.findall(line):
                allowed |= numbers(json_strings(_bank_get(bank, k)))
            extra = numbers(core.strip_tags(line)) - allowed
            if extra:
                shown = ", ".join(f"{x:g}" for x in sorted(extra))
                bad.append(f"{path.name}:{n} numbers not in cited facts ({shown}): {line[:120]}")
    return bad


if __name__ == "__main__":
    cli(check, "numbers_match")
