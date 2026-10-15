# new-job-packet

1. Read the principles index.
2. Re-fetch the posting. If it's closed or the req ID changed, stop and log.
3. Load the fit row. If any blocker restriction applies, stop and log.
4. Tailor the resume from `profile.yaml` only, then render the PDF.
5. Draft a cover letter if requested or useful, and run unslop on it.
6. Draft application answers from `answers_bank.yaml` and facts. Mark gaps with `[NEED INPUT]`.
7. Run `checks/`. On failure, fix and retry, with at most 2 loops.
8. Run the multi-model review.
9. Write the packet, `changes.diff`, and `review.md`. Set status `ready_for_review`.
10. Stop. You review and submit.

Code: `agents/packet.py:build`. Unresolved issues after 2 loops set status
`needs_input` and are written to `out/<Company>_<Role>/open_issues.md`.
