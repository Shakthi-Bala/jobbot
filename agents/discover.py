"""Discovery agent: poll public ATS boards, alert emails and web search; store new roles.

Plain software except the requirements parse (one cheap LLM call per *new* posting).
Re-running is safe: jobs are keyed by hash(company, title, location).
"""
from __future__ import annotations

import base64
import html
import re
from datetime import datetime, timezone
from typing import Iterable

import httpx
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

from . import core
from .schemas import ParsedPosting

UA = {"User-Agent": "jobbot/1.0 (personal job search; human-in-the-loop)"}
TIMEOUT = httpx.Timeout(30.0)

ATS_URL_PATTERNS = {
    "greenhouse": re.compile(
        r"https?://(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_app\?for=)?"
        r"([\w-]+)/jobs/(\d+)"),
    "lever": re.compile(r"https?://jobs\.lever\.co/([\w.-]+)/([0-9a-f-]{36})"),
    "ashby": re.compile(r"https?://jobs\.ashbyhq\.com/([\w.%-]+)/([0-9a-f-]{36})"),
}
ATS_DOMAINS = ["boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co",
               "jobs.ashbyhq.com"]
HIDDEN_STYLE_RE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|"
    r"color\s*:\s*(?:#fff\b|#ffffff\b|white\b|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))",
    re.I)


# ------------------------------------------------------------ fetchers

def _get(url: str, **params) -> httpx.Response:
    r = httpx.get(url, params=params or None, headers=UA, timeout=TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return r


def html_to_text(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def hidden_text_flags(raw_html: str) -> list[str]:
    """Text styled to be invisible to a human reader, a common injection trick."""
    flags = []
    soup = BeautifulSoup(raw_html or "", "html.parser")
    for el in soup.find_all(style=HIDDEN_STYLE_RE):
        text = el.get_text(" ", strip=True)
        if text:
            flags.append(f"hidden text: {text[:200]}")
    return flags


def _pay(lo, hi, text: str, source: str) -> dict:
    listed = lo is not None or hi is not None
    return {"comp_min": int(lo) if lo is not None else None,
            "comp_max": int(hi) if hi is not None else None,
            "comp_currency": "USD" if listed else None, "comp_text": text or None,
            "comp_source": source if listed else None}


def _pay_from_text(text: str) -> dict:
    found = core.parse_pay_text(text)
    if not found:
        return _pay(None, None, None, None)
    return _pay(*found, f"${found[0]:,} - ${found[1]:,} (from posting text)", "text")


def _greenhouse_job(slug: str, j: dict) -> dict:
    content = html.unescape(j.get("content") or "")
    text = html_to_text(content)
    return _pay_from_text(text) | {
        "company": j.get("company_name") or slug, "title": j["title"],
        "location": (j.get("location") or {}).get("name", ""),
        # One internal requisition can have several separately published postings.
        "req_id": str(j["id"]),
        # Branded career-page URLs cannot be re-fetched by our ATS adapter.
        # Keep the public board identity available to packet/checks.
        "url": f"https://job-boards.greenhouse.io/{slug}/jobs/{j['id']}",
        "source": "greenhouse",
        "posted_at": j.get("first_published") or j.get("updated_at"),
        "raw_text": text, "raw_html": content,
    }


def _lever_job(slug: str, j: dict) -> dict:
    parts = [j.get("descriptionPlain") or ""]
    raw_html = j.get("description") or ""
    for lst in j.get("lists", []):
        parts.append(lst.get("text", ""))
        parts.append(html_to_text(lst.get("content", "")))
        raw_html += lst.get("content", "")
    parts.append(j.get("additionalPlain") or "")
    created = j.get("createdAt")
    raw_text = "\n\n".join(p for p in parts if p).strip()
    sr = j.get("salaryRange") or {}
    if sr.get("max") and sr.get("currency", "USD") == "USD":
        mult = core.HOURS_PER_YEAR if "hour" in (sr.get("interval") or "") else 1
        pay = _pay(sr["min"] * mult if sr.get("min") is not None else None, sr["max"] * mult,
                   f"${sr.get('min')}-${sr['max']} {sr.get('interval', '')}", "ats")
    else:
        pay = _pay_from_text(raw_text)
    return pay | {
        "company": slug, "title": j["text"],
        "location": (j.get("categories") or {}).get("location", ""),
        "req_id": j["id"], "url": j.get("hostedUrl"), "source": "lever",
        "posted_at": datetime.fromtimestamp(created / 1000, timezone.utc).date().isoformat()
        if created else None,
        "raw_text": raw_text, "raw_html": raw_html,
    }


def _ashby_job(slug: str, j: dict) -> dict:
    raw_html = j.get("descriptionHtml") or ""
    raw_text = j.get("descriptionPlain") or html_to_text(raw_html)
    comp = j.get("compensation") or {}
    salary = [c for c in comp.get("summaryComponents", [])
              if c.get("compensationType") == "Salary" and c.get("maxValue")
              and (c.get("currencyCode") or "USD") == "USD"]
    if salary:
        c = salary[0]
        mult = core.HOURS_PER_YEAR if "HOUR" in (c.get("interval") or "") else 1
        pay = _pay((c.get("minValue") or 0) * mult, c["maxValue"] * mult,
                   comp.get("compensationTierSummary"), "ats")
    else:
        pay = _pay_from_text(raw_text)
    return pay | {
        "company": slug, "title": j["title"], "location": j.get("location", ""),
        "req_id": j["id"], "url": j.get("jobUrl"), "source": "ashby",
        "posted_at": (j.get("publishedAt") or "")[:10] or None,
        "raw_text": raw_text, "raw_html": raw_html,
    }


def fetch_board(ats: str, slug: str) -> list[dict]:
    if ats == "greenhouse":
        data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", content="true").json()
        return [_greenhouse_job(slug, j) for j in data.get("jobs", [])]
    if ats == "lever":
        data = _get(f"https://api.lever.co/v0/postings/{slug}", mode="json").json()
        return [_lever_job(slug, j) for j in data]
    if ats == "ashby":
        data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                    includeCompensation="true").json()
        return [_ashby_job(slug, j) for j in data.get("jobs", []) if j.get("isListed", True)]
    raise core.JobbotError(f"Unsupported ATS {ats!r} (use greenhouse, lever or ashby)")


def parse_ats_url(url: str) -> tuple[str, str, str] | None:
    for ats, pattern in ATS_URL_PATTERNS.items():
        m = pattern.match(url)
        if m:
            return ats, m.group(1), m.group(2)
    return None


def fetch_by_url(url: str) -> dict | None:
    """Fetch one live posting from its public ATS URL. None if it's gone.

    Used by discovery (alert emails, web search) and by checks/req_match.py.
    """
    parsed = parse_ats_url(url)
    if not parsed:
        return None
    ats, slug, job_id = parsed
    try:
        if ats == "greenhouse":
            j = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}").json()
            return _greenhouse_job(slug, j)
        if ats == "lever":
            j = _get(f"https://api.lever.co/v0/postings/{slug}/{job_id}").json()
            return _lever_job(slug, j)
        if ats == "ashby":
            for job in fetch_board("ashby", slug):
                if job["req_id"] == job_id:
                    return job
            return None
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise
    return None


# ------------------------------------------------------------- filters

def _has_word(phrase: str, text: str) -> bool:
    """Whole-word match, so 'RL' doesn't match 'world' and 'Intern' doesn't match 'Internal'."""
    return re.search(rf"(?<![\w]){re.escape(phrase.lower())}(?![\w])", text) is not None


def matches_targets(job: dict, targets: dict) -> tuple[bool, str]:
    title = job["title"].lower()
    for kw in targets.get("exclude_keywords", []):
        if _has_word(kw, title):
            return False, f"title contains excluded keyword {kw!r}"
    titles = targets.get("titles", [])
    includes = targets.get("include_keywords", [])
    norm_title = core.normalize(title)  # strip punctuation: "Engineer," must match "Engineer"
    # token_sort, not token_set: extra words count against the match, so
    # "Mechanical Engineer, Robotics" no longer matches "Robotics Engineer".
    title_hit = any(fuzz.token_sort_ratio(core.normalize(t), norm_title) >= 85 for t in titles)
    kw_hit = any(_has_word(k, title) for k in includes)
    if titles and not (title_hit or kw_hit):
        return False, "title does not match any target title or keyword"
    locations = targets.get("locations", [])
    if locations and job.get("location"):
        loc = job["location"].lower()
        wanted = {l.split(",")[0].strip().lower() for l in locations}
        remote_ok = any("remote" in l.lower() for l in locations)
        if not (any(w and w in loc for w in wanted) or (remote_ok and "remote" in loc)):
            return False, f"location {job['location']!r} not in targets"
    return True, "matches targets"


# --------------------------------------------------------------- parse

def parse_posting(job: dict) -> ParsedPosting:
    return core.llm_json(
        "discovery_parse",
        core.system_prompt("discover"),
        core.untrusted('job_metadata', core.dumps({k: job[k] for k in ('company', 'title', 'location')})) + '\n\n'
        + core.untrusted("posting", job["raw_text"]),
        ParsedPosting,
        max_tokens=4000,
    )


def verify_quotes(parsed: ParsedPosting, raw_text: str) -> list[str]:
    """Drop restrictions whose quote isn't verbatim in the posting. Returns dropped quotes."""
    kept, dropped = [], []
    for r in parsed.restrictions:
        r.quote = html.unescape(r.quote)
        (kept if core.quote_in_text(r.quote, raw_text) else dropped).append(r)
    parsed.restrictions = kept
    return [r.quote for r in dropped]


# --------------------------------------------------------------- store

def apply_parse(conn, job_id: str, raw_text: str, parsed: ParsedPosting, raw_html: str,
                targets: dict) -> bool:
    """Store a parse result after rules-as-code. False if the job is now excluded."""
    for q in verify_quotes(parsed, raw_text):
        core.log_decision("discover", job_id, "dropped_restriction",
                          f"quote not found verbatim: {q[:120]}")
    data = parsed.model_dump()
    data["injection_flags"] = hidden_text_flags(raw_html)
    if parsed.injection_attempt:
        data["injection_flags"].append(f"model flagged: {parsed.injection_attempt}")
    conn.execute("UPDATE jobs SET parsed_json=?, deadline=COALESCE(deadline, ?) WHERE id=?",
                 (core.dumps(data), parsed.deadline, job_id))
    max_years = targets.get("max_years_experience")
    if (max_years is not None and (parsed.min_years_experience or 0) > max_years
            and may_reopen(conn, job_id)):
        conn.execute("UPDATE jobs SET status='skipped' WHERE id=?", (job_id,))
        core.log_decision("discover", job_id, "excluded",
                          f"requires {parsed.min_years_experience}+ years")
        conn.commit()
        return False
    conn.commit()
    return True


def posting_id(conn, job: dict) -> str:
    """Preserve legacy IDs while distinguishing new requisitions."""
    public = parse_ats_url(job.get("url") or "")
    if public and public[0] == "greenhouse":
        # Adopt the old row by its public URL when migrating away from shared
        # internal requisitions. Preserve its document/action foreign keys.
        for row in conn.execute("SELECT id, url FROM jobs WHERE company=?", (job["company"],)):
            if parse_ats_url(row["url"] or "") == public:
                return row["id"]
    req_id = str(job.get("req_id") or "").strip() or None
    if req_id:
        row = conn.execute("SELECT id, url FROM jobs WHERE company=? AND req_id=?",
                           (job["company"], req_id)).fetchone()
        other_public = parse_ats_url(row["url"] or "") if row else None
        if row and not (public and other_public and public != other_public):
            return row["id"]
    legacy = core.job_id_for(job["company"], job["title"], job.get("location", ""))
    row = conn.execute("SELECT req_id FROM jobs WHERE id=?", (legacy,)).fetchone()
    if row and (str(row["req_id"] or "").strip() or None) == req_id:
        return legacy
    return core.job_id_for(job["company"], job["title"], job.get("location", ""), req_id)


def may_reopen(conn, job_id: str) -> bool:
    """Only automatically reopen closures without a recorded human outcome."""
    return conn.execute("SELECT 1 FROM actions WHERE job_id=? AND action IN "
                        "('applied','responded','interview','rejected','offer','closed') LIMIT 1",
                        (job_id,)).fetchone() is None


def upsert_jobs(conn, jobs: Iterable[dict], targets: dict, parse: bool = True,
                min_pay: int = 0) -> list[str]:
    """Insert new matching jobs, refresh known ones. Returns new job IDs.

    In manual mode the requirements parse becomes a task; the job is stored with
    parsed_json NULL and fit.run() picks the parse up once Claude has answered.
    """
    new_ids = []
    for job in jobs:
        jid = posting_id(conn, job)
        comp = (job.get("comp_min"), job.get("comp_max"), job.get("comp_currency"),
                job.get("comp_text"), job.get("comp_source"))
        existing = conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        if existing:
            changed = existing["raw_text"] != job["raw_text"]
            reopened = existing['status'] == 'closed' and may_reopen(conn, jid)
            conn.execute(
                "UPDATE jobs SET last_verified=?, active=1, url=COALESCE(?, url), "
                "title=?, location=?, req_id=?, raw_text=?, raw_html=?, "
                "comp_min=COALESCE(?, comp_min), comp_max=COALESCE(?, comp_max), "
                "comp_currency=COALESCE(?, comp_currency), comp_text=COALESCE(?, comp_text), "
                "comp_source=COALESCE(?, comp_source) WHERE id=?",
                (core.now(), job.get("url"), job["title"], job.get("location", ""), job.get("req_id"),
                 job["raw_text"], job.get("raw_html", ""), *comp, jid))
            if changed or reopened:
                conn.execute("UPDATE jobs SET parsed_json=NULL, deadline=? WHERE id=?",
                             (job.get("deadline"), jid))
                # Recorded outcomes retain the assessment behind the application.
                preserve_history = (not may_reopen(conn, jid) or (
                    existing["status"] in ("applied", "responded", "interview", "rejected", "offer", "closed")
                    and not reopened))
                # Older dashboard skips were recorded only in the decision log;
                # conservatively retain skipped jobs rather than undoing that choice.
                if not preserve_history:
                    conn.execute("DELETE FROM fit WHERE job_id=?", (jid,))
                if reopened or (not preserve_history and existing["status"] != "skipped"):
                    conn.execute("UPDATE jobs SET status='discovered' WHERE id=?", (jid,))
                core.log_decision("discover", jid, "posting_changed",
                                  "stored posting refreshed; requirements invalidated; "
                                  + ("recorded fit retained" if preserve_history else "fit invalidated"))
                if reopened:
                    core.log_decision('discover', jid, 'reopened', 'previously unavailable posting is live again')
            continue
        ok, reason = matches_targets(job, targets)
        if not ok:
            continue  # not logged: most postings at a company are irrelevant
        if min_pay and job.get("comp_max") and job["comp_max"] < min_pay:
            core.log_decision("discover", jid, "excluded",
                              f"pay tops out at ${job['comp_max']:,} (< ${min_pay:,} minimum)",
                              [job.get("url") or ""])
            continue
        conn.execute(
            "INSERT INTO jobs (id, company, title, location, req_id, url, source, posted_at, "
            "deadline, first_seen, last_verified, active, raw_text, raw_html, parsed_json, status, "
            "comp_min, comp_max, comp_currency, comp_text, comp_source) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,NULL,'discovered',?,?,?,?,?)",
            (jid, job["company"], job["title"], job.get("location", ""), job.get("req_id"),
             job.get("url"), job["source"], job.get("posted_at"), job.get("deadline"),
             core.now(), core.now(), job["raw_text"], job.get("raw_html", ""), *comp),
        )
        conn.commit()
        core.log_decision("discover", jid, "new_job",
                          f"{reason}; pay {core.pay_band(job.get('comp_max'))}",
                          [job.get("url") or ""])
        new_ids.append(jid)
        if parse:
            try:
                apply_parse(conn, jid, job["raw_text"], parse_posting(job),
                            job.get("raw_html", ""), targets)
            except core.ManualTaskPending:
                pass  # answered later; fit.run() re-tries the parse
            except core.JobbotError as e:
                core.log_decision("discover", jid, "parse_failed", str(e), [job.get("url", "")])
    conn.commit()
    return new_ids


def mark_missing_inactive(conn, company: str, seen_ids: set[str]) -> int:
    rows = conn.execute("SELECT id FROM jobs WHERE company=? AND active=1 AND source IN "
                        "('greenhouse','lever','ashby')", (company,)).fetchall()
    gone = [r["id"] for r in rows if r["id"] not in seen_ids]
    for jid in gone:
        conn.execute("UPDATE jobs SET active=0 WHERE id=?", (jid,))
        core.log_decision("discover", jid, "inactive", "no longer on the company board")
    conn.commit()
    return len(gone)


# ------------------------------------------------------------- sources

def poll_boards(conn, targets: dict, min_pay: int = 0) -> list[str]:
    new_ids = []
    for c in core.load_companies():
        ats, slug = c.get("ats"), c.get("slug")
        if not ats or not slug:
            core.warn(f"skipping {c.get('name')}: needs ats + slug in companies.yaml")
            continue
        try:
            jobs = fetch_board(ats, slug)
        except (httpx.HTTPError, core.JobbotError, ValueError, TypeError, KeyError) as e:
            core.warn(f"{c.get('name')}: {e}")
            core.log_decision("discover", None, "board_error", f"{c.get('name')}: {e}")
            continue
        name = c.get("name") or slug
        for j in jobs:
            j["company"] = name
        new_ids += upsert_jobs(conn, jobs, targets, min_pay=min_pay)
        seen = {posting_id(conn, j) for j in jobs}
        mark_missing_inactive(conn, name, seen)
    return new_ids


def _company_name_for(slug: str) -> str:
    for c in core.load_companies():
        if c.get("slug") == slug:
            return c.get("name") or slug
    return slug


def ingest_urls(conn, urls: Iterable[str], targets: dict, source: str,
                min_pay: int = 0) -> list[str]:
    new_ids = []
    for url in dict.fromkeys(urls):
        try:
            job = fetch_by_url(url)
        except httpx.HTTPError as e:
            core.warn(f"{url}: {e}")
            continue
        if job is None:
            continue
        job["company"] = _company_name_for(parse_ats_url(url)[1])
        job["source"] = source
        new_ids += upsert_jobs(conn, [job], targets, min_pay=min_pay)
    return new_ids


def _authorize_gmail(creds_path, scopes, interactive):
    if not interactive:
        raise core.JobbotError('Gmail authorization required; run `python jobbot.py gmail-auth` interactively')
    from google_auth_oauthlib.flow import InstalledAppFlow
    return InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes).run_local_server(
        port=0, timeout_seconds=120)


def gmail_credentials(interactive: bool = False):
    creds_path = core.DATA / "credentials.json"
    if not creds_path.exists():
        return None
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    token_path = core.DATA / "token.json"
    creds = None
    if token_path.exists():
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            from google.auth.exceptions import RefreshError
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = _authorize_gmail(creds_path, scopes, interactive)
        else:
            creds = _authorize_gmail(creds_path, scopes, interactive)
        token_path.write_text(creds.to_json())
        token_path.chmod(0o600)
    return creds


def gmail_alert_urls(label: str = "jobbot/alerts", days: int = 3) -> list[str]:
    """Read alerts using existing credentials; never open an interactive login."""
    creds = gmail_credentials()
    if creds is None:
        return []
    from googleapiclient.discovery import build
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
    q = f'label:"{label}" newer_than:{days}d'
    msgs = svc.users().messages().list(userId="me", q=q, maxResults=100).execute()
    urls = []
    for m in msgs.get("messages", []):
        full = svc.users().messages().get(userId="me", id=m["id"], format="full").execute()
        for body in _walk_parts(full.get("payload", {})):
            urls += re.findall(r"https?://[^\s\"'<>]+", body)
    return [u for u in urls if parse_ats_url(u)]


def _walk_parts(part: dict) -> Iterable[str]:
    data = part.get("body", {}).get("data")
    if data:
        yield base64.urlsafe_b64decode(data + "==").decode("utf-8", "ignore")
    for p in part.get("parts", []) or []:
        yield from _walk_parts(p)


def web_search_urls(targets: dict, max_queries: int = 4) -> list[str]:
    """Ask Claude's web search for postings, restricted to public ATS domains."""
    titles = targets.get("titles", [])[:max_queries]
    if not titles or core.is_manual():
        return []  # manual mode: Claude searches in chat and runs `jobbot.py ingest URL...`
    cfg = core.model_for("fit")
    locations = ", ".join(targets.get("locations", [])) or "United States"
    prompt = (
        "Find currently open job postings for these roles: "
        + "; ".join(titles) + f". Locations: {locations}. Seniority: "
        + ", ".join(targets.get("seniority", [])) + ". Return the posting URLs."
    )
    messages = [{"role": "user", "content": prompt}]
    urls: list[str] = []
    for _ in range(3):  # resume pause_turn at most twice
        import anthropic
        try:
            resp = core.client().messages.create(
                model=cfg["model"], max_tokens=8000, messages=messages,
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8,
                        "allowed_domains": ATS_DOMAINS}],
            )
        except (anthropic.AnthropicError, httpx.HTTPError) as e:
            raise core.JobbotError(f'Web search request failed ({type(e).__name__})') from e
        core.record_usage('web_search', cfg['model'], resp)
        for block in resp.content:
            if block.type == "web_search_tool_result" and isinstance(block.content, list):
                urls += [r.url for r in block.content if getattr(r, "url", None)]
            elif block.type == "text":
                urls += re.findall(r"https?://[^\s)\]]+", block.text)
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    return [u for u in dict.fromkeys(urls) if parse_ats_url(u)]


def run(web: bool = True, alerts: bool = True) -> list[str]:
    profile = core.load_profile()
    targets = profile.get("targets", {})
    min_pay = core.min_salary(profile)
    conn = core.connect()
    new_ids = poll_boards(conn, targets, min_pay)
    if alerts:
        try:
            new_ids += ingest_urls(conn, gmail_alert_urls(), targets, "alert_email", min_pay)
        except Exception as e:  # optional source; never fail the run on it
            core.warn(f"gmail alerts skipped: {e}")
    if web:
        try:
            new_ids += ingest_urls(conn, web_search_urls(targets), targets, "web", min_pay)
        except Exception as e:
            core.warn(f"web search skipped: {e}")
    return sort_by_pay(conn, new_ids)


def sort_by_pay(conn, job_ids: list[str]) -> list[str]:
    """Highest pay first; unlisted pay last."""
    if not job_ids:
        return []
    rows = conn.execute(
        f"SELECT j.id FROM jobs j WHERE j.id IN ({','.join('?' * len(job_ids))}) "
        f"ORDER BY {core.PAY_ORDER_SQL}", job_ids).fetchall()
    return [r["id"] for r in rows]


def add_manual(company: str, title: str, text: str, location: str = "", url: str = "",
               req_id: str = "") -> str:
    """Phase 1 entry point: paste any JD. Skips target filtering."""
    conn = core.connect()
    job = {"company": company, "title": title, "location": location, "url": url or None,
           "req_id": req_id or None, "source": "manual", "raw_text": text, "raw_html": ""}
    job |= _pay_from_text(text)
    jid = posting_id(conn, job)
    if conn.execute("SELECT 1 FROM jobs WHERE id=?", (jid,)).fetchone():
        upsert_jobs(conn, [job], targets={}, parse=False)
        return jid
    ids = upsert_jobs(conn, [job], targets={}, parse=True)
    return ids[0] if ids else jid
