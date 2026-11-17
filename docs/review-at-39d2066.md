# Review follow-up at `39d2066`

This round addresses both high-severity regressions and the smaller findings using an explicit acceptance/rejection corpus and full-suite validation. Changes remain on `dev` for a pull request; `main` is not updated directly.

- **Versions:** exemption requires a literal tool/version pair in cited facts or skills. Units and counted nouns remain quantitative claims, including when a measured phrase is also present in posting metadata. Version labels do not supply numbers for unrelated metrics. A technical modifier such as “ROS 2 camera processing” is distinguished from “ROS 2 cameras” and “ROS 2 robot deployments.”
- **Salary:** a dedicated pure parser assigns component labels and currency to each range. An adjacent or separate bonus no longer suppresses base salary; RSU, equity, OTE, stipend, allowance, and bonus ranges do not widen it. Explicit foreign currencies are not relabelled as USD, including when an ATS provides currency metadata but the posting text uses bare dollar signs.
- **Counts and rankings:** “team of eight” and “mentored eight” are checked even without a following noun. Ordinals in ranking context, such as “second place,” require matching rank evidence.
- **Diagnostic trust:** a shared formatter separates code-owned failure descriptions from reflected data. Keywords, metadata, requisitions, company/role names, document excerpts, and contact fields are escaped and wrapped as untrusted evidence. End-to-end tests inspect the actual writer prompt.
- **Application dates:** UTC tomorrow is accepted as a one-day timezone allowance; later dates are rejected. Whitespace-only spreadsheet dates are treated as blank.

The [fixed corpora](../tests/corpora/README.md) contain 55 honest sentences, 34 adversarial claims, 50 authored salary edge cases, and 50 attributed public posting excerpts. CI runs these before the full test suite on every push or pull request targeting `main` or `dev`. `AGENTS.md` requires retaining their expectations and adding regression cases for future numerical or salary changes.

Validation: the full Slurm run passed **622 tests**, including the fixed corpora, offline demo, master-resume rendering, real PDF checks, and end-to-end diagnostic-boundary tests.

Tests use fictional candidate evidence, isolated trackers, mocked service responses, and frozen public salary excerpts. They do not use the candidate tracker, call paid models, submit applications, or send recruiter outreach. These checks establish bounded lexical/numerical provenance, not semantic proof of every claim or an interview probability.
