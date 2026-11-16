"""Networking agent: find people from public professional sources, confirm identity
with 2 independent sources, draft one short message each. You send it.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from . import core
from .schemas import ContactList, OutreachDraft

sys.path.insert(0, str(core.ROOT))
from checks import contact_sources, run_all  # noqa: E402

BLOCKED_DOMAINS = ["linkedin.com", "glassdoor.com", "dice.com"]
CYCLE_DAYS = 30


def people_prompt(job, profile: dict) -> str:
    net = profile.get("networking", {})
    return (
        f"I'm applying for {job['title']} at {job['company']}. Find up to 6 people at "
        f"{job['company']} who would plausibly work with or hire for this role "
        "(team leads, engineers on the relevant team, researchers, recruiters for this area). "
        "Use only public professional sources: company team/research pages, papers, conference "
        "talks, GitHub, university alumni pages. Do not use LinkedIn. Do not collect any "
        "personal-life details.\n"
        f"My affiliations (shared ground is a good reason to reach out): {net.get('affiliations', [])}\n"
        "For each person give: full name, role, the URLs that confirm they work there in that "
        "role (at least two different websites), and one specific, true reason I could contact "
        "them (e.g. a paper or talk related to the role), with its URL.\n\n"
        + core.untrusted("posting_excerpt", (job["raw_text"] or "")[:3000])
    )


def search_people(job, profile: dict) -> str:
    """Web research step (API mode). Returns the model's notes with source URLs."""
    cfg = core.model_for("outreach")
    messages = [{"role": "user", "content": people_prompt(job, profile)}]
    notes = []
    for _ in range(3):
        import anthropic
        import httpx
        try:
            resp = core.client().messages.create(
                model=cfg["model"], max_tokens=16000, messages=messages,
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 10,
                        "blocked_domains": BLOCKED_DOMAINS},
                       {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 10,
                        "blocked_domains": BLOCKED_DOMAINS}],
            )
        except (anthropic.AnthropicError, httpx.HTTPError) as e:
            raise core.JobbotError(f"People search request failed ({type(e).__name__})") from e
        core.record_usage('people_search', cfg['model'], resp)
        notes += [b.text for b in resp.content if b.type == "text"]
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    return "\n".join(notes)


def contacts_this_cycle(conn, company: str) -> int:
    since = (date.fromisoformat(core.today()) - timedelta(days=CYCLE_DAYS)).isoformat()
    return conn.execute("SELECT COUNT(*) FROM contacts WHERE company=? AND created_at >= ?",
                        (company, since)).fetchone()[0]


def draft_message(job, candidate, profile: dict) -> OutreachDraft:
    prefs = profile.get("preferences", {})
    user = (
        "## Profile (the only source of facts about me)\n" + core.dumps({
            k: profile.get(k) for k in ("person", "education", "experience", "projects",
                                        "facts", "networking")})
        + f"\n\n## Writing samples\n{core.dumps(profile.get('writing_samples', []))}"
        + f"\n\n## Limits\nmax words: {prefs.get('outreach_max_words', 120)}; "
        f"banned phrases: {prefs.get('banned_phrases', [])}"
        + f"\n\n## Role\n{job['title']} at {job['company']} ({job['url'] or 'no url'})"
        + "\n\n## Recipient (verified)\n" + core.dumps(candidate)
    )
    return core.llm_json("outreach", core.system_prompt("outreach"), user, OutreachDraft,
                         max_tokens=4000)


def run(job_id: str, offline_review: bool = False) -> dict:
    conn = core.connect()
    profile = core.load_profile()
    job = core.get_job(conn, job_id)
    net = profile.get("networking", {})
    cap = net.get("max_contacts_per_company", 3)
    room = cap - contacts_this_cycle(conn, job["company"])
    if room <= 0:
        core.log_decision("outreach", job_id, "skip", f"already {cap} contacts at "
                          f"{job['company']} in the last {CYCLE_DAYS} days")
        return {"job_id": job_id, "drafted": 0, "reason": "contact cap reached"}

    if core.is_manual():
        # Claude researches with its own web search in chat and answers with the list.
        # Code still re-fetches every source below before anyone is drafted.
        found = core.llm_json(
            "outreach", "Research these people with web search, then answer with the list. "
            "Copy URLs exactly. Leave out anyone without two source URLs on different sites "
            "or without a concrete, sourced reason.",
            people_prompt(job, profile)
            + f"\nAllowed channels: {net.get('channels', ['email'])}", ContactList)
    else:
        found = _extract_contacts(job, net, search_people(job, profile))
    return _draft_all(conn, job_id, job, profile, net, room, found, offline_review)


def _extract_contacts(job, net: dict, notes: str) -> ContactList:
    return core.llm_json(
        "outreach",
        "Extract the people described in these research notes. Copy URLs exactly. "
        "Leave out anyone without at least two source URLs or without a concrete reason.",
        f"Company: {job['company']}\nAllowed channels: {net.get('channels', ['email'])}\n\n"
        + core.untrusted("research_notes", notes),
        ContactList, max_tokens=8000,
    )


def _draft_all(conn, job_id: str, job, profile: dict, net: dict, room: int,
               found: ContactList, offline_review: bool) -> dict:
    d = core.job_dir(job_id, conn) / "outreach"
    d.mkdir(parents=True, exist_ok=True)
    drafted, pending = [], 0
    for c in found.candidates:
        if len(drafted) + pending >= room:
            break
        if conn.execute("SELECT 1 FROM contacts WHERE company=? AND name=?",
                        (job["company"], c.name)).fetchone():
            continue
        verified = contact_sources.verified_sources(c.sources, c.name, job["company"])
        if len(verified) < 2:
            core.log_decision("outreach", job_id, "dropped_contact",
                              f"{c.name}: {len(verified)} verified source(s)", c.sources)
            continue
        candidate = c.model_dump() | {"sources": verified, "company": job["company"]}
        try:
            msg = draft_message(job, candidate, profile)
        except core.ManualTaskPending:
            pending += 1  # every draft becomes a task in one pass; re-run after answering
            continue
        slug = core.slugify(c.name)
        (d / f"{slug}.json").write_text(core.dumps(candidate))
        (d / f"{slug}.md").write_text(f"Subject: {msg.subject}\n\n{msg.body.strip()}\n")
        body_lines = [l for l in msg.body.strip().splitlines() if l.strip()]
        tagged = [f"# To: {c.name}, {c.role} ({c.channel})", f"# Subject: {msg.subject}"]
        # The salutation and sign-off are not claims; mark them '//' so fact_ids skips them.
        for i, line in enumerate(body_lines):
            is_frame = i == 0 or i == len(body_lines) - 1
            tagged.append(f"// {line}" if is_frame else
                          f"{line} " + "".join(f"[{f}]" for f in msg.fact_ids))
        (d / f"{slug}.tagged.md").write_text("\n".join(tagged) + "\n")

        followup = (date.fromisoformat(core.today()) + timedelta(days=7)).isoformat()
        cur = conn.execute(
            "INSERT OR IGNORE INTO contacts (job_id, name, role, company, sources_json, reason, "
            "channel, status, next_followup, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job_id, c.name, c.role, job["company"], json.dumps(verified), c.reason, c.channel,
             "drafted", followup, core.today()))
        conn.commit()
        core.record_document(conn, job_id, "outreach", d / f"{slug}.md")
        core.log_decision("outreach", job_id, "drafted", f"{c.name}: {c.reason}", verified)
        drafted.append({"id": cur.lastrowid, "name": c.name, "file": str(d / f"{slug}.md")})

    if pending:
        raise core.JobbotError(f"{pending} outreach draft(s) waiting for Claude; "
                               "answer the tasks, then re-run outreach")
    if drafted:
        results = run_all.run(d.parent, outreach=True, offline=offline_review)
        failed = run_all.failures(results)
        if failed:
            core.log_decision("outreach", job_id, "checks_failed", "; ".join(failed)[:500])
        try:
            from . import review
            review.review(conn, job_id, d.parent, results, outreach=True)
        except core.JobbotError as e:
            core.warn(f"outreach review skipped: {e}")
    return {"job_id": job_id, "drafted": len(drafted), "contacts": drafted}


def mark_sent(contact_id: int, followup_days: int = 7) -> None:
    conn = core.connect()
    c = conn.execute("SELECT * FROM contacts WHERE id=?", (contact_id,)).fetchone()
    if not c:
        raise core.JobbotError(f"Unknown contact {contact_id}")
    if c["sent_at"]:
        return  # repeated CLI calls must not duplicate the send or its follow-up
    due = (date.fromisoformat(core.today()) + timedelta(days=followup_days)).isoformat()
    conn.execute("UPDATE contacts SET status='sent', sent_at=?, next_followup=? WHERE id=?",
                 (core.now(), due, contact_id))
    conn.execute("INSERT INTO followups (job_id, contact_id, due, note) VALUES (?,?,?,?)",
                 (c["job_id"], contact_id, due, f"Follow up with {c['name']}"))
    conn.commit()
    core.record_action(conn, c["job_id"], "me", "sent", f"outreach to {c['name']}")
