---
topic: orchestrate-to-drive-rename-and-next-asymmetry
author: claude-opus-4-8
created_at: 2026-07-06T02:56:20Z
spec_commitments:
  impl_followups:
    - id_hint: orchestrate-to-drive-rename-and-plan-retirement
      description: |
        Rename the operator surface from `orchestrate` to `drive` across this plugin's
        code and tests, and demote it to a pure executor. Rename
        `.claude-plugin/scripts/bin/orchestrate.py` -> `.claude-plugin/scripts/bin/drive.py`
        and the shared `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/orchestrate.py`
        -> `commands/drive.py`, plus the Claude operator SKILL.md binding and the Codex
        binding for this plugin. RETIRE the `plan` two-`next` composition sub-command and
        the bare interactive walkthrough (composition relocates to the future
        `needs-attention` read surface; the interactive see -> select -> execute loop
        belongs to the console); REMOVE the spec-action (`spec:<action>:<index>`) handoff
        path from the executor (spec-side actions are routed by the awareness surface as a
        human handoff, not `drive`-executable). KEEP the impl-dispatch action and the five
        human valve/policy actions (`approve:` / `accept:` / `reject:` /
        `set-admission:` / `set-acceptance:`) and their existing semantics. Rename the
        exercising tests (`tests/integration/test_orchestrate_*` and
        `tests/**/*orchestrate*`) to their `drive` equivalents and rebind the
        `tests/heading-coverage.json` entries for Scenarios 17 / 21 / 31 to the renamed
        test node ids. (The `SPECIFICATION/README.md` orientation references are NOT an
        impl follow-up: README is a governed, revise-tracked spec target amended in this
        same revise pass — see Proposed Change K below.)
        Cross-repo rename blast radius (the `livespec-driver-claude` /
        `livespec-driver-codex` bindings and the `livespec-console-beads-fabro`
        Scenario 11 reference to "the `orchestrate` action surface") is carried by the
        sibling pieces of the `needs-attention` epic, not by this plugin's follow-up.
---

## Proposal: Rename the `orchestrate` operator surface to `drive`, retire `orchestrate plan`, and document the `next` scope-asymmetry

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- SPECIFICATION/constraints.md
- SPECIFICATION/spec.md
- SPECIFICATION/README.md

### Summary

Rename this plugin's single operator skill from `orchestrate` to `drive`
and demote it to a **pure executor**: `drive` executes exactly one
operator action identified by its action-id (an `impl:` dispatch action
or one of the five human valve/policy actions), and composes/ranks
nothing. The `orchestrate plan` two-`next` composition sub-command and
the bare `orchestrate` interactive walkthrough are **retired** — the
composition/awareness role relocates to a future `needs-attention` read
surface, and the interactive "see -> select -> execute" loop belongs to
the console. `drive` and `needs-attention` are **peers coupled only by
the shared action-id grammar**; neither calls the other, and spec-side
actions are no longer `drive`-executable (the awareness surface routes
them as human handoffs). Independently, a spec statement is added
documenting the **`next` scope-asymmetry**: this plugin's impl-side
`next` is a pure ranker of dispatchable `ready` work (action `implement`
only) that deliberately excludes the impl-side human valves, whereas the
spec-side `/livespec:next` includes human actions (e.g. `revise`); so
composing *only the two `next`s* (what the retired `orchestrate plan`
did) yields an incomplete attention picture that no caller should
rebuild.

### Motivation

This is spec piece SP1 of the cross-repo `needs-attention` epic (anchored
by the plan thread `plan/needs-attention/` in the `livespec` core repo;
design record `plan/needs-attention/research/design.md`). The design
extracts "what needs attention" into a first-class reusable read surface
(`needs-attention`) and demotes the former `orchestrate` surface to a
pure executor. Per that design: "`orchestrate` was demoted to a pure
executor, so it no longer deserves the name of the whole plane — hence
`drive`, the fleet's own verb for making the work-item machinery go (it
spans both the factory and the ledger). `orchestrate plan` retires; its
composition role moves to `needs-attention`." And: "`needs-attention` and
`drive` are peers, not layered — coupled ONLY by the shared action-id
grammar. Neither calls the other." Spec-first ordering: the current
contract enumerates `orchestrate`'s composition + walkthrough surfaces, so
the spec must be amended before the code rename lands, or the rename would
create impl->spec drift that `capture-spec-drift` would flag. The
`next` scope-asymmetry is documented "so no one rebuilds the incomplete
two-`next` composition" (design record §"Why the two `next` primitives
are NOT mis-designed").

Scope note (mechanism, surfaced for the maintainer): this proposal
renames the existing `orchestrate run --action <action-id>` invocation to
`drive --action <action-id>` — a faithful minimal rename that keeps the
`--action` flag form. The action-id itself is the real contract token
("coupled only by the shared action-id grammar"); the design record's
human-rendered handoff string (`drive <action-id>`, positional) is a
`needs-attention` rendering-field concern belonging to that sibling piece,
not the `drive` CLI contract, so the flag form is left unchanged here.

### Proposed Changes

**A. Rename and rewrite the operator surface — `SPECIFICATION/contracts.md` §"`orchestrate`" (the entire subsection).** The `#### orchestrate` subsection in its entirety — from the heading `#### orchestrate` through the paragraph ending "...so machine callers SHOULD pass `--repo` and `--json` explicitly to keep a fully-specified invocation." — MUST be replaced with the following `#### drive` subsection:

```markdown
#### `drive`

Permanent minimal operator **executor** surface. `drive` executes exactly
one operator action, identified by its action-id, against the target
repo. The skill is a thin binding over
`.claude-plugin/scripts/bin/drive.py` and the shared
`commands/drive.py` implementation. `drive` composes and ranks NOTHING:
it is a pure executor of its own **action-id grammar** — an `impl:`
dispatch action or one of the five human valve/policy actions
(`approve:` / `accept:` / `reject:` / `set-admission:` /
`set-acceptance:`). It MUST NOT duplicate ranking or composition logic
from any `next` surface, and it MUST NOT create net-new work-items.

`drive` and the read/awareness surface `needs-attention` are **peers,
not layered** — coupled ONLY by the shared action-id grammar. Neither
calls the other: an operator (or the console) reads what needs attention
from `needs-attention`, then invokes `drive` on a selected drive-grammar
action-id. The former `orchestrate plan` two-`next` composition and the
former bare `orchestrate` interactive walkthrough are RETIRED: the
composition/awareness role relocates to `needs-attention`, and the
interactive "see -> select -> execute" loop belongs to the console. Only
drive-grammar action-ids are `drive`-executable; spec-side actions
(e.g. `/livespec:*` handoffs) are NOT — they are surfaced and routed by
the awareness surface as a human handoff, never executed by `drive`.

CLI surface:

- `drive [--repo <path>] --action <action-id> [--json]`

Two operator-surface defaults shape the everyday path; each has an
explicit override so scripts, CI, and the Dispatcher keep a fully
specified invocation:

- **`--repo` defaults to the current repo.** When `--repo` is omitted,
  the surface MUST default the target repo to the current working
  directory's repo (the governed checkout the operator is in).
  `--repo <path>` remains accepted and overrides the default.
  Resolution failure (the cwd is not inside a governed repo, or the
  resolved path does not exist) MUST surface a precondition error
  (exit 3) naming the unresolved path.
- **Markdown output by default; `--json` is the machine opt-in.**
  Console output MUST default to human-readable Markdown. `--json` is
  the explicit opt-in to machine-readable JSON output; the
  Dispatcher-facing and CI-facing invocations continue to pass `--json`
  for stable parsing. The JSON payload shape (the dispatch/handoff
  envelope from an executed action) is unchanged — only the default
  rendering flips from JSON to Markdown.

Operator procedure: the operator (or the console) obtains a selectable
drive-grammar action-id from the awareness surface (`needs-attention`),
then invokes `drive [--repo <path>] --action <action-id> [--json]` for
that action id and summarizes the result, including `status`, Dispatcher
exit code, parsed Dispatcher JSON when present, stderr when non-empty,
and PR/run fields when present. This procedure supersedes manual
bootstrap handoff prompts as the steady-state operator execution step;
bootstrap prompts MAY still exist as historical recovery artifacts.

`drive` executes only the selected action. For a selected impl dispatch
action (`impl:<work-item-id>`, marked `factory_safe: true`) it invokes
the existing Dispatcher/Fabro loop with `--mode shadow --budget 1
--parallel 1 --item <work-item-id> --json`, then summarizes the
Dispatcher status, exit code, stdout JSON, stderr, and the selected
work-item id. The `factory_safe` marking itself is produced by whichever
surface emits the action-id (the `needs-attention`/`drive` action-id
coordination defined by the broader epic), not by `drive`; it is
forward-referenced here rather than defined by this section.

**Human valve actions.** `drive` additionally accepts the five human
operator action ids (the two human-delegable gate commands, the
corrective `reject:`, and the two policy edits) —
`approve:<work-item-id>` (the human approval act: transitions an
effective-`manual` item from `pending-approval` to `ready`; admission to
`active` then follows mechanically when a WIP slot frees, dependencies
are clear, and an assignee resolves), `accept:<work-item-id>` (the human
leg of post-merge acceptance: `acceptance → done`),
`reject:<work-item-id>:rework` / `reject:<work-item-id>:regroom`
(`acceptance → active` fix-forward; `acceptance → backlog` with the
merged change reverted), and the two policy-edit actions
`set-admission:<work-item-id>:auto|manual` and
`set-acceptance:<work-item-id>:ai-only|human-only|ai-then-human`. A
policy-edit action MUST modify ONLY the named policy field of an
existing item (realized on beads as the `admission:` / `acceptance:`
label through the store seam) and MUST NOT change the item's status. A
policy edit NEVER moves an item between states: flipping an item's
`admission_policy` from `manual` to `auto` while it rests at
`pending-approval` MUST NOT approve it into `ready` — the automatic GO
fires only once, at capture/groom time; after a later policy flip,
moving the item still requires an explicit `approve:<work-item-id>`.
Symmetrically, flipping `auto` to `manual` on an item already at `ready`
MUST NOT demote it — it was already approved; only an explicit defer
takes an item out of `ready`. These are human-TRIGGERED operator
commands, not machine-path dispositions: the explicit action selection
is the consent (an up-front operation decision per §"Store-write consent
discipline"), each writes through the same store seam, and the journal
records the actor. This is the published surface the console invokes for
the two human-delegable gates — `approve` and `accept` — and the
policy-edit actions (§"Dispatcher admission, WIP cap, and post-merge
acceptance"); the console never writes the ledger directly. The
operator-action behavior is exercised by `scenarios.md` Scenario 31.

Codex and other non-Claude runtimes MUST use the same Python CLI rather
than copying Claude-specific skill prose. When the slash skill is not
available, the required fallback is direct invocation of
`.claude-plugin/scripts/bin/drive.py --repo <path> --action
<action-id> --json` under the same Beads/Dolt environment that the
Dispatcher requires. The same operator-surface defaults (cwd-default
`--repo`, Markdown rendering without `--json`) apply uniformly to direct
Python CLI invocation — the defaults are a property of the CLI, not of
the Claude skill binding — so machine callers SHOULD pass `--repo` and
`--json` explicitly to keep a fully-specified invocation.
```

**B. Document the `next` scope-asymmetry — `SPECIFICATION/contracts.md` §"`next`".** After the paragraph ending "The wrapper MUST always emit a valid (possibly empty) `candidates` array." (the last paragraph of the §"`next`" subsection, immediately before the `#### detect-impl-gaps` heading), the following paragraph MUST be inserted:

```markdown
**Scope asymmetry with the spec-side `next`.** This impl-side `next` is a
pure ranker of *dispatchable `ready` work* — its only action type is
`implement`, and it deliberately EXCLUDES the impl-side human valves
(items resting at `pending-approval`, at `acceptance`, or `blocked`
awaiting a human). The spec-side `/livespec:next`, by contrast, includes
human actions (e.g. `revise`). This asymmetry is correct per each
primitive's job and MUST be preserved. Its consequence: composing ONLY
the two `next` outputs (spec-side + impl-side) yields an INCOMPLETE
attention picture — it misses the impl-side human valves. A complete
"what needs attention" view therefore composes a wider primitive set (the
human-valve lanes via `list-work-items`, plus plan threads and hygiene)
in the read/awareness surface (`needs-attention`), NOT here. No caller
SHOULD rebuild the incomplete two-`next` composition (the retired
`orchestrate plan`, per §"`drive`"): the composition role belongs to the
awareness surface, and `next` MUST remain a pure `implement`-only ranker.
```

**C. Downstream `orchestrate` references in `SPECIFICATION/contracts.md`.** Four scattered references to the renamed surface MUST be updated:

- In §"Store-write consent discipline", the sentence fragment "The human-triggered operator commands (`orchestrate run` `approve:`/`accept:`/`reject:`/`set-admission:`/`set-acceptance:` action ids, per §\"`orchestrate`\") are NOT machine-path dispositions — their consent is the operator's" MUST become "The human-triggered operator commands (`drive` `approve:`/`accept:`/`reject:`/`set-admission:`/`set-acceptance:` action ids, per §\"`drive`\") are NOT machine-path dispositions — their consent is the operator's".
- In the two-valve pattern paragraph, "a human triggers `approve` for a manual item resting at `pending-approval`, through the `orchestrate` human-valve actions" MUST become "a human triggers `approve` for a manual item resting at `pending-approval`, through the `drive` human-valve actions".
- In the `accept` acceptance-policy bullet, "`human-only` — a human accepts from the console (via the `orchestrate run` `accept:<id>` valve action)." MUST become "`human-only` — a human accepts from the console (via the `drive` `accept:<id>` valve action).".
- In §"Arming full autonomous mode", the opt-in bullet "`orchestrate run --mode autonomous` (alongside the existing" MUST become "`drive --mode autonomous` (alongside the existing".

**D. Operator-skill and Codex references — `SPECIFICATION/constraints.md`.** Two bullets MUST be updated:

- The operator-skill bullet "The operator skill (`orchestrate`) carries only harness binding prose in SKILL.md. Deterministic planning, selected-action execution, and outcome summarization live in the shared `orchestrate.py` wrapper and command module so Claude Code and Codex bindings call the same logic." MUST become "The operator skill (`drive`) carries only harness binding prose in SKILL.md. Selected-action execution and outcome summarization live in the shared `drive.py` wrapper and command module so Claude Code and Codex bindings call the same logic." (The retired composition removes the "Deterministic planning" responsibility.)
- In the Codex bullet, the sentences "The `orchestrate` surface is likewise a thin runtime binding over `orchestrate.py`, with user selection handled by the harness and selected impl work executed by the shared CLI. The human Codex TUI discovery surface MUST be verified separately from model-visible plugin loading: `/skills` → `List skills` (or the `@` picker) searches the short skill name such as `orchestrate` and renders the plugin context as `orchestrate (livespec-orchestrator-beads-fabro)`." MUST become "The `drive` surface is likewise a thin runtime binding over `drive.py`, with the selected action executed by the shared CLI. The human Codex TUI discovery surface MUST be verified separately from model-visible plugin loading: `/skills` → `List skills` (or the `@` picker) searches the short skill name such as `drive` and renders the plugin context as `drive (livespec-orchestrator-beads-fabro)`."

**E. Autonomous-mode wire surface — `SPECIFICATION/spec.md`.** In the autonomous-mode wire-surface sentence, "the `orchestrate run --mode autonomous` opt-in, and the per-decision audit" MUST become "the `drive --mode autonomous` opt-in, and the per-decision audit".

**F. Rename and prune Scenario 17 — `SPECIFICATION/scenarios.md`.** The bare interactive walkthrough retires, so its sub-scenario is removed and the heading/preamble are re-scoped to `drive`; the cwd-default and Markdown-default behaviors survive on `drive`. The block from the heading `## Scenario 17 — orchestrate operator-surface defaults` through the closing ```` ``` ```` of its gherkin fence MUST be replaced with:

````markdown
## Scenario 17 — drive operator-surface defaults

```gherkin
Feature: drive operator surface defaults to the ergonomic path
  As an operator working inside a governed repo
  I want a cwd-default repo and Markdown output
  So that the everyday operator execution step needs no boilerplate
  while scripts and the Dispatcher keep a fully specified invocation

Scenario: An omitted --repo resolves to the current working directory's repo
  Given the operator's current working directory is inside a governed repo
  When the operator invokes `drive --action <action-id>` without `--repo`
  Then the surface resolves the target repo to that current-directory repo
  And an explicit `--repo <path>` still overrides the default when supplied

Scenario: Console output is Markdown by default and JSON only with --json
  Given any `drive` invocation
  When the operator omits `--json`
  Then the surface renders human-readable Markdown
  And passing `--json` renders the same payload as machine-readable JSON
```
````

**G. Rename Scenario 21 — `SPECIFICATION/scenarios.md`.** The block from the heading `## Scenario 21 — Codex skills picker discovers orchestrate by short name` through the closing ```` ``` ```` of its gherkin fence MUST be replaced with:

````markdown
## Scenario 21 — Codex skills picker discovers drive by short name

```gherkin
Feature: Codex TUI skill discoverability
  As an operator using the Codex TUI
  I want to find the drive operator skill through the supported /skills picker
  So that the installed plugin is discoverable without knowing internal
    model-facing names

Scenario: The /skills picker renders drive under this plugin
  Given the livespec-orchestrator-beads-fabro Codex plugin is installed
  And the operator opens the Codex TUI
  When the operator opens "/skills"
  And chooses "List skills"
  And searches for "drive"
  Then the picker renders "drive (livespec-orchestrator-beads-fabro)"
  And the rendered row is typed as a Skill
  And the operator does not need to search for the colon-qualified
    "livespec-orchestrator-beads-fabro:drive" form
```
````

**H. Rename Scenario 31 — `SPECIFICATION/scenarios.md`.** The block from the heading `## Scenario 31 — orchestrate human valve actions` through the closing ```` ``` ```` of its gherkin fence MUST be replaced with:

````markdown
## Scenario 31 — drive human valve actions

```gherkin
Feature: drive human valve actions
  As the operator (or the console acting on the operator's behalf)
  I want approve, accept, reject, set-admission, and set-acceptance commands on the drive surface
  So that the two human-delegable gates and the policy edits are commanded through the plugin's published surface, never a direct ledger write

Scenario: approve authorizes a resting manual-admission item into ready
  Given a `pending-approval` item whose effective admission_policy is manual
  When the operator invokes `drive --action approve:<work-item-id>`
  Then the item transitions to `ready` (the human approval act — `pending-approval → ready`)
  And admission to `active` then follows mechanically when a WIP slot frees, dependencies are clear, and an assignee resolves
  And the journal records the actor

Scenario: accept confirms a parked item to done
  Given an item parked in the acceptance state awaiting the human leg of its acceptance_policy
  When the operator invokes `drive --action accept:<work-item-id>`
  Then the item transitions to done

Scenario: reject routes by corrective kind
  Given an item in the acceptance state
  When the operator invokes `drive --action reject:<work-item-id>:rework`
  Then the item transitions to active for a fix-forward patch
    And when the operator instead invokes `drive --action reject:<work-item-id>:regroom`
  Then the merged change is reverted and the item transitions to backlog

Scenario: set-admission edits the policy without touching the status
  Given an item whose stored admission_policy is manual
  When the operator invokes `drive --action set-admission:<work-item-id>:auto`
  Then the item's admission_policy becomes auto
  And the item's status is unchanged
  And the journal records the actor

Scenario: a manual → auto flip on a pending-approval item does not approve it
  Given a `pending-approval` item whose stored admission_policy is manual
  When the operator invokes `drive --action set-admission:<work-item-id>:auto`
  Then the item remains at `pending-approval`
  And moving it to `ready` still requires an explicit `approve:<work-item-id>`
```
````

**I. Inline `orchestrate run` references in the remaining scenarios — `SPECIFICATION/scenarios.md`.** Three inline references (whose H2 headings do NOT contain "orchestrate", so no heading rename) MUST be updated:

- In the `ai-then-human parks in acceptance` scenario, the line "  And it transitions to done only after a human confirms from the console (the `orchestrate run accept:<id>` valve action)" MUST become "  And it transitions to done only after a human confirms from the console (the `drive --action accept:<id>` valve action)".
- In Scenario 33, the line "  Given full autonomous mode is enabled for the invocation via `orchestrate run --mode autonomous`" MUST become "  Given full autonomous mode is enabled for the invocation via `drive --mode autonomous`".
- In Scenario 37, the line "  When an orchestrate run starts" MUST become "  When a drive run starts", and the line "  Given an operator requests `orchestrate run --mode autonomous`" MUST become "  Given an operator requests `drive --mode autonomous`".

**J. Heading-coverage co-edit — `tests/heading-coverage.json`.** The revision accepting this proposal MUST co-edit `tests/heading-coverage.json` atomically (path spelled `../tests/heading-coverage.json` in the revise payload's `resulting_files[]`, since `--spec-target` is the main `SPECIFICATION/` tree), updating the three affected entries so each `heading` field matches its renamed H2 heading:

- `## Scenario 17 — orchestrate operator-surface defaults` -> `## Scenario 17 — drive operator-surface defaults`. Because Scenario 17's currently-bound test exercises the RETIRED bare walkthrough (`test_bare_orchestrate_runs_the_plan_walkthrough_without_erroring`), its `test` field MUST be reset to `TODO` with a reason noting the rebind follows the drive-rename impl follow-up.
- `## Scenario 21 — Codex skills picker discovers orchestrate by short name` -> `## Scenario 21 — Codex skills picker discovers drive by short name`. The bound test's behavior survives under the new name; the `test` node id is renamed by the drive-rename impl follow-up (the code is unchanged at revise time, so the existing node id remains valid until then).
- `## Scenario 31 — orchestrate human valve actions` -> `## Scenario 31 — drive human valve actions`. Same treatment as Scenario 21 — the valve-action behavior survives; the `test` node id is renamed by the impl follow-up.

No other `tests/heading-coverage.json` entries change (Scenarios 33 and 37 keep their headings; the retired `#### orchestrate` and `#### next` contract subsections are H4, which the H2-only heading-coverage map does not track).

**K. Orientation-doc amendments — `SPECIFICATION/README.md`.** README is a governed, revise-tracked spec file (its orientation prose is snapshotted into `history/vNNN/README.md` and was co-amended in past revise passes, e.g. commit `6df3ef8`), so it MUST be amended in THIS revise pass and included in the revise payload's `resulting_files[]` alongside the other target files (and snapshotted into the new `history/vNNN/`). Its three surviving `orchestrate` references MUST be updated:

- **Skill-surface line (§"Required content").** The line "  one operator skill: orchestrate; three thin-transport skills:" MUST become "  one operator skill: drive; three thin-transport skills:". (The `plan` in the preceding heavyweight-skill list — "…groom, plan;" — is the `/livespec-orchestrator-beads-fabro:plan` planning-thread skill, NOT `orchestrate plan`, and MUST be left unchanged.)

- **Invocation examples (§"Lifecycle").** Inside the ```` ```text ```` fenced block, the two lines

````text
/livespec-orchestrator-beads-fabro:orchestrate plan --repo /path/to/repo --json
/livespec-orchestrator-beads-fabro:orchestrate run --repo /path/to/repo --action <selected-action-id> --json
````

  MUST be replaced with the single line

````text
/livespec-orchestrator-beads-fabro:drive --repo /path/to/repo --action <selected-action-id> --json
````

  The `orchestrate plan` example MUST be DROPPED entirely — there is NO `drive plan` equivalent (the two-`next` composition role relocates to the not-yet-shipped `needs-attention` read surface); do NOT invent an invalid `drive plan` command.

- **Description paragraph (§"Lifecycle").** The paragraph "`plan` is read-only and composes spec-side `/livespec:next` with impl-side `next`. `run` requires an explicit selected action id: `spec:<action>:<n>` returns a human-gated `/livespec:*` handoff, while `impl:<work-item-id>` dispatches that existing item through Dispatcher/Fabro with the default small budget." MUST be replaced with: "`drive` is a pure executor of the operator action-id grammar: it executes exactly one selected action and composes/ranks nothing. An `impl:<work-item-id>` action dispatches that existing item through Dispatcher/Fabro with the default small budget; the human valve/policy actions (`approve:` / `accept:` / `reject:` / `set-admission:` / `set-acceptance:`) apply the corresponding ledger disposition. Spec-side `/livespec:*` handoffs are NOT `drive`-executable — composing what needs attention across spec, impl, and plan belongs to the separate `needs-attention` read surface, not `drive`." This removes the two-`next` composition description and the `spec:<action>:<n>` handoff — the exact anti-pattern this proposal forbids (per §"`drive`" and §"`next`").

### Interaction with the pending `orchestrate-plan-surfaces-unarchived-plan-threads` proposal

The pending proposed change `SPECIFICATION/proposed_changes/orchestrate-plan-surfaces-unarchived-plan-threads.md` ENHANCES `orchestrate plan` (it adds a third composed candidate source — a plan-thread scan — to the `plan` sub-command). THIS proposal RETIRES `orchestrate plan` entirely, which obsoletes that proposal's `orchestrate plan`-based approach. Per the design record (`plan/needs-attention/research/design.md` §"Read primitives `needs-attention` composes"), that proposal's plan-thread-surfacing intent is **redirected** into a NEW `list-plan-threads` thin-transport primitive (a sibling of `list-work-items`, consumed by `needs-attention`), NOT the retiring `orchestrate plan`. This proposal does NOT delete or rewrite that pending proposal. The maintainer SHOULD resolve it at the same `/livespec:revise` pass — either reject-as-superseded (its intent lives on in `list-plan-threads`) or redirect it — so the two do not both land against a surface only one of them keeps.
