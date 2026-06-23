---
topic: provider-subscription-worker-credential-projection
author: claude-opus-4-8
created_at: 2026-06-23T00:24:15Z
spec_commitments:
  impl_followups:
    - id_hint: codex-acp-workflow-variant
      description: |
        Add a Codex/OpenAI ACP worker workflow variant (Fabro `backend="acp"` nodes invoking the Codex ACP adapter, e.g. @zed-industries/codex-acp) alongside the existing Claude `@agentclientprotocol/claude-agent-acp` workflow, so a work-item can be implemented by a ChatGPT-subscription Codex worker.
    - id_hint: dispatcher-codex-credential-projection
      description: |
        Extend the Dispatcher's run-scoped overlay to materialize a CODEX_HOME/auth.json FILE (Codex auth is file-based, unlike the Claude single-env-var token) carrying a non-rotatable credential snapshot — the real refresh_token replaced by an inert sentinel — so the worker runs on the multi-day access token and physically cannot rotate the shared credential family.
    - id_hint: dispatcher-credential-freshness-gate
      description: |
        Add a Dispatcher freshness gate: refuse to dispatch a subscription-credentialed worker unless the projected access token's remaining usable lifetime exceeds the maximum run budget; on failure, refuse and surface a clear 'host credential needs renewal/re-login' message instead of dispatching.
    - id_hint: codex-credential-source-wiring
      description: |
        Wire the host's canonical Codex subscription credential into the dispatch environment via the livespec env wrapper / `fabro secret` (never committed to .livespec.jsonc or .beads/), with the host as the single login + refresh owner.
    - id_hint: worker-provider-model-routing
      description: |
        Add per-work-item provider/model routing so the Dispatcher can select which subscription provider (Claude vs OpenAI/Codex) and workflow variant a given ready work-item dispatches to.
    - id_hint: subscription-worker-tests
      description: |
        Hermetic tests for the credential-projection transform (non-rotatable snapshot) and the freshness gate, plus an end-to-end proof that a Codex-subscription worker completes a dispatch through the janitor hard-gate.
    - id_hint: codex-acp-version-reverify-docs
      description: |
        Re-verify the codex-core auth behavior against the exact codex-core version pinned by the chosen Codex ACP adapter (verification was run on Codex CLI 0.141.0; @zed-industries/codex-acp@0.16.0 pins codex-core rust-v0.137.0), and realign the orchestrator docs/contracts to describe the multi-provider worker path.
---

## Proposal: Provider-subscription worker credential projection

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Codify a provider-agnostic contract under which the Dispatcher MAY authenticate Fabro worker sandboxes with a projected provider-subscription credential (Claude subscription today; OpenAI/ChatGPT subscription as a second provider via an ACP coding-agent backend) instead of only a provider API key. A projected worker credential MUST be non-rotatable by the worker and freshness-gated by the Dispatcher, and the orchestrator host MUST be the sole owner/refresher of the long-lived credential.

### Motivation

Subscription billing requires running the real coding-agent CLI (Claude Code or Codex) inside the sandbox via the ACP backend, authenticated from a projected credential rather than a Fabro-native API key. Long-running OAuth-subscription credentials rotate their refresh token on refresh; if a worker sandbox refreshes, the rotated refresh token discarded with the ephemeral sandbox can invalidate the shared credential for the host and peer workers. Empirical verification (the Codex ACP adapter builds on codex-core's AuthManager, which self-refreshes and rewrites auth.json; an inert refresh_token still loads, runs on the multi-day access token, and fails soft when a refresh is triggered) confirms that projecting a non-rotatable credential snapshot plus a Dispatcher freshness gate fully prevents the credential-poisoning failure mode WITHOUT any copy-back, broker, or central-rotation machinery.

### Proposed Changes

Add a new provider-agnostic credential-projection contract to `SPECIFICATION/contracts.md` (e.g. a `## Worker credential projection` section) carrying these clauses:

- The Dispatcher MAY authenticate a worker sandbox's coding-agent runtime from a **projected provider-subscription credential** (e.g. a Claude subscription or an OpenAI/ChatGPT subscription), as an alternative to a provider API key. This is the path that lets workers spend subscription quota rather than metered API billing.
- A projected worker credential MUST be **non-rotatable by the worker**: a worker MUST NOT be able to mint or rotate the shared long-lived refresh credential. No worker — including one whose run triggers a credential refresh — may invalidate the credential for the orchestrator host or for peer workers.
- The Dispatcher MUST NOT dispatch a worker unless the projected credential's usable lifetime exceeds the worker's maximum run budget (a **freshness gate**). When the gate cannot be satisfied, the Dispatcher MUST refuse the dispatch and surface that the host credential requires renewal, rather than projecting a credential that MAY expire mid-run.
- The orchestrator host MUST be the **sole owner and refresher** of the long-lived provider refresh credential; worker sandboxes MUST be read-only consumers of a projected snapshot.
- This contract is provider-agnostic and governs Claude-subscription and OpenAI/ChatGPT-subscription workers identically. The exact projection mechanism — the credential file/field layout, the encoding that renders the snapshot non-rotatable, and the numeric freshness threshold — is implementation-owned and MUST NOT be fixed by this contract.

Add two governing scenarios to `SPECIFICATION/scenarios.md`:

`## Scenario — Dispatcher projects a non-rotatable subscription credential into a worker sandbox`
Given the orchestrator host holds a valid provider-subscription credential whose usable lifetime exceeds the worker run budget,
When the Dispatcher dispatches a ready work-item to a worker sandbox,
Then the Dispatcher MUST project a non-rotatable credential snapshot into the sandbox such that the worker cannot rotate the shared refresh credential,
And the worker MUST authenticate its coding-agent runtime from that projected snapshot,
And no refresh performed or attempted inside the sandbox MAY invalidate the host's or any peer worker's credential.

`## Scenario — Dispatcher refuses dispatch when the credential freshness gate fails`
Given the host provider-subscription credential's usable lifetime does NOT exceed the worker run budget,
When the Dispatcher considers dispatching a ready work-item,
Then the Dispatcher MUST refuse the dispatch,
And the Dispatcher MUST surface that the host credential requires renewal rather than projecting a credential that MAY expire mid-run.

The revise pass that accepts this proposal MUST co-edit the orchestrator repo's heading-coverage map (if maintained) for the two added `## Scenario` headings, atomically per the repo's self-application discipline.
