"""Every restriction quote is found verbatim in the stored posting (jobs.raw_text)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checks._lib import cli, core, db, meta  # noqa: E402


def check(d: Path) -> list[str]:
    job_id = meta(d).get("job_id")
    if not job_id:
        return ["meta.json missing job_id"]
    conn = db()
    job = conn.execute("SELECT raw_text, parsed_json FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        return [f"job {job_id} not in tracker"]
    posting = job["raw_text"]
    quotes = [r["quote"] for r in json.loads(job["parsed_json"] or "{}").get("restrictions", [])]
    fit = conn.execute("SELECT restrictions_json FROM fit WHERE job_id=?", (job_id,)).fetchone()
    if fit:
        quotes += [r["quote"] for r in json.loads(fit["restrictions_json"] or "[]")]
    return ['quote not in posting:\n' + core.untrusted('restriction_quote', q[:150]) for q in quotes
            if not core.quote_in_text(q, posting)]


if __name__ == "__main__":
    cli(check, "restriction_quotes")
