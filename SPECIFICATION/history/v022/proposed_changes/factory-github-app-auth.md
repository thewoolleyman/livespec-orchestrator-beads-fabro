---
topic: factory-github-app-auth
author: claude-fable-5
created_at: 2026-07-02T04:47:01Z
---

## Proposal: Factory GitHub auth via the target credential_wrapper App-token provider

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Extend the `## Self-contained plugin dispatch` contract with the factory
GitHub-credential resolution clauses (github-app-auth design record,
Pillars 1 and 2): every automated GitHub operation on the dispatch path
authenticates with a GitHub App installation token minted from the App
environment the dispatch TARGET's own `credential_wrapper` injects; no
dispatch path reads the retired fleet PAT
(`LIVESPEC_FAMILY_GITHUB_TOKEN`); resolution is fail-closed (no fleet
fallback, no ambient `gh` login); token acquisition is first-class
remint (a caching provider re-mints before expiry and every spawned
subprocess resolves a currently-valid token — never a once-at-start
export), and the sandbox receives only an ephemeral installation token,
never the durable App private key or a long-lived PAT.

### Motivation

Work-item `livespec-in7snc` (absorbing `bd-ib-gsl`), a groom-minted
cross-repo slice of the github-app-auth epic (`livespec-2ef0`, core
tenant). The prior credential model hard-required the fleet PAT at
preflight, forwarded it into the orchestrator container, and hardcoded a
once-at-start `export GH_TOKEN=...` into the dispatcher invocation —
blocking adopters (no preflight without the fleet secret), lacking
`Pull requests: write` on some repos, and expiring nothing (a long-lived
PAT where an ephemeral credential belongs). The livespec-runtime v0.8.0
`github_auth` primitive (fail-closed env config boundary, mint railway,
caching provider with transparent pre-expiry re-mint, git credential
helper) is now vendored and wired through the Dispatcher, the
orchestrator entrypoint, and every dispatch shell path.

### Proposed Changes

(1) EXTEND the existing H2 `## Self-contained plugin dispatch` in
`SPECIFICATION/contracts.md` (no heading change) with two new closing
paragraphs: (a) tenant-scoped fail-closed resolution — App installation
tokens minted from the wrapper-injected App environment, no fleet-PAT
read, hard refusal when the App environment is absent and the target
has no `credential_wrapper`, fleet-as-adopter-#0; (b) first-class
remint — the Dispatcher's caching provider re-mints before expiry and
resolves a currently-valid token per spawned subprocess, and the
sandbox environment table receives only an ephemeral installation
token (never the App private key, never a long-lived PAT).

No heading-coverage co-edit is required: the H2 set of contracts.md is
unchanged (the clauses extend the existing section). The enforcing
tests are the dispatcher/provider suite in
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher.py`
and `test_mint_app_token.py`, plus the shell static guards
`test_orchestrator_entrypoint_github.py` and
`test_real_work_dispatch_script.py`.
