"""Tracker and scheduler: plain software, no AI except optional follow-up drafts.

Daily log, follow-ups, outcomes, and the weekly funnel report.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from . import core
from .schemas import Rewrite

OUTCOMES = ("applied", "responded", "interview", "rejected", "offer", "closed")


def edit_draft(job_id: str, *, changes: str | None = None) -> None:
    """Dashboard draft actions cannot overwrite recorded application outcomes."""
    conn = core.connect()
    try:
        job = core.get_job(conn, job_id)
        recorded = conn.execute("SELECT 1 FROM actions WHERE job_id=? AND action IN "
                                "('applied','responded','interview','rejected','offer','closed') LIMIT 1",
                                (job_id,)).fetchone()
        if job['status'] in OUTCOMES or recorded:
            raise core.JobbotError('Application history is recorded; draft actions are disabled')
        if changes is not None:
            if not changes.strip():
                raise core.JobbotError('Requested changes cannot be empty')
            (core.job_dir(job_id, conn) / 'requested_changes.md').write_text(changes.strip() + '\n')
        core.set_status(conn, job_id, 'shortlisted' if changes is not None else 'skipped')
        if changes is None:
            core.record_action(conn, job_id, 'me', 'skip', 'skipped from dashboard')
        core.log_decision('me', job_id, 'request_changes' if changes is not None else 'skip',
                          changes.strip() if changes is not None else 'skipped from dashboard')
    finally:
        conn.close()


def mark_applied(job_id: str, applied_on: str | None = None) -> int | None:
    """Record exactly which resume version you sent (by hash)."""
    conn = core.connect()
    job = core.get_job(conn, job_id)
    existing = conn.execute("SELECT doc_id FROM actions WHERE job_id=? AND action='applied' "
                            "ORDER BY id LIMIT 1", (job_id,)).fetchone()
    if existing:
        return existing["doc_id"]
    from . import discover
    if job['status'] in ('responded', 'interview', 'rejected', 'offer') or (
            job['status'] == 'closed' and not discover.may_reopen(conn, job_id)):
        raise core.JobbotError(f"Job is already {job['status']}; marking applied cannot overwrite that outcome")
    doc = conn.execute(
        "SELECT * FROM documents WHERE job_id=? AND kind='resume' ORDER BY version DESC, id DESC LIMIT 1",
        (job_id,)).fetchone()
    if doc:
        path = Path(doc["path"])
        if not path.is_absolute():
            path = core.ROOT / path
        if not path.exists() or core.sha256_file(path) != doc["sha256"]:
            raise core.JobbotError("Recorded resume bytes are missing or changed; record the submitted file first")
        draft = core.job_dir(job_id, conn) / "resume.pdf"
        if draft.exists() and core.sha256_file(draft) != doc["sha256"]:
            raise core.JobbotError("Current resume differs from the recorded version; finish the packet before marking applied")
    detail = f"resume v{doc['version']} sha256={doc['sha256'][:16]}" if doc else "no resume on file"
    try:
        submitted = date.fromisoformat(applied_on or core.today())
    except ValueError as invalid_date:
        raise core.JobbotError('Date applied must be an ISO date (YYYY-MM-DD)') from invalid_date
    due = (submitted + timedelta(days=10)).isoformat()
    recorded_at = submitted.isoformat() if applied_on else core.now()
    with conn:
        conn.execute("INSERT INTO actions (job_id, actor, action, detail, doc_id, at) "
                     "VALUES (?, 'me', 'applied', ?, ?, ?)",
                     (job_id, detail, doc["id"] if doc else None, recorded_at))
        conn.execute("UPDATE jobs SET status='applied' WHERE id=?", (job_id,))
        conn.execute("INSERT INTO followups (job_id, due, note) VALUES (?,?,?)",
                     (job_id, due, "Check application status / nudge recruiter"))
    return doc["id"] if doc else None


def record_outcome(job_id: str, outcome: str, note: str = "") -> None:
    if outcome not in OUTCOMES:
        raise core.JobbotError(f"outcome must be one of {OUTCOMES}")
    conn = core.connect()
    core.get_job(conn, job_id)
    core.record_action(conn, job_id, "me", outcome, note)
    core.set_status(conn, job_id, outcome)
    if outcome in ("rejected", "closed"):
        conn.execute("UPDATE followups SET done=1 WHERE job_id=?", (job_id,))
        conn.commit()
    core.log_decision("me", job_id, outcome, note)


def due_followups(conn, on: str | None = None) -> list:
    on = on or core.today()
    return conn.execute(
        "SELECT f.*, j.company, j.title, c.name AS contact_name, c.channel "
        "FROM followups f LEFT JOIN jobs j ON j.id=f.job_id "
        "LEFT JOIN contacts c ON c.id=f.contact_id "
        "WHERE f.done=0 AND f.due <= ? ORDER BY f.due", (on,)).fetchall()


def complete_followup(followup_id: int) -> None:
    conn = core.connect()
    conn.execute("UPDATE followups SET done=1 WHERE id=?", (followup_id,))
    conn.commit()


def draft_nudges() -> list[str]:
    """follow-up playbook: draft short nudges for due contact follow-ups. You send."""
    conn = core.connect()
    profile = core.load_profile()
    paths = []
    for f in due_followups(conn):
        if not f["contact_id"]:
            continue
        d = core.job_dir(f["job_id"], conn) / "outreach"
        original = d / f"{core.slugify(f['contact_name'])}.md"
        if not original.exists():
            continue
        out = d / f"{core.slugify(f['contact_name'])}.followup.md"
        if out.exists():
            continue
        r = core.llm_json(
            "outreach", core.system_prompt("outreach"),
            "Write a 2-3 sentence follow-up to the message below, sent about a week later. "
            "Add no new claims. No guilt-tripping. Plain text body only.\n\n"
            f"Banned phrases: {profile.get('preferences', {}).get('banned_phrases', [])}\n\n"
            + original.read_text(), Rewrite, max_tokens=2000)
        out.write_text(r.text.strip() + "\n")
        paths.append(str(out))
    return paths


def daily_log(new_ids: list[str], packets: list[dict]) -> str:
    conn = core.connect()
    soon = (date.fromisoformat(core.today()) + timedelta(days=7)).isoformat()
    lines = [f"# jobbot daily log: {core.today()}", ""]

    lines += ["## New shortlist", ""]
    new = set(new_ids)
    rows = conn.execute(
        "SELECT j.id, j.company, j.title, j.location, j.url, j.comp_max, f.score FROM jobs j "
        "JOIN fit f ON f.job_id=j.id WHERE j.status='shortlisted' "
        f"ORDER BY {core.PAY_ORDER_SQL}, f.score DESC").fetchall()
    lines += [f"- {'**new** ' if r['id'] in new else ''}{core.pay_band(r['comp_max'])} · "
              f"fit {r['score']} · {r['title']}, "
              f"{r['company']} ({r['location']}) `{r['id']}` {r['url'] or ''}"
              for r in rows] or ["- none"]

    lines += ["", "## Packets ready for your review", ""]
    rows = conn.execute("SELECT id, company, title FROM jobs WHERE status='ready_for_review'").fetchall()
    lines += [f"- {r['title']}, {r['company']}: out/{core.job_dir(r['id'], conn).name}/" for r in rows] or ["- none"]
    stuck = [p for p in packets if p.get("status") not in ("ready_for_review",)]
    if stuck:
        lines += ["", "## Packets that stopped", ""]
        lines += [f"- `{p['job_id']}`: {p['status']}: {p.get('reason', '')}" for p in stuck]

    lines += ["", "## Deadlines in the next 7 days", ""]
    rows = conn.execute(
        "SELECT company, title, deadline FROM jobs WHERE deadline IS NOT NULL AND deadline <= ? "
        "AND deadline >= ? AND status NOT IN ('applied','rejected','closed','skipped','blocked')",
        (soon, core.today())).fetchall()
    lines += [f"- {r['deadline']}: {r['title']}, {r['company']}" for r in rows] or ["- none"]

    lines += ["", "## Follow-ups due", ""]
    lines += [f"- {f['due']}: {f['note']} ({f['company'] or ''})" for f in due_followups(conn)] \
        or ["- none"]
    text = "\n".join(lines) + "\n"
    (core.DATA / "daily_log.md").write_text(text)
    return text


def weekly_review() -> str:
    """Funnel and response rates by source and role type."""
    conn = core.connect()
    since = (date.fromisoformat(core.today()) - timedelta(days=7)).isoformat()
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    discovered = q("SELECT COUNT(*) FROM jobs WHERE first_seen >= ?", since)
    shortlisted = q("SELECT COUNT(*) FROM fit WHERE decision='shortlist' AND created_at >= ?", since)
    applied = q("SELECT COUNT(*) FROM actions WHERE action='applied' AND at >= ?", since)
    responses = q("SELECT COUNT(DISTINCT job_id) FROM actions WHERE action IN "
                  "('responded','interview','offer','rejected') AND at >= ?", since)

    lines = [f"# Weekly review: week ending {core.today()}", "",
             "## Funnel (last 7 days)", "",
             f"discovered {discovered} -> shortlisted {shortlisted} -> applied {applied} "
             f"-> responses {responses}", ""]

    def rate_table(group_sql: str, label: str) -> list[str]:
        rows = conn.execute(f"""
            SELECT {group_sql} AS g,
                   COUNT(DISTINCT CASE WHEN a.action='applied' THEN j.id END) AS applied,
                   COUNT(DISTINCT CASE WHEN a.action IN ('responded','interview','offer')
                         THEN j.id END) AS positive
            FROM jobs j JOIN actions a ON a.job_id=j.id GROUP BY g""").fetchall()
        out = [f"## Response rate by {label} (all time)", "", f"| {label} | applied | positive | rate |",
               "|---|---|---|---|"]
        for r in rows:
            if r["applied"]:
                out.append(f"| {r['g']} | {r['applied']} | {r['positive']} | "
                           f"{r['positive'] / r['applied']:.0%} |")
        return out + [""]

    lines += rate_table("j.source", "source")
    profile = core.load_profile()
    titles = profile.get("targets", {}).get("titles", [])
    case = "CASE " + " ".join(
        f"WHEN lower(j.title) LIKE '%{t.lower().replace(chr(39), '')}%' THEN '{t.replace(chr(39), '')}'"
        for t in titles) + " ELSE 'other' END" if titles else "'all'"
    lines += rate_table(case, "role type")

    scores = conn.execute(
        "SELECT f.score, EXISTS(SELECT 1 FROM actions a WHERE a.job_id=f.job_id AND a.action IN "
        "('responded','interview','offer')) AS positive FROM fit f "
        "WHERE EXISTS(SELECT 1 FROM actions a WHERE a.job_id=f.job_id AND a.action='applied')"
    ).fetchall()
    threshold = profile.get("targets", {}).get("min_fit_score", 70)
    lines += ["## Threshold tuning", ""]
    if len(scores) < 10:
        lines.append(f"Only {len(scores)} applications with outcomes; keep min_fit_score at "
                     f"{threshold} until there are at least 10.")
    else:
        pos = [s["score"] for s in scores if s["positive"]]
        neg = [s["score"] for s in scores if not s["positive"]]
        avg = lambda xs: sum(xs) / len(xs) if xs else float("nan")
        lines.append(f"Mean fit score: positive responses {avg(pos):.0f}, others {avg(neg):.0f}. "
                     f"Current threshold {threshold}.")
        if pos and min(pos) > threshold + 5:
            lines.append(f"No positive response below {min(pos)}; consider raising the threshold.")
    text = "\n".join(lines) + "\n"
    (core.DATA / "weekly_review.md").write_text(text)
    return text


def pipeline_counts(conn) -> dict[str, int]:
    return {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")}


def fit_row(conn, job_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM fit WHERE job_id=?", (job_id,)).fetchone()
    if not r:
        return None
    out = dict(r)
    for k in ("strengths_json", "gaps_json", "restrictions_json", "unknowns_json", "questions_json"):
        out[k.removesuffix("_json")] = json.loads(r[k] or "[]")
    return out
