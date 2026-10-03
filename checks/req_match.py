"""Company, title and req ID in the packet match the live posting, and no document
names a different target company."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rapidfuzz import fuzz  # noqa: E402

from checks._lib import cli, core, db, meta, rendered_texts  # noqa: E402


def check(d: Path, live: bool = True) -> list[str]:
    from agents import discover
    m = meta(d)
    if not m:
        return ["meta.json missing"]
    bad = []
    job = db().execute("SELECT * FROM jobs WHERE id=?", (m["job_id"],)).fetchone()
    if not job:
        return [f"job {m['job_id']} not in tracker"]
    for k in ("company", "title", "req_id"):
        if (m.get(k) or "") != (job[k] or ""):
            bad.append(f"meta {k} {m.get(k)!r} != tracker {job[k]!r}")

    if live and job["url"] and discover.parse_ats_url(job["url"]):
        posting = discover.fetch_by_url(job["url"])
        if posting is None:
            bad.append(f"posting is no longer live: {job['url']}")
        else:
            if fuzz.ratio(core.normalize(posting["title"]), core.normalize(job["title"])) < 90:
                bad.append(f"live title {posting['title']!r} != {job['title']!r}")
            if job["req_id"] and posting["req_id"] != job["req_id"]:
                bad.append(f"live req ID {posting['req_id']!r} != {job['req_id']!r}")

    texts = rendered_texts(d)
    others = {c.get("name") for c in core.load_companies()} - {job["company"], None, ""}
    for name, text in texts.items():
        if name == "resume" or name.startswith("outreach/"):
            continue
        for other in others:
            if re.search(rf"\b{re.escape(other)}\b", text, re.I):
                bad.append(f"{name} mentions a different company: {other}")
    if "cover_letter.md" in texts and job["company"].lower() not in texts["cover_letter.md"].lower():
        bad.append(f"cover letter never names {job['company']}")
    return bad


if __name__ == "__main__":
    cli(check, "req_match")
