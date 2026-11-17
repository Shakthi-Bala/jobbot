# Follow-up to the review at `ae03621`

The reported cases are covered by regression tests with fictional evidence and temporary trackers. Tests, dependency installation, and rendering run through Slurm. Changes are pushed directly to `main` as authorized.

| Finding | Result and coverage |
| --- | --- |
| Procedural “one” wording and one-stage detector | Specific procedural idioms are allowed. Other spelled-out numbers enter claim checks when followed by a recognized count noun or unit. Actual “one engineer” and nearby invented performance numbers still fail. `tests/test_number_context.py` |
| Tool versions and project descriptions | Known tools supported by the profile/cited facts may carry a version label. Removing a version does not exempt unrelated metrics. Descriptions such as “Two projects show…” are checked against available project counts. `tests/test_number_context.py` |
| Education dates in prose | Cited school start/end dates support their actual month/year labels, and the end year supports graduation/expected wording. An unsupported month or the same year reused as a performance quantity still fails. `tests/test_number_context.py` |
| “dozens of”, “by half”, “order of magnitude” | Recognized as approximate-count or multiplicative claims and require matching source evidence. `tests/test_number_context.py` |
| Posting text in trusted diagnostics | Missing questions, live titles, and restriction excerpts are escaped and wrapped as untrusted data. The deterministic failure remains actionable. Tests inspect the assembled writer prompt using instruction-shaped source text. `tests/test_diagnostic_boundaries.py` |
| Monthly payment cadence, stipends, M&A and B.S. | Annual-sized amounts are not multiplied by twelve; explicit monthly amounts up to $30,000 can be annualized. Stipend/allowance/bonus components do not widen the base range. Degree/merger labels are distinct from funding suffixes. `tests/test_salary_parsing.py` |
| Future application dates and CLI row errors | Future dates are rejected before recording an action or follow-up. The command prints returned row errors; API callers can inspect the structured error mapping. `tests/test_sheet_filter.py` |
| Hidden saved-edits growth | Blank/default rows are not archived. The hidden tab is capped at 1,000 meaningful rows, with overflow retained in a private, atomic, ignored sidecar. Tests reduce the cap and verify that every note survives refresh. `tests/test_sheet_filter.py` |
| Public-suffix source domains | Separate publishers such as BBC and Acme under `co.uk` count separately. Private hosting tenants remain separate; lookups cannot fetch a suffix list over the network. `tests/test_contact_domains.py` |
| Invented questions without numbers | Only declared questions quoted in posting text are printed, using the source label. Checks block tampered labels and parser-invented questions without provenance. `tests/test_question_sources.py` |

Domain extraction uses the bundled snapshot in [tldextract](https://github.com/john-kurkowski/tldextract#how-to-disable-http-suffix-list-fetching), with remote fetching and disk caching disabled and private suffixes enabled.

Validation: the full Slurm suite passed **412 tests**, including the offline CLI demo, master-resume rendering, real PDF checks, and adversarial provenance cases. The code tested includes the master-document fix at `e8dba8d`.

These are bounded provenance and formatting checks. They do not establish every paraphrase's meaning, ownership of a technical contribution, the quality of an evaluation, or an interview probability. No numerical rating is inferred from test success. No real applications or recruiter outreach were sent.
