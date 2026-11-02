"""Build a reviewed packet, with durable checkpoints for manual-mode resumption."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import core, discover, panel, review, tailor

sys.path.insert(0, str(core.ROOT))
from checks import run_all  # noqa: E402

MAX_FIX_LOOPS = 2
MAX_PANEL_ROUNDS = 3
RECORDED_STATUSES = ("applied", "responded", "interview", "rejected", "offer", "closed")
ARTIFACTS = ("meta.json", "resume.json", "resume.pdf", "resume.tagged.md",
             "cover_letter.pdf", "cover_letter.md", "cover_letter.tagged.md",
             "answers.md", "answers.tagged.md")


def _stop(conn, job_id: str, status: str, reason: str, d: Path | None = None) -> dict:
    core.set_status(conn, job_id, status)
    core.log_decision("packet", job_id, f"stopped:{status}", reason)
    result = {"job_id": job_id, "status": status, "reason": reason}
    if d is not None:
        result["dir"] = str(d)
    return result


def _inputs(job, requested: Path, skip_review: bool, offline: bool, skip_panel: bool) -> str:
    """Invalidate checkpoints when evidence, instructions or build options change."""
    paths = [core.DATA / n for n in ("profile.yaml", "answers_bank.yaml", "master_resume.yaml")]
    paths += [core.ROOT / "models.yaml", requested]
    for folder in (core.TEMPLATES, core.SKILLS, core.PRINCIPLES):
        paths += sorted(p for p in folder.rglob("*") if p.is_file())
    payload = {
        "checkpoint_version": 1,
        "job": {k: job[k] for k in ("id", "company", "title", "location", "req_id", "url",
                                   "raw_text", "parsed_json")},
        "files": [(str(p), core.sha256_file(p) if p.exists() else None) for p in paths],
        "options": [skip_review, offline, skip_panel],
    }
    return hashlib.sha256(core.dumps(payload).encode()).hexdigest()


def _manifest(d: Path) -> dict:
    return {n: core.sha256_file(d / n) for n in ARTIFACTS if (d / n).exists()}


def _save(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(core.dumps(state))
    temp.replace(path)


def build(job_id: str, skip_review: bool = False, offline: bool = False,
          skip_panel: bool = False) -> dict:
    conn = core.connect()
    try:
        return _build(conn, job_id, skip_review, offline, skip_panel)
    finally:
        conn.close()


def _build(conn, job_id: str, skip_review: bool, offline: bool, skip_panel: bool) -> dict:
    job = core.get_job(conn, job_id)
    if job["status"] in RECORDED_STATUSES:
        raise core.JobbotError(f"Job {job_id} is already {job['status']}; its application history is retained")
    if not job["active"]:
        return _stop(conn, job_id, "closed", "posting is inactive")

    if not offline and job["url"] and discover.parse_ats_url(job["url"]):
        live = discover.fetch_by_url(job["url"])
        if live is None:
            conn.execute("UPDATE jobs SET active=0 WHERE id=?", (job_id,))
            return _stop(conn, job_id, "closed", "posting is no longer live")
        if job["req_id"] and live["req_id"] != job["req_id"]:
            return _stop(conn, job_id, "closed", "live requisition ID changed")
        if live["raw_text"] != job["raw_text"]:
            conn.execute("UPDATE jobs SET raw_text=?, raw_html=?, parsed_json=NULL, deadline=NULL "
                         "WHERE id=?", (live["raw_text"], live.get("raw_html", ""), job_id))
            conn.execute("DELETE FROM fit WHERE job_id=?", (job_id,))
        conn.execute("UPDATE jobs SET last_verified=? WHERE id=?", (core.now(), job_id))
        conn.commit()
        job = core.get_job(conn, job_id)
    else:
        core.log_decision("packet", job_id, "unverified_source",
                          "offline mode or no supported ATS URL; live verification skipped")

    fit = conn.execute("SELECT decision FROM fit WHERE job_id=?", (job_id,)).fetchone()
    if fit is None:
        from . import fit as fit_agent
        result = fit_agent.score_job(conn, job_id)
        decision = result["decision"]
        job = core.get_job(conn, job_id)
    else:
        decision = fit["decision"]
    if decision != "shortlist":
        status = "blocked" if decision == "blocked" else "skipped"
        return _stop(conn, job_id, status, f"fit decision is {decision}")

    d = core.job_dir(job_id, conn)
    requested = d / "requested_changes.md"
    key = _inputs(job, requested, skip_review, offline, skip_panel)
    state_path = d / "packet_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get("inputs") != key or state.get("manifest", {}) != _manifest(d):
        state = {"inputs": key, "phase": "draft", "fix_loops": 0, "panel_round": 0,
                 "blocking": [], "feedback": ([f"The candidate asked for: {requested.read_text().strip()}"]
                                               if requested.exists() else [])}
    if state["phase"] == "complete":
        return state["result"]

    while True:
        if state["phase"] == "draft":
            version = _next_version(job_id, conn)
            d = tailor.build(conn, job_id, state["feedback"] or None, version)
            # Reports from previous bytes must not appear to review the new draft.
            stale = ["review.md", "checks.json", "ats.json"]
            if not state["panel_round"]:
                stale += ["panel.json", "panel.md"]
            for name in stale:
                (d / name).unlink(missing_ok=True)
            state.update(phase="checks", manifest=_manifest(d))
            core.set_status(conn, job_id, "packet_drafted")
            _save(state_path, state)

        if state["phase"] == "checks":
            results = run_all.run(d, offline=offline)
            state.update(checks=results, blocking=run_all.failures(results), phase="review")
            _save(state_path, state)

        if state["phase"] == "review":
            if not state["blocking"] and not skip_review:
                state["blocking"] = review.act_on(review.review(conn, job_id, d, state["checks"]))
                core.set_status(conn, job_id, "reviewed")
            state["phase"] = "decide"
            _save(state_path, state)

        if state["phase"] == "decide":
            if state["blocking"]:
                if state["fix_loops"] >= MAX_FIX_LOOPS:
                    break
                state.update(fix_loops=state["fix_loops"] + 1,
                             feedback=state["blocking"], phase="draft")
                _save(state_path, state)
                continue
            if skip_review or skip_panel:
                break
            state.update(panel_round=state["panel_round"] + 1, phase="panel")
            _save(state_path, state)

        if state["phase"] == "panel":
            verdict = panel.run(conn, job_id, d, state["panel_round"])
            if verdict["done"]:
                break
            if state["panel_round"] >= MAX_PANEL_ROUNDS:
                state["blocking"] = ["Review panel still requests revisions: " + r
                                     for r in verdict["revisions"]] or ["Review panel did not approve"]
                break
            state.update(feedback=[f"Review panel (round {state['panel_round']}): {r}"
                                   for r in verdict["revisions"]], phase="draft")
            _save(state_path, state)

    blocking = state["blocking"]
    _record_documents(conn, job_id, d, "changes_requested" if blocking else "passed")
    need_input = "[NEED INPUT" in (d / "answers.md").read_text()
    if blocking:
        (d / "open_issues.md").write_text(
            "# Unresolved after automatic revisions\n\n" + "\n".join(f"- {f}" for f in blocking) + "\n")
        result = _stop(conn, job_id, "needs_input", "Revision limit reached; see open_issues.md", d)
    else:
        (d / "open_issues.md").unlink(missing_ok=True)
        requested.unlink(missing_ok=True)
        core.set_status(conn, job_id, "ready_for_review")
        core.log_decision("packet", job_id, "ready_for_review", "checks passed; "
                          f"accuracy review skipped={skip_review}; panel skipped={skip_panel or skip_review}; "
                          f"live verification skipped={offline}; unanswered questions={need_input}")
        result = {"job_id": job_id, "status": "ready_for_review", "dir": str(d), "need_input": need_input}
    state.update(phase="complete", result=result, manifest=_manifest(d),
                 inputs=_inputs(job, requested, skip_review, offline, skip_panel))
    _save(state_path, state)
    return result


def _next_version(job_id: str, conn) -> int:
    meta = core.job_dir(job_id, conn) / "meta.json"
    return json.loads(meta.read_text())["version"] + 1 if meta.exists() else 1


def _record_documents(conn, job_id: str, d: Path, review_status: str) -> None:
    kinds = {"resume.pdf": "resume", "cover_letter.pdf": "cover_letter",
             "cover_letter.md": "cover_letter_source", "answers.md": "answers"}
    for name, kind in kinds.items():
        if (d / name).exists():
            doc_id = core.record_document(conn, job_id, kind, d / name)
            conn.execute("UPDATE documents SET review_status=? WHERE id=?", (review_status, doc_id))
    conn.commit()
