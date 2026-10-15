-- jobbot tracker schema. Safe to re-run: every statement is idempotent.

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,               -- hash(company, norm_title, location)
  company TEXT, title TEXT, location TEXT, req_id TEXT,
  url TEXT, source TEXT,             -- greenhouse | lever | ashby | alert_email | web | manual
  posted_at TEXT, deadline TEXT, first_seen TEXT, last_verified TEXT,
  active INTEGER DEFAULT 1,
  raw_text TEXT,                     -- stored posting (untrusted data)
  parsed_json TEXT,                  -- must_have, nice_to_have, restrictions...
  status TEXT DEFAULT 'discovered',  -- pipeline status, see README section 9
  comp_min INTEGER, comp_max INTEGER,-- annual base pay in USD, from the posting
  comp_currency TEXT, comp_text TEXT, comp_source TEXT   -- ats | text
);

CREATE TABLE IF NOT EXISTS fit (
  job_id TEXT PRIMARY KEY REFERENCES jobs(id),
  score INTEGER, strengths_json TEXT, gaps_json TEXT,
  restrictions_json TEXT,            -- each with verbatim quote
  unknowns_json TEXT, questions_json TEXT,
  decision TEXT,                     -- shortlist | skip | blocked
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT, kind TEXT,            -- resume | cover_letter | answers | outreach
  path TEXT, sha256 TEXT, version INTEGER,
  review_status TEXT,                -- pending | changes_requested | passed
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT, name TEXT, role TEXT, company TEXT,
  sources_json TEXT,                 -- >=2 URLs confirming identity
  reason TEXT, channel TEXT,
  status TEXT,                       -- drafted | sent | replied | referral | no_reply
  sent_at TEXT, next_followup TEXT,
  created_at TEXT,
  UNIQUE (company, name)
);

CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT, actor TEXT,           -- agent name or "me"
  action TEXT,                       -- applied | sent | replied | interview | rejected | offer
  detail TEXT, doc_id INTEGER, at TEXT
);

CREATE TABLE IF NOT EXISTS followups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT, contact_id INTEGER, due TEXT, note TEXT, done INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_docs_job ON documents(job_id);
CREATE INDEX IF NOT EXISTS idx_followups_due ON followups(due, done);
