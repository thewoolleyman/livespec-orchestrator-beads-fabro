---
topic: orchestrator-currency-surfaces-push-agents
author: claude:gmktec-factory-placement
created_at: 2026-11-08T00:08:29Z
---

## Proposal: Orchestrator currency surfaces name the adopt step, treat a held clone as low urgency, and flag a newer executing build

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

livespec-dev-tooling spec v155 makes a fleet clone hold its installed orchestrator build across session starts, so a clone behind the offered build is the expected state between rolls, and a build moves only through `just adopt-orchestrator-build <clone> <build>`. This proposal brings §"Self-contained plugin dispatch" in line. Every currency remedy names that adopt step and never a raw `claude plugin update`. A clone behind the offered build is surfaced at low urgency. A dispatch whose executing build is NEWER than the target's registered install is flagged as an older one already is. The plugin's stale-build guidance gives the rollout path as release, adopt step, reload, dispatch.

### Motivation

bd-ib-rfhnqf was refused at dispatch on 2026-11-08T00:02:51Z as spec-change tier, verdict partial, generalizing ## Self-contained plugin dispatch, with linked topic orchestrator-currency-surfaces-push-agents. Its tier record says the ratified text 'states that a build lagging the latest release is surfaced as a non-blocking fact and that only a committed `dispatcher.minimum_release` floor blocks', but 'does not state the `just adopt-orchestrator-build` remedy, low-urgency needs-attention items for a clone behind the offered build, a finding for an executing build newer than the registered install, or the `.ai` rollout path'. Today these surfaces treat a deliberately held clone as a defect and tell agents to run the raw update, which routes around the operator step livespec-dev-tooling spec v155 (livespec-dev-tooling#3734, §"Orchestrator build adoption") makes the only way the build moves. livespec-dev-tooling-7upzav, which implements that hold, must not merge until bd-ib-rfhnqf ships. Filed by the livespec-dev-tooling plan seat gmktec-factory-placement at legacy-coordinator-agent's request (session 8e04c5e0, R301, 2026-11-08).

### Proposed Changes

All edits are inside contracts.md §"Self-contained plugin dispatch" and the bodies of two existing scenarios. No `## ` heading is added, removed or renamed, so tests/heading-coverage.json keeps its rows.

1. **Ambient staleness is surfaced, not enforced.** Replace "naming the restart-and-update remedy" with: "naming as its remedy livespec-dev-tooling's operator step `just adopt-orchestrator-build <clone> <build>` followed by a session reload, and never a raw `claude plugin update`". Then add: "A fleet clone's session reconcile holds its installed orchestrator build (livespec-dev-tooling `contracts.md` §\"Orchestrator build adoption\", ratified in its spec v155), so a clone behind the offered build is the expected state between rolls. This fact, and every needs-attention currency or release-adoption item raised because a clone's registered install is behind the offered or latest released build, MUST carry low urgency and MUST NOT carry high urgency on that ground alone. Any handoff such an item carries MUST name the same adopt step and MUST NOT tell an agent to refresh, update or reinstall the install directly."

2. **Session-start warning.** In the paragraph beginning "A session resolves its project's registered build", after "naming the registered install's version and the latest released version", add: ", and naming the adopt step `just adopt-orchestrator-build <clone> <build>` as its remedy rather than a raw `claude plugin update`".

3. **The sole blocking currency form is a deliberate operator floor.** Append: "A refusal under the floor, and every other Dispatcher refusal or finding about this plugin's build currency, MUST name `just adopt-orchestrator-build <clone> <build>` in livespec-dev-tooling as its remedy and MUST NOT name `claude plugin update`."

4. **New paragraph after the floor paragraph:** "**An executing build that differs from the registered install is surfaced in either direction.** When a dispatch's executing build of this plugin differs from the target repository's registered install of it, the Dispatcher MUST print a non-blocking finding naming both builds, whether the executing build is older or newer than the registered install. A newer executing build, such as one reached through a session bound to another project's newer install, runs a build the target clone has not adopted, so it is surfaced as an older one is. The plugin's agent guidance on stale plugin builds MUST give the fix rollout path as release, adopt step, reload, dispatch, and MUST NOT give a raw `claude plugin update` as that path."

5. **Scenario 95.** Extend the first scenario's last step to read "a non-blocking dispatcher-currency-staleness fact surfaces at low urgency that the provisioned build lags the latest release, naming `just adopt-orchestrator-build <clone> <build>` as its remedy". Extend the floor scenario with "And the diagnostic names `just adopt-orchestrator-build <clone> <build>` as its remedy and does not name `claude plugin update`". Add a fourth scenario: "Scenario: An executing build newer than the target's registered install is surfaced / Given a target repository whose registered install of this plugin is older than the executing build / When the Dispatcher admits a ready work-item for that target / Then it prints a non-blocking finding naming both builds / And the dispatch is not refused on that ground".

6. **Scenario 271.** Extend the session-start warning scenario with "And the warning names `just adopt-orchestrator-build <clone> <build>` as its remedy and does not name `claude plugin update`".
