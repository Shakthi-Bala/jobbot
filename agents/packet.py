"""The new-job-packet playbook as code (skills/jobbot-mode/playbooks/new-job-packet.md).

Ends at status ready_for_review. Nothing here can submit anything.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import core, discover, review, tailor

sys.path.insert(0, str(core.ROOT))
from checks import run_all  # noqa: E402

MAX_FIX_LOOPS = 2


def _stop(conn, job_id: str, status: str, reason: str) -> dict:
    core.set_status(conn, job_id, status)
    core.log_decision("packet", job_id, f"stopped:{status}", reason)
    return {"job_id": job_id, "status": status, "reason": reason}


def build(job_id: str, skip_review: bool = False, offline: bool = False) -> dict:
    conn = core.connect()
    job = core.get_job(conn, job_id)

    # 2. Re-fetch the posting. Closed or changed req ID -> stop.
    if not offline and job["url"] and discover.parse_ats_url(job["url"]):
        live = discover.fetch_by_url(job["url"])
        if live is None:
            conn.execute("UPDATE jobs SET active=0 WHERE id=?", (job_id,))
            return _stop(conn, job_id, "closed", "posting is no longer live")
        if job["req_id"] and live["req_id"] != job["req_id"]:
            return _stop(conn, job_id, "closed",
                         f"req ID changed {job['req_id']} -> {live['req_id']}")
        conn.execute("UPDATE jobs SET last_verified=? WHERE id=?", (core.now(), job_id))
        conn.commit()
    else:
        core.log_decision("packet", job_id, "unverified_source",
                          "no public ATS URL; posting could not be re-fetched")

    # 3. Fit row: a blocking restriction stops the packet.
    fit = conn.execute("SELECT decision FROM fit WHERE job_id=?", (job_id,)).fetchone()
    if fit is None:
        from . import fit as fit_agent
        fit_agent.score_job(conn, job_id)
        fit = conn.execute("SELECT decision FROM fit WHERE job_id=?", (job_id,)).fetchone()
    if fit["decision"] == "blocked":
        return _stop(conn, job_id, "blocked", "fit agent found a blocking restriction")

    # 4-9. Tailor -> checks -> review, with at most MAX_FIX_LOOPS rewrites.
    feedback: list[str] = []
    d: Path | None = None
    results: dict = {}
    judgment = None
    for attempt in range(MAX_FIX_LOOPS + 1):
        version = _next_version(job_id)
        d = tailor.build(conn, job_id, feedback or None, version)
        core.set_status(conn, job_id, "packet_drafted")
        results = run_all.run(d, offline=offline)
        failed = run_all.failures(results)
        if failed:
            core.log_decision("packet", job_id, f"checks_failed_v{version}", "; ".join(failed)[:500])
            feedback = failed
            if attempt < MAX_FIX_LOOPS:
                continue
            break
        if skip_review:
            break
        judgment = review.review(conn, job_id, d, results)
        core.set_status(conn, job_id, "reviewed")
        feedback = review.act_on(judgment)
        if not feedback:
            break
        core.log_decision("packet", job_id, f"review_act_on_v{version}", "; ".join(feedback)[:500])

    assert d is not None
    _record_documents(conn, job_id, d, "passed" if not feedback else "changes_requested")
    need_input = "[NEED INPUT" in (d / "answers.md").read_text()
    if feedback:
        (d / "open_issues.md").write_text(
            "# Unresolved after automatic fixes\n\n" + "\n".join(f"- {f}" for f in feedback) + "\n")
        return _stop(conn, job_id, "needs_input",
                     f"{len(feedback)} issue(s) remain after {MAX_FIX_LOOPS} fix loops; see open_issues.md")
    (d / "open_issues.md").unlink(missing_ok=True)
    core.set_status(conn, job_id, "ready_for_review")
    core.log_decision("packet", job_id, "ready_for_review",
                      "all checks passed" + ("; has [NEED INPUT] answers" if need_input else ""))
    return {"job_id": job_id, "status": "ready_for_review", "dir": str(d),
            "need_input": need_input}


def _next_version(job_id: str) -> int:
    meta = core.OUT / job_id / "meta.json"
    return json.loads(meta.read_text())["version"] + 1 if meta.exists() else 1


def _record_documents(conn, job_id: str, d: Path, review_status: str) -> None:
    kinds = {"resume.pdf": "resume", "cover_letter.pdf": "cover_letter",
             "cover_letter.md": "cover_letter", "answers.md": "answers"}
    for name, kind in kinds.items():
        if (d / name).exists():
            doc_id = core.record_document(conn, job_id, kind, d / name)
            conn.execute("UPDATE documents SET review_status=? WHERE id=?", (review_status, doc_id))
    conn.commit()
