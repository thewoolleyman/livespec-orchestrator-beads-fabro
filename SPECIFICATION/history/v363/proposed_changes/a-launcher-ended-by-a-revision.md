---
proposal: a-launcher-ended-by-a.md
decision: modify
revised_at: 2026-11-13T00:54:29Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:address-honeycomb-alerts
---

## Decision and Rationale

The proposal closes the gap the dispatch-stage spec-change tier named when it refused bd-ib-immkx7 on 2026-11-12 at 07:27:32Z (verdict unstated, generalization target §"Self-contained plugin dispatch", linked topic a-launcher-ended-by-a): the section states nothing about the private payload holders a launcher copies under the system temp directory. Measured on vmi3006760 on 2026-11-11: /tmp (a 48G RAM-backed tmpfs) reached 86%, payload holders held 7.9G in 464 directories, and the leak runs at about 1.4 GB a day, because the holder is removed only through atexit, which a signalled or killed launcher never reaches. The new paragraph under the same H2 requires a launcher to remove its holder on exit and on SIGTERM, SIGHUP or SIGINT, to spare a holder a running process names in LIVESPEC_RETAINED_PAYLOAD_ROOT, to record its creator pid and start time, and to sweep holders whose creator is gone (including on pid reuse) or that are unrecorded, unnamed and older than 24 hours, best-effort and never failing a dispatch. Placement is correct: this orchestrator's launcher realization belongs in its own contracts.md, and the proposal's fleet-scope survey found no other fleet plugin copying a payload into a temporary holder. No existing H2 heading is renamed or removed. legacy-coordinator-agent graded the proposal PASS-WITH-FIXES on 2026-11-13, decided the three modifications below, assigned this single-proposal pass to address-honeycomb-alerts as the carrier's owner, and acked the v363 claim.

## Modifications

Three modifications decided by legacy-coordinator-agent's grade (2026-11-13), applied as written:

(a) Behaviour gets a Gherkin scenario: a new `## Scenario 363 — A launcher removes its payload holder on exit or signal, spares a named one, and the next launcher reclaims a dead creator's` in scenarios.md, with six cases: a signal removes the holder and the launcher exits non-zero; a holder another running process names is spared and a later sweep reclaims it; a dead creator's holder is swept, including when its pid was reused; a running creator's holder and a fresh unrecorded holder are left; an unrecorded, unnamed holder older than 24 hours is reclaimed; an unremovable holder is logged and does not fail the dispatch. The paragraph ends "Scenario 363 in `scenarios.md` exercises this paragraph." 363 is the lowest number neither ratified on master (which tops at 359) nor claimed by any of the 69 open pull requests, scanned at 2026-11-13T00:52Z; 360-362 are reserved by pending proposals.

(b) The second half of the 24-hour rule is stated: the leave-in-place sentence now also leaves "every holder that carries no creator record and was last modified within the last 24 hours, which covers a holder whose creator has not yet written its record."

(c) The signal sentence reads "When it receives SIGTERM, SIGHUP or SIGINT it MUST remove the holder, except a holder the next sentence spares, and then exit with a non-zero status.", because as proposed "MUST remove" and "MUST leave in place" could both apply to a named holder.

Co-edit outside the spec target, in the same commit: tests/heading-coverage.json gains a TODO row for Scenario 363 owned by bd-ib-immkx7 (integration tier or above), and tests/heading-coverage-debt.json gains the matching debt-register entry.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T00:52:57Z
verdict: NO BLOCKERS
proposal_stem: a-launcher-ended-by-a
content_digest: 673d54bd3121ffededef266f458b6d72e325631449f1bc5a54fff0e584a5712a
