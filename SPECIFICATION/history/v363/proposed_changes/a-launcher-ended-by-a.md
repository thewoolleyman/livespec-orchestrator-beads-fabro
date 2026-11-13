---
topic: a-launcher-ended-by-a
author: claude-opus-5-5
created_at: 2026-11-12T07:29:47Z
---

## Proposal: A launcher removes its private payload holder, and the next launcher reclaims what a killed one left

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a paragraph to §"Self-contained plugin dispatch". A launcher that copies the payload into a private holder directory under the system temp directory must remove it before exiting, including on SIGTERM, SIGHUP or SIGINT, and then exit non-zero, except that a holder a running process other than itself names in `LIVESPEC_RETAINED_PAYLOAD_ROOT` is left for the next launcher's sweep. It must record its creator pid and start time in every holder. Before creating a holder, it must reclaim holders whose creator is gone and that no running process names in `LIVESPEC_RETAINED_PAYLOAD_ROOT`, plus unrecorded, unnamed holders older than 24 hours. A running creator's holder is left in place. The removal is best-effort and never turns a dispatch into a refusal or failure.

### Motivation

Implementation item bd-ib-immkx7 (bd-ib tenant), owned by the dev-host-disk-retention plan (livespec-dev-tooling-qgwxo4). On 2026-11-12 at 07:27:32Z its dispatch-stage spec-change tier refused it: verdict unstated, generalization target §"Self-contained plugin dispatch", linked topic a-launcher-ended-by-a. legacy-coordinator-agent confirmed the section states nothing about payload holders.

- On vmi3006760 on 2026-11-11, /tmp (a 48G RAM-backed tmpfs) reached 86%. Private payload holders (`livespec-orchestrator-beads-fabro-payload-<release>-*`) held 7.9G of it in 464 directories. About 86 had been created in the previous 24 h, so the leak runs at about 1.4 GB a day. Only 12 were referenced by any process. 379 unreferenced holders older than 24 h were moved off /tmp.
- Cause: `.claude-plugin/scripts/bin/_payload.py` creates the holder with `mkdtemp`, and `_bootstrap.py` removes it only through `atexit`. That runs only on a normal interpreter exit, so every launcher or Dispatcher loop ended by SIGTERM, SIGHUP or SIGKILL (a supervisor stop, a session kill, a restart) leaks its holder. `release_payload` defers anything it cannot remove to 'a later sweep', and no sweep exists.
- A SIGKILLed launcher cannot clean up, so a later launcher must. A recorded pid plus start time tells a dead creator from a reused pid. `LIVESPEC_RETAINED_PAYLOAD_ROOT` is how a running process names the holder it uses, so a holder named there is never reclaimed.
- The fleet's other two temp-artifact leaks got the same shape: livespec-dev-tooling v200's coverage-namespace sweep, and the proposed checks-leave-no-gpg-daemon clause.
- Fleet scope: no other fleet plugin copies a payload into a temporary holder. Every `tempfile.mkdtemp` and `TemporaryDirectory` call outside tests and vendored code on origin/master of livespec (core), livespec-overseer, livespec-driver-claude, livespec-driver-codex, livespec-driver-pi, livespec-orchestrator-git-jsonl, livespec-console-beads-fabro, livespec-runtime and livespec-dev-tooling was read on 2026-11-12. Each is a scoped scratch directory in a dev-tooling check or operator script: a copier smoke test, a gh config dir, an activity build, caam probes, an idle canary, codex hook validation, a release-source fetch, a merge-evidence backfill, and docs-only CI fixtures. None is a launcher payload holder, so no follow-up proposal is needed.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch", insert this paragraph directly after the paragraph that ends "Because that payload is not a git working tree, no promotion into it is possible and none is attempted.":

> **A launcher removes the private payload holder it made, and the next launcher reclaims what a killed one left.** A launcher invocation that copies the payload into a private holder directory under the system temp directory (named `livespec-orchestrator-beads-fabro-payload-<release>-*`) MUST remove that holder before it exits. When it receives SIGTERM, SIGHUP or SIGINT it MUST remove the holder and then exit with a non-zero status. On any exit, normal or signalled, it MUST leave in place a holder that a running process other than itself names in `LIVESPEC_RETAINED_PAYLOAD_ROOT`; the next launcher's sweep reclaims that holder once no running process names it. It MUST record, in every holder it creates, the pid of its own process and that process's start time. Before it creates a new holder, a launcher MUST remove every payload-holder directory under the system temp directory whose recorded creator is no longer running and that no running process names in `LIVESPEC_RETAINED_PAYLOAD_ROOT`; a pid now held by a different process does not count as the creator. It MUST also remove every payload-holder directory that carries no creator record, that no running process names, and that was last modified more than 24 hours earlier. It MUST leave in place every holder whose recorded creator is still running or that a running process names. This removal is best-effort: a holder that cannot be removed is logged, and it MUST NOT turn a dispatch into a refusal or a failure.
