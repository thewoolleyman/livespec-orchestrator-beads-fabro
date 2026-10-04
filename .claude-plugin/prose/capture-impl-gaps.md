# capture-impl-gaps

Harness-neutral driving prose for the `capture-impl-gaps` operation,
per `SPECIFICATION/constraints.md` §"Skill orchestration constraints":
this artifact is the plugin-owned LLM-facing half of the operation —
the consent flow, the multi-step dialogue, the
`livespec_orchestrator_beads_fabro.*` package calls, the wrapper-CLI
invocation flow, and the JSON / handoff semantics. Each per-runtime
SKILL.md is a THIN binding that resolves the plugin root, reads this
prose in full, and maps its harness-neutral vocabulary (the
`<plugin-root>` token, the "ask the user" / "read the file" verbs, the
named sibling operations) to that runtime's tools. Nothing in this file
names a specific agent runtime's tools or command namespace.

Mechanically surface untracked spec clauses as candidate gaps, then walk
the user through classifying each against the implementation (Step 2) —
the tool never reads implementation state itself; that comparison is a
human judgement call. The plugin's `detect-impl-gaps` thin-transport
sibling operation and `store` module are the load-bearing surfaces this
operation composes.

## Pre-requisites

- The consumer project has a `<spec-root>/` directory at the path
  declared in `.livespec.jsonc` (default: `SPECIFICATION/`).
- The `livespec-orchestrator-beads-fabro` Python package is on the import path.
  The shipped wrappers self-bootstrap this: `bin/_bootstrap.py` adds
  `scripts/` and `scripts/_vendor/` to `sys.path`, so each
  `python3 "<plugin-root>/scripts/bin/<name>.py"` invocation
  resolves `livespec_orchestrator_beads_fabro` and the vendored
  `livespec_runtime` with no `uv` and no project venv.
- The work-items JSONL store path is reachable (created on first
  append if absent).

## Flow

### Step 1 — Enumerate gap candidates via detect-impl-gaps

Invoke the sibling thin-transport `detect-impl-gaps` operation to
retrieve the authoritative gap-id set. Per
SPECIFICATION/contracts.md §"capture-impl-gaps", both this operation
and the doctor invariants consume the same canonical surface; in-skill
duplication of the detection logic is forbidden.

Run the operation twice — once with `--json` for the authoritative
gap-id set, once without for the rich line form used to surface each
candidate to the user in Step 2:

```bash
# Authoritative gap-id set:
python3 "<plugin-root>/scripts/bin/detect_impl_gaps.py" --json
# → {"gap_ids": ["gap-abc123", "gap-def456", ...]}

# Rich human-readable context for display:
python3 "<plugin-root>/scripts/bin/detect_impl_gaps.py"
# → each line: <spec-file> > <heading-path>  [<gap_id>]  <rule-text>
```

Both invocations use the same canonical `detect_rules` function and
emit deterministically-sorted output, so the two outputs can be joined
by `gap_id` to produce a candidate list of
`(gap_id, spec_file, heading_path, rule_text)` tuples. The `--json`
form is the authoritative set; the rich form is convenience metadata
for human display.

#### Optional `--since-version <vN>` scoping

`capture-impl-gaps` accepts an optional `--since-version <vN>` flag
and passes it through verbatim to BOTH `detect-impl-gaps` invocations
above. When set, gap detection is restricted to spec files whose
content differs between historical version `<vN>` and the live spec.

```bash
# Scoped to changes introduced since v082:
python3 "<plugin-root>/scripts/bin/detect_impl_gaps.py" --json --since-version v082
python3 "<plugin-root>/scripts/bin/detect_impl_gaps.py" --since-version v082
```

The flag is the user-facing surface that callers (notably
the propose-change/revise post-step per the parent coordinating epic,
livespec PC `revise-post-step-capture-impl-gaps`) use to scope
per-revise gap detection to the diff that revise just introduced.
Direct user invocations MAY use it for any "show me gaps for changes
since this version" workflow.

Validation is delegated to `detect-impl-gaps`. If the value is
invalid:

- Non-integer / non-positive input → `detect-impl-gaps` exits `2`
  with a usage error.
- Missing version directory (`<spec-root>/history/v<padded-N>/`
  does not exist) → `detect-impl-gaps` exits `3` with a
  `SpecVersionNotFoundError` message.

In either case, `capture-impl-gaps` surfaces the error to the user
and aborts before reaching Step 2; no work-items are filed.

When `--since-version` is omitted, behavior is unchanged — every
file in the live spec is scanned.

### Step 2 — Per-rule gap classification

For each candidate, ask the user:

> Is the implementation honoring this rule? (yes / no / skip)

- `yes` — no gap; move on.
- `no` — a gap exists. Proceed to Step 3.
- `skip` — defer judgment; move on without filing.

### Step 3 — Per-gap consent + filing

For each `no` rule, the `gap_id` is already in hand from Step 1 (derived
inside `detect-impl-gaps` from `<spec-file>\x1f<heading-path>\x1f<rule-text>`
hashing; shape `gap-<8-char-base32-suffix>`). Then:

1. Check the work-items store: if a record with this `gap_id` already
   exists and is not closed, surface "already filed as `<li-id>`" and
   skip filing.
2. Otherwise, ask the user to confirm title + description (auto-drafted
   from the rule text). Defaults are pre-filled; the user accepts or
   edits. Offer to author the item's `## Definition of Done` section as the
   FIRST heading of that description, to the rules below.
3. On confirm, append a new work-item JSONL record. Initialize `prev_rank` once before the per-gap filing pass; each newly filed item threads the prior value through `key_between(a=prev_rank, b=None)` so multi-item passes preserve filing order.

```python
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.work_items.rank import key_between
from datetime import datetime, timezone
from pathlib import Path

config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None)
prev_rank: str | None = None

# Inside each confirmed filing:
rank = key_between(a=prev_rank, b=None)
prev_rank = rank
item = WorkItem(
    # The id-prefix is the tenant's server-stored bd create-prefix
    # (config.prefix), DECOUPLED from the tenant DB name — so the id
    # carries config.prefix, not a hardcoded `li-`.
    id=new_work_item_id(prefix=config.prefix),
    type="task",
    status="pending-approval",
    title=user_confirmed_title,
    description=user_confirmed_description,
    origin="gap-tied",
    gap_id=gap_id,
    rank=rank,
    assignee=None,
    depends_on=(),
    captured_at=datetime.now(tz=timezone.utc).isoformat(),
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
)
append_work_item(path=config, item=item)
```

#### Authoring the Definition of Done

A gap-tied item is implement-kind, so it carries a `## Definition of Done`
section as the FIRST heading of its description. A gap's rule text names the
spec RULE, which is a good reference line and a poor assertion — the assertion
has to name what the delivered artifact will DO. Author the section to these
four rules, which are the rules the `dod_gate` node and the host-side wall both
grade it against
(`SPECIFICATION/contracts.md` §"Definition of Done and Proof of Done").

- **One behavioural assertion per bullet.** Each `- ` bullet is ONE
  gradeable assertion naming an observable behaviour of the delivered
  artifact on a real surface, written as a complete sentence ending in a
  period. An assertion whose subject is the existence, coverage or passing
  of tests or checks is a TEST-EXISTENCE assertion, and it is legitimate
  ONLY when the item's deliverable is itself a test, a check or a gate; on
  any other item, restate it as the behaviour those tests were meant to
  establish.
- **One proof mode per assertion, chosen in order.** The modes are
  `factory_captured`, then `host_captured`, then `human_attested`, and an
  assertion carries the FIRST of them that can actually prove it against
  the sandbox capabilities the display reports below. `factory_captured`
  is the default and needs no declaration. The other two are declared by
  POSITION — put the assertion under a `### Host-captured` or
  `### Human-attested` sub-heading inside the section, each carrying a
  non-empty `Reason:` line before its first bullet: the host surface or
  released-build requirement for the first, and why no agent session can
  exercise the proof for the second.
- **Reference the scenario that governs the assertion.** The section
  carries exactly one `References:` line naming the verbatim text of an
  existing H2 heading of the governed spec tree. Where a
  `## Scenario NN — ...` heading of `scenarios.md` states the behaviour an
  assertion names, THAT heading is the one to name — in preference to the
  heading the gap itself was detected under — because the proof steps
  exercise the scenario's own Given/When/Then.
- **Never state the carrier relation inside the section.** Which plan
  assertions a child carries is recorded only in its epic's carrier map;
  repeat it as prose BEFORE the Definition of Done heading if it helps a
  reader, never as a bullet inside the section.

Then DISPLAY the filing before the next gap is processed, through the one
public display primitive every filing front-end uses:

```python
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import (
    filing_display,
)

filing_advice = filing_display(item=item, cwd=Path.cwd())
```

Show the user every line. It carries the effective-criteria parse, each
assertion with its proof mode, the resolved sandbox capabilities (the committed
`dispatcher.sandbox_capabilities` array, or `sandbox-capabilities: unpublished`
when the key is unset), and every Definition-of-Done finding the host-side wall
can detect, each labelled `(mechanical)` or `(advisory)`. When the filer
declines the section it reports `definition-of-done: missing`. This is ADVICE,
never a refusal — a gap capture MUST NOT refuse on a finding — but the two
kinds differ in consequence: a MECHANICAL finding WITHHOLDS `ready` at the
intake step below, while an ADVISORY one does not and is instead surfaced by
`needs-attention` while the item rests in `ready`. Either kind is recorded on
the filed item as a ledger comment.

#### Intake Definition-of-Ready (per filed gap)

Every capture front-end MUST run the intake Definition-of-Ready
checklist at capture and route the filed item into its lifecycle state
(SPECIFICATION/scenarios.md "Scenario 8 — Intake Definition-of-Ready
triage"; contracts.md §"Gap-detectable behavior clauses"). The gate
logic is the ONE shared `livespec_orchestrator_beads_fabro.intake_dor`
primitive — never re-derive the gates in prose here.

Immediately after filing each gap-tied item, resolve the six gates from
the gap context (the rule text usually names a single coherent "done"
and a repo target) plus a short confirmation, then route the item:

```python
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)

verdict = apply_intake_dor(
    path=config,
    item_id=item.id,
    checklist=DefinitionOfReadyChecklist(
        single_coherent_done=single_coherent_done,
        autonomously_verifiable=autonomously_verifiable,
        autonomy_tiered=autonomy_tiered,
        dependency_linked=dependency_linked,
        repo_targeted=repo_targeted,
        above_floor=above_floor,
    ),
)
# verdict is one of "pending-approval" / "ready" / "backlog" / "blocked".
```

Narrate the verdict: `pending-approval` is DoR-passing and waiting for
the admission valve; `ready` is DoR-passing and approved onward because
the effective `admission_policy` is `auto` and no dependency edge blocks
dispatch; `backlog` is epic-shaped and waiting for decomposition;
`blocked` means the acceptance needs a human judgement call or a dispatch
facet is missing and carries `blocked_reason: needs-human`. If unresolved
blockers exist, keep their dependency edges linked in `depends_on`; linked
blockers derive the dependency lane and MUST NOT be bypassed by direct
`ready` routing.

`apply_intake_dor` also applies the filing-time Definition-of-Done wall: an
item carrying an outstanding MECHANICAL finding lands `pending-approval` even
when its effective `admission_policy` is `auto`. So a `pending-approval`
verdict on an item the six gates passed means the display's mechanical finding
is what is holding it — say so rather than attributing it to the admission
valve.

### Step 4 — Summary

When all candidates are processed, print a summary:

- N candidate rules surfaced
- M classified as gaps, of which K were newly filed and J were already-tracked
- Skipped: S

### Step 5 — Record the run on the detection-coverage anchor

Per SPECIFICATION/contracts.md §"Detection coverage records and staleness
facts", EVERY invocation of this operation — including one that aborts in
Step 1, one the user interrupts mid-classification, and one that surfaces
nothing at all — appends an attributed ATTEMPT record to the repository's
designated detection-coverage anchor. Run this step LAST, on every exit
path.

The anchor is a ledger item the OPERATOR provisions once through
`capture-work-item`, with its id committed as
`dispatcher.detection_coverage_anchor` in `.livespec.jsonc`. This
operation never creates it: when the key is unset,
`record_detection_run` returns an `AnchorNotConfigured` failure, and the
correct response is to tell the user the anchor is owed — not to file one
on their behalf.

```python
from livespec_orchestrator_beads_fabro.commands._detection_coverage import (
    GAP_CAPTURE_OPERATION,
    DetectionRun,
    detection_coverage_anchor,
    record_detection_run,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import (
    default_invoker_identity,
)
from livespec_orchestrator_beads_fabro.spec_reader import current_specification_version

outcome = record_detection_run(
    path=config,
    anchor=detection_coverage_anchor(cwd=project_root),
    run=DetectionRun(
        operation=GAP_CAPTURE_OPERATION,
        # The declared scope: the `--since-version` value when one was
        # supplied, else the whole live spec tree.
        scope=declared_scope,
        invoker=default_invoker_identity().invoker,
        # "succeeded" ONLY for a run that reached its own terminal summary.
        outcome=run_outcome,
        exit_code=run_exit_code,
        # Every gap id Step 1 surfaced, and the subset Step 3 durably
        # disposed — filed, handed off, or explicitly declined on the
        # record. A `skip` in Step 2 is NOT a disposition.
        surfaced_candidates=tuple(surfaced_gap_ids),
        disposed_candidates=tuple(disposed_gap_ids),
        # True when the declared range was only partly walked.
        partial_range=partial_range,
        # The ratified spec revision this pass ran against.
        coverage_point=f"v{current_specification_version(spec_root=spec_root):03d}",
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

These two appends are the ONLY ledger writes this operation performs
outside its per-gap consent flow. No other record is created or edited.

## Important properties

- **In-memory ephemeral detection state** — no persistent intermediate
  artifact. The candidate list is discarded at operation exit per
  livespec/SPECIFICATION/contracts.md §"Heavyweight authored
  skills (6)" → capture-impl-gaps.
- **Per-gap user consent is REQUIRED** — never auto-file without
  explicit confirmation.
- **Idempotent** — re-running surfaces no duplicates for gaps already
  tracked (status≠closed).
- **No LLM in the detection path itself** — pattern-matching of MUST /
  SHOULD clauses is deterministic. LLM dialogue is used only for the
  classification and authoring steps (and only with user-in-the-loop).

## What this operation does NOT do

- Does NOT close work-items. Use the `implement` operation for that.
- Does NOT modify the spec tree (all spec reads are delegated to
  the `detect-impl-gaps` operation).
- Does NOT detect impl→spec drift. That's the `capture-spec-drift`
  operation.
