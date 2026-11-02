"""jobbot dashboard.  Run: streamlit run dashboard/app.py"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agents import core, outreach, tracker  # noqa: E402

st.set_page_config(page_title="jobbot", layout="wide")
conn = core.connect()


def df(sql: str, *args) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=args)


st.title("jobbot")
st.caption("Nothing here submits or sends anything. You do that, then record it.")

tabs = st.tabs(["Today", "Pipeline", "Packet", "Gaps", "Contacts", "Funnel", "Log"])
GAPS, CONTACTS, FUNNEL, LOG = 3, 4, 5, 6

pending = core.pending_tasks()
if pending:
    st.info(f"{len(pending)} AI step(s) waiting for Claude in out/tasks/ (manual mode).")

# ------------------------------------------------------------------ Today
with tabs[0]:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("New shortlist")
        st.dataframe(df(
            "SELECT j.id, j.comp_min AS pay_min, j.comp_max AS pay_max, f.score, j.title, "
            "j.company, j.location, j.deadline, j.url FROM jobs j JOIN fit f ON f.job_id=j.id "
            f"WHERE j.status='shortlisted' ORDER BY {core.PAY_ORDER_SQL}, f.score DESC"),
            hide_index=True, width="stretch")
        st.subheader("Packets ready for review")
        st.dataframe(df("SELECT id, title, company FROM jobs WHERE status='ready_for_review'"),
                     hide_index=True, width="stretch")
        st.subheader("Need your input")
        st.dataframe(df("SELECT id, title, company FROM jobs WHERE status='needs_input'"),
                     hide_index=True, width="stretch")
    with c2:
        st.subheader("Follow-ups due")
        due = tracker.due_followups(conn)
        if not due:
            st.write("None.")
        for f in due:
            who = f" with {f['contact_name']}" if f["contact_name"] else ""
            cols = st.columns([4, 1])
            cols[0].write(f"**{f['due']}** {f['company'] or ''}{who}: {f['note']}")
            if cols[1].button("Done", key=f"fu{f['id']}"):
                tracker.complete_followup(f["id"])
                st.rerun()
        st.subheader("Deadlines this week")
        st.dataframe(df(
            "SELECT deadline, title, company, status FROM jobs WHERE deadline BETWEEN date('now') "
            "AND date('now','+7 days') AND status NOT IN ('applied','rejected','closed','skipped')"),
            hide_index=True, width="stretch")

# --------------------------------------------------------------- Pipeline
with tabs[1]:
    statuses = st.multiselect("Status", core.STATUSES, default=[])
    q = st.text_input("Search title/company")
    jobs = df("SELECT j.id, j.status, j.comp_min AS pay_min, j.comp_max AS pay_max, f.score, "
              "f.decision, j.title, j.company, j.location, j.source, j.first_seen, j.deadline, "
              "j.active, j.url FROM jobs j LEFT JOIN fit f ON f.job_id=j.id "
              f"ORDER BY {core.PAY_ORDER_SQL}, f.score DESC")
    if statuses:
        jobs = jobs[jobs.status.isin(statuses)]
    if q:
        mask = jobs.title.str.contains(q, case=False, na=False, regex=False) | \
            jobs.company.str.contains(q, case=False, na=False, regex=False)
        jobs = jobs[mask]
    st.dataframe(jobs, hide_index=True, width="stretch")
    st.caption(" · ".join(f"{k}: {v}" for k, v in tracker.pipeline_counts(conn).items()))

# ----------------------------------------------------------------- Packet
with tabs[2]:
    packet_jobs = [r for r in conn.execute(
        "SELECT id, title, company, status FROM jobs ORDER BY first_seen DESC").fetchall()
        if (core.job_dir(r["id"], conn) / "meta.json").exists()]
    if not packet_jobs:
        st.info("No packets yet. Run `python jobbot.py packet JOB_ID`.")
    else:
        choice = st.selectbox("Job", packet_jobs,
                              format_func=lambda r: f"{r['title']}, {r['company']} [{r['status']}]")
        d = core.job_dir(choice["id"], conn)
        meta = json.loads((d / "meta.json").read_text())
        st.write(f"**{meta['title']}** at **{meta['company']}** · req {meta.get('req_id') or 'n/a'} "
                 f"· v{meta['version']} · [posting]({meta.get('url') or '#'})")

        fit = tracker.fit_row(conn, choice["id"])
        if fit:
            with st.expander(f"Fit: {fit['score']} ({fit['decision']})"):
                st.json({k: fit[k] for k in ("strengths", "gaps", "restrictions", "unknowns",
                                              "questions")})

        if (d / "open_issues.md").exists():
            st.warning((d / "open_issues.md").read_text())
        sub = st.tabs(["Review", "Resume", "Cover letter", "Answers", "changes.diff", "Checks", "Panel"])
        with sub[6]:
            st.markdown((d / "panel.md").read_text() if (d / "panel.md").exists()
                        else "_Review panel hasn't run yet._")
        with sub[0]:
            st.markdown((d / "review.md").read_text() if (d / "review.md").exists()
                        else "_No review yet._")
        with sub[1]:
            if (d / "resume.pdf").exists():
                st.download_button("Download resume.pdf", (d / "resume.pdf").read_bytes(),
                                   file_name=f"resume_{meta['company']}.pdf")
                from checks._lib import pdf_text
                st.text(pdf_text(d / "resume.pdf"))
        with sub[2]:
            if (d / "cover_letter.md").exists():
                st.markdown((d / "cover_letter.md").read_text())
                if (d / "cover_letter.pdf").exists():
                    st.download_button("Download cover_letter.pdf",
                                       (d / "cover_letter.pdf").read_bytes(),
                                       file_name=f"cover_letter_{meta['company']}.pdf")
            else:
                st.write("No cover letter for this role.")
        with sub[3]:
            st.markdown((d / "answers.md").read_text() if (d / "answers.md").exists() else "")
        with sub[4]:
            st.code((d / "changes.diff").read_text() if (d / "changes.diff").exists() else "",
                    language="diff")
        with sub[5]:
            if (d / "checks.json").exists():
                st.json(json.loads((d / "checks.json").read_text()))

        st.divider()
        b1, b2, b3 = st.columns(3)
        if b1.button("Mark applied", type="primary",
                     help="Click after YOU submitted it. Records the resume hash."):
            tracker.mark_applied(choice["id"])
            st.success("Recorded. Follow-up scheduled in 10 days.")
        with b2:
            note = st.text_area("Requested changes", key="changes")
            if st.button("Request changes") and note.strip():
                (d / "requested_changes.md").write_text(note.strip() + "\n")
                core.set_status(conn, choice["id"], "shortlisted")
                core.log_decision("me", choice["id"], "request_changes", note.strip())
                st.info(f"Saved. Rebuild with: python jobbot.py packet {choice['id']}")
        if b3.button("Skip"):
            core.set_status(conn, choice["id"], "skipped")
            core.log_decision("me", choice["id"], "skip", "skipped from dashboard")
            st.rerun()

# ------------------------------------------------------------------- Gaps
with tabs[GAPS]:
    summary = core.OUT / "gaps" / "summary.md"
    if summary.exists():
        st.markdown(summary.read_text())
    else:
        st.info("No gap reports yet. Run `python jobbot.py gaps`.")
    reports = sorted(core.OUT.glob("*/gaps.md"))
    if reports:
        pick = st.selectbox("Job report", reports, format_func=lambda p: p.read_text().splitlines()[0][2:])
        st.markdown(pick.read_text())

# --------------------------------------------------------------- Contacts
with tabs[CONTACTS]:
    contacts = conn.execute(
        "SELECT c.*, j.title FROM contacts c LEFT JOIN jobs j ON j.id=c.job_id "
        "ORDER BY c.created_at DESC").fetchall()
    if not contacts:
        st.info("No contacts yet. Run `python jobbot.py outreach JOB_ID`.")
    for c in contacts:
        with st.expander(f"{c['name']}, {c['role']} at {c['company']} [{c['status']}] "
                         f"next: {c['next_followup'] or '-'}"):
            st.write(f"**Reason:** {c['reason']}  \n**Channel:** {c['channel']}")
            st.write("**Sources:** " + ", ".join(json.loads(c["sources_json"] or "[]")))
            draft = core.job_dir(c["job_id"] or "", conn) / "outreach" / f"{core.slugify(c['name'])}.md"
            if draft.exists():
                st.code(draft.read_text(), language=None)
            cols = st.columns(3)
            if c["status"] == "drafted" and cols[0].button("Mark sent", key=f"s{c['id']}"):
                outreach.mark_sent(c["id"])
                st.rerun()
            new = cols[1].selectbox("Status", ["drafted", "sent", "replied", "referral", "no_reply"],
                                    index=["drafted", "sent", "replied", "referral",
                                           "no_reply"].index(c["status"] or "drafted"),
                                    key=f"st{c['id']}")
            if new != c["status"] and cols[2].button("Update", key=f"u{c['id']}"):
                conn.execute("UPDATE contacts SET status=? WHERE id=?", (new, c["id"]))
                conn.commit()
                core.record_action(conn, c["job_id"], "me", new, f"contact {c['name']}")
                st.rerun()

# ----------------------------------------------------------------- Funnel
with tabs[FUNNEL]:
    weekly = df("""
        SELECT strftime('%Y-%W', first_seen) AS week, COUNT(*) AS discovered,
               SUM(CASE WHEN id IN (SELECT job_id FROM fit WHERE decision='shortlist') THEN 1 ELSE 0 END) AS shortlisted,
               SUM(CASE WHEN id IN (SELECT job_id FROM actions WHERE action='applied') THEN 1 ELSE 0 END) AS applied,
               SUM(CASE WHEN id IN (SELECT job_id FROM actions WHERE action IN ('responded','interview','offer')) THEN 1 ELSE 0 END) AS positive
        FROM jobs GROUP BY week ORDER BY week""")
    if weekly.empty:
        st.info("No data yet.")
    else:
        st.bar_chart(weekly.set_index("week")[["discovered", "shortlisted", "applied", "positive"]])
        st.dataframe(weekly, hide_index=True, width="stretch")
    if st.button("Generate weekly review"):
        st.markdown(tracker.weekly_review())

# -------------------------------------------------------------------- Log
with tabs[LOG]:
    if core.DECISIONS_PATH.exists():
        with open(core.DECISIONS_PATH, encoding="utf-8") as f:
            log = pd.DataFrame(list(csv.DictReader(f, delimiter="\t")))
        term = st.text_input("Search decisions")
        if term and not log.empty:
            log = log[log.apply(lambda r: r.astype(str).str.contains(term, case=False, regex=False).any(), axis=1)]
        st.dataframe(log.iloc[::-1], hide_index=True, width="stretch")
    else:
        st.info("No decisions logged yet.")
