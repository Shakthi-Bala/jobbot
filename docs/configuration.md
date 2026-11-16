# Configuration guide

Run `python jobbot.py init`, then replace the illustrative content in `data/profile.yaml` and `data/answers_bank.yaml`. These files are ignored by Git. The tracked [example profile](../data/profile.example.yaml) shows the base structure.

## Candidate profile

| Section | What to supply |
| --- | --- |
| `person` | Contact details and absolute HTTPS links to your professional pages. |
| `authorization` | Actual work authorization, sponsorship needs, eligibility, availability, and location preferences. Use `unsure` where appropriate. |
| `education` | Degrees, dates, coursework, and optional GPA and thesis details. |
| `facts` | Verified claims with unique fact IDs, evidence references, and metrics. |
| `experience` | Accurate titles, organizations, dates, and associated fact IDs. |
| `projects` | Relevant projects, your contribution, dates, associated facts, and public links. |
| `skills` | Skills with an honest level and evidence references. |
| `targets` | Titles, seniority, locations, keywords, fit threshold, and salary floor. |
| `preferences` | Document format, length, content, review, and disclosure settings. |
| `networking` | Professional affiliations, contact limits, and permitted channels. |

Store more evidence in the profile than will fit on a résumé. The writer selects relevant entries for each posting. A metric set to `null` is unavailable; do not replace it with an estimate. Distinguish completed evaluations from ongoing tests and planned submissions from published papers.

For team projects, state what you personally implemented. For benchmarks, record the dataset, split, baseline, measurement scope, and limitations. Keep confidential results out of material supplied to the writer.

## Résumé and cover-letter preferences

Add the settings you need under `preferences` in your private profile. This example is not the default for every installation:

```yaml
preferences:
  resume_format: latex
  resume_pages: 1
  resume_font: sans                  # sans | charter
  resume_presentation: research      # research | classic
  resume_summary: false
  resume_compact_education: true
  resume_coursework: true
  resume_coursework_in_education: true
  resume_skills_last: true
  resume_min_projects: 4
  resume_min_project_bullets: 2
  resume_max_bottom_blank_in: 1.6
  cover_letter: requested            # requested | always
  cover_letter_max_words: 300
  panel_min_score: 9.0
  panel_strict_rubric: true
```

Choose content minimums that your verified inventory can support. Checks enforce minimum distinct projects and bullets; they do not create missing evidence. The bottom-blank limit measures inches from the lowest text baseline to the page edge, including the margin.

The LaTeX template uses an 11-point body and single line spacing. It supports compact education entries, coursework within education, and skills placed after projects. `resume_skill_groups` groups selected skills under display categories. `resume_auto_add_skills: true` opts into adding supported posting matches; leave it false to retain the writer's selection.

To group consecutive roles at one employer, set their shared `employer` and distinct `team` fields explicitly. Preserve original organizations, titles, and dates; the renderer does not infer shared employers from similar names.

Use `resume_disclosure_constraints` to record wording or disclosure boundaries. Source facts still need to be suitable for the model service you use. Review the final PDF and extracted text after a configuration change.

## Reusable wording and master résumés

`python jobbot.py approve JOB_ID` promotes a packet's bullet wording into local `data/approved_bullets.yaml`. Future drafts can reuse approved wording while adapting the selection to each job.

The optional `data/master_resume.yaml` stores source bullets by role family:

```bash
python jobbot.py master --draft
python jobbot.py master --family perception
```

Drafting a master can require an AI task. Rendering an existing master does not require a new writing call. Families include `perception`, `rl`, `robotics_swe`, and `ml`; use `python jobbot.py master --help` for the full CLI choices. Master text is source material, not an independent quality endorsement.

## Reviews and model calls

Configure mode and models in local `models.yaml`, copied from the tracked [example configuration](../models.example.yaml) by `init`. Without a local file, the example supplies the defaults. In manual mode, task files and answer schemas are saved under `out/tasks/`; complete the answers in a coding-assistant session, validate them, and rerun the original command.

The panel's minimum score is an editorial gate. A high average cannot override a reader below the configured threshold. If stronger evidence is needed, the pipeline stops rather than inventing a result. See [the review guide](resume-review-loop.md) for scoring and visual-review limitations.

## Optional integrations

- **Gmail alerts:** use a read-only OAuth client, save credentials in ignored `data/credentials.json`, and run `python jobbot.py gmail-auth` interactively. Label alerts `jobbot/alerts`. Scheduled discovery only uses existing credentials and never opens a browser. Board discovery can run with `--no-alerts`.
- **Discord:** set `DISCORD_WEBHOOK_URL` in the environment or ignored `.env` file. `python -m agents.notify --help` documents explicit updates and supported media attachments. Keep candidate data and credentials out of messages.
- **Spreadsheet:** `python jobbot.py sheet` refreshes `data/applications.xlsx`. Review edits to application-status fields before refreshing; the integration can record entries marked as applied.
- **Daily runs:** use `python run_daily.py --help` to control packet count and discovery sources. Manual mode queues tasks for your assistant; it cannot answer them unattended.

Return to the [README](../README.md).
