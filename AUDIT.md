# Jobbot audit

Reviewed discovery, eligibility, tailoring, rendering, checks, manual tasks, review/panel loops, tracking, the dashboard, and Discord delivery. Personal resume findings live separately in the ignored `out/audit/resume_findings.md`; no personal profile, resume, database, webhook, or private recording is committed. The README animation uses synthetic example content.

## Verified failures and changes

| Priority | Failure | Correction |
| --- | --- | --- |
| High | Two requisitions with the same company/title/location collapsed into one job. Gap/outreach folders could also collide before a resume existed. | New IDs incorporate the requisition; existing IDs are retained. Artifact folders record their owner before tailoring. |
| High | Refreshed postings retained old requirements and fit decisions. | Store the latest text/HTML, invalidate parsed requirements/fit when text changes, and rescore before building. |
| High | Manual daily runs selected only `shortlisted` jobs, stranding tasks after drafting/review. Re-running a packet redrafted earlier stages and reset its revision counters. | Resume `packet_drafted`/`reviewed` jobs. Persist build stages, input/artifact hashes, feedback and counters in `packet_state.json`. |
| High | Reaching the panel's round limit could produce `ready_for_review` even with outstanding revisions. | Stop at `needs_input` and retain actionable issues when revisions remain. |
| High | Historical document rows pointed at files overwritten on each revision, so their hashes could no longer be reproduced. | Copy new document versions into content-addressed archives and number versions across each document kind. Refuse to mark a changed/missing/stale resume as submitted. Previously lost bytes cannot be reconstructed. |
| High | Repeating `mark-applied`/`mark-sent` duplicated actions and follow-ups. Rescoring could replace an interview/application status. | Make repeated recording idempotent, preserve recorded application states during fit scoring, and cancel reminders for rejected/closed applications. |
| High | A sponsorship mention was treated as a prohibition; citizenship was inferred from export-control eligibility. The fit model could omit a restriction already extracted from the posting. | Require negative sponsorship wording before blocking; keep citizenship separate and uncertain cases as questions. Merge quoted parsed restrictions into fit checks. This is a conservative workflow check, not an eligibility determination. |
| High | Citing an approved answer-bank key did not prevent the model from changing its value. | Render approved values directly for answers backed only by the bank and for self-identification. Unknown answer sources require input. |
| High | A required cover letter or application question could be omitted without a check failing. | Add `required_content` to the packet checks. Explicit `[NEED INPUT]` questions remain visible for human review. |
| Medium | LaTeX emitted education/skills/research experience/projects, while checks expected summary/skills/experience/projects/education. | Record the actual rendered order/headings and omit unrendered content from the render description. Allow layout whitespace in headings. |
| Medium | Without `pdftotext`, the fallback extractor split `PyTorch` into `PyT orch`, failing two existing tests. | Use pypdf layout extraction. Both Typst PDFs and an actual Tectonic LaTeX PDF were checked. |
| Medium | Failed renders could leave a previous resume PDF looking current. Links could introduce raw TeX syntax; compiler runs had no timeout. | Remove old PDFs before rendering, encode link delimiters, disable shell escape/use Tectonic untrusted mode, and bound compiler runtime. |
| Medium | Outreach checking tried to parse its own `checks.json` as a contact. Name-only pages could confirm the wrong employer. | Skip the report and require both full name and company on a source page. |
| Medium | ATS URL matching accepted a supported URL embedded inside another site's URL. Dashboard searches interpreted ordinary text as regular expressions. | Anchor ATS matching at the beginning; use literal dashboard searches. |
| Medium | Discord transport errors could crash callers or expose the webhook through exception text. Only text posts were supported. | Catch errors without logging secret URLs, honor bounded rate-limit retries, enforce embed limits, suppress mentions, and support explicit media attachments. |

## Limits that still matter

1. **Fact IDs establish provenance, not truth or entailment.** A real ID can be attached to a false claim. Numeric checks compare number sets, not units, baselines, attribution, confidence intervals, or experimental conditions. A valid number can be attributed to the wrong system. The private sample-resume report contains a concrete example. Accuracy review and candidate verification remain essential.
2. **Inputs need stronger validation.** The profile is a free-form YAML mapping. Duplicate IDs, invalid evidence links, stale dates, contradictory availability, and missing entry metadata do not receive comprehensive intake validation. An evidence string is not proof that an experiment was reproduced.
3. **Scores are heuristics.** Keyword coverage is not an employer's ATS score. Persona reviews are simulations; seven prompts to one model are not seven independent hiring decisions. Manual mode uses one accuracy reviewer. No evidence currently calibrates fit/readiness scores against a sufficiently large outcome set.
4. **Discovery still has coverage and pay limitations.** Remote-region rules and fuzzy title matching are approximate. Pay-text parsing can confuse currencies, intervals, or total compensation with USD base salary. Ranking by the top of a range can overprioritize jobs whose likely offer or seniority is a poor match. Sources without requisition IDs still fall back to company/title/location identity.
5. **Networking verification is conservative but incomplete.** Two domains and co-occurring name/company text do not prove a current role or substantiate the outreach reason. Domain independence uses a simple hostname heuristic, not a public-suffix database. Source redirects, private-network URLs, stale pages and misleading page content need additional protection if this becomes a hosted/multi-user service.
6. **Operational hardening remains.** There is no enforced API spend budget, cross-process build lock, comprehensive model/provider integration test, or tested restore process. Checkpoints support sequential resumption; avoid concurrent builds of the same job. Dependency minimums are broad rather than locked.
7. **Manual mode still requires a person to answer tasks.** Slurm/cron can discover and queue work, but cannot complete an unanswered AI task. Offline/skip-review flags deliberately reduce verification and are logged. `ready_for_review` means the candidate should inspect the packet; unresolved form answers can still require input.
8. **Existing history has limits.** New records preserve bytes; old overwritten files cannot be recovered by this change. The bot cannot establish which file a person actually uploaded outside it. Keep the submitted copy and record the application after checking that it matches.

## Follow-up repository review

- The privacy scanner now extracts account handles only from known account URL structures. A portfolio's ordinary path segments previously caused widespread false positives. Full personal links remain protected.
- Greenhouse discovery now stores a public board URL even when the company supplies a branded career-page URL. This lets both packet creation and requisition checks actually re-fetch those postings; previously they logged that live verification was skipped.
- Packet checkpoints now include the Python agent/check sources and dependency/schema files. A completed packet must be checked again after a writer or validation rule changes; previously unchanged documents could reuse an old completion result.
- If the panel identifies only missing evidence and no supported edits, it stops with `needs_input` immediately. It preserves the scores and evidence gaps rather than re-rendering identical claims until the round limit. Manual accuracy reports identify their reviewer as a manual assistant rather than assuming a particular assistant product.

These changes do not resolve the limits above. In particular, approved wording still needs semantic review when a fact changes under the same ID, and built-in panel calls remain text-only. Private job-search batches retain their live posting snapshots, factual reviews, rendered previews and validation reports under ignored `out/` directories.

## Validation

Baseline: **46 passed, 2 failed**, both PDF extraction regressions. The expanded suite covers requisition separation and legacy IDs, changed postings, archived bytes, repeated recording, eligibility uncertainty, approved answers, required content, manual review/panel resumption, revision limits, stale PDFs, LaTeX headings, contact checks and Discord behavior.

The final suite and a real LaTeX compilation run through Slurm. Exact results, a JUnit report, and the synthetic walkthrough are in ignored `out/audit/` artifacts. Tests use isolated example data; no paid model calls, live job applications, recruiter messages, or production-tracker changes are part of validation.

Implementation references: [packet pipeline](agents/packet.py), [discovery](agents/discover.py), [document storage](agents/core.py), [tracker](agents/tracker.py), [required content](checks/required_content.py), [regression tests](tests/test_audit_regressions.py).

The PDF fallback follows [pypdf's documented layout extraction](https://pypdf.readthedocs.io/en/stable/user/extract-text.html). Discord delivery follows its [webhook execution and attachment contract](https://docs.discord.com/developers/resources/webhook#execute-webhook); compiler isolation uses [Tectonic's untrusted mode](https://tectonic-typesetting.github.io/book/latest/v2cli/compile.html).
