# acp-implement-zero-output-hang

**Ledger anchor:** bd-ib-b5dg

A verified factory-dispatch defect, escalated from the console repo on
2026-08-29 at the maintainer's direction: an ACP implement-agent in the Fabro
`implement-work-item` workflow (factory `hp`) activates and then produces zero
output — zero stdout, zero stderr, zero inference — until the 30-minute ACP
turn timeout fires; the in-run retry hangs identically, so each occurrence
burns roughly 60 minutes of factory wall-clock before parking on a needs-human
interview.

## Notation used in this document

- **Zero-output turn** — an ACP agent turn whose timeout event reports
  `stderr[0b]` `stdout[0b]` with `active_time_ms=0`, `inference_time_ms=0`,
  `tool_time_ms=0`.
- **Launch env** — the environment delivered to the ACP agent process at
  PROCESS LAUNCH; a stage retry inside the same run reuses it, a fresh
  dispatch does not.
- **Measured / inferred / hypothesis** — the dossier labels every claim; keep
  the labels when quoting it.

## What this track is

One live, fully-evidenced occurrence (run `01M16KMWY5Y2DY0X90S1BDXCQX`,
2026-08-29, dispatched for `livespec-console-beads-fabro-txtzn5.14`) plus its
bounds and prior art, written up in
`research/001-acp-implement-zero-output-hang-dossier.md`. The prior-art scan
(full tenant ledger, 832 records, 2026-08-29) found NO existing item tracking
the zero-output activation hang itself; the nearest neighbors — `bd-ib-2nq`
(token-refresh lore the launch-env hypothesis overlaps), `bd-ib-oj71`
(dead-implementer circuit breaker, Codex-usage-window trigger),
`livespec-impl-beads-oyg` (silent-stall watchdog, covers zero-EVENT runs not
zero-OUTPUT turns) — are cross-referenced in the dossier, not duplicated
here.

The plan's three aims, with grooming owning the final cut:

1. Root-cause the zero-output activation hang (launch-env/token delivery into
   the remote sandbox ACP adapter is the leading hypothesis).
2. Fail fast: kill-and-retry WITH FRESH LAUNCH ENV, or a typed stage failure,
   after a zero-output floor measured in minutes — never 2×30 min before a
   human gate.
3. Surface zero-output agent turns as a first-class telemetry signal.

Consequence while this stays open: the console repo's test-adequacy coverage
lane (epic `livespec-console-beads-fabro-4jb3kl`) has PAUSED factory dispatch
of its remaining children pending an orchestrator-side fix.

## Timeline

- **2026-08-29** — plan opened. Ledger epic `bd-ib-b5dg` created and verified
  by read-back; prior-art scan completed (no overlap owning this defect);
  dossier 001 written from the console repo's live catch.
- **2026-08-29** — dossier corrected before merge, on the console team-lead's
  relay of the filer's own retraction: `bd-ib-a4e7` was withdrawn as a false
  alarm (kept only as a history note), and the not-universal hedge was
  strengthened with the corrected `ag0` facts (two completed runs, PR #873 and
  PR #876). The ledger epic description was corrected to match, verified by
  read-back.

## Next action

Next action: groom the plan epic bd-ib-b5dg into ready, dependency-layered children starting from the three aims in research/001-acp-implement-zero-output-hang-dossier.md.
