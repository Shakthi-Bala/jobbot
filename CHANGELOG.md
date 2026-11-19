# Changelog

## Unreleased

- Apply evidence-bounded XYZ guidance to tailored and master-resume drafting and editor review; allow approved wording to be rephrased without losing facts, caveats or candidate review.
- Use a dynamic release badge; permit only the configured public repository's badge URL in privacy scans.
- Vary fictional reader scores, show review rounds before the packet result in the GIF, and retain demo validation when Python runs with optimization.
- Show a supported wording revision across two real offline-demo panel rounds; include the reviewer feedback and redraft in the README recording, with fixture scores clearly labeled.

## 1.0.0 — 2026-11-17

### Correctness and reliability

- Preserve currency-anchored pay ranges after level/band/tier/step labels; a dollar sign on a later endpoint cannot anchor an earlier table number. Keep valid shared-code and trailing-USD ranges.
- Treat total-compensation/OTE labels before base-pay explanatory wording, and keep delimiter commas outside monetary amounts.
- Normalize numeric and spelled-out ordinal ranks after ranking verbs and before “of N,” so unrelated cardinal values cannot supply rank evidence and equivalent honest ranks compare consistently.

- Distinguish degrees of freedom from angles; check hyphenated rankings, placement verbs, half-dozen counts, and large number words without a following noun.
- Honor bracketed and trailing-only currency codes, keep foreign ranges separate from US pay, and retain base ranges that explicitly exclude bonus or equity.
- Keep all outreach failures in the check report and log every failing check's count and report path instead of truncating diagnostic wrappers.
- Run the full CI suite even when the separate regression-corpus step fails.
- Require documented tool/version pairs for version exemptions; preserve percentages and count nouns, and prevent version-label source numbers from supporting unrelated metrics.
- Check bare-word team/mentorship counts and ordinals in ranking contexts. Keep technical version modifiers distinct from deployment counts.
- Classify salary ranges independently so bonus mentions cannot suppress base pay; exclude RSUs/OTE/equity and preserve currency metadata during ATS fallback.
- Use a shared diagnostic formatter for reflected source/document fields. Allow one day of application-date timezone slack and treat whitespace dates as blank.
- Gate CI on fixed positive/adversarial sentence corpora and authored/public salary snapshots before the full suite; retain regression expectations for future changes.

- Check spelled-out quantities in measurement/count context while allowing procedural one-at-a-time wording, verified tool versions, supported document counts, and cited education dates in calendar/graduation prose. Detect plural dozens, “by half,” and “order of magnitude.”
- Wrap source questions, live titles, and restriction quotations as untrusted excerpts within deterministic diagnostics. Print only declared application questions verified against posting text; block unknown labels and missing question provenance.
- Keep annual-sized pay from being multiplied by monthly payment cadence; exclude stipends, allowances, and bonuses from base-pay ranges. Preserve salary ranges followed by `M&A` or `B.S.` labels.
- Reject future application dates, print collected sheet errors from the CLI, and cap hidden saved edits at 1,000 meaningful rows. Preserve overflow notes in an ignored private JSON archive.
- Use an offline Public Suffix List for contact-source domains, distinguishing separate `co.uk` publishers while retaining independent private-hosting tenants.

- Exempt ordinary idioms such as “one of” and “zero-copy” without exempting actual zero/one measurements. Expand compact/scaled numbers, dozen counts, and common multipliers; distinguish currency from distance and comma-separated years from grouped thousands.
- Preserve feedback origin: candidate requests and deterministic check failures remain actionable; reviewer and panel suggestions are wrapped as untrusted data.
- Parse salary ranges followed by `m/w/d` or `M-F`, annualize monthly pay, and exclude `mm`/`mil` funding suffixes. Fall back to posting text for invalid or zero-ceiling board ranges.
- Match paragraph rewrites by stable source identity; preserve omitted paragraphs and reject duplicate identities. Deduplicate resume entries, protect LaTeX bracketed bullets, and stop rejected panels without actionable revisions.
- Preserve Greenhouse EU hosts, isolate malformed ingested postings, and scope missing-posting detection to each board.
- Keep spreadsheet collection read-only and honor entered application dates for recorded actions and follow-up schedules. Write refreshed tokens atomically with private permissions; normalize whitespace in privacy identities and recognize Unicode/slash phone separators.
- Scope education dates to verified education labels and cited calendar/graduation prose, bind counts to recognized nouns, and check unquoted question labels for numerical assertions. Numerical provenance remains a bounded check rather than proof of a claim's meaning.

- Restrict generated skill headings to profile labels; flatten claim text and remove model-supplied citation tags, including recursively exposed nested tags, before rendering and checking.
- Preserve saved answer-bank wording even when the writer also cites facts; decode restriction quotations before comparing them with postings.
- Keep posting data and its derivatives untrusted while treating candidate revision requests and deterministic check failures as actionable requirements bounded by verified facts. Retain candidate requests throughout revision rounds.
- Ignore funding ranges with million/billion suffixes; preserve zero salary bounds, enforce the salary floor for a disclosed zero ceiling, and display maximum-only pay in spreadsheets.
- Require passing reader verdicts for panel approval; an empty revision plan or editor flag cannot waive rejection.
- Preserve manual skips and recorded fit scores when postings change. Allow recording an application after an automatic closure and continue spreadsheet imports after row errors without losing edits.
- Filter skipped, blocked, and closed spreadsheet rows on refresh; preserve their notes and dates in a hidden worksheet and restore them if the job returns. Keep failed application recordings visible for correction.
- Handle malformed contact URLs, people-search failures, posting-fetch failures, wrong-section entry IDs, and revoked Gmail tokens.
- Match exclusions and contact identities as whole phrases; distinguish independent GitHub Pages tenants.
- Check fractional quantities, English cardinal and decimal number words, multiplicative wording, and hyphenated measurement units; keep entry dates from supporting achievement numbers.
- Honor disabled summaries in Typst, preserve comparison operators in approved wording, render external dashboard content as plain text, and use UTC calendar dates consistently.
- Distinguish Greenhouse public postings that share an internal requisition, preserving existing application history by public URL during migration.
- Handle missing salary bounds and shared-unit ranges such as `$120–150K`.
- Convert provider failures, missing text, and invalid JSON into recoverable workflow errors. Record input/output/cache token counts.
- Preserve later daily-run stages when an expected discovery or fit error occurs.
- Recheck automatically closed postings and reopen rediscovered roles without overwriting recorded outcomes.
- Quote paused commands correctly and validate job paths and evaluation arguments.
- Compare actual evaluation packet directories and isolate evaluation logs, tasks, and databases.
- Make dashboard browsing read-only and protect recorded application states from draft controls.
- Require explicit interactive Gmail authorization before unattended alert ingestion.

### Input and privacy checks

- Block the private spreadsheet notes archive (`data/applications.edits.json`) in outgoing commits, including forced additions of this ignored file.
- Ignore root-level PDFs without naming private files; protect runtime logs and Streamlit secrets and detect phone separator variants.
- Install the privacy hook with the current Python interpreter and distinguish scan failures from detected private data.
- Escape untrusted data wrappers and separate posting warnings from generated-output contamination checks.
- Validate contact-source addresses and every redirect; pin connections to approved public IPs and bound response sizes.
- Inspect committed contents in every outgoing commit before push, independently of the working tree.
- Extract PDF text and metadata, flag uninspectable documents and binaries, and record reviewed synthetic media hashes.

### Contributor experience

- Consolidate review fixes here and remove internal process notes from public documentation.
- Preserve API mode for existing model configurations; use the explicit manual example when local configuration is absent.
- Ship `models.example.yaml` and retain ignored local `models.yaml` settings; point the CI badge at `main`.
- Add an MIT license and Python 3.10/3.12 CI with Typst and PDF tools.
- Require Streamlit 1.49 or newer for the dashboard's `width="stretch"` API ([release notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2025#version-1490)).
- Document manual task answering in AGENTS.md and CLAUDE.md.
- Replace project-derived examples with clearly fictional fixtures and use an 11-point Typst body.
- Add an isolated offline CLI demo with recorded answers, a real PDF preview, captured terminal output, and clearly labeled fixture review scores.

## Earlier fixes

- Save immutable document versions and submitted résumé hashes.
- Resume manual packet builds with durable checkpoints and bounded review rounds.
- Enforce required letters/questions and preserve approved answer-bank values.
- Keep unresolved eligibility questions distinct from quoted disqualifying restrictions.
- Require each reader to meet a configured panel target; retain raw findings and artifact hashes.

## Validation

The revised suite passes **720 tests**, including the fixed numerical and salary corpora, adversarial claim-generation cases, the offline CLI demo, actual PDF rendering and extraction, a Streamlit dashboard integration check, outgoing-history privacy scans, network-target restrictions, and application-state regressions. This local run used Python 3.13 with a LaTeX compiler available. The synthetic demo also passes all 11 packet checks. GitHub Actions is configured for Python 3.10 and 3.12; hosted run status is reported by the workflow badge.

## Known limits

- Fact IDs and numeric matching establish provenance and detect specific mistakes; they do not prove the meaning or truth of every claim.
- Built-in review personas are text-only AI assessments, not employer decisions. Inspect the actual PDF separately.
- Salary extraction, location matching, and source-domain independence remain approximate.
- There is no enforced API spending budget or concurrent packet-build lock.
- Manual tasks require an assistant or person to supply answers. Real applications and recruiter outreach remain manual.
- Privacy checks use known identifiers and configured secrets; they cannot inspect every unknown secret, hosted cache, fork, or prior clone.
