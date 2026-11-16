# Changelog

## Unreleased — dev

### Correctness and reliability

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

- Escape untrusted data wrappers and separate posting warnings from generated-output contamination checks.
- Validate contact-source addresses and every redirect; pin connections to approved public IPs and bound response sizes.
- Inspect committed contents in every outgoing commit before push, independently of the working tree.
- Extract PDF text and metadata, flag uninspectable documents and binaries, and record reviewed synthetic media hashes.

### Contributor experience

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

The revised suite passes **190 tests**, including the offline CLI demo, actual PDF rendering and extraction, outgoing-history privacy scans, network-target restrictions, and application-state regressions. The synthetic demo also passes all 11 packet checks. GitHub Actions is configured for Python 3.10 and 3.12; hosted run status is reported by the workflow badge.

## Known limits

- Fact IDs and numeric matching establish provenance and detect specific mistakes; they do not prove the meaning or truth of every claim.
- Built-in review personas are text-only AI assessments, not employer decisions. Inspect the actual PDF separately.
- Salary extraction, location matching, and source-domain independence remain approximate.
- There is no enforced API spending budget or concurrent packet-build lock.
- Manual tasks require an assistant or person to supply answers. Real applications and recruiter outreach remain manual.
- Privacy checks use known identifiers and configured secrets; they cannot inspect every unknown secret, hosted cache, fork, or prior clone.
