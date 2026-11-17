"""Every claim line has a valid [Fxxx]/[Exxx]/[Xxxx]/[Pxxx] or [A:key] tag."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import claim_lines, cli, core, diagnostic, tagged_files  # noqa: E402


def check(d: Path) -> list[str]:
    profile = core.load_profile()
    ids = core.profile_ids(profile)
    bank = core.load_answers_bank()
    from agents.tailor import _bank_get
    bad = []
    for path in tagged_files(d):
        for n, line in claim_lines(path):
            if core.NEED_INPUT_RE.fullmatch(line):
                continue
            fact_tags = core.FACT_TAG_RE.findall(line)
            answer_tags = core.ANSWER_TAG_RE.findall(line)
            if not fact_tags and not answer_tags:
                bad.append(diagnostic(f"{path.name}:{n} uncited", claim=line[:120]))
            for t in fact_tags:
                if t not in ids:
                    bad.append(diagnostic(f"{path.name}:{n} unknown id {t}", claim=line[:120]))
            for k in answer_tags:
                if _bank_get(bank, k) is None:
                    bad.append(f"{path.name}:{n} unknown answer key {k}")
    return bad


if __name__ == "__main__":
    cli(check, "fact_ids")
