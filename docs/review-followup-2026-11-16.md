# Review follow-up: 2026-11-16

For the subsequent review of `ae03621`, see the [latest follow-up](review-at-ae03621.md).

This follow-up checks the report against the code merged at `5daa579` (the source tree from `73e212d`). Fixes are committed incrementally on `dev`. Tests use fictional evidence, temporary trackers, mocked services, and actual local document rendering. Test and rendering jobs run through Slurm.

| Finding | Outcome and regression coverage |
| --- | --- |
| “one of”, “no one else”, “one-hot”, “zero-copy” false positives | Confirmed and fixed using specific idiom exemptions. Actual zero/one counts, compound numbers, and nearby measurements remain checked. See `tests/test_number_words.py`. |
| Reviewer/panel suggestions treated as instructions | Confirmed and fixed by retaining the origin of each feedback item. Only code-check failures enter the actionable diagnostic section. Reviewer/panel text is escaped and wrapped as untrusted data; local candidate requests remain actionable. See `tests/test_review_fixes.py`. |
| `m/w/d`, `M-F`, `mm`, `mil`, and monthly salaries | Confirmed and fixed. Employment labels do not imply millions; funding suffixes are rejected; explicit monthly pay is annualized. See `tests/test_salary_parsing.py`. |
| `24k`, `24 thousand`, money, dozen counts, vague hundreds, and tenfold | Confirmed and fixed for these forms. Currency quantities are distinct from distance; vague counts require matching evidence instead of borrowing an unrelated literal value. See `tests/test_number_words.py`. |
| Education dates, count nouns, comma-separated years | Confirmed and fixed. Dates support exact education labels only; recognized count nouns cannot borrow throughput values; `2023,2024` yields two numbers. See `tests/test_number_words.py`. |
| Question labels bypass numerical checks | Confirmed and fixed for numerical assertions. An exact question quoted from the posting remains input data; other labels receive number checks. Existing injection checks also inspect the human-facing answers document. Qualitative presuppositions still require human review. |
| Board placeholders and inverted pay ranges | Defensive handling added; the report did not establish that providers actually emit placeholders. Non-finite, nonpositive-ceiling, negative, and inverted ranges fall back to posting text. A genuine zero lower bound with a positive ceiling remains valid. See `tests/test_salary_floor.py`. |
| Paragraph loss/duplication, duplicate entries, LaTeX bracket labels | Confirmed and fixed. Rewrites carry source indexes, ambiguous rewrites fall back to original paragraphs, entries are deduplicated, and an empty TeX group prevents bracketed prose becoming a bullet label. See `tests/test_pipeline_identity.py`. |
| Rejected panel with no actions redrafts repeatedly | Confirmed and fixed: stop after that panel result and report the unmet gate. See `tests/test_pipeline_identity.py`. |
| EU Greenhouse routing, malformed ingest, same-name board deactivation | Confirmed and fixed in mocked adapter tests. Region survives URL normalization; ingestion continues after malformed responses; missing-job detection is scoped to board identity. Live provider behavior was not exercised. See `tests/test_discovery_regions.py`. |
| Spreadsheet creates folders and ignores application dates | Confirmed and fixed. Collection is read-only; entered dates control application timestamps and follow-up due dates. See `tests/test_sheet_filter.py`. |
| Spreadsheet never prints row errors | Not reproduced: `apply_edits` already calls `core.warn` on stderr. Added coverage also confirms invalid dates are reported without recording an application. |
| Token file permissions and implicit mode selection | Confirmed and fixed. Secrets are written to a private temporary file before atomic replacement. Existing model configuration without a mode retains the API default; absent local configuration uses the explicit manual example. See `tests/test_config_privacy_followup.py`. |
| Unicode/slash phones and whitespace-varied names | Confirmed and fixed by phone-separator recognition and whitespace normalization in both identifiers and scanned text. See `tests/test_config_privacy_followup.py`. |

These changes do not alter repository visibility, rewrite history, submit applications, or send recruiter messages. Numerical checks cover supported forms and recognized units/count nouns; they do not establish attribution, causal claims, evaluation quality, or every possible English paraphrase. Scores and interview odds are not inferred from passing tests.
