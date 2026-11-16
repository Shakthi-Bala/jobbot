# Review fixes

The reported local code and repository-file issues are addressed. Tests use fictional profiles, temporary trackers, stubbed model calls, and actual document rendering. No real applications or outreach were sent.

| Report item | Result |
| --- | --- |
| 1. Invented skill headings | Only category labels supplied in the profile or its display-group preferences survive. |
| 2. Skipped claim lines | Generated claim text is flattened before checks and rendering. Tagged prose receives a claim prefix so leading comment markers cannot hide it. |
| 3. Inline fact-tag bypass | Model-supplied citation tags are removed to a fixed point, so nested tags cannot expose new evidence IDs. The tagged artifact uses validated citation lists. |
| 4. Rewritten saved answers | Answer-bank citations use the saved answer, including when facts are also cited. |
| 5. Dropped hiring restrictions | HTML entities in quotes are decoded before comparison and eligibility assessment. |
| 6. Trusted posting derivatives | Parsed requirements, source metadata, keyword diagnostics, and review documents remain untrusted data. Candidate requests and deterministic check failures are actionable, constrained by verified facts; reviewer and panel suggestions remain untrusted data; quoted excerpts in diagnostics remain data. Candidate requests persist across drafting rounds. |
| 7. Funding mistaken for pay | Million/billion range suffixes are excluded from salary extraction. |
| 8. Spreadsheet salary errors | Missing bounds display correctly; zero remains zero and a disclosed zero ceiling fails a positive salary floor. ATS adapters distinguish missing lower bounds from zero, but reject zero ceilings and impossible ranges as ambiguous board data and fall back to posting text. |
| 9. Panel approval bypass | ATS, hiring-manager, and reader gates must pass independently of editor flags or empty plans. |
| 10. Changed-posting state loss | Refreshes preserve skipped statuses and recorded application scores. |
| 11. Closure/application import | Automatically closed roles can be recorded as applied. Row errors are reported while remaining rows continue; failed application edits stay visible. Skipped/blocked/closed rows are filtered; their notes and dates survive in a hidden worksheet and return when the job is reopened. |
| 12. Unhandled errors | Contact URL validation and provider/posting failures are handled. Wrong-section entries are dropped before rendering. |
| 13. Partial matches | Exclusions and contact names/companies use phrase boundaries. GitHub Pages tenants count separately. Preference exclusions produce forceable skips; quoted eligibility conflicts remain blocked. |
| 14. Numeric provenance | Numeric and English-word cardinal/decimal quantities, common multiplicative claims, and recognized units (including hyphenated units) are checked. Entry dates cannot supply achievement numbers; numbers in product names permit only those names. |
| 15. Smaller issues | Both renderers honor disabled summaries. Approved wording preserves operators. Dashboard reports are plain text. Revoked Gmail refresh tokens request authorization. Calendar dates and follow-up calculations use UTC. |
| Privacy and housekeeping | Root PDF ignore patterns reveal no filenames. The school fixture is fictional. New privacy hooks bind to the installing interpreter and report scan errors accurately. Phone separators, runtime logs, spreadsheet files, and Streamlit secrets are protected. |
| Configuration and badge | `models.example.yaml` is tracked; local `models.yaml` remains ignored and is preserved by initialization. The badge targets `main`. |

`tests/test_review_fixes.py` adds adversarial and integration regressions. Existing tests were updated where they asserted the behavior being fixed. The local suite includes the offline demo, real PDF checks, nested-citation attacks, instruction routing, salary-floor boundaries, filtered-sheet edit restoration, and number-word/unit regressions.

These fixes do not rewrite Git history or change repository visibility. GitHub repository topics require authenticated repository-metadata access and are separate from the source changes. Suggested topics: `job-search`, `resume`, `python`, `robotics`, `human-in-the-loop`.

Numeric provenance checks cover recognized quantities and common multiplier wording; semantic accuracy still requires reviewing claims against their evidence. External services and paid model calls were not exercised.


The [follow-up audit](review-followup-2026-11-16.md) records the subsequent regression fixes and which report claims could not be reproduced.
