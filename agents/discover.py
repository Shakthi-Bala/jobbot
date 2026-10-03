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


def _greenhouse_job(slug: str, j: dict) -> dict:
    content = html.unescape(j.get("content") or "")
    return {
        "company": j.get("company_name") or slug, "title": j["title"],
        "location": (j.get("location") or {}).get("name", ""),
        "req_id": str(j.get("requisition_id") or j.get("internal_job_id") or j["id"]),
        "url": j.get("absolute_url"), "source": "greenhouse",
        "posted_at": j.get("first_published") or j.get("updated_at"),
        "raw_text": html_to_text(content), "raw_html": content,
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
    return {
        "company": slug, "title": j["text"],
        "location": (j.get("categories") or {}).get("location", ""),
        "req_id": j["id"], "url": j.get("hostedUrl"), "source": "lever",
        "posted_at": datetime.fromtimestamp(created / 1000, timezone.utc).date().isoformat()
        if created else None,
        "raw_text": "\n\n".join(p for p in parts if p).strip(), "raw_html": raw_html,
    }


def _ashby_job(slug: str, j: dict) -> dict:
    raw_html = j.get("descriptionHtml") or ""
    return {
        "company": slug, "title": j["title"], "location": j.get("location", ""),
        "req_id": j["id"], "url": j.get("jobUrl"), "source": "ashby",
        "posted_at": (j.get("publishedAt") or "")[:10] or None,
        "raw_text": j.get("descriptionPlain") or html_to_text(raw_html), "raw_html": raw_html,
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
        m = pattern.search(url)
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

def matches_targets(job: dict, targets: dict) -> tuple[bool, str]:
    title = job["title"].lower()
    for kw in targets.get("exclude_keywords", []):
        if kw.lower() in title:
            return False, f"title contains excluded keyword {kw!r}"
    titles = targets.get("titles", [])
    includes = targets.get("include_keywords", [])
    title_hit = any(fuzz.token_set_ratio(t.lower(), title) >= 85 for t in titles)
    kw_hit = any(k.lower() in title for k in includes)
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
        f"Company: {job['company']}\nTitle: {job['title']}\nLocation: {job['location']}\n\n"
        + core.untrusted("posting", job["raw_text"]),
        ParsedPosting,
        max_tokens=4000,
    )


def verify_quotes(parsed: ParsedPosting, raw_text: str) -> list[str]:
    """Drop restrictions whose quote isn't verbatim in the posting. Returns dropped quotes."""
    norm = core.normalize(raw_text)
    kept, dropped = [], []
    for r in parsed.restrictions:
        (kept if core.normalize(r.quote) in norm else dropped).append(r)
    parsed.restrictions = kept
    return [r.quote for r in dropped]


# --------------------------------------------------------------- store

def upsert_jobs(conn, jobs: Iterable[dict], targets: dict, parse: bool = True) -> list[str]:
    """Insert new matching jobs, refresh known ones. Returns new job IDs."""
    new_ids = []
    for job in jobs:
        jid = core.job_id_for(job["company"], job["title"], job.get("location", ""))
        existing = conn.execute("SELECT id, req_id FROM jobs WHERE id = ?", (jid,)).fetchone()
        if existing:
            conn.execute("UPDATE jobs SET last_verified=?, active=1, url=COALESCE(?, url) WHERE id=?",
                         (core.now(), job.get("url"), jid))
            continue
        ok, reason = matches_targets(job, targets)
        if not ok:
            continue  # not logged: most postings at a company are irrelevant
        parsed_json = None
        if parse:
            try:
                parsed = parse_posting(job)
            except core.JobbotError as e:
                core.log_decision("discover", jid, "parse_failed", str(e), [job.get("url", "")])
                parsed = None
            if parsed:
                dropped = verify_quotes(parsed, job["raw_text"])
                for q in dropped:
                    core.log_decision("discover", jid, "dropped_restriction",
                                      f"quote not found verbatim: {q[:120]}")
                data = parsed.model_dump()
                data["injection_flags"] = hidden_text_flags(job.get("raw_html", ""))
                if parsed.injection_attempt:
                    data["injection_flags"].append(f"model flagged: {parsed.injection_attempt}")
                max_years = targets.get("max_years_experience")
                if max_years is not None and (parsed.min_years_experience or 0) > max_years:
                    core.log_decision("discover", jid, "excluded",
                                      f"requires {parsed.min_years_experience}+ years")
                    continue
                parsed_json = core.dumps(data)
                job["deadline"] = parsed.deadline
        conn.execute(
            "INSERT INTO jobs (id, company, title, location, req_id, url, source, posted_at, "
            "deadline, first_seen, last_verified, active, raw_text, parsed_json, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,1,?,?,'discovered')",
            (jid, job["company"], job["title"], job.get("location", ""), job.get("req_id"),
             job.get("url"), job["source"], job.get("posted_at"), job.get("deadline"),
             core.now(), core.now(), job["raw_text"], parsed_json),
        )
        conn.commit()
        core.log_decision("discover", jid, "new_job", reason, [job.get("url") or ""])
        new_ids.append(jid)
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

def poll_boards(conn, targets: dict) -> list[str]:
    new_ids = []
    for c in core.load_companies():
        ats, slug = c.get("ats"), c.get("slug")
        if not ats or not slug:
            core.warn(f"skipping {c.get('name')}: needs ats + slug in companies.yaml")
            continue
        try:
            jobs = fetch_board(ats, slug)
        except (httpx.HTTPError, core.JobbotError) as e:
            core.warn(f"{c.get('name')}: {e}")
            core.log_decision("discover", None, "board_error", f"{c.get('name')}: {e}")
            continue
        name = c.get("name") or slug
        for j in jobs:
            j["company"] = name
        new_ids += upsert_jobs(conn, jobs, targets)
        seen = {core.job_id_for(name, j["title"], j.get("location", "")) for j in jobs}
        mark_missing_inactive(conn, name, seen)
    return new_ids


def _company_name_for(slug: str) -> str:
    for c in core.load_companies():
        if c.get("slug") == slug:
            return c.get("name") or slug
    return slug


def ingest_urls(conn, urls: Iterable[str], targets: dict, source: str) -> list[str]:
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
        new_ids += upsert_jobs(conn, [job], targets)
    return new_ids


def gmail_alert_urls(label: str = "jobbot/alerts", days: int = 3) -> list[str]:
    """URLs from job-alert emails. Requires data/credentials.json (gmail.readonly)."""
    creds_path = core.DATA / "credentials.json"
    if not creds_path.exists():
        return []
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    token_path = core.DATA / "token.json"
    creds = Credentials.from_authorized_user_file(str(token_path), scopes) \
        if token_path.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes) \
                .run_local_server(port=0)
        token_path.write_text(creds.to_json())
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
    if not titles:
        return []
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
        resp = core.client().messages.create(
            model=cfg["model"], max_tokens=8000, messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 8,
                    "allowed_domains": ATS_DOMAINS}],
        )
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
    conn = core.connect()
    new_ids = poll_boards(conn, targets)
    if alerts:
        try:
            new_ids += ingest_urls(conn, gmail_alert_urls(), targets, "alert_email")
        except Exception as e:  # optional source; never fail the run on it
            core.warn(f"gmail alerts skipped: {e}")
    if web:
        try:
            new_ids += ingest_urls(conn, web_search_urls(targets), targets, "web")
        except Exception as e:
            core.warn(f"web search skipped: {e}")
    return new_ids


def add_manual(company: str, title: str, text: str, location: str = "", url: str = "",
               req_id: str = "") -> str:
    """Phase 1 entry point: paste any JD. Skips target filtering."""
    conn = core.connect()
    job = {"company": company, "title": title, "location": location, "url": url or None,
           "req_id": req_id or None, "source": "manual", "raw_text": text, "raw_html": ""}
    jid = core.job_id_for(company, title, location)
    if conn.execute("SELECT 1 FROM jobs WHERE id=?", (jid,)).fetchone():
        return jid
    ids = upsert_jobs(conn, [job], targets={}, parse=True)
    return ids[0] if ids else jid
