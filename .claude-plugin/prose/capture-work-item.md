# capture-work-item

Harness-neutral driving prose for the `capture-work-item` operation,
per `SPECIFICATION/constraints.md` §"Skill orchestration constraints":
this artifact is the plugin-owned LLM-facing half of the operation —
the consent flow, the multi-step dialogue, the
`livespec_orchestrator_beads_fabro.*` package calls, and the JSON /
handoff semantics. Each per-runtime SKILL.md is a THIN binding that
resolves the plugin root, reads this prose in full, and maps its
harness-neutral vocabulary (the `<plugin-root>` token, the
"ask the user" / "read the file" / "write the file" verbs, the named
sibling operations) to that runtime's tools. Nothing in this file
names a specific agent runtime's tools or command namespace.

The freeform direct-filing operation. Use this for bugs, refactors,
tactical tasks, and anything else that doesn't trace back to a spec
rule. For spec-traceable items, use the `capture-impl-gaps` operation
instead.

## Pre-requisites

- The work-items store (the resolved beads tenant connection) is
  reachable.
- `livespec_orchestrator_beads_fabro` package on import path.

## Flow

### Step 1 — Gather inputs

Ask the user (one question at a time):

1. **Title** — one-line summary.
2. **Description** — multi-line free-form (markdown permitted).
3. **Type** — one of `bug`, `feature`, `task`, `chore`, `epic`.
Optional follow-ups (skip-confirmable):

- **Acceptance criteria** — the gradeable assertions the item is judged
  against; string or null (default null). Author them to the rules in
  "Writing acceptance criteria" below BEFORE filing.
- **Size justification** — null unless the sanctioned effective-criteria
  count exceeds a configured adopted assertion-count ceiling. An exception is
  valid only as an object with EXACTLY `rationale`, `author`, and `at`: each
  value is a non-empty string after trimming and `at` is an ISO-8601
  timestamp. Gather the rationale and attribution from the approving human;
  never invent them. A malformed or absent object does not waive the gate.
- **Assignee** — string or null (default null).
- **Depends-on** — comma-separated work-item ids (the tenant's
  configured `<prefix>-XXXXXX` form); empty list permitted.
- **Plan parent** — when the caller is filing this as a child of a
  plan epic, the plan epic id; otherwise null. This is distinct from
  `depends_on`: plan-child linkage is a beads parent-child relation, not
  a blocker edge.
- **Spec-commitment-hint** — string `id_hint` or null (default null).
  Supplied via `--spec-commitment-hint <id_hint>` when the work-item
  is being filed in response to a spec-side
  `spec_commitments.impl_followups[].id_hint` declaration (per livespec
  `SPECIFICATION/contracts.md` §"Implementation-plugin contract — the
  10-skill surface" → "Work-item `spec_commitment_hint` field"). When
  supplied, the resulting record's `spec_commitment_hint` MUST equal
  the verbatim `id_hint`; when omitted, the field defaults to `null`
  (the freeform case). This is the surface livespec's
  `unresolved-spec-commitment` doctor invariant queries via
  `list-work-items --json` to verify each declared spec→impl
  commitment maps to a filed work-item.

#### Writing acceptance criteria

The acceptance pass grades the criteria field one gradeable ASSERTION at a
time, as standalone claims. `criteria_lines` segments the field by CONTENT,
never by line width: only a blank line, a list marker, or a header starts a
block, and each block is then split into sentences. A flush-left line with
no marker CONTINUES the block above it. Filers MUST therefore write **one
bulleted assertion per criterion, ending in a period**:

- **One `- ` bullet per assertion, each a complete sentence with a
  terminal period.** The marker starts the block and the period ends the
  sentence, so the assertion is graded on its own however the text is
  later reflowed. Plain flush-left lines with no marker and no period
  collapse into ONE assertion (measured 2026-08-31: nine such lines
  parsed as one; the same nine as bullets parsed as nine).
- **Wrapping is safe inside a bullet.** A continuation line, indented or
  not, joins the sentence it belongs to; what must not happen is two
  assertions sharing one sentence.
- **Keep rationale, provenance and explanation out of the field.** They
  belong in the description or a ledger comment; in the criteria field
  they become sentences that are graded as assertions.
- **No negative criteria.** The judge passes a criterion on literal
  merged-diff vocabulary, and "no file contains X" has none to offer.

Apply this AT FILING TIME. Acceptance grades the criteria SNAPSHOT taken
at dispatch time, not the live ledger row, so a post-dispatch reflow of
the criteria is inert against the run already in flight: rewriting the
field after dispatch cannot rescue that dispatch, and the failure only
surfaces after the work has merged. Filing conforming criteria here is
the whole mitigation.

#### Authoring the Definition of Done

An implement-kind item's criteria belong in a `## Definition of Done`
section that is the FIRST heading of its description — that section is the
first effective-criteria source, and the criteria field above is a LEGACY
one kept for items already in flight. Offer to author the section, and
author it to the four rules below, which are the rules the `dod_gate` node
and the host-side wall both grade it against
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
  assertion names, THAT heading is the one to name, because the proof
  steps exercise the scenario's own Given/When/Then.
- **Never state the carrier relation inside the section.** Which plan
  assertions a child carries is recorded only in its epic's carrier map;
  repeat it as prose BEFORE the Definition of Done heading if it helps a
  reader, never as a bullet inside the section.

### Step 2 — Confirm and file

Resolve the six intake answers in Step 3, show the user the assembled record
including the raw `size_justification`, and ask "file?". On `yes`, call the
single filing seam below. It validates the committed adopted-ceiling setting
BEFORE its first ledger write, records the justification before routing, and
then invokes the shared intake gate; do not split those acts into hand-written
store calls:

```python
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.work_items.rank import key_between
from datetime import datetime, timezone
from pathlib import Path

config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None)
rank = key_between(a=None, b=None)
item = WorkItem(
    # The id-prefix is the tenant's server-stored bd create-prefix
    # (config.prefix), DECOUPLED from the tenant DB name — so the id
    # carries config.prefix, not a hardcoded `li-`.
    id=new_work_item_id(prefix=config.prefix),
    type=type_,
    status="backlog",
    title=title,
    description=description,
    origin="freeform",
    gap_id=None,
    rank=rank,
    assignee=assignee,
    depends_on=tuple(depends_on),
    captured_at=datetime.now(tz=timezone.utc).isoformat(),
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
    spec_commitment_hint=spec_commitment_hint,  # str | None; None for freeform.
    # One `- ` bullet per assertion, each ending in a period, per "Writing acceptance criteria".
    acceptance_criteria=acceptance_criteria,  # str | None; None when unsupplied.
)
verdict = file_captured_work_item(
    path=config,
    item=item,
    size_justification=size_justification,
    plan_parent_id=plan_parent_id,
    checklist=DefinitionOfReadyChecklist(
        single_coherent_done=single_coherent_done,
        autonomously_verifiable=autonomously_verifiable,
        autonomy_tiered=autonomy_tiered,
        dependency_linked=dependency_linked,
        repo_targeted=repo_targeted,
        above_floor=above_floor,
    )
)
```

`verdict` is an `IOResult`. If it is a failure, surface its configuration or
store error and STOP: no item was filed when committed ceiling validation
failed. On success, unwrap the routed status and continue.

An epic IS a plan, so an epic filed here MUST carry the canonical
`plan_slug` that listings and the Control-Plane surface resolve it by —
every epic-creating route owes that write, not just the `plan` front-end.
Derive it from the title by passing no `slug`; supply one only when the
user names a handle, and let the primitive canonicalize it rather than
canonicalizing by hand:

```python
from livespec_orchestrator_beads_fabro.commands._plan_identity import tag_epic_plan_slug

if item.type == "epic":
    plan_slug = tag_epic_plan_slug(config=config, epic_id=item.id, title=item.title)
```

Print the assigned id back to the user, plus `plan_slug` for an epic.

Then resolve and DISPLAY the filing, through the one public display primitive
every filing front-end uses — never by re-reading the criteria field or the
description by hand
(`SPECIFICATION/contracts.md` §"Effective acceptance criteria" and
§"Definition of Done and Proof of Done"):

```python
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import (
    filing_display,
)

filing_advice = filing_display(item=item, cwd=Path.cwd())
```

Show the user every line of `filing_advice`. It carries four things, and each
is there because it answers a question the filer would otherwise have to go and
re-derive:

- the effective-criteria parse — the gradeable-assertion count and the resolved
  source (`description-definition-of-done`, or the legacy `criteria-field` /
  `description-exit-criteria`, in which case the line also carries
  `definition-of-done: missing`);
- each assertion with its proof mode, so the POSITION-declared modes are
  visible as the machine read them rather than as the author intended them;
- the resolved sandbox capabilities — the committed
  `dispatcher.sandbox_capabilities` array, or `sandbox-capabilities:
  unpublished` when the key is unset — which is what a `factory_captured`
  declaration has to be chosen against;
- every Definition-of-Done finding the host-side wall can detect, each labelled
  `(mechanical)` or `(advisory)`.

This is ADVICE, never a refusal: capture MUST NOT refuse on a finding or on an
empty parse, because filing stays consent-gated and criteria may legitimately
arrive at groom time. When the filer declines the section, the display reports
`definition-of-done: missing` and the filing proceeds.

Say plainly what each kind costs, though, because the two differ:

- a MECHANICAL finding — the section absent, a reference that does not resolve,
  a `### Host-captured` / `### Human-attested` sub-heading with no `Reason:`
  line — WITHHOLDS `ready`: Step 3 below files the item but will not route it
  onward, and the pre-dispatch wall refuses it with exit code `5`;
- an ADVISORY finding — a test-existence form, a generic reference where a
  scenario governs the assertion, a carrier relation stated inside the section —
  does NOT withhold `ready`, because only the `dod_gate` node can judge it. It
  is surfaced by `needs-attention` while the item rests in `ready`, and the gate
  will rest the run at needs-human if it survives to dispatch.

Either kind is also recorded on the filed item as a ledger comment by Step 3,
so it is repaired where it was made. The remedy for an empty parse is to author
the section (here, or later via groom or edit), or to set the item's
`acceptance_policy` to `human-only` where machine grading is genuinely
inapplicable.

### Step 3 — Run the intake Definition-of-Ready checklist

Every capture front-end MUST run the intake Definition-of-Ready
checklist at capture and route the filed item into its lifecycle state
(SPECIFICATION/scenarios.md "Scenario 8 — Intake Definition-of-Ready
triage"; contracts.md §"Gap-detectable behavior clauses"). The gate
logic is the ONE shared `livespec_orchestrator_beads_fabro.intake_dor`
primitive — never re-derive the gates in prose here.

Resolve the six gates from the inputs you already gathered plus a short
confirmation dialogue (one question at a time; many gates are already
answerable from Step 1):

- `single_coherent_done` — does the item describe exactly ONE coherent
  "done"? (more than one means an epic routed to `backlog`)
- `autonomously_verifiable` — can the acceptance be checked WITHOUT a
  human judgement call?
- `autonomy_tiered` — does the item carry an explicit autonomy tier?
- `dependency_linked` — are its blockers linked (the `depends_on` set),
  or does it genuinely have none?
- `repo_targeted` — does it name the repo it lands in?
- `above_floor` — is it above the size floor (worth a discrete
  dispatch)?

Step 2 already routed the just-filed item through this checklist. Do NOT call
the router a second time: comments are append-only and a second pass would
duplicate the audit record. The unwrapped status is one of
`pending-approval` / `ready` / `backlog` / `blocked`.

Narrate the verdict to the user:

- `pending-approval` — DoR-passing and waiting for the admission valve.
- `ready` — DoR-passing and approved onward because the effective
  `admission_policy` is `auto` and no dependency edge blocks dispatch.
- `backlog` — either epic-shaped or above the adopted assertion ceiling
  without a valid justification. For the size case, show the recorded reason
  verbatim; it names the adopted ceiling, sanctioned-parser count, and missing
  or invalid justification.
- `blocked` — not autonomously verifiable or missing a dispatch facet;
  carries `blocked_reason: needs-human` and MUST NOT be filed `ready`.

`apply_intake_dor` also applies the filing-time Definition-of-Done wall from
Step 2: an item carrying an outstanding MECHANICAL finding lands
`pending-approval` even when its effective `admission_policy` is `auto`, and
every finding of either kind is appended to the item as a ledger comment. So a
`pending-approval` verdict on an item the six gates passed means the display's
mechanical finding is what is holding it — say so rather than attributing it to
the admission valve.

If the item has unresolved blockers, make sure the dependency edges are
linked in `depends_on`; linked blockers derive the dependency lane and
MUST NOT be bypassed by direct `ready` routing.

If the item is part of a plan thread, make sure the plan epic is linked
through `plan_parent_id` / `parent_id`, not `depends_on`. Task children
cannot block epics on the live beads server, and the plan archive gate
enumerates parent-child children when refusing archive for undisposed
work.

## Important properties

- **`origin: freeform`** — never `gap-tied`. Use the `capture-impl-gaps`
  operation for gap-traceable items.
- **`gap_id: null`** — REQUIRED. The schema check fires on any
  non-null value combined with `origin: freeform`.
- **Closure path** — closed via the `implement` operation's freeform
  fix path (a user-supplied `--reason` with no re-detection step).

## What this operation does NOT do

- Does NOT close work-items. Use the `implement` operation.
- Does NOT detect gaps. Use the `capture-impl-gaps` operation.
- Does NOT auto-set `assignee` or `depends_on`. User supplies both.
