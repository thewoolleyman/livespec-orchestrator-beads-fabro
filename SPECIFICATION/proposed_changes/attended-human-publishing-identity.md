---
topic: attended-human-publishing-identity
author: claude-opus-5-5
created_at: 2026-11-12T03:34:29Z
---

## Proposal: A computed publishing identity is a human only when a human attends the post

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Every primitive that computes a publishing identity (post-host-record, post-plan-record, the completeness-review evidence's reviewer identity, and the release-spec-tier attestation actor) today treats "no agent session variable" as "a human" and records the forge login. This proposal requires a positive attended-human signal for the human branch: an explicit --human-publisher flag, an interactive stdin, a typed-back forge login, and no agent marker. Otherwise the posting primitives refuse and the attestation records the unattributed mark. So a credential wrapper that scrubs the agent session variables can no longer turn an agent's post into a maintainer's.

### Motivation

Work item bd-ib-ax3rds.1 (plan bd-ib-ax3rds), routed by the fleet coordinator, records a measured incident. On 2026-11-12 an independent codex replayer ran under `hl param run`, homelab's credential wrapper, whose child environment is built from an allowlist rather than inherited. The wrapper dropped CODEX_SESSION_ID, and post-plan-record (v0.320.0) posted the replay as human thewoolleyman on homelab hl-bvycoc at 03:15:11Z. The primitive fabricated human evidence. The three current clauses say "the invoking agent session's id, or the forge login for a human" but never say how a human is established, so the implementation reads the absence of an agent variable as a human. Refusing on that absence alone would break the ratified human path. The discriminator was measured before it was chosen, on 2026-11-12 on the VPS; the table is on bd-ib-ax3rds.1. `[ -t 0 ]` reads NOTTY in Claude Code's Bash tool (no controlling tty), in codex exec bare and under setsid nohup, and in herdr-pane codex and Claude TUIs running a shell command. But `script -q -c` gives any agent an interactive stdin, so an interactive terminal alone is not proof of a human. `HERDR_PANE_ID` is present in a human's own pane shell, so it cannot be an agent marker. Agent markers are present on every agent path but are removed by an allowlist wrapper, so their absence proves nothing. Hence the four-part signal. Prior art: bd-ib-y6polc forwarded the session variables through the plugin's own re-exec, but a wrapper outside the plugin is unreachable that way. In-flight alignment: open PR #4992 only snapshots these clauses into history/v357 (align). bd-ib-tgkx5f, active, implements the attestation-actor clause this proposal amends (modify-to-accommodate: its no-invoker human branch gains the attended-signal precondition, and its unattributed fallback widens to cover the scrubbed case).

### Proposed Changes

**1. One attended-human rule for every computed publishing identity (`contracts.md`).**

Add the following paragraph to `contracts.md` §"Self-contained plugin dispatch", immediately after the host-record posting primitive's identity clause (the one that begins "The primitive MUST compute the publishing identity itself"). The plan-record clause under §"Planning Lane realization" and the attestation-actor clause under §"Work-item state semantics" MUST each gain one sentence citing it: "The human branch of that identity is governed by §"Self-contained plugin dispatch" → "Attended human identity"."

> **Attended human identity.** Every primitive that computes a publishing identity MUST apply this rule: `post-host-record`, `post-plan-record`, the plan operation's completeness-review evidence record (its `reviewer-identity`), and the `release-spec-tier` attestation actor. When `CODEX_SESSION_ID`, `CLAUDE_CODE_SESSION_ID` or `PI_SESSION_ID` is set non-empty, the identity MUST be that agent session's id, exactly as today.
>
> When none of the three is set, the primitive MUST compute a human identity, the forge login, ONLY when the invocation carries the ATTENDED HUMAN SIGNAL. The signal is all four of the following:
> (a) the caller passes the explicit `--human-publisher` flag;
> (b) standard input is an interactive terminal;
> (c) the operator types the forge login back at a confirmation prompt read from that terminal, and it equals the login the forge reports for the token in use;
> (d) none of the agent markers `CLAUDECODE`, `CLAUDE_CODE_SESSION_ID`, `CODEX_SESSION_ID`, `CODEX_THREAD_ID` or `PI_SESSION_ID` is present in the environment.
>
> When no agent session id is set and the signal is incomplete, `post-host-record`, `post-plan-record` and the completeness-review evidence write MUST refuse before posting or writing anything. The refusal MUST state that no agent session identity was found, and MUST name each missing part of the attended human signal. They MUST NOT fall back to the forge login.
>
> The `release-spec-tier` attestation with no asserted invoker MUST instead record the `unattributed:<os-user>@<hostname>` mark in that case, never `human:<forge-login>`.
>
> A `--human-publisher` flag passed while an agent session id is set MUST be refused, naming the conflict. A terminal-multiplexer variable such as `HERDR_PANE_ID` MUST NOT be treated as an agent marker, because a human's own multiplexer pane carries it.
>
> The rule guarantees that an agent whose session variables a credential wrapper scrubbed cannot be attributed as a human BY ACCIDENT. It does not claim to stop a deliberate forgery that supplies the flag, a pseudo-terminal and the typed confirmation; no local primitive can prevent that.

**2. Amend the attestation scenario (`scenarios.md`).**

In Scenario 206's feature, the scenario "An attestation from a human terminal with no asserted invoker records the forge login" MUST gain the step "And the invocation carries the attended human signal" after its second Given.

A new scenario in that feature MUST state the scrubbed case:

```gherkin
  Scenario: An attestation from a session with no agent identity and no attended human signal records the fallback mark
    Given release-spec-tier is driven for a held feature with no asserted invoker
    And the invoking session sets no agent session id and the forge reports a login
    And the invocation does not carry the attended human signal
    When the valve records the attestation
    Then the ledger comment and the dispatch-journal entry record the unattributed:<os-user>@<hostname> mark as the actor
```

**3. New scenario heading (`scenarios.md`).**

Add the following at the end of `scenarios.md`, the heading followed by its gherkin block:

## Scenario: a proof post from a session with no agent identity is refused unless a human attends it

```gherkin
Feature: a computed publishing identity is a human only when a human attends the post
  Scenario: A scrubbed agent session's proof post is refused
    Given CODEX_SESSION_ID, CLAUDE_CODE_SESSION_ID and PI_SESSION_ID are all unset
    And standard input is not an interactive terminal
    When post-plan-record, post-host-record or the completeness-review evidence write is invoked
    Then it refuses before posting or writing anything
    And the refusal states that no agent session identity was found and names the missing parts of the attended human signal
  Scenario: A pseudo-terminal alone does not make a human
    Given the three agent session variables are all unset
    And standard input is an interactive terminal allocated by a pseudo-terminal wrapper
    And the caller does not pass --human-publisher
    When post-plan-record is invoked
    Then it refuses before posting and names the missing --human-publisher flag
  Scenario: A human who attends the post is recorded by forge login
    Given the three agent session variables and every agent marker are unset
    And standard input is an interactive terminal
    And the caller passes --human-publisher and types back the login the forge reports
    When post-host-record is invoked
    Then the record's publishing identity is that forge login as a human identity
  Scenario: An agent session id is used unchanged
    Given CODEX_SESSION_ID is set non-empty
    When post-plan-record is invoked
    Then the record's publishing identity is that agent session id
  Scenario: The human flag beside an agent session id is refused
    Given CLAUDE_CODE_SESSION_ID is set non-empty
    When post-host-record is invoked with --human-publisher
    Then it refuses naming the conflict between the flag and the agent session id
```

**4. Revise co-edit.** The revise pass that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new heading through `resulting_files[]`. `test` MAY be `"TODO"` owned by work item bd-ib-ax3rds.1, with a non-empty `reason`.
