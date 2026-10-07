---
topic: relay-delivery-and-progress-deadline
author: codex
created_at: 2026-10-07T22:55:35Z
---

## Proposal: Verify relay delivery and bound activity without required results

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Make relay delivery and plan progress depend on authoritative target state, with explicit budgets, diagnosed recovery, attention reporting and across-dispatch non-progress admission.

### Motivation

The maintainer approved plan bd-ib-lrik25 outcomes and order with "I approve, continue autonomously". Research 001 documents 42 handoffs in 28 hours without the required slice advancing and queue acknowledgments requiring manual delivery checks. Research 002 resolves scope and policy choices. The amendment preserves the ledger-only Planning Lane design and existing within-run controls.

### Proposed Changes

Amend contracts.md §"Planning Lane realization", especially "Typed `next_action` and `last_session`", "Ledger-held handoff persistence", "Plan-record conformance checks" and "Planning Lane restraint budget", and the Dispatcher admission and needs-attention contracts. Add the scenarios below to scenarios.md and co-edit tests/heading-coverage.json at ratification. Scenario numbers are allocated from the current highest number at ratification; the named behaviors below are the stable proposal references. Add a concise user-visible description to spec.md. Keep all realization rules in this repository.

### Shared authoritative result reader

A required result MUST be a typed reference containing a canonical repository identity and exactly one kind-specific target: `item_status` (item id and expected status), `item_comment` (item id and exact marker), `pull_request_state` (PR number and expected state), `verified_proof` (subject id, build identity and assertion identifiers), or `file_on_branch` (branch, path and expected Git blob id). Comment-marker satisfaction proves only the requested marker's presence; it MUST NOT stand in for completed implementation or verified proof. A verified-proof read MUST validate the existing typed Proof of Done semantics, scope, build and verdict rather than match text. A file result MUST compare the remote branch's blob identity, not a stale checkout or mere path existence.

The shared reader MUST return `satisfied`, `unsatisfied`, or `unobservable`, together with target identity, UTC observation time, and source evidence identity (ledger comment/version, forge state/timestamp, proof record, or Git object). Both delivery and deadline callers MUST use it. Authentication, network, malformed evidence and missing repository-resolution failures MUST be `unobservable`, never satisfaction or a confident negative. Reads MUST use the named repository's configuration and credential seam; cross-tenant commands MUST execute from that target repository. Arbitrary shell predicates MUST NOT be accepted as result references. A bounded read failure MUST name the failed source and leave the obligation outstanding.

### Required result, budget and progress epoch

A new write of an open live plan's `next_action` MUST carry exactly `kind`, `ref`, `text`, `required_result` and `budget`. Existing meanings of kind/ref/text remain. For `impl` and `spec-op`, required_result MUST be a valid typed reference and budget MUST contain an absolute UTC `deadline` and positive integer `max_handoffs`; the first limit reached expires the obligation. For `human` and `none`, both tracking fields MUST be explicit null, and changing to them MUST retain any unmet obligation in the progress history. A human pointer names the needed decision or diagnostic. Legacy three-key pointers MUST remain readable, report `plan-progress-tracking: missing`, and acquire the new shape on their next sanctioned write; legacy reads alone MUST NOT invent budgets or mutate the ledger.

A fixed-first-line `plan-progress-event` ledger comment MUST hold the epoch identity, canonical result, initial budget, UTC start, accepted handoff count/baseline and event kind. It is the durable obligation history, not a filesystem queue or new table. Canonical result identity, rather than session, wording, kind/ref or last_session, MUST govern continuity. Routine handoffs, supervisor handoffs and direct set_next_action calls MUST NOT reset the deadline or count. A replacement of an unmet result MUST require a changed-approach record or explicit human escalation, so changing a ref cannot evade the deadline.

All sanctioned pointer writers MUST read the prior obligation and its target before accepting continuation. While a known-unsatisfied obligation has budget remaining, an accepted handoff consumes one handoff unit; direct pointer writes consume none but cannot reset either limit. Satisfied results permit advancing to a new result and budget. After expiry, same-obligation continuation MUST be refused before appending a handoff or updating the pointer unless a fresh changed approach is supplied or the pointer escalates to human. Unobservable results MUST preserve the original budget and refuse any transition claiming completion; the diagnostic and an explicit recovery/escalation remain recordable. At the exact deadline or when accepted handoffs reach max_handoffs, the next continuation is expired. An expired wall clock MUST be visible even when no new handoff is written.

A changed approach MUST be a typed event naming the previous epoch, diagnosis, concrete operational change, evidence references and a replacement explicit budget. A prose `approach:` line or cosmetic pointer rewrite MUST NOT qualify. An accepted changed-approach event opens one new epoch and MUST NOT be reusable to rearm subsequent epochs. Writes MUST serialize per epic and detect a stale prior epoch before mutation; retried calls with the same operation identity MUST recover the original event rather than duplicate handoffs or extend a deadline. A partial write MUST be diagnosable and must not authorize a fresh dispatch until reconciled.

resume_directive MUST report missing, expired and unobservable tracking findings. It MUST NOT automatically dispatch an exhausted or unobservable obligation. An unattended expired resume MUST retain the obligation and set a human diagnostic pointer through the sanctioned primitive; an authorized session MAY record a changed approach to resume work. Existing human/none picker and missing-Definition-of-Done behavior remain; add the progress check before the unattended dispatch decision.

The Planning Lane restraint budget MUST explicitly include these two fixed-shape next_action fields and progress/relay comments on the existing epic. It MUST continue to forbid parallel plan status files, tables, queues or a second front end. Guidance MUST distinguish a recorded attempt from its required result and instruct readers to diagnose an exceeded record-rate warning instead of merely acknowledging it.

### Relay delivery

The plan primitive recording a relay MUST accept a stable relay id, typed expected result and absolute UTC deadline, and MUST read the target before recording `delivered`. A sender queue receipt, peer acknowledgment or peer_recorded value MUST NOT establish delivery. If the result is unsatisfied or unobservable, the primitive MUST record an undelivered relay, its unchanged deadline and the observation; the sender retains the obligation. Retrying the same operation identity for an existing relay MUST return its recorded observation and MUST NOT extend the original deadline; a distinct recheck operation MAY record a new observation for that same relay and original deadline; a conflicting target requires a new explicit supersession that preserves the old obligation's disposition. Subsequent target evidence MAY discharge the relay. The existing supervisor obligation schema MUST retain receipt_ack and peer_recorded and add the target-evidence delivery leg; ownership transfer/closure requires all three. This repository's guidance changes with the implementation; consumers in livespec-overseer are referred through their own spec/work-item lane. Messages with no durable target effect remain undelivered.

### Attention without confusing activity with results

needs-attention MUST include an overdue-result fact for every open live plan whose declared required result remains unsatisfied after either budget limit. The fact MUST identify the epic, target, deadline/count, last observation and recovery action. New ancillary PRs, handoffs or closed repair children MUST NOT clear this fact while its declared result remains absent.

A report-only no-result-window fact MUST also identify open live plans with at least the configured `plan_progress_handoff_threshold` handoffs during `plan_progress_window_seconds` and no new attributable merged PR, closed child or verified proof record in that window. Both values MUST be positive committed dispatcher configuration; absence or invalid values MUST surface a configuration finding rather than an invented numerical policy. The fact MUST include UTC window bounds, entry count, last required result (or explicit legacy-missing marker), and last observed result time. A source that cannot be read MUST produce an unobservable-source finding, not a confident no-result fact. Attribution MUST use the union of explicit parent-child and implicit dotted-id children, the existing item-to-PR provenance, and typed proof records. Events before the window MUST NOT count as new progress. Window/count boundaries MUST be deterministic with an injected current time. Existing activity detectors and record-rate warnings remain independent; this fact is report-only and does not itself stop another agent.

### Across-dispatch progress

Before claiming a work-item, drive/Dispatcher admission MUST compare each comparable completed attempt with the progress high-water mark established BEFORE that attempt. The first observed terminal establishes the baseline. Advancing beyond the prior high-water mark resets the consecutive non-progress count; an item-attributable terminal at or below it increments that count. A positive committed `dispatcher.redispatch_no_progress_limit` MUST select how many such attempts refuse the NEXT dispatch. Missing or invalid policy MUST yield a configuration diagnostic/refusal, not an implicit count. Refusal MUST precede claim, name the relevant run ids, causes and high-water milestone, and require a fresh typed changed-approach record before another epoch.

Progress MUST use the actual workflow dependency ordering of successful milestones, not lexical stage names or retry numbers. Histories from incomparable workflow variants MUST require an explicit diagnosed baseline/changed approach. Duplicate observations and active runs MUST NOT count as completed attempts. Known host-attributable failures neither increment nor reset the item count; unknown terminal causes MUST require diagnosis rather than silently count as host failures. Run evidence MUST be read from the factory recorded for that run; local default server observations MUST NOT replace remote history. A changed-approach event names the prior history/epoch, diagnosis, operational change and evidence, authorizes one epoch, and MUST NOT be replayable to reset every subsequent dispatch. Existing within-run fix/review caps and ordinary lifecycle admission still apply.

### Required scenario additions

Each named scenario MUST be expressed as Given/When/Then in scenarios.md with its clause link and heading-coverage entry in the same revision:

1. **Authoritative result readers distinguish fulfillment from observation failure.** Given named targets in two repositories and both positive and negative examples of every result kind, when the reader checks them, then it selects the correct target and returns the matching state/evidence; a query failure returns unobservable; stale local files and a comment merely saying verified cannot satisfy the corresponding stronger result.
2. **A plan deadline survives pointer rewrites and permits diagnosed recovery.** Given one unmet result with an explicit budget, when ordinary/supervisor handoffs and direct pointer writes repeat or change wording, then the original epoch persists; at either boundary continuation is refused without a partial handoff; a fresh typed approach rearms once; an old approach, replacement result without diagnosis, concurrent stale writer and duplicate operation cannot reset it. Given a human escalation, then the unmet obligation remains readable.
3. **Unattended resume observes expired, legacy and unobservable progress.** Given each of those pointer states, when resume runs, then it reports the precise finding; it preserves legacy reading without invented budgets; expired/unobservable tracking cannot auto-dispatch; a sanctioned recovery can restore dispatchability without overriding other admission checks.
4. **Acknowledgment cannot discharge a relay.** Given queue receipt and peer_recorded but unchanged target, when delivery is recorded and retried, then it remains undelivered with original deadline and sender ownership; after the exact target effect is observed, it records delivery evidence; source failure or a wrong repository never discharges it.
5. **Plan attention names missing results despite busy repair work.** Given an expired required result and a merged ancillary repair, when needs-attention runs, then the overdue-result fact remains. Given a configured window with threshold handoffs and no new attributable milestone, then it emits window/count/target details; a new attributable milestone clears only the historical-window condition. Include a dotted-id child, an explicit-edge child, an old closure, a legacy pointer and an unreadable source as controls.
6. **Repeated item failures require a changed dispatch approach.** Given comparable run histories on a recorded remote factory, when the configured number of item-attributable flat attempts follows the baseline, then the next drive refuses before claim with named evidence. Include advancing history, known host failure, unknown cause, duplicated observations, an active run, incomparable variants and one-time diagnosed recovery as separate examples.

Implementation admission MUST follow ratification. The plan's released-artifact proof MUST exercise the corresponding positive and negative cases through normal installed surfaces; child closure alone does not discharge any plan assertion. Proof-reuse and bounded-wait work remain owned by their existing plans.

