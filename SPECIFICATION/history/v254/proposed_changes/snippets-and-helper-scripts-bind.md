---
topic: snippets-and-helper-scripts-bind
author: claude-opus-5-5:anthropic-burn-mitigation
created_at: 2026-10-29T15:26:40Z
---

## Proposal: A session resolves its project's registered plugin build, and session start surfaces a stale one

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Under ## Self-contained plugin dispatch, the plugin ships a command printing the plugin root of a governed project's registered install, operation-prose snippets bootstrap the package through that root instead of a literal cache-build path, and the session-start hook prints a non-blocking warning when the registered install is older than the latest release.

### Motivation

Work-item bd-ib-uyg266 (plan anthropic-burn-mitigation, epic bd-ib-b2jzxw, coordinator ruling R125) measured on 2026-10-27 that snippets and helper scripts put a literal plugin cache build on sys.path. At 10:07:01Z a seat's filing script ran cache build 6ae0f4e4d7c0 (v0.243.4) and so took the pre-Codex-first judge (`claude -p --model claude-opus-4-8`) while that repository's registered install was v0.243.15; another seat pinned v0.243.8 the same way and misreported its own build; the coordinator measured ten registered projects running orchestrator builds from v0.240.0 to v0.243.14. The habit comes from the operation prose itself, which tells agents to insert a literal `<plugin-root>/scripts/bin` path, so a long-lived session carries a hash that goes stale at the next release and every released fix, burn reductions included, is silently bypassed. The ratified text already says ambient staleness is surfaced rather than enforced (Scenario 95) and that dispatch resolves from the plugin root, but it states no way for a snippet to find the project's registered build and no session-start surfacing. The orchestrator's spec-change-tier gate held bd-ib-uyg266 on 2026-10-29 (topic snippets-and-helper-scripts-bind) and named ## Self-contained plugin dispatch as the heading to generalize. Fleet-wide plugin-currency reporting belongs to livespec-dev-tooling; this proposal covers the orchestrator side only.

### Proposed Changes

In SPECIFICATION/contracts.md, under ## Self-contained plugin dispatch, immediately after the paragraph that begins '**Ambient staleness is surfaced, not enforced.**', add:

**A session resolves its project's registered build rather than a remembered one.** The plugin MUST ship a command that prints the plugin root of a governed project's registered install of this plugin, resolved by matching that project's path against the host's installed-plugins record, never by an entry's position in that record and never from the invoking session's own bound plugin root. When the project has no registered install of this plugin, the command MUST exit non-zero and say so, and MUST NOT fall back to another project's install. Every operation-prose step that has an agent import this plugin's package from a snippet MUST bootstrap that import through the plugin root this command prints for the governed project, and MUST NOT name a literal cache-build path. The plugin's session-start hook MUST print a staleness warning naming the registered install's version and the latest released version when the governed project's registered install is older than the latest release. When either version is unobservable, the hook MUST say that currency could not be determined rather than reporting the install current. The warning is surfacing only: the hook MUST NOT fail the session start, and it composes with the needs-attention dispatcher-currency-staleness fact rather than replacing it.

In SPECIFICATION/scenarios.md, append one scenario (numbered at revise):

## Scenario NNN — A session finds its project's registered plugin build and is told when it is stale

Given a host whose installed-plugins record holds installs of this plugin for two projects at different builds

When the registered-root command runs for the second project

Then it prints the plugin root of the second project's install

And not the first project's, nor the invoking session's own bound root

Scenario: a project with no registered install is refused

Given a project path with no install of this plugin in the installed-plugins record

When the registered-root command runs for it

Then it exits non-zero naming the missing install

Scenario: session start warns about a registered install older than the latest release

Given a governed project whose registered install is older than the latest released version

When the plugin's session-start hook runs

Then it prints a warning naming the registered install's version and the latest released version

And the session start succeeds

The revise that accepts this proposal MUST add a tests/heading-coverage.json entry for the new scenario heading, with test "TODO" and a reason naming bd-ib-uyg266 as the implementing item.
