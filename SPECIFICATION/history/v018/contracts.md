# contracts.md — livespec-orchestrator-beads-fabro

Wire-level surfaces this plugin exposes (slash commands and internal
APIs), plus the beads-issue mapping the skills read and write through
the pinned `bd` CLI. Every contract here concretizes a slot in
`livespec/SPECIFICATION/contracts.md`; nothing here overrides upstream.

## Plugin namespace

The plugin's slash commands live under `/livespec-orchestrator-beads-fabro:`. That
namespace is fixed by `.claude-plugin/plugin.json` and may not be
changed without a coordinated rename across consumers (because doctor's
cross-boundary invariants in `livespec` invoke skills through this
namespace prefix per `livespec/SPECIFICATION/contracts.md`
§"Cross-plugin invocation"). Renaming is a major-version-bump
operation.

## The eight-skill surface

Every entry below is REQUIRED. The descriptions concretize each skill's
behavior on the beads substrate; cross-boundary semantics (handoffs,
JSON output schemas, user-consent rules) are defined by
`livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
contract — the 10-skill surface" and apply uniformly.

### Heavyweight authored skills (6)

Each heavyweight op decomposes into (a) a SHARED, harness-neutral prose
artifact at `.claude-plugin/prose/<op>.md` carrying the consent flow,
the multi-step dialogue, the `livespec_orchestrator_beads_fabro.*`
package calls, and the JSON / handoff semantics, and (b) thin
per-runtime SKILL.md bindings (one for Claude Code, one for Codex) that
resolve the plugin root, read `prose/<op>.md` in full, and map its
harness-neutral vocabulary to the runtime's tools — adding no operation
behavior of their own (per `constraints.md` §"Skill orchestration
constraints"). This mirrors livespec CORE's prose + thin-Driver-binding
architecture (`livespec/SPECIFICATION/spec.md` §"Contract + reference
implementations architecture"). The six heavyweight ops are
`capture-impl-gaps`, `capture-spec-drift`, `capture-work-item`,
`implement`, `groom`, and `plan`. `groom` is the FIFTH heavyweight op; it
is ALSO the one new maintainer front-end catalogued under §"Skills —
augmented versus new", and is detailed in §"Grooming and slice-size
calibration" → "The four maintainer touchpoints" (touchpoint 2) — see
that section for its read-only-draft / human-approves contract. `plan` is
the SIXTH heavyweight op; it is the Orchestrator-Plane realization of the
Planning Lane and is detailed in §"Planning Lane realization" — see that
section for its create/resume API, the `plan/<topic>/` thread store, the
handoff self-sufficiency gate, and the archive-on-close transition. The
remaining four ops (`capture-impl-gaps`, `capture-spec-drift`,
`capture-work-item`, `implement`) are detailed in the subsections that
follow.

#### `capture-impl-gaps`

Detect spec → impl gaps by invoking the sibling
`/livespec-orchestrator-beads-fabro:detect-impl-gaps --json` thin-transport skill (no
in-skill duplication of the detection logic; both this skill and doctor
consume the same canonical surface). The returned gap-ids are presented
to the user one at a time; on consent, a new work-item is created in the
tenant DB via `bd create` carrying the `origin:gap-tied` and
`gap-id:<stable-id>` labels. Detection state is in-memory and discarded
at skill exit — no persistent intermediate artifact. Re-running the
skill is idempotent: an already-tracked gap-id is detected as "already
filed" and not re-prompted unless the user explicitly asks for a
refresh.

**`--since-version <vN>`** (optional). When set, passed through verbatim
to both `detect-impl-gaps` invocations (the `--json`
authoritative-set call and the rich-display call). Validation is
delegated to the underlying skill — if the value is invalid,
`detect-impl-gaps` exits `2` or `3` and `capture-impl-gaps` surfaces the
error and aborts.

The flag is the surface that callers (notably `/livespec:revise`'s
post-step per the coordinating epic
`livespec#coordinating-epic-stale-revise-enforcement`) use to scope
per-revise gap detection. Direct user invocations MAY use it as well
for any "show me gaps for changes since this version" workflow.

#### `capture-spec-drift`

Detect impl → spec drift heuristically (LLM-driven). For each finding,
present it to the user with a recommended action; on consent, hand off
to `/livespec:propose-change` via the cross-boundary handoff (per
`livespec/SPECIFICATION/contracts.md` §"Cross-boundary handoffs"
entry 1). The handoff produces a proposed-change file under the
consumer's spec-side `<spec-root>/proposed_changes/`; this plugin never
writes to spec-side state directly.

#### `capture-work-item`

Freeform direct filing of a work-item. The user supplies title,
description, type, and priority; the skill creates a new beads issue via
`bd create` carrying the `origin:freeform` label and no `gap-id:` label,
plus the supplied fields. No gap detection runs; no closure-verification
rules attach. Closure is via the freeform path in `implement`.

The skill accepts an optional `--spec-commitment-hint <id_hint>` flag.
When supplied, the resulting work-item's `spec_commitment_hint` MUST
equal the verbatim `id_hint` (carried on the beads issue's native
`spec_id` field per §"Work-item beads-issue mapping"); when omitted, the
hint is absent (the freeform case). This is the surface livespec's
`unresolved-spec-commitment` doctor invariant queries via
`list-work-items --json` to verify each declared spec→impl commitment
maps to a filed work-item (per
`livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
contract — the 10-skill surface" → "Work-item `spec_commitment_hint`
field").

#### `implement`

Drive Red → Green for a single work-item. The user picks the work-item
(or the skill defers to `next`'s recommendation). The skill walks the
user through:

1. Authoring a failing test (Red).
2. Implementing the change until the test passes (Green).
3. Closing the work-item.

Closure branches on `origin × disposition`. In every branch the closure
mutates the existing beads issue row IN PLACE (close-in-place): `bd
close --reason <reason>` sets terminal status and `close_reason`, `bd
update` sets the `resolution:<enum>` label, and — for resolutions that
imply a canonical-branch merge — the full `AuditRecord` is written into
the issue's `metadata` JSON column. No second record is appended.

- **gap-tied completion** — invoke `detect-impl-gaps --json`; confirm
  the `gap_id` is NO LONGER in the returned gap-id set; close with
  `resolution: completed` and an `AuditRecord`
  (`verification_timestamp`, `commits`, `files_changed`, `merge_sha`,
  optional `pr_number`) in `metadata`.
- **freeform completion** — close with `resolution: completed` and a
  user-supplied `--reason`.
- **non-completion administrative closure** — close with
  `resolution: <wontfix | duplicate | spec-revised |
  no-longer-applicable | resolved-out-of-band>`, carrying a
  user-supplied `--reason`.

### Operator skill (1)

#### `orchestrate`

Permanent minimal operator surface for cross-side work selection. The
skill is a thin binding over `.claude-plugin/scripts/bin/orchestrate.py`
and the shared `commands/orchestrate.py` implementation. It composes the
existing spec-side `/livespec:next` output with this plugin's impl-side
`next` output and emits a small `actions[]` plan. It MUST NOT duplicate
ranking logic from either `next` surface.

CLI surface:

- `orchestrate` (no subcommand) — interactive operator walkthrough.
- `orchestrate plan [--repo <path>] [--json]`
- `orchestrate run [--repo <path>] --action <action-id> [--json]`

Three operator-surface defaults shape the everyday path; each has an
explicit override so scripts, CI, and the Dispatcher keep a fully
specified invocation:

- **Bare `orchestrate` — interactive walkthrough.** Invoked with no
  subcommand, `orchestrate` MUST present an interactive operator
  walkthrough rather than erroring on a missing subcommand. The
  walkthrough composes the same read-only `plan` → select → `run`
  flow: it runs `plan` against the resolved repo, presents the
  returned `actions[]` for the operator to choose from, and on a
  selection invokes the equivalent `run` for that action id. It MUST
  NOT introduce any new selection or ranking logic — it is a
  presentation layer over `plan` and `run`. The explicit `plan` and
  `run` subcommands remain available unchanged for non-interactive
  callers.
- **`--repo` defaults to the current repo.** When `--repo` is
  omitted, the surface MUST default the target repo to the current
  working directory's repo (the governed checkout the operator is
  in). `--repo <path>` remains accepted and overrides the default.
  Resolution failure (the cwd is not inside a governed repo, or the
  resolved path does not exist) MUST surface a precondition error
  (exit 3) naming the unresolved path, as today.
- **Markdown output by default; `--json` is the machine opt-in.**
  Console output MUST default to human-readable Markdown. `--json`
  is the explicit opt-in to machine-readable JSON output; the
  Dispatcher-facing and CI-facing invocations continue to pass
  `--json` for stable parsing. The JSON payload shape (the
  `actions[]` plan from `plan`; the dispatch/handoff envelope from
  `run`) is unchanged — only the default rendering flips from JSON
  to Markdown.

Operator procedure (interactive form): invoke bare `orchestrate`; it
runs `plan` for the resolved repo, presents the `actions[]`, and on a
selection runs the equivalent `run` and summarizes the result.

Operator procedure (explicit form):

1. Invoke `plan [--repo <path>] [--json]`.
2. Present the returned `actions[]` to the human operator.
3. Invoke `run [--repo <path>] --action <action-id> [--json]` only for
   the selected action id.
4. Summarize the result, including `status`, Dispatcher exit code,
   parsed Dispatcher JSON when present, stderr when non-empty, PR/run
   fields when present, and any spec-side handoff command.

This procedure supersedes manual bootstrap handoff prompts as the
steady-state operator loop. Bootstrap prompts MAY still exist as
historical recovery artifacts, but routine follow-on orchestration MUST
start from `orchestrate plan` and proceed through an explicit selected
action id.

`plan` is read-only. It resolves the target repo explicitly, invokes the
spec-side and impl-side `next` wrappers, and returns selectable action
records. Spec actions have ids shaped as `spec:<action>:<index>` and
carry a `/livespec:* --spec-target SPECIFICATION/` handoff. Impl actions
have ids shaped as `impl:<work-item-id>` and are marked
`factory_safe: true`.

`run` executes only a selected impl action. It invokes the existing
Dispatcher/Fabro loop with `--mode shadow --budget 1 --parallel 1
--item <work-item-id> --json`, then summarizes the Dispatcher status,
exit code, stdout JSON, stderr, and the selected work-item id. A selected
spec action returns `status: human-gated` plus the handoff command; it
MUST NOT mutate spec-side state directly. The surface MUST NOT create
net-new work-items.

Codex and other non-Claude runtimes MUST use the same Python CLI rather
than copying Claude-specific skill prose. When the slash skill is not
available, the required fallback is direct invocation of
`.claude-plugin/scripts/bin/orchestrate.py plan --repo <path> --json`
and `.claude-plugin/scripts/bin/orchestrate.py run --repo <path>
--action <action-id> --json` under the same Beads/Dolt environment that
the Dispatcher requires. The same operator-surface defaults (cwd-default
`--repo`, Markdown rendering without `--json`, and the bare-`orchestrate`
walkthrough) apply uniformly to direct Python CLI invocation — the
defaults are a property of the CLI, not of the Claude skill binding —
so machine callers SHOULD pass `--repo` and `--json` explicitly to keep
a fully-specified invocation.

### Thin-transport skills (3)

Each thin-transport skill is a short SKILL.md pass-through over a Python
`bin/` implementation (the wrapper-shape contract codified in
`livespec/SPECIFICATION/contracts.md` §"Wrapper CLI surface").
SKILL.md MUST NOT accrete logic — every behavior lives under
`.claude-plugin/scripts/bin/<skill>.py`.

#### `list-work-items`

CLI surface: `list-work-items [--filter <name>] [--with-gap-id=<id>] [--with-spec-commitment-hint=<id_hint>] [--json] [--work-items-path <path>] [--project-root <path>]`.

`--filter` flags:

- `--filter=gap-tied` — `origin: gap-tied` only.
- `--filter=freeform` — `origin: freeform` only.
- `--filter=blocked` — `status: blocked` only.
- `--filter=ready` — `status: open` AND no unresolved `depends_on`
  edges.
- `--filter=closed` — `status: closed` only.
- `--filter=all` — default.

`--with-gap-id=<id>` — exact-match on the `gap_id` value (the
`gap-id:<id>` label).

`--with-spec-commitment-hint=<id_hint>` — exact-match on the
`spec_commitment_hint` value (the issue's `spec_id` field). Combinable
with `--filter` and with `--with-gap-id`.

`--project-root <path>` — override the cross-repo manifest and
connection-resolution base. Default: `Path.cwd()`. Used by doctor's
cross-boundary handoffs to invoke this skill from outside the consumer
project root.

`--work-items-path <path>` — repurposed connection-descriptor override.
The default substrate location is the beads tenant DB resolved from the
consumer's `.livespec.jsonc` `connection` block; this flag overrides the
resolved store descriptor (used by tests and by doctor invocations that
want to scope to a non-default store — e.g. the in-memory fake backend).
The keyword is retained for call-site parity with the plaintext sibling;
its value is no longer a filesystem path to a JSONL file.

The skill reads all issues from the tenant DB via `bd` and filters in
Python (mirroring the plaintext sibling's materialize-then-filter; no
SQL is issued by the plugin). `--json` output: an array of work-item
materialized views.

#### `next`

Cross-reference: cross-repo dispatch is the Dispatcher's concern
(`dispatcher.py` `dispatch` / `loop`; see README §"Dispatcher and
telemetry"). This surface ranks impl-side state only; it MUST NOT
bake a cross-repo sequencing or cross-side weighting in — the
Dispatcher consumes this ranking and handles sequencing externally.

CLI surface: `next [--limit <count>] [--offset <count>] [--json] [--work-items-path <path>] [--project-root <path>]`.
No `--filter` flag — the skill's job is to RANK rather than to filter.

`--limit <count>` — positive integer, default `5`. Maximum number of
candidates returned in the `candidates` array. Non-positive values MUST
cause the wrapper to exit `2` with a `UsageError`.

`--offset <count>` — non-negative integer, default `0`. Number of ranked
candidates to skip from the front of the ranked list before returning.
Negative values MUST cause the wrapper to exit `2` with a `UsageError`.

`--project-root <path>` — override the cross-repo manifest and
connection-resolution base. Default: `Path.cwd()`. Used by doctor's
cross-boundary handoffs to invoke this skill from outside the consumer
project root.

`--work-items-path <path>` — repurposed connection-descriptor override
(same semantics as for `list-work-items`): overrides the resolved beads
store descriptor; used by tests and by doctor invocations that want to
scope to a non-default store.

Ranking is a pure function of the materialized work-items read back from
`bd` (no LLM, and NOT delegated to `bd ready` — the cross-repo manifest
exclusion must run in Python). The reader populates each work-item's
`depends_on` from the issue's `blocks` edges so the ranker operates on
the same shape the plaintext sibling produces. The algorithm:

1. Identify ready items: `status: open`, `depends_on` either empty or
   all-closed.
2. Score by priority (lower number = more urgent) then by `gap-tied`
   ahead of `freeform` (gap-tied items have explicit spec backing) then
   by oldest `captured_at`.
3. Ties are broken deterministically by `id` lexicographic order.
4. Apply `--offset` and `--limit` to produce the returned slice.

Output schema (per `livespec/SPECIFICATION/contracts.md`
§"Implementation-plugin contract — the 10-skill surface" → `next` and
the upstream §"`/livespec:next` spec-side thin-transport skill" →
§"Output schema"): the output is a JSON object with two top-level keys,
`candidates[]` and `pagination`:

```jsonc
{
  "candidates": [
    {
      "action": "implement",
      "reason": "<one-line human narration>",
      "urgency": "high",
      "work_item_ref": "<id-of-ranked-item>"
    }
  ],
  "pagination": {
    "offset": 0,
    "limit": 5,
    "total": 12,
    "has_more": true
  }
}
```

Field semantics:

- `candidates[]` — array of candidate objects. `action` MUST be one of
  `"implement"` | `"none"`. The work-items-only scoping is principled:
  gap-detection and drift-detection are Dispatcher-side concerns invoked
  outside of `next`'s ranking. Each candidate MUST carry
  `action`, `reason` (non-empty human-readable narration), `urgency`
  (one of `high`, `medium`, `low`), and `work_item_ref` (the `id` of the
  ranked work-item, or `null` for `action: "none"`). Each candidate MAY
  include additional impl-beads-specific fields the wrapper emits (e.g.,
  `priority`, `origin`); the cross-plugin contract MUST NOT prescribe
  `additionalProperties` discipline per upstream.
- `pagination.offset` — echoed from `--offset`.
- `pagination.limit` — echoed from `--limit`.
- `pagination.total` — total count of ripe candidates BEFORE `offset`
  and `limit` are applied.
- `pagination.has_more` — `true` iff
  `offset + len(candidates) < total`.

`urgency` derivation per candidate: P0 → high; P1, P2 → medium; P3,
P4 → low.

When no items are ready, the wrapper MUST emit `candidates: []` with a
`pagination` echoing the inputs and `has_more: false`. An empty
`candidates` array IS the no-work signal; it does NOT degrade to any
legacy single-object shape. This surface MUST NOT bake a hygiene
fallback into the emission: emission of the empty array is purely
advisory, and any empty-queue response (e.g. a hygiene pass) is a
Dispatcher / operator concern (per `scenarios.md` Scenario 6's
empty-queue handoff sub-step).

When `offset >= total`, the wrapper MUST emit `candidates: []` and
`has_more: false`. The wrapper MUST always emit a valid (possibly
empty) `candidates` array.

#### `detect-impl-gaps`

CLI surface: `detect-impl-gaps [--spec-target <path>]
[--project-root <path>] [--since-version <vN>] [--json]`. No `--filter`
flag — the skill emits the complete current gap-id set.

The skill reads the live Specification via the Spec Reader, enumerates
every MUST/SHOULD rule per the gap-rule enumeration contract (per
upstream §"Spec Reader required-capability surface" capability 1), and
computes a stable `gap_id` per detected rule. Gap-id derivation is a
pure function of rule text + canonical heading path; the same rule text
always yields the same gap-id across runs. This skill is
substrate-agnostic — it reads the spec tree, never the work-items store.

**`--since-version <vN>`** (optional, default `null`). When set to a
historical version integer that exists under
`<spec-root>/history/v<NNN>/`, the skill restricts its scan to files
whose content differs between `<vN>` and the live spec (i.e., the file
appears in `SpecDiff(version_a=<vN>, version_b=<live>).per_file`). For
each such file, only MUST / SHOULD clauses present in the live version
are considered (clauses removed by the diff are not gaps — they were
spec content that no longer exists).

Validation:

- The value MUST be a positive integer. Non-integer / negative input
  exits `2` with a usage error.
- The version directory `<spec-root>/history/v<padded-N>/` MUST exist.
  Missing version exits `3` with `PreconditionError` naming the expected
  path.

When omitted, the behavior is unchanged — scan every file in the live
spec.

`--json` output: a top-level JSON object with one key, `gap_ids`, whose
value is an array of strings:

```json
{
  "gap_ids": ["gap-<stable-id-1>", "gap-<stable-id-2>", "..."]
}
```

Default human output: one line per gap-id, prefixed with the spec-file
path + heading the rule was sourced from.

The skill is the canonical gap-detection surface for the plugin.
Consumers:

- `livespec` doctor's `gap-tracking-one-to-one` and `no-stale-gap-tied`
  invariants subprocess this skill via the
  `<impl-plugin>:detect-impl-gaps --json` cross-boundary handoff (per
  upstream §"Cross-boundary handoffs" entry 5).
- The heavyweight sibling `capture-impl-gaps` invokes this skill as its
  detection step before walking the user through per-gap consent.
- The heavyweight `implement` skill invokes this skill at gap-tied
  work-item closure to confirm the `gap_id` is no longer detected before
  closing the record.

The skill MUST NOT mutate any impl-side store; it MUST NOT write to the
tenant DB; it MUST NOT prompt the user. It is a pure read-and-emit
pass-through over the Spec Reader's output and the gap-rule enumeration.

## Interactive dialogue ownership (orchestrator-side)

The interactive gap/drift dialogue — per-finding human review and
consent — is OWNED BY THIS ORCHESTRATOR, not by livespec core or its
per-runtime Driver. This plugin ships its own runtime-specific
interactive front-ends to its capture CLIs: the consent-dialogue
skills `capture-impl-gaps`, `capture-spec-drift`, `capture-work-item`,
and `groom` (per §"Store-write consent discipline"), usable from the
supported agent runtimes (Claude Code and Codex CLI). These front-ends
are orchestrator-INTERNAL: core's contract does not name them, the
Driver does not depend on them, and they MUST NOT call back into the
Driver. They MAY invoke core operations — e.g. the
`/livespec:propose-change` cross-boundary handoff (per §"Cross-boundary
handoffs") — because those are core's surface that the Driver merely
binds; invoking a core operation is NOT a dependency on the Driver
itself. This preserves the load-bearing zero-dependency property
between Driver and orchestrator: the Driver binds core's CLIs and prose
only, and everything orchestrator-interactive ships with this
orchestrator.

## Store-write consent discipline

Substrate-agnostic principle: a state-changing write to the
orchestrator's persistent work-items store performed on the
user's behalf MUST be per-operation user-consented, unless the user
has explicitly waived consent for the named operation class. Per
§"Interactive dialogue ownership (orchestrator-side)", the consent
dialogue is orchestrator-owned: this plugin's six heavyweight
front-ends —
`capture-impl-gaps`, `capture-spec-drift`, `capture-work-item`,
`implement`, `groom`, and `plan` — are exactly those front-ends and are
the governed surface of this discipline. (`groom` is a consented
store-writer via `file_approved_slices` / `regroom.exit_regroom` — its
approve-then-file step writes the regroomed `ready` slices, so it
obtains maintainer approval before that write per §"Grooming and
slice-size calibration". `plan` is a consented store-writer via the
`capture-work-item` operation — it anchors a thread's ledger epic and
files matured pieces as work-items only through that consented seam,
never a direct store write, per §"Planning Lane realization".) Each
front-end's consent flow lives in the shared
`.claude-plugin/prose/<op>.md` artifact the per-runtime SKILL.md
bindings read (per §"Heavyweight authored skills (6)").

### Recognized consent forms

Consent MUST be obtained before the store write executes, in one of
three recognized forms:

- **Explicit confirmation** — the skill presents the assembled
  record and the user confirms it. Examples: `capture-work-item`'s
  "file?" step, `capture-impl-gaps`' per-gap confirm.
- **Consent-by-authorship** — the user-supplied free text fully
  determines the single resulting write and the skill performs no
  other store write. Example: `capture-work-item`'s freeform deposit —
  the typed title/description IS the consent for the single create; no
  second confirmation prompt beyond the "file?" step is required.
- **Up-front operation decision** — an explicit user decision at the
  start of the operation that names the write the operation will
  perform. Example: `implement`'s resolution-path decision, which is
  the consent for the eventual closure write (gap-tied closures
  additionally confirm the re-detection outcome before the close).

### Operation-class waiver

The user MAY explicitly waive per-operation consent for a named
operation class (e.g. "file every detected gap without asking"). A
waiver MUST be
explicit, MUST name the operation class it covers, and is scoped to
the current invocation. It MUST NOT be a default, MUST NOT be
inferred from context, and MUST NOT persist across sessions. Absent
a waiver, per-operation consent is required.

### Machine-path exemption — the Dispatcher

The Dispatcher (`dispatcher.py` `dispatch` / `loop`) writes to the
work-items store ONLY as machine-path dispositions of already-filed
items: close-on-confirmed-merge, carrying PR-number and merge-sha
audit evidence in the `AuditRecord`. These writes are EXEMPT from
the per-operation consent discipline by design — the Dispatcher acts
on items a human or a consented front-end already filed, and
`--no-close-on-merge` disables even that path. The exemption covers
ONLY dispositions of already-filed items; the Dispatcher MUST NOT
create net-new work-items on its own initiative. The
Dispatcher's module docstring documents this boundary.

### Out-of-scope surfaces

The three thin-transport skills (`list-work-items`, `next`,
`detect-impl-gaps`) are query-only by contract (per
`constraints.md` §"Forbidden patterns") and never write to the
store; the consent discipline does not apply to them.
`capture-spec-drift` writes nothing to this plugin's store — its
output is a `/livespec:propose-change` cross-boundary handoff,
itself per-finding user-consented.


## Grooming and slice-size calibration

This section realizes the repo-agnostic grooming pattern/guidance
that `livespec`'s `non-functional-requirements.md` carries as
Orchestrator-internal guidance (beside its existing §"Orchestrator-internal
Dispatcher guidance"); core gains only the guidance, never a skill,
CLI, or doctor invariant. Grooming — how a maintainer breaks and
sizes work into agent-feedable slices BEFORE autonomous dispatch —
operates on this plugin's ledger (the beads tenant DB), is
Orchestrator-internal, and is therefore NOT part of `livespec`'s
functional cross-boundary contract.

### The four maintainer touchpoints

1. **Capture / intake (augmented).** Work is filed as today via
   `capture-work-item` / `capture-impl-gaps`, but each now runs an
   intake Definition-of-Ready checklist in-dialogue, auto-answering
   what it can and prompting the human only on the rest, and tags the
   resulting item `ready` / `needs-regroom` / `not-yet-actionable`.
   The Definition-of-Ready holds when ALL of these hold, otherwise the
   item is ROUTED not filed-as-ready:

   - **Exactly one coherent "done"** — one named scenario,
     scenario-verified; OR the standing gates `just check` +
     `/livespec:doctor` fully define done with no scenario,
     gate-verified. Being unable to name exactly one means the item is
     an epic and routes to `needs-regroom`.
   - **The acceptance is autonomously verifiable** with no human
     judgement call.
   - **An autonomy tier is assigned** — spec-change is human-gated and
     routes to `/livespec:propose-change` / `/livespec:revise`;
     everything else is factory-dispatchable.
   - **Dependencies are linked** as beads `blocked-by` edges (ready
     requires blockers closed AND an acceptance — never deps alone).
   - **The repo target is named** — one slice maps to one ledger.
   - **The slice is above the size floor** (anti-over-split; the floor
     is human judgement until slice-size calibration yields a value).

2. **Groom (the one new maintainer surface).** For a `needs-regroom`
   item the maintainer runs a groom front-end (provisional command
   name `groom <id>`) — a read-only scoping conversation that DRAFTS a
   layered decomposition, each candidate slice pre-filled with
   acceptance / autonomy tier / dependency links / repo target /
   scope. The maintainer edits and approves (or sends it back to
   re-draft); on approval the front-end files the slices via the
   existing `capture-work-item` machinery with dependency edges
   linked; spec-change slices route to `/livespec:propose-change`
   rather than the factory. The draft is read-only until the human
   approves — it proposes; it files nothing until approval.

3. **Dispatch (unattended, exceptions only).** The Dispatcher drains
   `ready` slices into Fabro sandboxes by dependency layer, gates each
   on `just check` + `/livespec:doctor`, merges, and closes — pulling
   the maintainer in ONLY to SURFACE a `human-gated` (spec-change)
   item or a `needs-regroom` bounce (escalate-don't-drop, back to
   touchpoint 2).

4. **Calibration (mostly invisible).** A periodic analysis pass
   correlates run outcomes against mechanical size proxies and
   proposes ceiling thresholds; once a maintainer adopts them they
   make the intake size-gate flag oversized items advisorily.

### Skills — augmented versus new

**Augmented** (existing skills of this plugin's seven-skill surface):
`capture-work-item` and `capture-impl-gaps` run the intake
Definition-of-Ready checklist and apply the readiness tag.

**New (exactly ONE):** the groom front-end (provisional `groom`), the
agent-drafts / human-approves regroom surface. It is ALSO a heavyweight
authored skill (the fifth, per §"Heavyweight authored skills (6)"), so
its orchestration follows the same shared-`.claude-plugin/prose/<op>.md`
+ thin per-runtime SKILL.md decomposition as the other four heavyweight
ops; "new" here describes its place in the skill inventory, not a
different binding shape.

**NOT skills (Orchestrator machinery):** the Dispatcher's
grooming-related behavior, the single new `needs-regroom` ledger
state, and the calibration analysis pass.

State the restraint budget explicitly: the realization adds at most
one new front-end + one new ledger state + outcome/size FIELDS on the
existing Dispatcher journal + one periodic analysis pass; everything
else reuses Beads (ready / dependency layers / labels) and the
existing capture front-ends. If the realization ever grew past roughly
one new front-end + one new state, that is the signal to stop and
reconsider.

### Dispatcher grooming behavior

The Dispatcher MUST refuse to auto-dispatch a `human-gated`
(spec-change) item — it surfaces it for the maintainer instead. On
factory NON-CONVERGENCE (a dispatched slice that will not converge
through the janitor gate) the Dispatcher MUST mark the item
`needs-regroom` and SURFACE it (escalate-don't-drop), never
infinite-retry — non-convergence is the empirical "too big" signal
that routes back to the groom front-end. The Dispatcher MUST emit
calibration telemetry: an outcome signal plus mechanical size proxies
recorded on the EXISTING Dispatcher journal (the journal → Honeycomb
leg already designed in the operability preconditions), with NO new
always-on service. And — per in-flight work-item
`livespec-impl-beads-i3jiny` — the Dispatcher MUST COMPOSE `next`'s
ranking rather than re-rank inline: `next` is the single ranking
authority and the Dispatcher composes it (the existing fix is the
mechanism; this records the spec intent).

This subsection is consistent with, and does not relax, the existing
§"Store-write consent discipline" → "### Machine-path exemption — the
Dispatcher" carve-out (the Dispatcher still only dispositions
already-filed items and creates no net-new work-items on its own
initiative; marking `needs-regroom` and surfacing is a
disposition/escalation of an already-filed item, not a net-new
creation).

### Calibration telemetry and the single Fabro tweak

Breakdown is entirely UPSTREAM of Fabro (ledger + Dispatcher +
skills); Fabro assumes the human has already decomposed work into
agent-feedable tasks. So the realization requires NO Fabro platform or
setup change. Only two Fabro-adjacent touchpoints:

1. **Dispatcher-side run-outcome capture.** The Dispatcher already
   reads Fabro run state and writes the journal, so calibration just
   records, on that journal, the outcome signal (converged?; fix-loop
   count; outcome class; wall-clock and token/cost; bounced-to-regroom?)
   plus the candidate mechanical size proxies (acceptance count;
   merged-PR diff size; dependency fan-out; spec surface touched;
   dispatch context size; archetype; repo).

2. **ONE Fabro workflow-DOT tweak** within the existing DOT
   vocabulary — a fix-loop cap plus a "non-converged" exit edge that
   routes back to the Dispatcher (→ `needs-regroom`), reusing Fabro's
   existing verify→fix-loop nodes and `max_node_visits` governor.

Per-slice sandboxing (a fresh Fabro sandbox per work-item) is already
how the Dispatcher uses Fabro and is unchanged. The calibration
analysis pass is a periodic query + correlation over the journal, not
an always-on service; thresholds it proposes stay provisional and
advisory until a maintainer adopts them.

### Gate type determines hard versus advisory

Resolve the hard-versus-advisory question by gate TYPE. The STRUCTURAL
Definition-of-Ready gates — exactly one coherent "done"; the
acceptance exists and is autonomously verifiable; dependencies are
linked — are HARD. The SIZE gate (above the floor / below the
calibrated ceiling) is ADVISORY because it is data-derived and
uncertain; the cut-line's qualitative "one coherent done" remains the
primary rule and the calibrated numbers are a secondary, advisory
safety net. The reactive ceiling (bail after N fix-loops → route to
`needs-regroom`) needs no calibration and is the non-convergence
trigger above; the predictive intake size-flag needs calibration and
the reactive bail-out is its training signal.

### Open realization choices

State, as explicit UNRESOLVED questions to be settled by a maintainer
(NOT resolved by this section):

- Whether the groom front-end is its OWN skill (the recommended shape)
  or an "epic mode" of `capture-work-item`.
- The exact `needs-regroom` ledger representation — a beads label
  versus a status.

Both choices affect the skill inventory and the ledger-state
realization and are deliberately left open here.

### Gap-detectable behavior clauses

This subsection restates the realization's NON-Dispatcher fundamental
behaviors as explicit normative clauses so the mechanical gap-detector
and the heading-coverage map can hold the impl accountable; the
surrounding prose subsections remain as augmentation. Where behaviors
1-3, 7, and 8 were previously stated only as prose in §"The four
maintainer touchpoints" / §"Calibration telemetry and the single Fabro
tweak", that prose stays in place as augmentation but the authoritative
normative statement is now the clause line here. The DISPATCHER
behaviors (refuse `human-gated`; bounce on non-convergence; emit
calibration telemetry) are NOT restated here to avoid a duplicate
gap-detectable line — their authoritative normative clauses live in
§"Dispatcher grooming behavior", and the periodic calibration analysis
pass (a non-Dispatcher behavior) plus the single Fabro DOT tweak remain
below.

The `capture-work-item` and `capture-impl-gaps` capture front-ends MUST run the intake Definition-of-Ready checklist over the six gates at capture and MUST tag the resulting item `ready`, `needs-regroom`, or `not-yet-actionable` accordingly — a single-coherent-done, autonomously-verifiable, autonomy-tiered, dependency-linked, repo-targeted, above-floor item is tagged `ready`; an item with more than one coherent "done" (an epic) MUST be tagged `needs-regroom`; an item whose acceptance is not autonomously verifiable, or that has unresolved blockers, MUST be tagged `not-yet-actionable` and MUST NOT be filed as `ready`.

Given a `needs-regroom` item, the groom regroom front-end MUST produce a READ-ONLY drafted decomposition (candidate slices pre-filled with acceptance / autonomy tier / dependency links / repo target / scope and arranged into dependency layers) and MUST file nothing until the maintainer approves; on approval it MUST file the approved slices via `capture-work-item` with dependency edges linked, and MUST route any spec-change slice to `/livespec:propose-change` rather than to the factory.

An item MUST enter `needs-regroom` on an intake Definition-of-Ready failure and MUST enter `needs-regroom` on a Dispatcher non-convergence bounce; groom approval MUST transition the `needs-regroom` item out by filing `ready` slices (the original item is regroomed-out, never silently dropped).

A periodic calibration analysis pass MUST correlate run outcomes against the recorded mechanical size proxies and MUST propose ceiling thresholds that remain advisory until a maintainer adopts them (it MUST NOT auto-enforce a threshold and MUST NOT run as an always-on service).

The single Fabro workflow-DOT tweak MUST stay within Fabro's existing DOT vocabulary — a fix-loop cap plus a "non-converged" exit edge that routes back to the Dispatcher (→ `needs-regroom`), reusing Fabro's existing verify→fix-loop nodes and `max_node_visits` governor — and MUST NOT require any Fabro platform or setup change.

The compose-next behavior (the Dispatcher composes `next`'s ranking
rather than re-ranking inline; its existing normative clause line in
§"Dispatcher grooming behavior" stays unchanged and is the authoritative
statement) is already implemented per in-flight work-item
`livespec-impl-beads-i3jiny`, and is therefore documented and
scenario-covered (Scenario 15) but is NOT a fresh gap. It is deliberately
left out of the clause list above so that no duplicate gap-detectable
line is introduced for an already-satisfied behavior.


## Planning Lane realization

This section realizes the repo-agnostic Planning Lane pattern/guidance
that `livespec`'s `non-functional-requirements.md` carries as
Orchestrator-Plane guidance (§"Planning Lane guidance", beside
§"Orchestrator-internal grooming guidance"); core gains only the
guidance, never a skill, CLI, or doctor invariant. The Planning Lane —
the durable, multi-session *planning* work that decides what should
become spec, implementation, or research before any lane is committed to
— operates on this plugin's filesystem thread store and ledger, is
Orchestrator-internal, and is therefore NOT part of `livespec`'s
functional cross-boundary contract. The architectural frame (the three
planes and the two seams) is `livespec`'s `spec.md` §"Workflow planes
and the Planning Lane"; what this section adds is the realization: the
`plan` front-end and the `plan/<topic>/` thread store, the same cut as
grooming above.

### The `plan` front-end

`plan` is the SIXTH heavyweight authored skill (§"Heavyweight authored
skills (6)"), so its orchestration follows the same shared
`.claude-plugin/prose/<op>.md` + thin per-runtime SKILL.md decomposition
as the other five. Unlike the one-shot `capture-*` family, a planning
thread is stateful and re-entered for the same topic, like `groom`. Its
invocation surface has two modes:

- **`plan` (no argument)** — the interactive entry. It lists the open
  threads (composed from the ledger's open planning epics via the
  `list-work-items` operation AND the on-disk `plan/<topic>/`
  directories) to resume, OR the maintainer describes a new thread and
  the front-end proposes a canonical dash-cased slug — using the SAME
  canonicalization the `propose-change` operation applies to a topic hint
  (lowercase; hyphenate runs of non-alphanumerics; strip; truncate to
  64) — confirms it, and on confirmation creates `plan/<slug>/` and
  anchors a ledger epic for the thread (filed through the
  `capture-work-item` operation). The human never hand-crafts the
  identifier.
- **`plan <slug>` (argument)** — strict resume. It MUST match an existing
  `plan/<slug>/` exactly, or it fails hard with an error listing the
  existing slugs. No fuzzy match and no create-on-typo; creation happens
  only through the no-argument interview path.

Each invocation MAY update the thread's reasoning, refresh its handoff
(subject to the self-sufficiency gate below), route a now-ripe piece (to
the `propose-change` operation for spec, or the `capture-work-item`
operation for ledger work filed as a child of the thread's epic), or
archive the thread on close.

### The `plan/<topic>/` thread store

A planning thread is a first-class directory `plan/<topic>/` holding two
facets: AT MOST ONE handoff (the reserved filename
`plan/<topic>/handoff.md`, the single resumable execution-coordination
point per topic — a second handoff is refused) and ZERO OR MORE research
notes (durable reasoning; one note MAY sit directly in `plan/<topic>/`,
multiple sub-topic notes live under `plan/<topic>/research/`). A young
thread MAY be research-only. The broader `research/` tree stays for
standalone analysis that is not an active planning thread.

### The two seams and the no-shadow-ledger rule

The Planning Lane is Spec-Plane but touches the Orchestrator Plane at
exactly two explicit, one-directional seams (the same cross-boundary
discipline as the Gap and Drift flows): (1) *prompt → ledger* is
READ-ONLY — a handoff cites ledger ids and composes status from the
`list-work-items` / `next` query surface, never writing the ledger; (2)
*plan → work* routes ripe work into the ledger ONLY through the
`capture-work-item` operation, never a direct cross-plane store write. A
planning artifact derives status from the ledger as its first action and
never stores status in the artifact — no checklist item is a parallel
work queue that shadows the ledger.

### The handoff self-sufficiency gate

A handoff MUST NOT be declared ready until it is self-sufficient: a fresh
session opening ONLY the handoff can execute its next action without
re-deriving anything, every depended-on artifact committed and reachable
through the handoff's read-first chain. The `plan` front-end enforces
three checks before declaring a handoff ready: (1) a COLD-OPEN readiness
test — a fresh-context reader opens only the handoff and its read-first
chain and confirms it can proceed; (2) ONE PATH — the next-session
command names exactly one path, the handoff; (3) NO DANGLING REFERENCE
(fail-closed) — every artifact the handoff cites exists and is committed,
else the gate fails. This realizes `livespec`'s §"Planning Lane
guidance" → "Handoff self-sufficiency".

### Archive on epic close

A plan thread's lifecycle binds to its ledger epic: `plan/<topic>/` is
active if and only if its epic is open, and archived to
`plan/archive/<topic>/` if and only if the epic is closed (reopening the
epic unarchives it); whatever closes the epic also archives the
directory. Nothing is lost — the archived thread stays under
`plan/archive/` and in git history. The mechanical backstops (exactly one
handoff per topic; `archived` matches `epic-closed`) are five-slot
conformance concerns paired with Ledger-closure, whose always-on
enforcement is realized by the Conformance Pattern, not by `plan` itself;
this realization holds them behaviorally.

### Planning Lane restraint budget

The Planning Lane realization adds at most one new front-end (`plan`) and
the `plan/<topic>/` (+ `plan/archive/`) thread store path; it adds NO new
ledger state (a thread anchors a plain Beads `epic`) and reuses the
`capture-work-item` machinery for every ledger write. If the realization
ever grew past roughly one new front-end + the thread store, that is the
signal to stop and reconsider.


## Dispatch-time baseline conformance gate

This section realizes the **dispatch-time** tier of livespec's
Conformance Pattern (livespec core `non-functional-requirements.md`
§"Conformance Pattern", four-tier enforcement-in-depth) for the
Beads/Fabro Dispatcher — parallel to how §"Planning Lane realization"
and §"Grooming and slice-size calibration" realize their repo-agnostic
core patterns here.

Before driving any work-item into a Fabro worker sandbox, the
Dispatcher's prepare chain provisions the sandbox to the `baseline`
profile and then GATES on it. The chain MUST install the canonical
structural commit-refuse hook (concern #1 Worktree-discipline,
Mechanism) and declare the sandbox's `livespec.sandboxExempt` marker
(concern #1 Exemption), and it MUST then run the baseline Verifiers over
the provisioned sandbox:
`check-primary-checkout-commit-refuse-hook-installed` (concern #1) and
`check-plugin-resolution` in declaration-integrity mode (concern #2
cross-harness plugin-resolution). A Verifier's non-zero exit MUST abort
the run before any work is driven, so a baseline violation surfaces as a
failed dispatch rather than as silently non-conformant work — every
dispatched sandbox is conformant by construction.

The Verifiers are the SHARED `livespec-dev-tooling` checks (reused, not
re-implemented; an earlier `uv sync --all-groups` prepare step installs
`livespec_dev_tooling` into the sandbox venv), the SAME Verifiers the
commit-time and fleet-time tiers run — enforcement-in-depth is one
Verifier layered across the tiers, not a per-tier reimplementation. The
prepare chain that installs the Mechanism, sets the Exemption marker, and
invokes the Verifiers lives in the Dispatcher's Fabro workflow definition
(`.fabro/workflows/implement-work-item/workflow.toml`); this section is
the normative contract that chain satisfies.


## Beads connection model

The plugin reaches its tenant DB exclusively through the pinned `bd`
CLI in server mode with a FLAGS connection. This model is the verified
v1.0.5 surface; its derivation lives in
`livespec/dev-tooling/implementation/research/beads-schema-mapping.md`
§2.1, and the contract-level commitments are:

- **Pinned binary.** `bd` is pinned to v1.0.5 (sha256-verified release
  tarball). The plugin invokes `bd` by a managed absolute path resolved
  from configuration (the `LIVESPEC_BD_PATH` environment variable, or a
  configured default); it MUST NOT rely on the stale mise shim at
  `~/.local/share/mise/shims/bd`.
- **Server mode, externally managed.** The connection is established via
  `bd init --server --external --server-host <host> --server-port
  <port> --server-user <tenant> --database <tenant> --prefix <issue-prefix>
  --skip-agents --skip-hooks --non-interactive --quiet` (where `<tenant>`
  is the ≤32-char tenant DB name and `<issue-prefix>` is the short
  decoupled create-prefix, e.g. `bd-ib`). The
  `--external` flag declares the `dolt sql-server` externally managed:
  the plugin never starts, stops, or owns the server. `--server-socket
  <path>` overrides host/port when supplied; TCP is the default for
  sandboxed callers that lack `0750` socket-directory access.
- **FLAGS connection — one secret only.** Every connection input is a
  flag EXCEPT the tenant password, which is supplied at `bd`-call time
  via the `BEADS_DOLT_PASSWORD` environment variable. The password is
  NEVER persisted in `.livespec.jsonc` or any committed file. The
  superseded `BEADS_DOLT_SERVER_*` env-var connection surface is NOT
  used.
- **Tenant identity vs. decoupled issue-prefix.** The tenant DB name is
  the load-bearing identity (`database == server_user == tenant`, one
  ≤32-char Dolt name serving all three). The beads `prefix` is bd's
  server-stored issue-ID create-prefix — a short, readable alias
  DECOUPLED from the tenant DB name; it MAY differ from it (here it is
  `bd-ib` for the `livespec-orch-beads-fabro` tenant). Issue ids read
  back as `<prefix>-<suffix>` using that decoupled prefix.
- **Operator-pre-created tenant DB.** The tenant DB is pre-created by
  the `dolt-server` operator via the root-run `onboard-tenant.sh`. The
  plugin NEVER issues `CREATE DATABASE`.
- **`dolt.auto-start: false`; auto-commit OFF.** `bd config
  dolt.auto-start` is set `false` so `bd dolt status` reports
  `running (external)` truthfully. Server-mode auto-commit stays OFF
  (the default); the server owns the transaction lifecycle and the
  plugin MUST NOT re-enable per-write commits.
- **In-memory fake backend.** For hermetic CI and the
  no-live-connection runtime fallback, the plugin selects an in-memory
  fake backend (via `LIVESPEC_BEADS_FAKE=1` or the `connection.fake`
  config key). The fake satisfies the same store API; the live-tier
  path against a real tenant DB is opt-in and gated on
  `BEADS_DOLT_PASSWORD`.

## Work-item beads-issue mapping

A work-item is one beads issue in the tenant DB. The mapping below is
the contract-level outcome of the field-map derivation in
`livespec/dev-tooling/implementation/research/beads-schema-mapping.md`
§Part 1. The logical work-item field set is identical to the plaintext
sibling's; only the on-substrate home of each field differs. The
materialized work-item the skills read back carries the SAME logical
fields the plaintext sibling exposes, so cross-boundary consumers
(doctor, the ranker) see a consistent shape.

Logical field → beads home:

- `id` — beads issue `id`, supplied explicitly at `bd create --id` time.
  Format `<prefix>-<6-char-base32-suffix>` where `prefix` is the tenant's
  decoupled issue-prefix (bd's server-stored create-prefix, e.g.
  `bd-ib`), NOT the tenant DB name. The legacy `li-`-style random suffix
  is preserved as the beads suffix so cross-references survive.
- `type` — beads `issue_type`. Identity for `bug` / `feature` / `task` /
  `chore` / `epic`.
- `status` — beads `status`. Identity for `open` / `in_progress` /
  `blocked` / `closed` / `deferred`. (beads-only statuses are never
  emitted by a plugin write.)
- `title` — beads `title`. Identity.
- `description` — beads `description`. Identity.
- `priority` — beads `priority` (int). Identity; `0` = highest /
  critical on both sides, `4` = backlog.
- `assignee` — beads `assignee` (first-class field). Identity when
  present; absent when null.
- `origin` (`gap-tied` / `freeform`) — beads label `origin:<value>`.
- `gap_id` — beads label `gap-id:<id>`. Present iff `origin == gap-tied`;
  REQUIRED non-empty when present, absent when `origin == freeform`. The
  gap-id ↔ label exactly-once invariant is honored as exactly one
  `gap-id:` label per gap-tied issue.
- `priority`/`status`/etc. unchanged on read — materialization parses
  the `bd` JSON.
- `depends_on` — beads `blocks` dependency edges. For each blocker, a
  `bd dep add <this-issue> <blocker> --type blocks` edge exists; the
  reader populates `depends_on` from these edges.
- `superseded_by` — beads `supersedes` dependency edge (`bd dep add
  <superseding> <this> --type supersedes`). Present iff non-null.
- epic linkage — beads native `parent-child` (`bd create … --parent
  <epic>` / `bd update <child> --parent <epic>`). An epic is a
  `type: epic` issue whose members are its beads children.
- `captured_at` — beads `created_at`. On live create the value is read
  back from the server; on import the supplied timestamp is preserved.
- `resolution` (typed enum) — beads label `resolution:<enum>`, one of:
  `completed`, `wontfix`, `duplicate`, `spec-revised`,
  `no-longer-applicable`, `resolved-out-of-band`. REQUIRED present when
  `status == closed`.
- `reason` — beads `close_reason` (set via `bd close --reason`).
  REQUIRED non-empty for closure records.
- `spec_commitment_hint` — beads native `spec_id` field. When non-null,
  carries the verbatim `id_hint` from a spec-side
  `spec_commitments.impl_followups[]` declaration (per
  `livespec/SPECIFICATION/contracts.md` §"Implementation-plugin
  contract — the 10-skill surface" → "Work-item `spec_commitment_hint`
  field"). Absent for freeform items with no spec-side commitment.
- `audit` (the whole `AuditRecord`) — serialized losslessly into the
  beads issue's `metadata` JSON column. Present when `resolution` is one
  of `{completed, spec-revised, resolved-out-of-band}` (the resolutions
  that imply git activity landed on the canonical branch); absent
  otherwise. `AuditRecord` schema:
  - `verification_timestamp` (string, required). UTC ISO-8601 seconds of
    audit-record creation.
  - `commits` (array of strings, required, MAY be empty). SHAs of
    commits comprising the work. After squash-merge these SHAs may no
    longer exist locally; tooling MUST tolerate that case.
  - `files_changed` (array of strings, required, MAY be empty).
    Repo-root-relative paths touched by the work.
  - **`merge_sha`** (string, required, non-empty). SHA of the merge
    commit on the canonical branch that introduced this work. Tooling
    MUST verify it is reachable from `origin/<canonical_branch>` via
    `git merge-base --is-ancestor`.
  - **`pr_number`** (integer or null, optional). GitHub PR number for
    traceability; null when the merge did not originate from a PR.

  The audit MUST be present when `resolution` is one of `{completed,
  spec-revised, resolved-out-of-band}` — all three carry an implied
  canonical-branch merge that the audit attests. Resolutions in
  `{wontfix, duplicate, no-longer-applicable}` MUST carry no
  `AuditRecord` in `metadata`.

### Materialized view and close-in-place

Each work-item is exactly ONE beads issue row; there is no
latest-record-wins reduction (that is the plaintext sibling's concern).
A closure mutates the row IN PLACE: `bd close --reason` sets the
terminal status and `close_reason`, `bd update` sets the
`resolution:<enum>` label, and the `AuditRecord` (when required) is
written into `metadata`. A `status: closed` issue is terminal —
re-opening (`bd update --status open`) is ALLOWED but DISCOURAGED (the
right pattern is to file a new work-item with a fresh `id` that
references the closed one via `superseded_by` or `depends_on`). The
tenant DB's own version history is the immutable backing log behind the
in-place mutation; doctor's `no-orphan-blocker` invariant in `livespec`
reads materialized views, and readers of this plugin MUST do the same.

### `work_item_merge_evidence` static check

The check walks every materialized work-item from the configured store
descriptor (reading the `AuditRecord` from each closed issue's
`metadata` column) and applies the following rules.

For each work-item with `status == "closed"`:

- If `resolution` is in `{completed, spec-revised, resolved-out-of-band}`:
  - REQUIRE an `AuditRecord` is present in `metadata`.
  - REQUIRE `audit.merge_sha` is non-empty.
  - REQUIRE `git cat-file -e <merge_sha>` exits 0 (the SHA exists in the
    local repo).
  - REQUIRE
    `git merge-base --is-ancestor <merge_sha> origin/<canonical_branch>`
    exits 0.
- If `resolution` is in `{wontfix, duplicate, no-longer-applicable}`:
  - REQUIRE no `AuditRecord` is present (the negative-evidence case — a
    record that says "this was closed administratively" must not carry
    merge-evidence).
- If `resolution` is null AND `status == "closed"`:
  - FAIL with message "closed work-item without resolution is
    malformed."

Work-items with `type == "epic"` are EXEMPT from the merge-evidence
requirement. Epics close when their child work-items (beads
parent-child members) are all closed; the check INSTEAD requires that
every child resolves to a closed work-item.

All operations are local `git` invocations (`cat-file`, `merge-base`);
the check is network-free per the existing no-network-I/O constraint
(the `bd` reads it depends on go through the same local `bd` client, not
a separate network surface owned by the check).

The check is plugin-private to `livespec-orchestrator-beads-fabro` (it depends on the
beads-issue mapping this plugin defines — specifically the `AuditRecord`
in `metadata` and the `resolution:` label). The plaintext sibling ships
its own JSONL-shaped equivalent; the two are not interchangeable.

### Closed-item-integrity check

The `closed_item_integrity` check is the mechanical guard for the
closed-item-integrity invariant in `constraints.md` §"Closed-item
integrity" — it makes "closed but unproven is forbidden" un-bypassable
rather than a remember-to-verify review.

The `closed_item_integrity` check MUST enumerate every closed gap-tied work-item in the beads store, derive each item's `gap-id` from its `gap-id:<id>` label, resolve that gap-id to an acceptance scenario via the `clauses[]` gap-id→scenario map in `tests/heading-coverage.json`, and emit a `closed-item-integrity` finding for any such item whose resolved scenario's `heading-coverage` entry is still bound to the `TODO` sentinel (not a real integration-tier-or-above test node id) OR which lacks the `resolution:completed` label.

The `closed_item_integrity` check MUST be always-wired into the `just check` aggregate and always-running; it MUST NOT be silently skipped. Its severity is governed by a self-documenting per-check lever — the `LIVESPEC_CLOSED_ITEM_INTEGRITY` environment variable — whose only recognized values are `warn` and `fail`. In `warn` mode (the DEFAULT) the check MUST surface each offender as a warning and exit `0`; in `fail` mode it MUST surface each offender as an error and exit non-zero. An unset or unrecognized lever value MUST default to `warn`. The lever is the SEVERITY switch, not a wiring carve-out: the check always enumerates every closed gap-tied item and always runs regardless of the lever value.

The check REUSES existing primitives and introduces NO new gap-id logic:
it derives gap-ids through the shared `livespec_spec_clauses` extractor
(the same primitive impl-beads' `detect-impl-gaps` detector already
imports — single-source gap-id, no duplication), reads the `clauses[]`
map already defined by livespec core's `constraints.md` §"Heading
taxonomy", and reads closed gap-tied items through the existing beads
reader (`bd` store). This check is enforced by
`just check-closed-item-integrity`.

Preconditions (recorded so the future revise/impl loop sees them, NOT as
separate invariants): the check requires (a) the `clauses[]`
gap-id→scenario map to be populated in `tests/heading-coverage.json` for
each gap-tied behavior clause (linking its gap-id to its acceptance
scenario's H2 section name) — this is the core `clauses[]` contract
(`constraints.md` §"Heading taxonomy", `non-functional-requirements.md`
§"Behavior-clause-to-scenario link check") that impl-beads adopts; and
(b) the shared `livespec_spec_clauses` extractor available to
impl-beads' dev-tooling. Both are existing primitives; the impl
work-item adopts the `clauses[]` map into impl-beads' heading-coverage
and wires the check — it does not build new gap-id machinery.

Implementation-approach note (recorded so the future impl loop sees it,
NOT a second invariant): the `resolution:completed` half of the
invariant is best upheld by a "pit of success" `close-work-item`
wrapper that atomically closes a work-item AND applies the
`resolution:completed` label in one operation — so the
`constraints.md` §"Closed-item integrity" two-step close recipe (`bd
close --reason …` then `bd update --add-label resolution:completed`) can
never be half-done (closed without the label). This wrapper is an impl
work-item to be built alongside the `closed_item_integrity` check, not a
separate spec invariant; the invariant states WHAT must hold, the check
DETECTS violations, and the wrapper makes the compliant path the path of
least resistance.

## Spec Reader internal API

Per `livespec/SPECIFICATION/contracts.md` §"Spec Reader
required-capability surface", every `livespec-impl-*` plugin MUST expose
four capabilities through an internal adapter. The shape is
implementation-dependent; this plugin's shape is a Python module with
these public functions:

```python
def read_current_specification(spec_root: Path) -> SpecSnapshot: ...
def read_specification_history(spec_root: Path, version: int) -> SpecSnapshot: ...
def current_specification_version(spec_root: Path) -> int: ...
def diff_specification_versions(
    spec_root: Path, version_a: int, version_b: int,
) -> SpecDiff: ...
```

`SpecSnapshot` and `SpecDiff` are dataclasses defined under
`.claude-plugin/scripts/<adapter>/spec_reader.py`. The Spec Reader is
substrate-agnostic — it reads the spec tree, never the beads tenant DB —
so its implementation is shared near-verbatim with the plaintext
sibling. The initial implementation is a thin file pass-through (no
caching, no indexing); cached or section-indexed implementations remain
valid future refinements without contract change.

The Spec Reader MUST:

- Consult the active template manifest's `spec_files` list rather than
  hardcoding the well-known file set (per upstream §"Spec Reader
  required-capability surface" capability 1).
- Surface the `version-directories-complete` pruned-marker exemption
  when reading history (capability 2).
- Return `int` for the current version (capability 3).
- Compute diffs as a structured change list (capability 4); the initial
  implementation returns a `SpecDiff` carrying per-file
  added/removed-line counts plus a unified-diff body.

The Spec Reader MUST exclude content from
`<spec-root>/proposed_changes/`. Only ratified canonical content is
exposed; pending proposals are not yet intent.

The Spec Reader is consumed by `detect-impl-gaps`, `capture-spec-drift`,
and `implement`. It is NOT a slash command and NOT
exposed through the `/livespec-orchestrator-beads-fabro:` namespace.

## Persistent Agent Knowledge realization

Per `livespec/SPECIFICATION/contracts.md` §"Persistent Agent
Knowledge realization", the per-plugin form is
implementation-dependent. `livespec-orchestrator-beads-fabro` realizes the store as:

- A directory `.ai/` at the consumer project's root containing one
  markdown file per topic (`.ai/<topic-slug>.md`).
- Each topic file is referenced from the consumer project's `CLAUDE.md`
  and/or `AGENTS.md` via a one-line bullet pointing at the file path.
  Reference inclusion is REQUIRED — orphaned topic files MUST NOT exist.
- A topic file is authored by writing the durable knowledge to the
  chosen topic file (creating it if absent) and updating
  `CLAUDE.md` / `AGENTS.md` references if needed in one atomic step.
- Topic files MAY accumulate; pruning is the user's call (this store
  does NOT auto-trim). Persistent-knowledge content is durable-pending,
  never transient, so no productivity-heuristic hygiene invariant
  applies to it (per upstream §"Persistent Agent Knowledge realization"
  bullet 3).

The harness loads `CLAUDE.md` / `AGENTS.md` automatically into agent
context per Claude Code / Codex / other harness conventions; the linked
`.ai/<topic>.md` files are loaded on-demand by the agent following
bullet references when relevant. This realization is the same slot the
plaintext sibling implements — it is substrate-independent (the
Persistent Agent Knowledge store is markdown files, never beads issues).

## `compat` block

Per `livespec/SPECIFICATION/contracts.md` §"Cross-repo
coordination — pin-and-bump", every consuming project's `.livespec.jsonc`
declares a `compat` block for each active impl-plugin. For
`livespec-orchestrator-beads-fabro`:

```jsonc
{
  "implementation": { "plugin": "livespec-orchestrator-beads-fabro" },
  "livespec-orchestrator-beads-fabro": {
    "format": "beads",
    "compat": {
      "livespec": ">=0.1.0,<1.0.0",
      "pinned": "master"
    },
    "connection": {
      "tenant": "livespec-orch-beads-fabro",
      "prefix": "bd-ib",
      "database": "livespec-orch-beads-fabro",
      "server_user": "livespec-orch-beads-fabro",
      "server_host": "127.0.0.1",
      "server_port": 3307,
      "fake": false
    }
  }
}
```

`format: beads` is fixed for this plugin (the substrate marker — the
plaintext sibling declares `jsonl`). `livespec` is a semver range
matching every `livespec` release this plugin's pinned version is known
to be compatible with. `pinned` is the SPECIFIC `livespec` release tag
the consumer currently runs against (`master` during bootstrap, which
fires doctor's `contract-version-compatibility` `warn` as expected).
Both are REQUIRED per upstream.

The `connection` block is plugin-specific configuration. Its keys:

- `tenant` / `database` / `server_user` — all equal (the load-bearing
  ≤32-char tenant identity; one Dolt name serves all three).
- `prefix` — the beads issue-ID create-prefix (bd's server-stored
  prefix). It is DECOUPLED from the tenant DB name: a short, readable
  alias that MAY differ from it (here it is `bd-ib`). Skills read it from
  this value rather than assume it equals the tenant.
- `server_user` — the least-privilege tenant user scoped to this DB.
- `server_host` / `server_port` — the TCP connection to the shared
  `dolt sql-server`.
- `socket` — the Unix socket path; OVERRIDES host/port when reachable.
  TCP is the default for sandboxed callers that lack `0750`
  socket-directory access.
- `fake` — selects the hermetic in-memory backend; `false` in the
  committed config (which describes the real connection). CI and tests
  set `LIVESPEC_BEADS_FAKE=1` to force the fake.

The tenant PASSWORD is deliberately ABSENT from this block. It is
supplied only via the `BEADS_DOLT_PASSWORD` environment variable at
`bd`-call time and is NEVER committed. The `LIVESPEC_BD_PATH`
environment variable (the managed absolute path to the pinned `bd`
binary) and `LIVESPEC_BEADS_FAKE` likewise overlay this block at
runtime and are not committed config keys.

There is no `work_items_path` key — that is the plaintext sibling's
JSONL-file location; this plugin's substrate is the tenant DB resolved
from the `connection` block.

**`canonical_branch`** (optional string). The canonical branch name
against which merge-evidence checks (see §"`work_item_merge_evidence`
static check") verify reachability. Default: the value of
`git symbolic-ref --short refs/remotes/origin/HEAD` (typically `master`
or `main`). Hard-coded fallback when symbolic-ref resolution fails:
`"master"`. The key is project-level (one value per repo), not
per-work-item — static checks resolve it once per invocation and apply
it uniformly.

The configuration block is read by every skill at invocation time. A
missing or malformed block MUST fire a `fail` finding from doctor's
`contract-version-compatibility` invariant (upstream §"Cross-boundary
doctor invariants").

## Cross-boundary handoffs

Per `livespec/SPECIFICATION/contracts.md` §"Cross-boundary handoffs",
this plugin participates in these red-edge handoffs:

1. `/livespec-orchestrator-beads-fabro:capture-spec-drift` →
   `/livespec:propose-change` (drift findings).
2. `/livespec:doctor` → `/livespec-orchestrator-beads-fabro:list-work-items --json`
   (work-item structural invariants).
3. `/livespec:doctor` → `/livespec-orchestrator-beads-fabro:detect-impl-gaps --json`
   (gap-detection invariants `gap-tracking-one-to-one` and
   `no-stale-gap-tied`).

The handoff mechanism is namespace invocation (per
`livespec/SPECIFICATION/contracts.md` §"Cross-plugin invocation") —
never direct CLI shelling-out to wrapper paths.

## Worker credential projection

The Dispatcher MAY authenticate a worker sandbox's coding-agent runtime from a
**projected provider-subscription credential** (for example a Claude subscription
or an OpenAI/ChatGPT subscription) as an alternative to a provider API key, so
workers MAY spend subscription quota rather than metered API billing. This
contract is provider-agnostic: it governs Claude-subscription and
OpenAI/ChatGPT-subscription workers identically.

A projected worker credential MUST be **non-rotatable by the worker**: a worker
MUST NOT be able to mint or rotate the shared long-lived refresh credential. No
worker — including one whose run triggers a credential refresh — MAY invalidate
the credential for the orchestrator host or for any peer worker.

The Dispatcher MUST NOT dispatch a worker unless the projected credential's
usable lifetime exceeds the worker's maximum run budget (the **freshness
gate**). When the freshness gate cannot be satisfied, the Dispatcher MUST refuse
the dispatch and MUST surface that the host credential requires renewal, rather
than projecting a credential that MAY expire mid-run.

The orchestrator **host** MUST be the sole owner and refresher of the long-lived
provider refresh credential; worker sandboxes MUST be read-only consumers of a
projected snapshot.

The projection mechanism — the credential file or field layout, the encoding
that renders the snapshot non-rotatable, and the numeric freshness threshold —
is implementation-owned and MUST NOT be fixed by this contract. The behavior is
exercised by Scenario 18 and Scenario 19 in `scenarios.md`.
