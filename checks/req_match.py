"""Company, title and req ID in the packet match the live posting, and no document
names a different target company."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rapidfuzz import fuzz  # noqa: E402

from checks._lib import cli, core, db, diagnostic, meta, rendered_texts  # noqa: E402


def check(d: Path, live: bool = True) -> list[str]:
    from agents import discover
    m = meta(d)
    if not m:
        return ["meta.json missing"]
    bad = []
    job = db().execute("SELECT * FROM jobs WHERE id=?", (m["job_id"],)).fetchone()
    if not job:
        return [diagnostic('job not in tracker', job_id=m['job_id'])]
    for k in ("company", "title", "req_id"):
        if (m.get(k) or "") != (job[k] or ""):
            bad.append(diagnostic(f"meta {k} differs from tracker", packet=m.get(k), tracker=job[k]))

    if live and job["url"] and discover.parse_ats_url(job["url"]):
        posting = discover.fetch_by_url(job["url"])
        if posting is None:
            bad.append(diagnostic('posting is no longer live', url=job['url']))
        else:
            if fuzz.ratio(core.normalize(posting["title"]), core.normalize(job["title"])) < 90:
                bad.append('live title differs from stored title:\n' + core.untrusted(
                    'posting_titles', core.dumps({'live': posting['title'], 'stored': job['title']})))
            if job["req_id"] and posting["req_id"] != job["req_id"]:
                bad.append(diagnostic('live req ID differs from stored ID', live=posting['req_id'], stored=job['req_id']))

    texts = rendered_texts(d)
    others = {c.get("name") for c in core.load_companies()} - {job["company"], None, ""}
    for name, text in texts.items():
        if name == "resume" or name.startswith("outreach/"):
            continue
        for other in others:
            if re.search(rf"\b{re.escape(other)}\b", text, re.I):
                bad.append(diagnostic('document mentions a different company', document=name, company=other))
    if "cover_letter.md" in texts and job["company"].lower() not in texts["cover_letter.md"].lower():
        bad.append(diagnostic('cover letter never names the target company', company=job['company']))
    return bad


if __name__ == "__main__":
    cli(check, "req_match")
