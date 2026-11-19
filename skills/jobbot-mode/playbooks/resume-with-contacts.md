# resume-with-contacts

1. Read the principles index and the private profile, including document preferences, networking preferences, contact limits and existing outreach history.
2. For each selected role, follow `new-job-packet.md` completely and in order. Preserve its stop conditions, evidence gaps and review status. Do not prepare outreach for a closed or blocked application as if it were eligible.
3. For each remaining company, follow `outreach.md` completely and in order. Prioritize relevant engineers, researchers, hiring managers or recruiters and genuine shared affiliations. Respect `networking.max_contacts_per_company` and the existing 30-day cycle; deduplicate contacts across roles at the same company.
4. Retain only contacts whose identity, company and professional role are confirmed by two independent, re-fetched professional sources. Record the sources, verification date, specific reason to contact the person and related job link. LinkedIn may be a confirmed contact route but never a verification source or a scraping target. Include only published professional email addresses; do not guess addresses or profile URLs, infer alumni affiliations, or collect personal phone numbers. Record unavailable or conflicting evidence as a gap.
5. Review each short personalized message against the candidate's facts and the sourced reason for contacting that person. Preserve the outreach word limit and unslop/tone review. Start with a small question or request for a pointer; do not imply a relationship, hiring responsibility or referral commitment that is unverified. Keep every message as a draft for the candidate.
6. Save a companion contact sheet, machine-readable contact list and message drafts in the application delivery folder. For batches, include them in the ZIP. In the README, link the contacts and drafts and show which roles have verified contacts, which have none, and which searches are still pending. Reuse a relevant contact across roles without duplicating first-contact messages.
7. Verify the final delivery contains the promised files and links and clearly preserves resume and outreach review limitations. An incomplete contact search does not prevent delivery of the completed resume: identify the missing contacts explicitly instead of calling the full bundle complete.
8. Stop. The candidate reviews the documents and contacts and sends any messages themselves. Do not submit an application, upload a resume, send a message or mark outreach as sent.

This is the assistant's combined delivery workflow. The standalone CLI commands
remain separate: `python jobbot.py packet JOB_ID` prepares application documents;
`python jobbot.py outreach JOB_ID` researches contacts and drafts messages. In manual
mode, answer and validate each queued task before resuming its command. Do not claim
automatic live-source or model checks passed when only manual review was performed.
