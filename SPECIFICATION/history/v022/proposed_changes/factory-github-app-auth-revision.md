---
proposal: factory-github-app-auth.md
decision: accept
revised_at: 2026-07-02T04:47:01Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Codifies github-app-auth Pillars 1 and 2 for the factory dispatch path
(work-item `livespec-in7snc`, absorbing `bd-ib-gsl`; maintainer-approved
at the careful self-modification admission gate): the dispatch TARGET's
own `credential_wrapper` is the sole GitHub credential source, feeding
the vendored livespec-runtime App installation-token provider; the
retired fleet PAT is read nowhere; resolution fails closed with no
fleet fallback; and token acquisition is first-class remint so the
merge-poll and any >1-hour operation survive token expiry. Clause-only
contract extension inside the existing `## Self-contained plugin
dispatch` H2 — no heading change, so no heading-coverage co-edit.

## Resulting Changes

- contracts.md
