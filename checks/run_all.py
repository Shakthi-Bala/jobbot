"""Run every check on a packet. Writes checks.json; exits 1 if any check fails.

    python checks/run_all.py out/<Company>_<Role> [--outreach] [--offline]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks import (ats_parse, banned_phrases, consistency, contact_sources,  # noqa: E402
                    fact_ids, injection_scan, length_limits, numbers_match, page_layout,
                    req_match, restriction_quotes, required_content)

PACKET = {
    "required_content": required_content.check,
    "fact_ids": fact_ids.check,
    "numbers_match": numbers_match.check,
    "restriction_quotes": restriction_quotes.check,
    "req_match": req_match.check,
    "ats_parse": ats_parse.check,
    "banned_phrases": banned_phrases.check,
    "length_limits": length_limits.check,
    "page_layout": page_layout.check,
    "consistency": consistency.check,
    "injection_scan": injection_scan.check,
}
OUTREACH = {
    "fact_ids": fact_ids.check,
    "numbers_match": numbers_match.check,
    "banned_phrases": banned_phrases.check,
    "length_limits": length_limits.check,
    "contact_sources": contact_sources.check,
}


def run(d: Path, outreach: bool = False, offline: bool = False) -> dict[str, list[str]]:
    suite = dict(OUTREACH if outreach else PACKET)
    if offline:
        if "req_match" in suite:
            suite["req_match"] = lambda p: req_match.check(p, live=False)
        suite.pop("contact_sources", None)
    results = {}
    for name, fn in suite.items():
        try:
            results[name] = fn(d)
        except Exception as e:  # a crashing check is a failing check
            results[name] = [f"check crashed: {type(e).__name__}: {e}"]
    out = d / ("outreach/checks.json" if outreach else "checks.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    return results


def failures(results: dict[str, list[str]]) -> list[str]:
    return [f"[{name}] {p}" for name, probs in results.items() for p in probs]


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        sys.exit(2)
    results = run(Path(args[0]), "--outreach" in sys.argv, "--offline" in sys.argv)
    for name, probs in results.items():
        print(f"{'ok  ' if not probs else 'FAIL'} {name}")
        for p in probs:
            print(f"     - {p}")
    sys.exit(1 if failures(results) else 0)


if __name__ == "__main__":
    main()
