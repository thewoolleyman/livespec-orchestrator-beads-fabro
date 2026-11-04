---
topic: factory-credential-from-whole-slot-pool
author: claude-opus-5-5
created_at: 2026-10-30T21:14:14Z
---

## Proposal: A factory dispatch takes its credential from the whole slot pool

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Make session-headroom admission choose the factory credential from every injected CLAUDE_CODE_OAUTH_TOKEN__ slot (qualifying slot with the soonest window reset, measured projection preferred over unavailable), refuse only when no slot qualifies, journal the chosen and rejected slots, and leave the caam interactive selection unchanged.

### Motivation

Maintainer top-priority direction on livespec-dev-tooling-dfixhe, 2026-10-30 about 21:1xZ, relayed in the coordinator task ('get them done asap to unblock'): the Dispatcher's session-headroom admission must choose the factory credential from the whole injected CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_N slot pool, not only the caam-selected account. A run keeps the token it was dispatched with, so only the injected account's headroom matters. Incident the same night: anthropic-2 was refused on headroom while anthropic-3, -4 and -6 sat at 0 percent utilization, which starved all five factory lanes; the spec's alignment advice between the caam trigger and the floor admitted exactly this idle band. Code location (prose only, the spec stays behavioural): select_factory_credential in .claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_factory_account_selector.py. Its caam mapping is read_selected_profile / parse_selected_profile (the ~/.local/state/caam-usage-rotate/selected-account.json record) feeding resolve_factory_credential_env_name, which maps the published profile to one CLAUDE_CODE_OAUTH_TOKEN__<PROFILE> slot and falls back to the unnumbered token. For the factory it becomes a pool chooser: enumerate every CLAUDE_CODE_OAUTH_TOKEN__* name in the injected env, assess each through the session-headroom gate, and pick per the ranking above. The gate's _projected_token in _dispatcher_session_headroom_gate.py, and the other callers (_dispatcher_credentials.py, _dispatcher_credential_env.py, _dispatcher_claude_credential_command.py, _acp_availability_probe_credential.py, _dispatcher_dod_judgement_candidate_command.py) must consume the one admission-time choice so assessment, probe and projection still name one account. The caam record stays the interactive account only.

### Proposed Changes

In SPECIFICATION/contracts.md, in the 'Admission filters candidates by projected Claude session headroom' paragraph of 'Dispatcher admission, WIP cap, and post-merge acceptance', apply these five exact replacements.

Replace:
"It MUST read the provider's five-hour session utilization using the exact credential snapshot that the dispatch would project."
with:
"The factory credential pool is every non-empty `CLAUDE_CODE_OAUTH_TOKEN__<SLOT>` credential the dispatch target's credential wrapper injects into the Dispatcher's environment, and the unnumbered `CLAUDE_CODE_OAUTH_TOKEN` is the sole pool slot only when no numbered slot is injected. The Dispatcher MUST choose the credential a dispatch projects from the WHOLE pool, once per admission evaluation, and MUST NOT restrict the choice to the account that an account-selection process outside the Dispatcher published for interactive use; a run keeps the credential it was dispatched with, so only the chosen slot's headroom bears on that run. For every pool slot it MUST read the provider's five-hour session utilization using the exact credential snapshot that the dispatch would project if that slot were chosen. A slot QUALIFIES when its reading is valid, its remaining headroom is not strictly below the floor, its seven-day status is not exhausted, and its projection does not call for a projection skip. A slot whose projection is unavailable qualifies by the fail-open rule below, but ranks below every qualifying slot whose projection was measured or carried. Among qualifying slots the Dispatcher MUST choose the slot that has the soonest five-hour window reset instant in the provider's response, so that quota does not expire unused; a slot whose response carries no reset instant ranks after every slot that carries one, and any remaining tie resolves by the slot name in ascending order so that the choice is deterministic. The reset instant is used only for this ranking and still MUST NOT change any skip. A covered candidate is skipped by this clause only when NO pool slot qualifies; when one does, the chosen slot is the credential that every covered candidate of the dispatch projects, and the skip kinds below apply to a slot, not to a candidate. Every assessment's journal record MUST name the chosen slot's opaque non-secret credential identity and, for each other slot assessed in the same admission evaluation, its identity and the reason it was not chosen: a floor skip, a seven-day skip, a projection skip, an unobservable reading, or a qualifying slot ranked lower, so that a refusal and a choice are each explainable from the record. The record names slots only by that opaque identity."

Replace:
"One assessment per distinct projected credential per admission evaluation MUST be reused across nodes and candidates sharing that credential."
with:
"One assessment per distinct pool slot per admission evaluation MUST be reused across nodes and candidates sharing that credential."

Replace:
"When an account-selection process outside the Dispatcher rotates away from an account when its five-hour remaining allowance falls below a trigger of its own, that trigger SHOULD NOT be below the committed floor, and the committed floor SHOULD NOT exceed it; an operator aligns the two by configuration, and the Dispatcher MUST NOT read that process's trigger or readings. A misaligned pair leaves a band in which the selection process holds an account the Dispatcher refuses, so the factory idles until the account drains past the trigger or resets."
with:
"An account-selection process outside the Dispatcher continues to own which account INTERACTIVE spend uses; that selection MUST NOT change which pool slot a factory dispatch projects, the Dispatcher MUST NOT read that process's selection, trigger or readings to choose a slot, and the factory takes its own allocation within the pool. An interactive account that is short of headroom therefore never idles the factory while another pool slot qualifies."

Replace:
"MUST NOT issue any usage request beyond the one bounded reading this clause already requires."
with:
"MUST NOT issue any usage request beyond the one bounded reading per pool slot this clause already requires."

Replace:
"A headroom-governed refusal MUST additionally name the assessed credential identity, reading or explicit unobservable result,"
with:
"A headroom-governed refusal MUST additionally name the assessed credential identity of every pool slot, each with its reading or explicit unobservable result and the skip kind that disqualified it,"

Replacement 3 replaces in full the sentence pair about aligning an external account-selection trigger with the floor. Nothing else in the paragraph changes.

In SPECIFICATION/scenarios.md add this scenario (numbered at revise):

## Scenario NN — A factory dispatch takes its credential from the whole slot pool, preferring the sooner window reset, and refuses only when no slot qualifies

```gherkin
Feature: Factory credential from the whole slot pool
  As a factory operator whose interactive account is short of headroom
  I want a dispatch to take the best-qualifying credential from the whole injected slot pool
  So that the factory is not starved while other slots sit unused, and quota does not expire unused

  Background:
    Given the credential wrapper injects the pool slots "ANTHROPIC_2", "ANTHROPIC_3" and "ANTHROPIC_4"
    And dispatcher.session_headroom_floor_percent is 20
    And dispatcher.session_headroom_horizon_minutes is 180
    And an item whose implement node's candidate is covered by the admission session-headroom clause
    And every other admission-valve condition is satisfied

  Scenario: The interactive account is short while another slot qualifies, so the other slot is used
    Given the account-selection process published "anthropic-2" for interactive spend
    And slot "ANTHROPIC_2" reads 90 percent utilization
    And slot "ANTHROPIC_3" reads 0 percent utilization
    When the Dispatcher evaluates admission
    Then the item is admitted with slot "ANTHROPIC_3" projected
    And the assessment record names the chosen slot's opaque credential identity
    And the assessment record names the "ANTHROPIC_2" identity as not chosen with the reason floor skip

  Scenario: Two slots qualify and the sooner window reset wins
    Given slot "ANTHROPIC_3" reads 10 percent utilization with a five-hour window reset 4 hours away
    And slot "ANTHROPIC_4" reads 30 percent utilization with a five-hour window reset 1 hour away
    And slot "ANTHROPIC_2" reads 95 percent utilization
    When the Dispatcher evaluates admission
    Then slot "ANTHROPIC_4" is projected
    And the record names "ANTHROPIC_3" as qualifying but ranked lower on its later reset

  Scenario: A measured qualifying projection outranks an unavailable one
    Given slot "ANTHROPIC_3" qualifies with a projection that is unavailable and a window reset 1 hour away
    And slot "ANTHROPIC_4" qualifies with a measured projection and a window reset 3 hours away
    When the Dispatcher evaluates admission
    Then slot "ANTHROPIC_4" is projected

  Scenario: No slot qualifies, so the existing refusal applies
    Given slot "ANTHROPIC_2" reads 85 percent utilization
    And slot "ANTHROPIC_3" reads an unobservable result
    And slot "ANTHROPIC_4" reads 40 percent utilization projected to exhaust within the horizon
    When the Dispatcher evaluates admission
    Then the item stays ready with no dispatch claim and no blocked_reason
    And its containment refusal record names every slot's opaque credential identity with its reading or unobservable result and its skip kind
    And the refusal names the admission-required node and scheduled reevaluation instant

  Scenario: The interactive selection is not changed by the factory's choice
    Given the account-selection process published "anthropic-2" for interactive spend
    And the Dispatcher chooses slot "ANTHROPIC_3" for a dispatch
    When admission completes
    Then the account-selection process's published selection is unchanged
    And the Dispatcher read neither that selection nor that process's trigger to choose the slot
```

