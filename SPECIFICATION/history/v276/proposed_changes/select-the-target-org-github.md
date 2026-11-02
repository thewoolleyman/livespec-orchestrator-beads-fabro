---
topic: select-the-target-org-github
author: claude-opus-5-5:fabro-currency
created_at: 2026-11-02T08:51:47Z
---

## Proposal: A shared Fabro server serves a run under the dispatch target's own GitHub App selected per run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend §"Self-contained plugin dispatch" ¶"Per-tenant engine identity" so a Fabro server whose global integration is one App can serve a dispatch target whose App differs, by selecting that target's App for that one run. The selection names server-held secret NAMES, never values. The selected authority is used consistently for the native repository checkout, managed stage credential renewal and publication. An explicit selection that cannot resolve refuses before any protected forge operation and never falls back to the server's global App. Concurrent runs keep their distinct authority, and neither the private key nor a minted token appears in an inspectable workflow record. The dispatch target declares the selection per factory, and the Dispatcher renders it into the run configuration. A per-tenant server instance remains a permitted route.

### Motivation

Work-item bd-ib-voozdp (homelab cannot launch on the shared main Petri service). The maintainer ordered homelab's default factory moved temporarily from its per-tenant org instance mi-homelab to the shared main Petri service (2026-11-02). That server's global integration is the maintainer's personal App 3668528, which is private to his account and cannot act on homelab's org repository. Homelab's org App 4688510 (installation 155847128) must stay canonical, and the main server's personal App must stay unchanged. The clause as written makes this unservable: it requires the serving server to hold the target tenant's own App and states that a server holds exactly ONE App integration. A read-only review of the serving engine (Petri 0.393.0-nightly.1, carrier 9f6c38f) located the measured seam. One worker-side resolution of the server's integration feeds the native clone, the stage credential source and the publisher. Run settings accept only `permissions` and `additional_repositories`, so no supported per-run selector exists. Clearing permissions stops sandbox token injection but leaves clone and publication on the server App. Projecting a token or key into the sandbox therefore does not suffice and would violate the no-durable-key-in-sandbox rule. The repair is an engine-level per-run credential source plus its dispatch-side binding. The clause must state both, and must state the fail-closed and isolation obligations that keep a shared server from silently publishing under the wrong identity.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch", replace the paragraph beginning `**Per-tenant engine identity.**` with the following two paragraphs. Keep its last two sentences on the withheld `workflows` grant word for word.

> **Per-tenant engine identity.** The Fabro server serving a dispatch MUST publish, check out and renew credentials for that dispatch under the dispatch TARGET tenant's own GitHub App identity. Two routes satisfy this. (1) A per-tenant server instance whose global integration IS the target's App (e.g. a dedicated `FABRO_HOME` carrying the adopter's `app_id`, its PEM in the server process environment, and its own port and authentication). (2) A SHARED server whose global integration is a different App, serving the run under a PER-RUN APP SELECTION (below). Without a per-run selection, a server serves every run under its one global integration, so dispatching an adopter repo through a shared server whose App is not installed for the target fails. A dispatch preflight SHOULD verify that the App the run will use can reach the target repo BEFORE launching. It refuses with an actionable diagnostic rather than failing inside the engine run. Workflow-file-touching pushes structurally require the App's `workflows` read-write permission grant, which the factory sandbox's credential MUST NOT hold (§"Factory sandbox credential constraints" in `constraints.md`). The preflight and the adopter docs MUST therefore surface that grant as one DELIBERATELY WITHHELD from the dispatch credential, and MUST name the attended-host-session route for work requiring it — never as an App-installation requirement to be granted. (Implementation tracked as `bd-ib-z2ctra` and `bd-ib-w4iaaf`.)
>
> **Per-run App selection on a shared server.** A dispatch target MAY declare, per factory, the GitHub App a run on that factory uses. Under `dispatcher.factories.<name>.github_app` it names an App-id secret and a private-key secret. Both are secret NAMES the operator provisioned in that factory's server-side vault, and neither is ever a value. The Dispatcher MUST render the declaration into the run configuration as the run's GitHub credential source, carrying the names only. It MUST refuse before claim, naming the key, when the declaration is malformed: not an object, missing either name, carrying an empty or non-string name, or carrying any other key. The engine MUST resolve the selected source from the server-held secrets in its worker. It MUST use that ONE selected authority, as renewable repository-scoped installation tokens, for every protected forge operation of the run: the native repository checkout, every managed stage credential renewal (the projected `GITHUB_TOKEN`), and the run's publication (branch push and pull-request creation). An explicitly selected source whose secrets are absent or empty, whose key does not parse, or whose App is not installed for or authorized on the target repository MUST fail the run BEFORE any protected forge operation, naming the selected secret names and the failing condition. It MUST NOT fall back to the server's global integration or to anonymous access. A run that selects no source keeps the server's global integration unchanged. Selection is per run: concurrent runs on one server under different Apps MUST each keep their own repository-scoped authority through every credential refresh and vault snapshot. A selection MUST NOT replace or mutate the server's global integration. The selected private key and every token minted from it MUST NOT appear in the run configuration, the immutable workflow version, `fabro inspect` or `fabro dump` output, or the sandbox environment, consistent with the ephemeral-token rule above. (Engine implementation tracked as `bd-ib-voozdp`, in the Fabro owner fork; the Dispatcher binding is tracked as its own child.)

In `SPECIFICATION/scenarios.md` §"Scenario 32 — Adopter-target dispatch compatibility", insert these three scenarios after the scenario `Preflight verifies the serving App reaches the target repo`, inside the existing gherkin block. Add no new H2 heading, so `tests/heading-coverage.json` is unchanged:

```gherkin
Scenario: A shared server serves a run under the target's per-run selected App
  Given a shared Fabro server whose global integration is an App not installed for the adopter target repo
  And the target declares dispatcher.factories.<name>.github_app naming an App-id secret and a private-key secret provisioned in that server's vault for an App installed on the target repo
  When the Dispatcher dispatches an item of the target to that factory
  Then the rendered run configuration selects that credential source by secret name and carries no secret value
  And the run's native checkout, each managed stage GITHUB_TOKEN renewal and its publication all authenticate as the selected App
  And the server's global integration is unchanged

Scenario: An unresolvable per-run App selection refuses before any forge operation
  Given a run whose configuration selects a GitHub credential source
  And a selected secret is absent, empty, unparseable, or names an App not installed for the target repo
  When the run's worker starts
  Then the run fails before any protected forge operation with a diagnostic naming the selected secret names and the failing condition
  And it does not fall back to the server's global App or to anonymous access

Scenario: Concurrent runs under different Apps keep distinct authority
  Given two concurrent runs on one shared server, one selecting no source and one selecting an org App
  When each run refreshes its credentials and snapshots its vault
  Then the first run authenticates only as the server's global App and the second only as the selected org App
  And neither run's inspect or dump output, workflow version or sandbox environment contains a private key or a minted token
```
