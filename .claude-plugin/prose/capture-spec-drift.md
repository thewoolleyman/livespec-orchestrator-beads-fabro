# capture-spec-drift

Per `SPECIFICATION/constraints.md` §"Skill orchestration constraints", this is the harness-neutral operation prose; each runtime binding only maps its tools to it.

## What done looks like

Done reports the coverage attempt and any withheld reason, including a pass with zero findings,
plus the disposition of every surfaced drift candidate.

This heuristic counterpart to `capture-impl-gaps` compares the canonical Specification with the
implementation and routes consented findings through `propose-change`.

## Pre-requisites

- A `<spec-root>/` containing ratified spec content at the path
  declared in `.livespec.jsonc` (default: `SPECIFICATION/`).
- The consumer project's impl tree (the rest of the repo besides
  `<spec-root>/`).
- livespec installed and accessible — the propose-change cross-boundary
  handoff requires it.

## Flow

### Step 1 — Load the comparison baseline

Use the Spec Reader to load the current specification:

```python
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from pathlib import Path

snapshot = read_current_specification(spec_root=Path("SPECIFICATION"))
```

The snapshot is the "what the project says it does." The impl tree is
"what the project actually does." Drift is the delta.

### Step 2 — Survey the impl tree

Scan the consumer project's impl tree (excluding `<spec-root>/`,
`.venv/`, `_vendor/`, generated artifacts) for:

- Public API surfaces (function signatures, CLI flag declarations,
  config schema entries, REST/gRPC endpoint definitions, etc.).
- Behavior documented inline in code (docstrings, comments tagged
  `# spec:`, etc.).
- Tests that assert behavior visible to external consumers.

For each candidate, ask:

> Is this behavior reflected in the Specification? (yes / no / partial / skip)

- `yes` — no drift; move on.
- `no` — drift exists; behavior is not in the spec. Proceed to Step 3.
- `partial` — drift exists; spec captures some but not all of the
  behavior. Proceed to Step 3 with a "refinement" framing.
- `skip` — defer judgment.

### Step 3 — Per-finding propose-change handoff

For each `no` / `partial` finding:

1. Draft a one-sentence proposed-change framing the missing behavior.
2. Surface it to the user with the recommended action ("file a propose-change
   targeting `<spec-root>/`?").
3. On consent, invoke the propose-change operation as the cross-boundary
   handoff:

```bash
the propose-change operation --spec-target SPECIFICATION/ --topic <slug> --body <draft>
```

The proposed-change file lands under `<spec-root>/proposed_changes/`
awaiting a subsequent revise pass.

### Targeted mode — `--for-work-item <id>`

Gate 3's forced-drift closure path (`SPECIFICATION/contracts.md`
§"`implement`" → "gap-tied completion") invokes this operation in a
TARGETED mode instead of Step 1-2's whole-tree survey, when a gap-tied
work-item's recorded check file was modified since the baseline blob
hash recorded when it was cited. This mode reuses Step 3's
cross-boundary propose-change handoff; it does NOT duplicate it, and it
does NOT run Step 2's whole-tree survey — a whole-tree heuristic for one
already-known finding is the wrong shape and duplicates effort for a
single, already-mechanically-detected change.

1. Read the work-item's `gap_check_path` metadata (the check file that
   changed) and diff its current content against the recorded baseline
   blob (`git diff <baseline-blob-hash> -- <check-path>`, or an
   equivalent working-tree diff when the baseline blob object is
   unavailable locally).
2. Skip Step 2's whole-tree survey entirely. Present exactly ONE
   candidate to the user, framed from the diff itself: "the check
   `<check-path>` cited by `<item-id>` changed — does the spec clause it
   settles need to change to match?"
3. On consent, run Step 3's propose-change handoff exactly as in the
   whole-tree mode, targeting the spec clause the check settles.
4. On the resulting proposed-change file landing, record its canonical
   topic onto the work-item:

   ```python
   from livespec_orchestrator_beads_fabro.commands._gap_closure import record_drift_propose_change

   record_drift_propose_change(
       config=config,
       item_id=work_item_id,
       propose_change_topic=canonical_topic,
   )
   ```

   so `evaluate_gap_closure` (consumed by `implement`'s gap-tied closure
   step) stops refusing this item's closure on the drift leg.

### Step 4 — Summary

When all candidates are processed, print a summary:

- N impl behaviors surveyed
- M classified as drift, of which K were filed as propose-changes
- S skipped

### Step 5 — Record the run on the detection-coverage anchor

Per SPECIFICATION/contracts.md §"Detection coverage records and staleness
facts", EVERY invocation of this operation — the whole-tree survey and the
`--for-work-item` targeted mode alike, including one that aborts early or
that the user interrupts — appends an attributed ATTEMPT record to the
repository's designated detection-coverage anchor. Run this step LAST, on
every exit path.

The anchor is a ledger item the OPERATOR provisions once through
`capture-work-item`, with its id committed as
`dispatcher.detection_coverage_anchor` in `.livespec.jsonc`. This
operation never creates it: when the key is unset,
`record_detection_run` returns an `AnchorNotConfigured` failure, and the
correct response is to tell the user the anchor is owed — not to file one
on their behalf.

```python
from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    DRIFT_CAPTURE_OPERATION,
    DetectionRun,
    detection_coverage_anchor,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    default_invoker_identity,
)

outcome = record_detection_run(
    path=config,
    anchor=detection_coverage_anchor(cwd=project_root),
    run=DetectionRun(
        operation=DRIFT_CAPTURE_OPERATION,
        # The declared scope: the whole-tree survey, the `--since-version`
        # value when one scoped the ledger-intent scan, or the targeted
        # `--for-work-item <id>` mode.
        scope=declared_scope,
        invoker=default_invoker_identity().invoker,
        # "succeeded" ONLY for a run that reached its own terminal summary.
        outcome=run_outcome,
        exit_code=run_exit_code,
        # Every finding this pass surfaced, and the subset durably disposed
        # — handed off to propose-change, or explicitly declined on the
        # record. A deferred or skipped finding is NOT a disposition.
        surfaced_candidates=tuple(surfaced_finding_keys),
        disposed_candidates=tuple(disposed_finding_keys),
        # True when the declared range was only partly walked.
        partial_range=partial_range,
        # The default-branch merge SHA this pass ran through.
        coverage_point=default_branch_sha,
    ),
)
```

⛔ DO NOT PRE-JUDGE WHETHER A COMPLETED RECORD IS OWED, AND DO NOT SUPPRESS
THE CALL TO AVOID WRITING ONE. `record_detection_run` decides that itself
and is the only surface that may: it always appends the attempt record,
and appends the all-or-nothing COMPLETED-coverage record only when the run
qualifies. Report `withheld_reason` verbatim to the user when it is
present — an aborted pass that says nothing about its coverage reads to
the operator exactly like one that succeeded, and the coverage point
silently did not move.

These two appends are the ONLY ledger writes this operation performs; the
ledger-intent scan of Step 2 stays strictly read-only, and this exception
covers exclusively this run's own records.

## Important properties

- **LLM-assisted, user-in-the-loop** — every drift finding requires
  explicit user consent before a propose-change is filed. The operation
  does NOT auto-file.
- **Read-only on the impl tree** — the operation never modifies source
  code. Spec authorship happens through the propose-change operation,
  not here.
- **Spec-side write goes through the cross-boundary handoff** — this
  plugin never writes to `<spec-root>/proposed_changes/` directly. The
  handoff invocation is the surface contract.

## What this operation does NOT do

- Does NOT modify the impl tree.
- Does NOT modify the spec tree directly. Routes through
  the propose-change operation.
- Does NOT detect spec→impl gaps. That's the `capture-impl-gaps`
  operation.
- Does NOT auto-accept findings. User confirms every handoff.
