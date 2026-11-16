"""Application tracker spreadsheet: data/applications.xlsx (gitignored).

    python jobbot.py sheet

Rows are every job with a packet in out/, highest pay first. The Applied?,
Date applied and Notes columns are yours: on each run they are read back first,
so your edits survive, and "Yes" in Applied? records the application in the
tracker (with the resume hash) if it isn't recorded yet.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from . import core, tracker

PATH = core.DATA / "applications.xlsx"
FONT = "Arial"
HEADER_FILL = PatternFill("solid", start_color="1F3864")
INPUT_FILL = PatternFill("solid", start_color="FFFF00")     # cells you fill in
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

RECOMMEND = {
    "apply_now": "Apply now",
    "apply_after_quick_fixes": "Apply after quick fixes (~1 week)",
    "stretch": "Build a project first, then apply",
    "not_a_fit": "Skip for now",
}

# (header, width, key) for the Applications tab. Order is the column order.
COLUMNS = [
    ("#", 4, "rank"), ("Company", 16, "company"), ("Role", 34, "title"),
    ("Location", 18, "location"), ("Base pay (posted)", 18, "pay"), ("Pay band", 11, "band"),
    ("Posted on", 11, "posted"), ("Days since posted", 9, None),
    ("Fit score (0-100)", 8, "score"), ("Readiness (0-100)", 9, "readiness"),
    ("ATS keyword score (now / max with your evidence)", 12, "ats"),
    ("ATS gate", 11, "gate"), ("Hiring manager", 11, "hm"), ("Panel readers avg /10", 9, "panel_avg"),
    ("Panel", 8, "panel"),
    ("Recommendation", 22, "recommend"), ("Fix before applying", 48, "fixes"),
    ("Project that would make you stronger", 40, "project"),
    ("Job posting", 12, "url"), ("Resume", 9, "resume"), ("Cover letter", 9, "cover"),
    ("Answers", 9, "answers"), ("Review", 9, "review"), ("Gap report", 9, "gaps"),
    ("Pipeline status", 14, "status"),
    ("Applied?", 9, "applied"), ("Date applied", 12, "date_applied"), ("Notes", 30, "notes"),
    ("Job ID", 13, "job_id"),
]
COL = {key or header: i + 1 for i, (header, _, key) in enumerate(COLUMNS)}
USER_KEYS = ("applied", "date_applied", "notes")
FIRST_ROW = 6   # rows 1-4: title and legend, row 5: headers
SAVED_EDITS_SHEET = "Saved edits"


def _posted(value: str | None) -> date | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed).date()
    except ValueError:
        return None


def _rel(target: Path, workbook: Path) -> str:
    """Hyperlink target relative to the workbook's folder, so it works on any machine."""
    return os.path.relpath(target, workbook.parent)


# ------------------------------------------------------------------ read back

def read_user_edits(path: Path = PATH) -> dict[str, dict]:
    """Applied?/Date applied/Notes per Job ID from the existing sheet."""
    if not path.exists():
        return {}
    wb = load_workbook(path)
    edits = {}
    # Filtered rows retain their inputs in the workbook. Visible edits take precedence.
    if SAVED_EDITS_SHEET in wb.sheetnames:
        for job_id, applied, date_applied, notes in wb[SAVED_EDITS_SHEET].iter_rows(
                min_row=2, max_col=4, values_only=True):
            if job_id:
                edits[str(job_id)] = dict(zip(USER_KEYS, (applied, date_applied, notes)))
    ws = wb["Applications"]
    for row in range(FIRST_ROW, ws.max_row + 1):
        job_id = ws.cell(row, COL["job_id"]).value
        if not job_id:
            continue
        edits[str(job_id)] = {k: ws.cell(row, COL[k]).value for k in USER_KEYS}
    return edits


def apply_edits(conn, edits: dict[str, dict], errors: dict[str, str] | None = None) -> list[str]:
    """'Yes' in Applied? -> record it in the tracker (once). Returns newly recorded IDs."""
    recorded = []
    for job_id, e in edits.items():
        if str(e.get("applied") or "").strip().lower() != "yes":
            continue
        row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row and row["status"] not in ("applied", "responded", "interview", "rejected", "offer"):
            try:
                tracker.mark_applied(job_id)
            except core.JobbotError as e:
                core.warn(f"sheet {job_id}: {e}")
                if errors is not None:
                    errors[job_id] = str(e)
            else:
                recorded.append(job_id)
    return recorded


# ---------------------------------------------------------------- collect rows

def _pay_label(lo: int | None, hi: int | None) -> str:
    if lo is not None and hi is not None:
        return f"${lo:,} - ${hi:,}"
    if hi is not None:
        return f"up to ${hi:,}"
    if lo is not None:
        return f"from ${lo:,}"
    return "not listed"

def collect(conn, include_ids=()) -> list[dict]:
    rows = []
    jobs = conn.execute(
        "SELECT j.*, f.score FROM jobs j LEFT JOIN fit f ON f.job_id=j.id "
        f"ORDER BY {core.PAY_ORDER_SQL}, f.score DESC").fetchall()
    for j in jobs:
        d = core.job_dir(j["id"], conn)
        if not (d / "meta.json").exists() or (
                j["status"] in ("skipped", "blocked", "closed") and j['id'] not in include_ids):
            continue  # only jobs you're still considering
        gaps = json.loads((d / "gaps.json").read_text()) if (d / "gaps.json").exists() else {}
        fixes = [i["change"] for i in gaps.get("resume_improvements", [])][:3]
        need = (d / "answers.md").read_text().count("[NEED INPUT") if (d / "answers.md").exists() else 0
        if need:
            fixes.append(f"Fill {need} [NEED INPUT] answer(s) in answers.md")
        projects = gaps.get("projects", [])
        ats = json.loads((d / "ats.json").read_text()) if (d / "ats.json").exists() else {}
        rounds = json.loads((d / "panel.json").read_text()) if (d / "panel.json").exists() else []
        last = rounds[-1] if rounds else {}
        rows.append({
            "job_id": j["id"], "company": j["company"], "title": j["title"].strip(),
            "location": j["location"],
            "pay": _pay_label(j["comp_min"], j["comp_max"]),
            "band": core.pay_band(j["comp_max"]), "posted": _posted(j["posted_at"]),
            "score": j["score"], "readiness": gaps.get("readiness"),
            "recommend": RECOMMEND.get(gaps.get("verdict"), "Run gap coach"),
            "fixes": "\n".join(f"{n}. {f}" for n, f in enumerate(fixes, 1)),
            "project": (f"{projects[0]['title']} (~{projects[0]['weeks']} wk)\n"
                        f"Metric: {projects[0]['success_metric']}") if projects else "",
            "url": j["url"],
            "resume": d / "resume.pdf", "cover": d / "cover_letter.pdf",
            "answers": d / "answers.md", "review": d / "review.md", "gaps": d / "gaps.md",
            "status": j["status"],
            "ats": f"{ats['score']}% / {ats['max_score']}%" if ats else "-",
            "gate": {"pass_to_human": "Pass", "reject": "Reject"}.get(last.get("gate"), "-"),
            "hm": {"interview": "Interview", "maybe": "Maybe", "no": "No"}.get(last.get("hiring_manager"), "-"),
            "panel_avg": last.get("reader_avg"), "panel": d / "panel.md",
            "gap_report": gaps,
        })
    for n, r in enumerate(rows, 1):
        r["rank"] = n
    return rows


# ------------------------------------------------------------------- writing

def _header(ws, row: int, labels: list[str], widths: list[int]) -> None:
    for c, (label, width) in enumerate(zip(labels, widths), 1):
        cell = ws.cell(row, c, label)
        cell.font = Font(name=FONT, bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(c)].width = width


def _applications(ws, rows: list[dict], edits: dict[str, dict], path: Path) -> None:
    ws["A1"] = "Job applications"
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    ws["A2"] = ("Highest pay first. Yellow columns are yours: type Yes in Applied? after you submit, "
                "the date in Date applied (e.g. 2026-10-16), and anything in Notes. "
                "Run `python jobbot.py sheet` to refresh; your entries are kept.")
    ws["A3"] = ("Days since posted = today minus Posted on (live formula). Pay is the posted base-pay "
                "range; total compensation with equity is usually higher.")
    ws["A4"] = (f"Generated {core.today()} from the jobbot tracker. Links open files in out/<Company>_<Role>/.")
    for r in (2, 3, 4):
        ws.cell(r, 1).font = Font(name=FONT, size=9, italic=True)
    _header(ws, FIRST_ROW - 1, [h for h, _, _ in COLUMNS], [w for _, w, _ in COLUMNS])
    ws.row_dimensions[FIRST_ROW - 1].height = 32

    applied_dv = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    ws.add_data_validation(applied_dv)
    link_font = Font(name=FONT, color="0563C1", underline="single")

    for i, r in enumerate(rows):
        row = FIRST_ROW + i
        user = edits.get(r["job_id"], {})
        for header, _, key in COLUMNS:
            c = COL[key or header]
            cell = ws.cell(row, c)
            cell.font = Font(name=FONT, size=10)
            cell.border = BORDER
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if key is None:  # Days since posted
                p = get_column_letter(COL["posted"])
                cell.value = f'=IF({p}{row}="","",TODAY()-{p}{row})'
                cell.number_format = "0"
            elif key in USER_KEYS:
                cell.value = user.get(key)
                if key == "applied" and cell.value is None:
                    cell.value = "No"
                cell.fill = INPUT_FILL
                if key == "date_applied":
                    cell.number_format = "yyyy-mm-dd"
            elif key == "url":
                if r["url"]:
                    cell.value, cell.hyperlink, cell.font = "Open posting", r["url"], link_font
            elif key in ("resume", "cover", "answers", "review", "gaps", "panel"):
                target = r[key]
                if target.exists():
                    cell.value, cell.hyperlink, cell.font = "Open", _rel(target, path), link_font
                else:
                    cell.value = "-"
            else:
                cell.value = r[key]
                if key == "posted":
                    cell.number_format = "yyyy-mm-dd"
        applied_dv.add(ws.cell(row, COL["applied"]))
        ws.row_dimensions[row].height = 105

    last = FIRST_ROW + max(len(rows), 1) - 1
    # Highlight rows you've applied to, and stale postings (> 60 days).
    full = f"A{FIRST_ROW}:{get_column_letter(len(COLUMNS))}{last}"
    ap = get_column_letter(COL["applied"])
    ws.conditional_formatting.add(full, FormulaRule(
        formula=[f'${ap}{FIRST_ROW}="Yes"'], fill=PatternFill("solid", start_color="C6EFCE")))
    ds = get_column_letter(COL["Days since posted"])
    ws.conditional_formatting.add(f"{ds}{FIRST_ROW}:{ds}{last}", FormulaRule(
        formula=[f'AND(ISNUMBER({ds}{FIRST_ROW}),{ds}{FIRST_ROW}>60)'],
        font=Font(name=FONT, color="C00000", bold=True)))
    ws.cell(FIRST_ROW - 1, COL["Days since posted"]).comment = Comment(
        "Red = posted more than 60 days ago. Long-open postings are often evergreen "
        "requisitions; still worth applying, but a referral matters more.", "jobbot")
    ws.cell(FIRST_ROW - 1, COL["readiness"]).comment = Comment(
        "From the gap coach: how competitive you are today for this role.", "jobbot")
    ws.freeze_panes = ws.cell(FIRST_ROW, COL["title"] + 1)
    ws.auto_filter.ref = f"A{FIRST_ROW - 1}:{get_column_letter(len(COLUMNS))}{last}"
    ws.column_dimensions[get_column_letter(COL["job_id"])].hidden = False


def _gaps(ws, rows: list[dict]) -> None:
    ws["A1"] = "Gaps and projects per job"
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    headers = ["#", "Company", "Role", "Requirement", "Type", "Status", "Evidence (fact IDs)", "Note"]
    widths = [4, 16, 30, 50, 12, 9, 16, 50]
    _header(ws, 3, headers, widths)
    status_fill = {"missing": "F8CBAD", "partial": "FFE699", "met": "C6EFCE"}
    order = {"missing": 0, "partial": 1, "met": 2}
    row = 4
    for r in rows:
        for q in sorted(r["gap_report"].get("requirements", []),
                        key=lambda q: (order[q["status"]], q["kind"])):
            vals = [r["rank"], r["company"], r["title"], q["requirement"],
                    q["kind"].replace("_", " "), q["status"], ", ".join(q["fact_ids"]), q["note"]]
            for c, v in enumerate(vals, 1):
                cell = ws.cell(row, c, v)
                cell.font = Font(name=FONT, size=10)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                cell.border = BORDER
            ws.cell(row, 6).fill = PatternFill("solid", start_color=status_fill[q["status"]])
            row += 1
    ws.freeze_panes = "D4"
    ws.auto_filter.ref = f"A3:H{max(row - 1, 3)}"


def _projects(ws, rows: list[dict]) -> None:
    ws["A1"] = "Projects ranked by how many of these jobs they help"
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    ws["A2"] = ("A project goes on your resume only after it's done and measured. "
                "Weeks are part-time estimates.")
    ws["A2"].font = Font(name=FONT, size=9, italic=True)
    headers = ["Project", "Weeks", "Jobs it helps", "Which jobs", "Closes", "Resume metric once done", "Builds on", "Deliverables"]
    widths = [44, 7, 8, 40, 50, 40, 14, 40]
    _header(ws, 4, headers, widths)
    merged: dict[str, dict] = {}
    for r in rows:
        for p in r["gap_report"].get("projects", []):
            m = merged.setdefault(p["title"], {"p": p, "jobs": [], "closes": set()})
            m["jobs"].append(f"#{r['rank']} {r['company']}: {r['title']}")
            m["closes"] |= set(p["closes"])
    ranked = sorted(merged.values(), key=lambda m: (-len(m["jobs"]), m["p"]["weeks"]))
    for i, m in enumerate(ranked):
        row = 5 + i
        p = m["p"]
        vals = [p["title"], p["weeks"], None, "\n".join(m["jobs"]), "; ".join(sorted(m["closes"])),
                p["success_metric"], ", ".join(p["builds_on"]) or "new", "; ".join(p["deliverables"])]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row, c, v)
            cell.font = Font(name=FONT, size=10)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = BORDER
        # Count of jobs = number of lines in "Which jobs" (live, so editing the list updates it)
        ws.cell(row, 3).value = f'=IF(D{row}="",0,LEN(D{row})-LEN(SUBSTITUTE(D{row},CHAR(10),""))+1)'
    ws.freeze_panes = "B5"


def _summary(ws, n_rows: int) -> None:
    ws["A1"] = "Summary"
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    a = "Applications"
    first, last = FIRST_ROW, FIRST_ROW + max(n_rows, 1) - 1
    rng = lambda key: f"'{a}'!${get_column_letter(COL[key])}${first}:${get_column_letter(COL[key])}${last}"
    items = [
        ("Jobs with packets ready", f"=COUNTA({rng('job_id')})"),
        ("Applied", f'=COUNTIF({rng("applied")},"Yes")'),
        ("Not applied yet", "=B3-B4"),
        ("Recommended: apply now or after quick fixes",
         f'=COUNTIF({rng("recommend")},"Apply now")+COUNTIF({rng("recommend")},"Apply after quick fixes*")'),
        ("Recommended: build a project first", f'=COUNTIF({rng("recommend")},"Build a project first*")'),
        ("Paying $200K+ at the top of the range", f'=COUNTIF({rng("band")},"$200K+")'),
        ("Average fit score", f'=IFERROR(AVERAGE({rng("score")}),"-")'),
        ("Average readiness", f'=IFERROR(AVERAGE({rng("readiness")}),"-")'),
    ]
    _header(ws, 2, ["Metric", "Value"], [46, 12])
    for i, (label, formula) in enumerate(items):
        ws.cell(3 + i, 1, label).font = Font(name=FONT)
        cell = ws.cell(3 + i, 2, formula)
        cell.font = Font(name=FONT)
        cell.number_format = "0"
        for c in (1, 2):
            ws.cell(3 + i, c).border = BORDER


def build(path: Path = PATH) -> dict:
    conn = core.connect()
    edits = read_user_edits(path)
    errors = {}
    recorded = apply_edits(conn, edits, errors)
    # Only failed application recordings need to stay visible for correction.
    # Merely having appeared in an older workbook must not defeat the status filter.
    rows = collect(conn, include_ids=errors)
    wb = Workbook()
    ws = wb.active
    ws.title = "Applications"
    _applications(ws, rows, edits, path)
    _gaps(wb.create_sheet("Gaps"), rows)
    _projects(wb.create_sheet("Projects"), rows)
    _summary(wb.create_sheet("Summary"), len(rows))
    visible = {r["job_id"] for r in rows}
    filtered_edits = {jid: e for jid, e in edits.items() if jid not in visible}
    if filtered_edits:
        saved = wb.create_sheet(SAVED_EDITS_SHEET)
        saved.append(["job_id", *USER_KEYS])
        for jid, e in sorted(filtered_edits.items()):
            saved.append([jid, *(e.get(k) for k in USER_KEYS)])
        saved.sheet_state = "hidden"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return {"path": path, "rows": len(rows), "recorded_applied": recorded, "errors": errors}
