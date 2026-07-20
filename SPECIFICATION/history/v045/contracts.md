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
namespace prefix per `livespec/SPECIFICATION/contracts.md`). Renaming is a major-version-bump
operation.

## The skill surface

Every entry below is REQUIRED. The descriptions concretize each skill's
behavior on the beads substrate; cross-boundary semantics (handoffs,
JSON output schemas, user-consent rules) are defined by
`livespec/SPECIFICATION/contracts.md` and apply uniformly.

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
architecture (`livespec/SPECIFICATION/spec.md`). The six heavyweight ops are
`capture-impl-gaps`, `capture-spec-drift`, `capture-work-item`,
`implement`, `groom`, and `plan` — this enumeration (six heavyweight +
one operator + four thin-transport) is the ONE authoritative skill
inventory; other sections and files reference it rather than restating
counts. `groom` is the one new maintainer front-end catalogued under
§"Skills — augmented versus new", and is detailed in §"Grooming and
slice-size calibration" → "The four maintainer touchpoints"
(touchpoint 2) — see that section for its read-only-draft /
human-approves contract. `plan` is the Orchestrator-Plane realization of
the Planning Lane and is detailed in §"Planning Lane realization" — see
that section for its create/resume API, the `plan/<topic>/` thread
store, the handoff self-sufficiency gate, and the archive-on-close
transition. The remaining four ops (`capture-impl-gaps`,
`capture-spec-drift`, `capture-work-item`, `implement`) are detailed in
the subsections that follow.

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

`capture-spec-drift` MUST detect drift from two sources: the impl → spec
heuristic above, and a **ledger-intent scan** — a read-only pass over
recent work-items in the Ledger that surfaces work-item intent (its
`title`, `description`, `acceptance_criteria`, and closure `reason`)
encoding an observable behavior, decision, or invariant NOT reflected in
the current spec. Each ledger-intent finding MUST be surfaced through the
same per-finding consent flow and, on consent, handed off to
`/livespec:propose-change`; the scan reads the Ledger through the store's
read API only, and MUST NOT emit a finding for intent already reflected
in the spec.

`capture-spec-drift` MUST accept an optional `--since-version <vN>` flag
mirroring `capture-impl-gaps`: when set, the ledger-intent scan MUST
consider only work-items captured on or after the cut of spec version
`<vN>`; when omitted, it MUST consider every live (non-`done`) work-item
plus every work-item captured on or after the most-recently-cut spec
version. The flag scopes only the ledger-intent source; the impl → spec
heuristic is unaffected.

#### `capture-work-item`

Freeform direct filing of a work-item. The user supplies title,
description, and type; the skill creates a new beads issue via
`bd create` carrying the `origin:freeform` label and no `gap-id:` label,
plus the supplied fields. There is no priority input — ordering is the
store's concern via `rank` (per §"Work-item beads-issue mapping"). No gap detection runs; no closure-verification
rules attach. Closure is via the freeform path in `implement`.

The skill accepts an optional `--spec-commitment-hint <id_hint>` flag.
When supplied, the resulting work-item's `spec_commitment_hint` MUST
equal the verbatim `id_hint` (carried on the beads issue's native
`spec_id` field per §"Work-item beads-issue mapping"); when omitted, the
hint is absent (the freeform case). This is the surface livespec's
`unresolved-spec-commitment` doctor invariant queries via
`list-work-items --json` to verify each declared spec→impl commitment
maps to a filed work-item (per
`livespec/SPECIFICATION/contracts.md`).

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

**Lifecycle placement.** `implement` is the HUMAN-DRIVEN loop: its
closure is a direct close-in-place from the item's current state,
consented up-front by the operator's resolution-path decision (per
§"Store-write consent discipline"). The post-merge `acceptance` valve
governs the Dispatcher's machine-driven dispositions only (§"Dispatcher
admission, WIP cap, and post-merge acceptance", §"Dispatcher policy
settings"); a human-driven `implement` closure
does NOT transit `acceptance` — the operator's own verification (the
gap-tied re-detection, the Red → Green evidence) is the closure's
verification consent.

### Operator skill (1)

#### `drive`

Permanent minimal operator **executor** surface. `drive` executes exactly
one operator action, identified by its action-id, against the target
repo. The skill is a thin binding over
`.claude-plugin/scripts/bin/drive.py` and the shared
`commands/drive.py` implementation. `drive` composes and ranks NOTHING:
it is a pure executor of its own **action-id grammar** — an `impl:`
dispatch action, one of the ten human valve/policy actions
(`approve:` / `accept:` / `reject:` / `resolve-blocked:` /
`set-admission:` / `set-acceptance:` / `set-merge-on-review-cap:` /
`set-review-fix-cap:` / `set-acceptance-rework-cap:` / `move:`), or a
config action (`config` / `config-manifest` /
`set-config:<key>:<value>`). It MUST NOT duplicate ranking or
composition logic from any `next` surface, and it MUST NOT create
net-new work-items.

`drive` and the read/awareness surface `needs-attention` are **peers,
not layered** — coupled ONLY by the shared action-id grammar. Neither
calls the other: an operator (or the console) reads what needs attention
from `needs-attention`, then invokes `drive` on a selected drive-grammar
action-id. The former `orchestrate plan` two-`next` composition and the
former bare `orchestrate` interactive walkthrough are RETIRED: the
composition/awareness role relocates to `needs-attention`, and the
interactive "see → select → execute" loop belongs to the console. Only
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
the existing Dispatcher/Fabro loop with `--budget 1 --parallel 1 --item
<work-item-id> --json`, then summarizes the Dispatcher status, exit code,
stdout JSON, stderr, and the selected work-item id. There is no run-mode
flag: `--item` ALONE scopes the run to that one work-item, and its
presence is what marks the dispatch as human hand-picked (§"Dispatcher
loop invocation surface"). The `factory_safe` marking itself is produced by whichever
surface emits the action-id (the `needs-attention`/`drive` action-id
coordination defined by the broader epic), not by `drive`; it is
forward-referenced here rather than defined by this section.

**Human valve actions.** `drive` additionally accepts the ten human
operator action ids (the two human-delegable gate commands, the
corrective `reject:`, the blocked-resolution `resolve-blocked:`, the two
admission/acceptance policy edits, the three per-item cap overrides, and
the guarded queue-control `move`) — `approve:<work-item-id>` (the human
approval act: transitions an
effective-`manual` item from `pending-approval` to `ready`; admission to
`active` then follows mechanically when a WIP slot frees, dependencies
are clear, an assignee resolves, and `factory_safety` is null), `accept:<work-item-id>` (the human
leg of post-merge acceptance: `acceptance → done`),
`reject:<work-item-id>:rework` / `reject:<work-item-id>:regroom`
(`acceptance → active` fix-forward; `acceptance → backlog` with the
merged change reverted), `resolve-blocked:<work-item-id>:ready|backlog`
(clears a human-gated block: moves a `blocked` item whose blocked-reason
is `needs-human` to `ready` or `backlog`, and is refused for any other
source state), the two policy-edit actions
`set-admission:<work-item-id>:auto|manual` and
`set-acceptance:<work-item-id>:ai-only|human-only|ai-then-human`, the
three per-item cap-override actions
`set-merge-on-review-cap:<work-item-id>:true|false|clear`,
`set-review-fix-cap:<work-item-id>:<positive-int>|clear`, and
`set-acceptance-rework-cap:<work-item-id>:<positive-int>|clear` (each a
per-item override of the correspondingly-named `dispatcher.*` policy
setting, §"Dispatcher policy settings"), and the guarded queue-control
action `move:<work-item-id>:backlog|ready|blocked|active`. A policy-edit
OR cap-override action MUST modify ONLY the named policy or cap field of
an existing item (realized on beads as the `admission:` / `acceptance:`
policy label, or the `merge-on-review-cap:` / `review-fix-cap:` /
`acceptance-rework-cap:` cap label, through the store seam) and MUST NOT
change the item's status. A policy edit NEVER moves an item between
states: flipping an item's `admission_policy` from `manual` to `auto`
while it rests at `pending-approval` MUST NOT approve it into `ready` —
the automatic GO fires only once, at capture/groom time; after a later
policy flip, moving the item still requires an explicit
`approve:<work-item-id>`. Symmetrically, flipping `auto` to `manual` on
an item already at `ready` MUST NOT demote it — it was already approved;
a policy flip never demotes an item out of `ready` — that takes an
explicit operator act (the `defer` un-approval, or a guarded `move`). A
cap-override action ALSO accepts the reserved value `clear`
(`set-<cap>:<work-item-id>:clear`), which REMOVES the per-item cap label
so the item reinherits the global `dispatcher.*` default; clearing an
already-absent override is a green no-op. The `clear` value can never
collide with a real cap value — the boolean cap is `true`/`false` and
the integer caps are positive integers — so it is an unambiguous
sentinel. The guarded `move:<work-item-id>:<status>` action is a
hands-on operator queue-control valve that writes ONLY the item's status
through the same store seam the other valves use, changing nothing else;
its allowed targets are EXACTLY `backlog`, `ready`, `blocked`, and
`active`, and `done`, `acceptance`, and `pending-approval` are FORBIDDEN
and MUST be refused with a clear error. `move` relocates an item from ANY
current status to one of those allowed pre-terminal targets — only the
TARGET is guarded, not the source. `done` is reachable ONLY through
the accept-from-acceptance path (the ship-guard against force-shipping
unverified work), and `acceptance` / `pending-approval` are entered only
on their own guarded/entry paths. These are human-TRIGGERED operator
commands, not machine-path dispositions: the explicit action selection
is the consent (an up-front operation decision per §"Store-write consent
discipline"), each writes through the same store seam, and the journal
records the actor. This is the published surface the console invokes for
the two human-delegable gates — `approve` and `accept` — the
blocked-resolution, the policy-edit actions, the three cap overrides, and
the guarded `move` (§"Dispatcher
admission, WIP cap, and post-merge acceptance"); the console never writes
the ledger directly. The console's single per-item override command FANS
OUT to the three named per-cap actions above — sending `clear` when that
command carries a null value — so it is the ONE console command that does
NOT map 1:1 onto a `drive` action-id; the orchestrator side is correctly
three named cap verbs, never one parameterized `set-override`. The
operator-action behavior is exercised by `scenarios.md` Scenario 31 (the
two gates, `reject:`, and the two policy edits), Scenario 46 (the cap
overrides and clear-to-inherit), and Scenario 47 (the guarded `move`).

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

### Thin-transport skills (4)

Each thin-transport skill is a short SKILL.md pass-through over a Python
`bin/` implementation (the wrapper-shape contract codified in
`livespec/SPECIFICATION/contracts.md`).
SKILL.md MUST NOT accrete logic — every behavior lives under
`.claude-plugin/scripts/bin/<skill>.py`.

#### `list-work-items`

CLI surface: `list-work-items [--filter <name>] [--with-gap-id=<id>] [--with-spec-commitment-hint=<id_hint>] [--json] [--work-items-path <path>] [--project-root <path>]`.

`--filter` flags:

- `--filter=gap-tied` — `origin: gap-tied` only.
- `--filter=freeform` — `origin: freeform` only.
- `--filter=blocked` — lane `blocked` (stored `blocked`, OR stored
  `ready` with an open dependency rendered as `blocked:dependency`).
- `--filter=ready` — lane `ready` (stored `ready` AND no unresolved
  `depends_on` edges).
- `--filter=done` — terminal items only (logical `done`, stored as
  beads-native `closed` per the adapter mapping). `closed` is accepted
  as a beads-layer alias for the same filter.
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
materialized views. Each item additionally carries two **computed flat**
keys — **`lane`** (the rendered lane, one of `backlog` /
`pending-approval` / `ready` / `active` / `acceptance` / `blocked` /
`done`) and **`lane_reason`** (the rendered blocked reason: `needs-human`
/ `infra-external` / `dependency`, else `null`) — computed by the shared
`livespec_runtime.work_items.lifecycle.lane_of` authority
(consume-don't-recompute: the console reads `lane`/`lane_reason`
directly and never re-derives a lane from the raw status). The new
`WorkItem` fields (`rank`, `admission_policy`, `acceptance_policy`,
`blocked_reason`, the 7-state `status`, `assignee`) emit via the existing
flat serializer; only `lane`/`lane_reason` are computed additions.

#### `list-plan-threads`

CLI surface: `list-plan-threads [--json] [--project-root <path>]`. No
`--filter` flag — the skill emits the complete set of open (unarchived)
plan threads.

`--project-root <path>` — override the base whose `plan/` thread store
is enumerated. Default: `Path.cwd()`. Used by the awareness surface's
(and any other consumer's) cross-boundary handoffs to invoke this skill
from outside the consumer project root.

This skill is the plan-thread enumerator sibling of `list-work-items`: a
pure read-and-emit pass-through that enumerates the open planning threads
under the governed repo's `plan/` thread store (per §"The
`plan/<topic>/` thread store"). It exists so the read/awareness surface
can compose "plan threads" (per §"`next`" scope-asymmetry) from a single
canonical primitive rather than re-scanning `plan/` inline.

The skill MUST enumerate exactly one entry per **unarchived** thread
directory — every direct child directory of `plan/` EXCEPT the archive
subtree `plan/archive/` — in ascending lexicographic topic order. An
**archived** thread (`plan/archive/<topic>/`) MUST NOT surface. The scan
is directory enumeration only: it MUST NOT read thread contents, rank,
filter beyond the unarchived/archived split, or consult the ledger —
whether a thread's anchoring epic state matches its archived/unarchived
placement remains the Conformance Pattern's concern (§"Archive on epic
close"), not this skill's.

`--json` output: a top-level JSON object with one key, `plan_threads`,
whose value is an array of unarchived thread topic strings (the thread
directory names) in ascending lexicographic order:

```json
{
  "plan_threads": ["alpha-topic", "beta-topic"]
}
```

Default human output: one line per thread topic. Each topic `<topic>` is
the natural key from which a consumer derives the thread path
(`plan/<topic>/`) and the `/livespec-orchestrator-beads-fabro:plan
<topic>` handoff; the skill emits neither derived form (per
`constraints.md` §"Forbidden patterns" no-off-substrate / derive-on-read
discipline).

Degrade-on-missing: a missing or empty `plan/` directory MUST yield
`plan_threads: []` and MUST exit `0` — an absent thread store is a valid
zero-thread state, never an error. This is the same per-source degraded
tolerance the ranking and listing primitives already carry.

The skill MUST NOT mutate any store: it MUST NOT write the tenant DB,
MUST NOT write or reorder the `plan/` thread store, and MUST NOT prompt
the user. It is query-only by contract (per `constraints.md` §"Forbidden
patterns").

#### `next`

Cross-reference: cross-repo dispatch is the Dispatcher's concern
(`dispatcher.py` `dispatch` / `loop`; see README). This surface ranks
impl-side state only; it MUST NOT
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

1. Identify ready items: lane `ready` (stored `ready`, `depends_on`
   either empty or all-closed).
2. Order by **`rank`** — the fractional/lexicographic ordering key, the
   sole ordering authority — in ascending lexicographic order (the
   earliest `rank` is the most urgent). The old `priority → gap-tied →
   oldest captured_at` heuristic is retired (`priority` removed).
3. Ties are broken deterministically by `id` lexicographic order.
4. Apply `--offset` and `--limit` to produce the returned slice.

This ranking IS `ready_sort_key` from
`livespec_runtime.work_items.lifecycle` (`(rank, id)`); `next` is the
single ranking authority and the Dispatcher composes it.

Output schema (per `livespec/SPECIFICATION/contracts.md` and the
upstream `/livespec:next` spec-side thin-transport skill's output
schema): the output is a JSON object with two top-level keys,
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
  `origin`, `lane`); the cross-plugin contract MUST NOT prescribe
  `additionalProperties` discipline per upstream.
- `pagination.offset` — echoed from `--offset`.
- `pagination.limit` — echoed from `--limit`.
- `pagination.total` — total count of ripe candidates BEFORE `offset`
  and `limit` are applied.
- `pagination.has_more` — `true` iff
  `offset + len(candidates) < total`.

`urgency` derivation per candidate: the discrete `priority`-tier mapping
(P0 → high; P1, P2 → medium; P3, P4 → low) is retired with `priority`.
Ranked candidates emit `urgency: "medium"` — the `rank` order itself is
the urgency signal (the candidates array is already in pull order).

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
human-valve lanes via `list-work-items`, plan threads via
`list-plan-threads`, plus hygiene) in the read/awareness surface
(`needs-attention`), NOT here. No caller
SHOULD rebuild the incomplete two-`next` composition (the retired
`orchestrate plan`, per §"`drive`"): the composition role belongs to the
awareness surface, and `next` MUST remain a pure `implement`-only ranker.

#### `detect-impl-gaps`

CLI surface: `detect-impl-gaps [--spec-target <path>]
[--project-root <path>] [--since-version <vN>] [--json]`. No `--filter`
flag — the skill emits the complete current gap-id set.

The skill reads the live Specification via the Spec Reader, enumerates
every MUST/SHOULD rule per the gap-rule enumeration contract (per the
upstream Spec Reader required-capability surface, capability 1), and
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
store-writer via `file_approved_slices` / `regroom.exit_regroom` — its approve-then-file step writes the regroomed slices (each transits `pending-approval`; an effective-`auto` slice approves on into `ready` at groom time, an effective-`manual` slice rests awaiting the human's explicit `approve`), so it
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
items — the lifecycle verbs `admit` (`ready → active`), `complete`
(`active → acceptance` on confirmed merge, carrying PR-number and
merge-sha audit evidence in the `AuditRecord`), `accept`
(`acceptance → done`, the AI leg of the item's effective
`acceptance_policy`), `reject` routing out of `acceptance`, the non-convergence `backlog` bounce, and — when the effective `admission_policy` is `auto` (via `dispatcher.auto_approve_ready` or a per-item label, per §"Dispatcher policy settings") — the auto-`approve` (`pending-approval → ready`) disposition. These writes are EXEMPT from
the per-operation consent discipline by design — the Dispatcher acts
on items a human or a consented front-end already filed, and
`--no-close-on-merge` disables the post-merge disposition writes
entirely. The exemption covers
ONLY dispositions of already-filed items; the Dispatcher MUST NOT
create net-new work-items on its own initiative. The
Dispatcher's module docstring documents this boundary. The human-triggered operator commands (`drive` `approve:`/`accept:`/`reject:`/`resolve-blocked:`/`set-admission:`/`set-acceptance:`/`set-merge-on-review-cap:`/`set-review-fix-cap:`/`set-acceptance-rework-cap:`/`move:` action ids, per §"`drive`") are NOT machine-path dispositions — their consent is the operator's
explicit action selection.

### Out-of-scope surfaces

The four thin-transport skills (`list-work-items`, `next`,
`detect-impl-gaps`, `list-plan-threads`) are query-only by contract (per
`constraints.md` §"Forbidden patterns") and never write to the
store; the consent discipline does not apply to them.
`capture-spec-drift` writes nothing to this plugin's store — its
output is a `/livespec:propose-change` cross-boundary handoff,
itself per-finding user-consented.


## Grooming and slice-size calibration

This section realizes the repo-agnostic grooming pattern/guidance
that `livespec`'s `non-functional-requirements.md` carries as
Orchestrator-internal guidance (beside its existing Orchestrator-internal
Dispatcher guidance); core gains only the guidance, never a skill,
CLI, or doctor invariant. Grooming — how a maintainer breaks and
sizes work into agent-feedable slices BEFORE autonomous dispatch —
operates on this plugin's ledger (the beads tenant DB), is
Orchestrator-internal, and is therefore NOT part of `livespec`'s
functional cross-boundary contract.

### The four maintainer touchpoints

1. **Capture / intake (augmented).** Work is filed as today via
   `capture-work-item` / `capture-impl-gaps`, but each now runs an
   intake Definition-of-Ready checklist in-dialogue, auto-answering
   what it can and prompting the human only on the rest, and routes the
   resulting item into its lifecycle state: a Definition-of-Ready-passing
   item lands in `pending-approval` (approved on into `ready` when its effective `admission_policy` is `auto`; an effective-`manual` item RESTS at `pending-approval` awaiting the human's explicit `approve` — the `pending-approval → ready` transition); an epic-shaped item lands in
   `backlog` for decomposition; a not-autonomously-verifiable item lands
   in `blocked` with `blocked_reason: needs-human`; unresolved
   dependencies are linked as edges (deriving the `blocked:dependency`
   lane). The Definition-of-Ready holds when ALL of these hold, otherwise
   the item is ROUTED not filed-as-ready:

   - **Exactly one coherent "done"** — one named scenario,
     scenario-verified; OR the standing gates `just check` +
     `/livespec:doctor` fully define done with no scenario,
     gate-verified. Being unable to name exactly one means the item is
     an epic and routes to `backlog` for decomposition.
   - **The acceptance is autonomously verifiable** with no human
     judgement call.
   - **An autonomy tier is assigned** — spec-change is human-gated
     (effective `admission_policy` `manual`) and
     routes to `/livespec:propose-change` / `/livespec:revise`;
     everything else is factory-dispatchable.
   - **Dependencies are linked** as beads `blocked-by` edges (ready
     requires blockers closed AND an acceptance — never deps alone).
   - **The repo target is named** — one slice maps to one ledger.
   - **The slice is above the size floor** (anti-over-split; the floor
     is human judgement until slice-size calibration yields a value).

2. **Groom (the one new maintainer surface).** For a `backlog` item
   needing re-decomposition (an intake-routed epic or a non-convergence
   bounce) the maintainer runs the shipped groom front-end
   (`groom <id>`) — a read-only scoping conversation that DRAFTS a
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
   on `just check` + `/livespec:doctor`, merges, and closes — pulling the maintainer in ONLY to `approve` a resting `pending-approval` item into `ready` (effective `admission_policy` `manual`, the risky/irreversible tier — a spec-change decision is human-gated by routing to `/livespec:propose-change`, not by resting here) or to
   re-groom a `backlog` bounce (escalate-don't-drop, back to
   touchpoint 2).

4. **Calibration (mostly invisible).** A periodic analysis pass
   correlates run outcomes against mechanical size proxies and
   proposes ceiling thresholds; once a maintainer adopts them they
   make the intake size-gate flag oversized items advisorily.

### Skills — augmented versus new

**Augmented** (existing skills of this plugin's skill surface, per
§"The skill surface"): `capture-work-item` and `capture-impl-gaps` run
the intake Definition-of-Ready checklist and route the item into its
lifecycle state.

**New (exactly ONE):** the groom front-end (`groom`), the
agent-drafts / human-approves regroom surface. It is ALSO a heavyweight
authored skill (per §"Heavyweight authored skills (6)"), so
its orchestration follows the same shared-`.claude-plugin/prose/<op>.md`
+ thin per-runtime SKILL.md decomposition as the other heavyweight
ops; "new" here describes its place in the skill inventory, not a
different binding shape.

**NOT skills (Orchestrator machinery):** the Dispatcher's
grooming-related behavior, the lifecycle `backlog` bounce disposition
(there is no separate needs-regroom state, per §"Resolved realization
choices"), and the calibration analysis pass.

State the restraint budget explicitly: the realization adds at most
one new front-end + the `backlog` bounce disposition (no new ledger
state) + outcome/size FIELDS on the
existing Dispatcher journal + one periodic analysis pass; everything
else reuses Beads (ready / dependency layers / labels) and the
existing capture front-ends. If the realization ever grew past roughly
one new front-end + one bounce disposition, that is the signal to stop
and reconsider.

### Dispatcher grooming behavior

The Dispatcher MUST NOT auto-approve (`pending-approval → ready`) any item whose effective `admission_policy` is `manual` (the first-class realization of the risky/irreversible human gate — the prior `human-gated` lineage (the orthogonal `host-only` runnability marker is now the `factory_safety` axis, not this field); a spec-change decision is human-gated by ROUTING to `/livespec:propose-change` rather than by resting here, per the intake autonomy-tier rule "spec-change is human-gated … and routes to `/livespec:propose-change` / `/livespec:revise`") — it surfaces the resting item for the maintainer's explicit `approve` instead of advancing it (the authoritative gate + valve contract is §"Dispatcher admission, WIP cap, and post-merge acceptance"). On
factory NON-CONVERGENCE (a dispatched slice that will not converge
through the janitor gate) the Dispatcher MUST bounce the item to
`backlog` and SURFACE it (escalate-don't-drop), never
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
initiative; bouncing to `backlog` and surfacing is a
disposition/escalation of an already-filed item, not a net-new
creation).

These clauses are stated in the lifecycle vocabulary: the prior
`human-gated` marker is realized by the item's effective
`admission_policy == manual` (resting at `pending-approval` until a human explicitly approves it into `ready`), and the prior `needs-regroom` disposition is the
lifecycle `bounce` back to the `backlog` state (re-decomposition). The authoritative gate + valve contract is §"Dispatcher admission, WIP cap, and post-merge acceptance"; Scenarios 9–11 express the same vocabulary.

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
   routes back to the Dispatcher (→ the `backlog` bounce), reusing Fabro's
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
safety net. The reactive ceiling (bail after N fix-loops → the
`backlog` bounce) needs no calibration and is the non-convergence
trigger above; the predictive intake size-flag needs calibration and
the reactive bail-out is its training signal.

### Resolved realization choices

Both questions previously left open here are now RESOLVED by the
deterministic lifecycle state machine:

- **groom front-end shape** — RESOLVED: `groom` is its OWN heavyweight
  authored skill (shipped), not an "epic mode" of `capture-work-item`.
- **`needs-regroom` ledger representation** — RESOLVED: there is no
  separate `needs-regroom` label OR status. The lifecycle folds it into a
  `bounce` back to the `backlog` state (re-decomposition); the lighter
  `defer` returns an item to `pending-approval` (still groomed, just
  un-approved). The ledger representation is the 7-state custom-status
  encoding in §"Work-item beads-issue mapping".

### Gap-detectable behavior clauses

This subsection restates the realization's NON-Dispatcher fundamental
behaviors as explicit normative clauses so the mechanical gap-detector
and the heading-coverage map can hold the impl accountable; the
surrounding prose subsections remain as augmentation. Where behaviors
1-3, 7, and 8 were previously stated only as prose in §"The four
maintainer touchpoints" / §"Calibration telemetry and the single Fabro
tweak", that prose stays in place as augmentation but the authoritative
normative statement is now the clause line here. The DISPATCHER behaviors (surface manual-admission items resting at `pending-approval` for the human's `approve`; bounce on non-convergence; emit calibration telemetry) are NOT restated here to avoid a duplicate
gap-detectable line — their authoritative normative clauses live in
§"Dispatcher grooming behavior", and the periodic calibration analysis
pass (a non-Dispatcher behavior) plus the single Fabro DOT tweak remain
below.

The `capture-work-item` and `capture-impl-gaps` capture front-ends MUST run the intake Definition-of-Ready checklist over the six gates at capture and MUST route the resulting item into its lifecycle state accordingly — a single-coherent-done, autonomously-verifiable, autonomy-tiered, dependency-linked, repo-targeted, above-floor item lands in `pending-approval` (approved on into `ready` when its effective `admission_policy` is `auto`; an effective-`manual` item RESTS at `pending-approval` awaiting the human's explicit `approve` — the `pending-approval → ready` transition); an item with more than one coherent "done" (an epic) MUST land in `backlog` for decomposition; an item whose acceptance is not autonomously verifiable MUST land in `blocked` with `blocked_reason: needs-human`; an item with unresolved blockers is filed with its dependency edges linked (deriving the `blocked:dependency` lane) and MUST NOT land directly in `ready`.

Given a `backlog` item needing re-decomposition, the groom front-end MUST produce a READ-ONLY drafted decomposition (candidate slices pre-filled with acceptance / autonomy tier / dependency links / repo target / scope and arranged into dependency layers) and MUST file nothing until the maintainer approves; on approval it MUST file the approved slices via `capture-work-item` with dependency edges linked, and MUST route any spec-change slice to `/livespec:propose-change` rather than to the factory.

An item MUST enter `backlog` on an intake Definition-of-Ready epic failure and MUST enter `backlog` on a Dispatcher non-convergence bounce; groom approval MUST transition the `backlog` item out by filing slices that transit `pending-approval` (approved on into `ready` when a slice's effective `admission_policy` is `auto`; an effective-`manual` slice rests at `pending-approval` awaiting the human's explicit `approve`; the original item is regroomed-out, never silently dropped).

A periodic calibration analysis pass MUST correlate run outcomes against the recorded mechanical size proxies and MUST propose ceiling thresholds that remain advisory until a maintainer adopts them (it MUST NOT auto-enforce a threshold and MUST NOT run as an always-on service).

The single Fabro workflow-DOT tweak MUST stay within Fabro's existing DOT vocabulary — a fix-loop cap plus a "non-converged" exit edge that routes back to the Dispatcher (→ the `backlog` bounce), reusing Fabro's existing verify→fix-loop nodes and `max_node_visits` governor — and MUST NOT require any Fabro platform or setup change.

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
Orchestrator-Plane guidance (the Planning Lane guidance, beside the
Orchestrator-internal grooming guidance); core gains only the
guidance, never a skill, CLI, or doctor invariant. The Planning Lane —
the durable, multi-session *planning* work that decides what should
become spec, implementation, or research before any lane is committed to
— operates on this plugin's filesystem thread store and ledger, is
Orchestrator-internal, and is therefore NOT part of `livespec`'s
functional cross-boundary contract. The architectural frame (the three
planes and the two seams) is `livespec`'s `spec.md`; what this section
adds is the realization: the
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
thread MAY be research-only. A root `research/` tree MUST NOT exist.
Standalone analysis MUST live in a plan thread (or, once the thread
closes, under `plan/archive/<topic>/`); a living reference document
MUST live in `docs/`, `.ai/`, or a dedicated top-level topic
directory (precedent: `loop-reflection-gate/`).

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
else the gate fails. This realizes `livespec`'s Planning Lane
guidance on handoff self-sufficiency.

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
Conformance Pattern (livespec core `non-functional-requirements.md`,
four-tier enforcement-in-depth) for the
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
(the packaged `.fabro/workflows/implement-work-item/workflow.toml`,
shipped in the plugin payload and resolved via the plugin root per the
§"Self-contained plugin dispatch" contract); this section is the
normative contract that chain satisfies.


## Self-contained plugin dispatch

The Fabro `implement-work-item` workflow payload — `workflow.toml`, the
workflow graph, and its prompt files — ships INSIDE this plugin's
packaged payload (under `.claude-plugin/`), so the plugin installer
copies it under the plugin root in the flattened install cache. The
Dispatcher (`dispatcher.py`) MUST resolve that workflow via the PLUGIN
ROOT — the location that is identical in the source layout
(`.claude-plugin/`) and the flattened install cache
(`${CLAUDE_PLUGIN_ROOT}`) — NOT via the orchestrator repository root. The
explicit `--workflow <path>` override remains the escape hatch.

Because the workflow ships in the payload and resolves from the plugin
root, the factory dispatches from the ENABLED PLUGIN ALONE: no clone of
the orchestrator's own source is required at dispatch time. Fleet
members and adopters therefore consume the orchestrator IDENTICALLY —
enabling the plugin is the whole installation. The only repository
clones the dispatch path makes are of the dispatch TARGET repo (the work
site, cloned host-side and again inside the Fabro sandbox); the
orchestrator's own source is never a dispatch-time prerequisite.

The host-side Dispatcher MUST run on the packaged payload alone — the
Python standard library plus the vendored runtime under
`scripts/_vendor/` — with no dependency on an orchestrator working
checkout and no `pyproject.toml` / lockfile install step. Behaviors that
presuppose a writable orchestrator checkout or fleet context MUST degrade
to clean no-ops rather than failing the dispatch: the post-merge
self-update canary records an explicit skip when there is no writable
orchestrator checkout to promote, and the fleet-manifest sibling-clone
projection renders empty when no fleet manifest is present.

The factory's GitHub credential is likewise self-contained and
tenant-scoped (the github-app-auth design record, Pillars 1 and 2).
Every automated GitHub operation on the dispatch path — the
in-container fresh clones, the in-sandbox PR leg, the merge-poll, the
post-merge refresh — MUST authenticate with a GitHub App INSTALLATION
TOKEN minted from the App environment (`GITHUB_APP_ID` +
`GITHUB_PRIVATE_KEY`, optional `GITHUB_APP_INSTALLATION_ID` /
`GITHUB_API_URL`) that the dispatch TARGET's own configured
`credential_wrapper` injects; no dispatch path reads a fleet PAT (the
retired `LIVESPEC_FAMILY_GITHUB_TOKEN`). Resolution is FAIL-CLOSED:
when the App environment is absent and the target repo has no
`credential_wrapper` to re-exec through, the dispatch MUST refuse with
an actionable diagnostic — it MUST NOT fall through to a fleet
credential or an ambient `gh` login. The fleet is adopter #0: an
adopter's dispatch target injects its own App through its own wrapper
the same way, so neither preflight nor dispatch carries a fleet-secret
prerequisite.

Token acquisition MUST be re-mintable at any time (first-class remint):
the Dispatcher holds a caching installation-token provider that
re-mints before the roughly one-hour token expiry, and it MUST resolve
a currently-valid token for every subprocess it spawns — never a
once-at-start export — so operations that outlive a single token's
validity (for example a seventy-plus-minute merge-poll) survive
transparently. The sandbox environment table receives an EPHEMERAL
freshly-minted installation token; the durable App private key and any
long-lived personal access token MUST NOT be projected into the
sandbox.

**The dispatch credential set.** A dispatch TARGET's configured
`credential_wrapper` MUST inject the FULL per-dispatch credential set:
the GitHub App environment (`GITHUB_APP_ID` + `GITHUB_PRIVATE_KEY`,
optional `GITHUB_APP_INSTALLATION_ID`), the tenant work-items store
secret (`BEADS_DOLT_PASSWORD` on the beads substrate), AND the engine
LLM credential (`CLAUDE_CODE_OAUTH_TOKEN` today; the variable is
engine-specific by nature). Every credential-consuming seam on the
dispatch path MUST fail closed naming the specific missing variable,
and every such diagnostic MUST name the dispatch TARGET's own
configured `credential_wrapper` — never a fleet wrapper — as the
corrective injection path. The full required set is surfaced up front
(preflight and adopter docs), never discovered one failure at a time.
(Implementation tracked as `bd-ib-3m44nx` and `bd-ib-ls32yb`;
architecture record: the openbrain adopter dogfood, github-app-auth
`p3icf6`, 2026-07-03.)

**Per-tenant engine identity.** The Fabro server serving a dispatch
MUST hold the dispatch TARGET tenant's own GitHub App identity. A
server instance holds exactly ONE App integration — a structural fact
of the engine — so dispatching an adopter repo through the fleet's
shared server fails (the fleet App is not installed for the target);
adopter dispatch therefore runs against a per-tenant server instance
(e.g. a dedicated `FABRO_HOME` carrying the adopter's `app_id`, its
PEM in the server process environment, and its own port and
authentication). A dispatch preflight SHOULD verify the serving App
can reach the target repo BEFORE launching, refusing with an
actionable diagnostic rather than failing inside the engine run.
Workflow-file-touching pushes structurally require the App's
`workflows` read-write permission grant, which the factory sandbox's
credential MUST NOT hold (§"Factory sandbox credential constraints" in
`constraints.md`). The preflight and the adopter docs MUST therefore
surface that grant as one DELIBERATELY WITHHELD from the dispatch
credential, and MUST name the attended-host-session route for work
requiring it — never as an App-installation requirement to be granted.
(Implementation tracked as `bd-ib-z2ctra` and `bd-ib-w4iaaf`.)

**Target-local workflow.** An adopter MAY carry its own
`implement-work-item` workflow in the TARGET repo
(`<target>/.fabro/workflows/implement-work-item/`), supplied today via
the dispatcher's explicit `--workflow` override. Prepare steps are
TARGET-TOOLCHAIN facts, not fleet constants: the plugin-default
payload's prepare chain (uv / lefthook / `livespec_dev_tooling`) is
the FLEET toolchain realization, and a non-Python adopter's equivalent
steps are that adopter's own facts. Any future automatic target-local
resolution (the target's `.fabro/workflows/...` taking precedence over
the plugin payload) amends THIS section's plugin-root resolution rule
before it ships. (Implementation tracked as `bd-ib-z2ctra`.)

**Default-branch resolution.** Every dispatch-path stage that
references the target's primary branch — the post-merge janitor's
pull-primary refresh above all — MUST resolve the TARGET repo's
default branch (`git symbolic-ref refs/remotes/origin/HEAD`, or
`gh repo view --json defaultBranchRef`) and MUST NOT hardcode
`master`; adopter repos commonly default to `main`. This is the same
resolution the `canonical_branch` key documents (§"`compat` block");
the dispatch path reuses that single resolution rather than carrying
its own ref constant. (Implementation tracked as `bd-ib-hkzcfb`.)


## Work-item state semantics

What each of the seven lifecycle states MEANS, in plain English. These
definitions are ratified semantics: every transition contract in this
specification (§"Dispatcher admission, WIP cap, and post-merge
acceptance", §"The four maintainer touchpoints", the scenarios) is
subordinate to them. Design record: repo `thewoolleyman/livespec`,
`plan/archive/work-item-state-machine/research/03-decision-log.md`
(decisions 26 and 32), with the maintainer's verbatim reasoning in
`plan/archive/work-item-state-machine/conversation/transcript.md`.

- `backlog` — captured but not yet groomed: the item needs
  decomposition or grooming before it can be worked.
- `pending-approval` — prepared (groomed) but not yet authorized to
  start — the lane that shows the maintainer exactly what waits on
  their GO.
- `ready` — authorized to start (a human approved it, or the item's
  `admission_policy: auto` delegation did), pulled into work when a
  WIP slot frees. An item awaiting a human's permission MUST NOT be
  in `ready`.
- `active` — admitted into a WIP slot and being worked.
- `acceptance` — merged, live, and observable, awaiting post-ship
  confirmation per its effective `acceptance_policy`.
- `blocked` — cannot proceed without something outside the factory
  (`blocked_reason: needs-human` or `infra-external`). This is a
  TRANSIENT lifecycle state — the item rests in `blocked` because
  something outside the factory is *currently* preventing progress, and
  it clears when that external thing resolves. It is a DIFFERENT axis
  from `factory_safety` (§"Work-item beads-issue mapping"), an INTRINSIC
  capture-time classification of the work ITSELF: a non-null
  `factory_safety` item is permanently host-only regardless of external
  state — `ready`/dispatchable-in-principle but routed to a host actor
  rather than an agent sandbox — and it never "clears".
- `done` — accepted and closed.

**`approve` IS the `pending-approval → ready` transition** ("manual: a
human; auto: automatic"). Being in `ready` MEANS approved-to-start
(approval ≡ `ready` membership). The admission valve (`ready →
active`) is mechanical — dependencies clear, a free WIP slot,
an assignee resolvable, and `factory_safety` null (a non-null value is
refused at admission and host-routed); permission was settled upstream at
`approve`.
`admission_policy` is the delegation dial on the `approve` routing
ONLY: the human always holds the ultimate decision but MAY delegate
the GO per item or blanket for low-risk work — that delegation IS
`admission_policy` (`auto` = the GO is delegated; `manual` = the human
gives it explicitly).

The maintainer's rationale, verbatim (source: repo
`thewoolleyman/livespec`,
`plan/archive/work-item-state-machine/conversation/transcript.md`):
"If we don't respect the groomed attribute and add autonomous
execution, then the factory can just go wild and go completely off
track and never stop, Piling up a bunch of incorrect work that should
have never been performed at the review gates, or even worse if the
review gate is automated, pushing it all to production." (The quote is
byte-exact to the transcript, including the mid-sentence capital
"Piling".)

### Intent preservation

- Every load-bearing semantic definition in this specification MUST
  carry its rationale and MUST cite its design record (repo-qualified
  location plus decision identifiers when they exist).
- When ratified statements of this specification are found to
  conflict (by critique, doctor, or any revise pass), the cited
  design record — the recorded maintainer intent — is the tiebreaker.
  Consistency with the shipped implementation is NEVER the tiebreaker.
- If no design record is cited or reachable for the conflicting
  statements, that absence is itself a finding that MUST be surfaced
  to the maintainer; it MUST NOT be self-resolved.


## Dispatcher loop invocation surface

The Dispatcher's `loop` subcommand is the factory's drain entry point. Its
governed CLI surface is:

`loop --repo <path> --budget <count> [--parallel <count>] [--item <work-item-id>]... [--dry-run] [--json]`

- **This grammar is NOT exhaustive of the flags `loop` accepts.** It names
  the flags this contract GOVERNS — those that determine WHAT the run
  selects, how far it goes, and how it reports. `loop` additionally carries
  OPERATIONAL flags that tune HOW a dispatch executes rather than what it
  selects (the workflow file, the Fabro binary, the janitor ref, the journal
  path, the PR-merge poll bounds, close-on-merge, and the ledger pre-check).
  Those are IMPLEMENTATION SURFACE: this section neither enumerates nor
  freezes them, and their presence is NOT a spec→impl gap.
- **No run-mode flag.** The surface carries NO run-mode argument: there is no
  arming flag and no scope-selecting mode. The Dispatcher's dispositions are
  governed by the `dispatcher.*` policy settings (§"Dispatcher policy
  settings"), which it reads from `.livespec.jsonc` itself — never by a
  per-run mode argument. This is the same rule §"Dispatcher policy settings"
  already imposes on the console's factory-drain launcher (which "invokes the
  Dispatcher `loop` with NO per-run policy flag").
- **Default selection (no `--item`): drain the ranked queue.** With no
  `--item`, `loop` MUST select dispatch-eligible items from the ranked queue
  — the same single ranking authority the `next` surface advertises, so the
  drain order never diverges from what `next` reports (§"Work-item
  beads-issue mapping") — and dispatch them, subject to `--dry-run` below
  (which plans the identical selection but dispatches nothing). This
  unattended drain is the factory's steady-state path; it is what the
  console's factory-drain launcher invokes.
- **`--budget <count>` (REQUIRED) bounds one invocation.** The Dispatcher
  MUST dispatch at most `budget` items in a single `loop` run. It is a
  per-run ceiling on how many items the run takes on, NOT a concurrency
  limit.
- **`--parallel <count>` (default `1`) bounds concurrency within the
  invocation.** It MUST NOT raise the per-repo WIP cap: the drain stays
  bounded by `wip_cap` (§"Per-repo WIP cap"), which remains the authority on
  how many items may be `active` at once.
- **`--item <work-item-id>` (repeatable) scopes the run to hand-picked
  items.** One or more `--item` flags RESTRICT the selection to exactly the
  named work-items. `--item` NARROWS the ranked selection; it never bypasses
  it — a named item that is not dispatch-eligible (dependencies unclear, no
  resolvable assignee, no free WIP slot, resting at `pending-approval`
  under an effective `admission_policy` of `manual`, or carrying a non-null
  `factory_safety`) MUST NOT be dispatched,
  exactly as if it were not named (§"Dispatcher admission, WIP cap, and
  post-merge acceptance"). The presence of `--item` is ALSO the contract's
  marker that a human hand-picked the dispatch and is present — the
  fail-closed cost gate below keys on it. This is the path the `drive`
  `impl:<work-item-id>` action invokes (§"The skill surface").
- **`--dry-run`: plan the selection, dispatch nothing.** `--dry-run` MUST
  compute and report exactly the selection the same invocation would dispatch
  — honoring `--budget`, the WIP cap, and any `--item` scoping — and MUST NOT
  launch a Fabro run, MUST NOT mutate the ledger, and MUST NOT write the
  work-item store. It is READ-ONLY with respect to the work-item store: the
  "what would this drain do?" surface. (Journaling the planned selection is
  permitted — the journal is an append-only audit record, not the work-item
  store.) Because a `--dry-run` invocation launches no run, it produces no
  per-run cost signal and therefore no cost-gate verdict (below).

The Dispatcher's guarded recovery surface for an already-merged item is
`reconcile-merged --repo <path> --item <work-item-id> [--json]` and, only after
an operator has confirmed the original dispatcher process is dead,
`reconcile-merged --repo <path> --item <work-item-id> --force [--json]`. It MUST
refuse unless the named item is currently `active`, because this valve exists
only for a dispatch whose merged PR did not complete post-run disposition.
Before resolving the PR or provisioning any janitor checkout, the valve MUST
read the dispatch heartbeat for the work-item id and refuse by default when a
recent heartbeat indicates a still-live dispatch. That refusal is load-bearing:
a live dispatch can legitimately be `active` with a merged PR while its
one-hour post-merge janitor window is still running, and a second janitor would
otherwise target the same deterministic checkout. The refusal message MUST tell
the operator to confirm liveness with `fabro ps`, wait for the janitor window to
close, or use `--force` only after confirming the original dispatcher process is
dead. `--force` bypasses only the heartbeat refusal; it MUST NOT bypass source
lane checks, merged-PR resolution, post-merge janitor execution, or acceptance
journaling. The shared post-merge janitor path MUST also hold a per-work-item
janitor checkout lock before precleaning or provisioning, so concurrent normal
and reconcile janitors for the same item cannot remove each other's checkout or
run duplicate completion.

The valve MUST resolve the PR number and merge SHA from GitHub, by the expected
`feat/<work-item-id>` branch or a merged PR title/search match carrying the
work-item id, and MUST NOT require or trust ledger audit metadata for that
resolution. After a merged PR resolves, the valve MUST NOT launch Fabro and
MUST NOT rebuild the change; it reruns the same post-merge janitor used by the
dispatch engine against a fresh checkout of the merged ref. A green janitor
MUST enter the existing post-merge acceptance path unchanged, including the
`active -> acceptance` ledger-complete write, acceptance journal records, and
policy-governed `acceptance -> done` auto-accept when applicable. A red janitor,
missing merged PR, wrong source lane, or held janitor checkout lock MUST leave
the item `active` and report the failed guarded precondition or janitor stage.
This is a distinct guarded entry path and does not widen the `drive move` target
set; `acceptance`, `done`, and `pending-approval` remain forbidden `move`
targets.

### Fail-closed cost gate (keyed on `--item` presence)

- **Gate coverage — which runs are gated at all.** The Dispatcher observes a
  per-run cost signal ONLY for a dispatched run that BOTH reached a
  successful terminal outcome AND carries a confirmed run record (a run id
  resolvable against the cost source). Two classes of run are therefore NOT
  gated:
  - A run that did NOT reach a successful terminal outcome yields no cost
    observation and no gate verdict — even though such a run MAY have
    consumed spend.
  - A run whose id CANNOT be resolved against the cost source MUST be
    journaled as a **skipped** gate record naming the work-item and the
    unresolvable-run-id reason, and MUST NOT refuse. This disposition is
    **FAIL-OPEN** — deliberately, and it stays fail-open even under the
    `enforce` posture with no `--item`.
- **Verdict keying.** For a GATED run whose cost signal is **UNOBSERVABLE**
  (no cost is readable for the run), the verdict is keyed on **whether the
  invocation named an `--item`** — the contract's proxy for whether a human
  is present:
  - **No `--item` — an unattended queue drain, no human present.** An
    unobservable cost is a **fail-closed REFUSAL**: the Dispatcher MUST stop
    picking rather than keep dispatching cost-blind.
  - **One or more `--item` — a hand-picked dispatch, a human present.** The
    same condition is a **WARNING**, never a refusal.
- **An OBSERVED cost never trips this gate.** Cost-VALUE enforcement (per-run
  and per-session spend ceilings) is a separate concern; this gate fires only
  on the unobservable condition.
- **Journaling.** Every GATED run MUST produce a gate record on the existing
  Dispatcher journal, carrying at minimum the work-item id, the run id,
  whether the cost was observable, the severity, and whether the run refused;
  an unresolvable run id MUST produce the skipped record above. No gated run
  goes unrecorded.
- **Enforcement posture (the always-wired severity lever).** Whether a keyed
  verdict is DERIVED and APPLIED is governed by the `LIVESPEC_COST_MODE`
  environment variable, whose only recognized values are `report` and
  `enforce`. In `report` (the **DEFAULT** — the subscription-billing posture,
  under which provider-side spend limits already bound spend, so a
  fail-closed dollar gate is the wrong model) a gate record MUST still be
  journaled, carrying the observability of the cost signal — but NO keyed
  verdict is derived and none is applied: the record's severity is `report`,
  and the Dispatcher MUST NOT refuse and MUST NOT apply a cost cap. In
  `enforce` (the opt-in posture for metered API billing) the keyed verdict
  above MUST be derived and the fail-closed refusal MUST be applied. An unset
  or unrecognized value MUST resolve to `report`. The lever is a SEVERITY
  switch, not a wiring carve-out — the cost signal is still observed and a
  gate record is still journaled regardless of its value. (This is the same
  always-wired-lever shape §"Closed-item-integrity check" uses for
  `LIVESPEC_CLOSED_ITEM_INTEGRITY`.)

## Dispatcher admission, WIP cap, and post-merge acceptance

Two human-delegable policy gates bracket the WIP-limited machine-driven
middle of the lifecycle — **`approve`** (`pending-approval → ready`) and
**`accept`** (`acceptance → done`). The **Dispatcher (`dispatcher.py`
`dispatch`/`loop`) is the sole enforcer** of the mechanical admission
valve (`ready → active`), the WIP cap, and the acceptance valve; the
console only commands (a human triggers `approve` for a manual item
resting at `pending-approval`, through the `drive` human-valve
actions) and observes — it never enforces. This realizes the
repo-agnostic two-valve pattern for the Beads/Fabro Dispatcher; the state machine + the valve semantics are the cross-repo design of record (repo `thewoolleyman/livespec`, `plan/archive/work-item-state-machine/research/03-decision-log.md`, decisions 26/32).

### Admission valve (`ready → active`)

By the time an item is `ready` it is, by definition, already approved
(approval ≡ `ready` membership — entering `ready` IS approving; see
§"Work-item state semantics"). So the valve's remaining conditions are
mechanical — capacity, dependencies, a resolvable assignee, and factory-safety:

- **Permission** was settled upstream at the `pending-approval → ready`
  (`approve`) transition, governed by the item's effective
  `admission_policy` (`item.admission_policy`, with `None` inheriting the
  global `dispatcher.auto_approve_ready` default, §"Dispatcher policy
  settings"): `auto` auto-approves into `ready` — at capture/groom time, or on
  a subsequent Dispatcher pass for an item resting at `pending-approval`;
  `manual` (whether stored on the item or inherited from a `false` global
  `auto_approve_ready`) rests at `pending-approval` until a human's explicit
  `approve`. The
  `admission_policy` field is the first-class realization that
  **replaces the prior `human-gated` text marker** — risky / irreversible
  work is held at the `approve` gate (resting at `pending-approval`), never
  by a pre-merge acceptance gate. It does NOT carry the prior `host-only`
  marker's role: `admission_policy` gates PERMISSION (does a human
  approve?), which is ORTHOGONAL to RUNNABILITY (can an agent sandbox run
  this work at all?). Runnability is the separate `factory_safety` axis
  (§"Work-item beads-issue mapping"), enforced at this same valve (below).
  The
  Dispatcher MUST NOT hold an item at `ready` awaiting a human — an item
  awaiting a human's permission MUST NOT be in `ready`.
- **Capacity:** a free WIP slot under the per-repo cap
  (`count(active) < wip_cap`).
- **Assignee resolvable:** an item whose assignee cannot be resolved is
  not admitted.
- **Factory-safe:** an item whose `factory_safety` is non-null names work
  that cannot run in an agent sandbox. The Dispatcher MUST refuse to admit
  it — BEFORE launching any sandbox run — and MUST surface an actionable
  host-route refusal naming the reason, rather than dispatching it and
  failing deep in the sandbox. The item is NOT marked `blocked` (its
  runnability is intrinsic, not a transient external block); it is surfaced
  for host routing via the needs-attention awareness surface for a host
  actor to run. That host actor is an attended host SESSION performing the
  work automatically, not the maintainer performing it by hand; a refusal
  MUST NOT be surfaced in a form that presents hand-editing as the intended
  resolution. The Dispatcher MUST NOT retry it into a sandbox.

The Dispatcher MUST, when a WIP slot frees, admit the **top-ranked**
(lexicographically earliest `rank`, per §"Work-item beads-issue
mapping") admission-eligible `ready` item (eligible = dependencies clear
AND an assignee is resolvable AND `factory_safety` is null —
`admission_policy` plays no part at this valve), set its `assignee` (the reused field, not a new `owner`), and
transition it to `active`. The Dispatcher MUST NOT auto-approve
(`pending-approval → ready`) an item whose effective `admission_policy`
is `manual`; it MUST surface the resting item for the maintainer's
explicit `approve` on every pass (independent of capacity).

### Per-repo WIP cap

The WIP cap is **per-repo**, sourced from this repo's `.livespec.jsonc`
(the `livespec-orchestrator-beads-fabro.dispatcher.wip_cap` key), default
**5** — NOT a single fleet-wide number. Total fleet concurrency is the
sum of the per-repo caps; a separate fleet ceiling is a later knob if
ever wanted. The Dispatcher MUST NOT drive more than `wip_cap` items into
the `active` state at once.

### Post-merge acceptance (`acceptance → done`)

Acceptance is **post-merge / in-production** (observability + reversibility).
The deterministic `just check` stays the HARD **pre-merge** floor (the
in-sandbox janitor gate, which already executes the suite); acceptance
verifies *fit + real behavior* against the **shipped** artifact:

- **`complete` (`active → acceptance`)** MUST **merge-on-green**: the
  Fabro impl run keeps today's `gh pr merge --rebase --auto`; entering
  `acceptance` means the change is **merged + live + observable** (OTel →
  Honeycomb; the OOB reflector reads `GROUP BY work.item.id`). The item
  transitions to the observable `acceptance` state instead of straight to
  `done`.
- **`accept` (`acceptance → done`)** is a **post-ship confirmation**
  against tests + telemetry, governed by the item's effective
  `acceptance_policy` — the item's own `acceptance_policy` label when it
  carries one, otherwise the global `dispatcher.acceptance_mode` default
  (§"Dispatcher policy settings"). The **AI acceptance pass** is a
  **read-and-judge of the merged diff against the item's acceptance criteria,
  plus a telemetry watch, yielding a PASS or FAIL verdict** — never a rubber
  stamp:
  - `ai-only` — a PASSING AI pass confirms and accepts the item to `done`
    autonomously.
  - `human-only` — a human accepts from the console (via the
    `drive` `accept:<id>` valve action). The AI pass still runs, but it is
    ADVISORY.
  - `ai-then-human` (the default) — on a PASSING AI pass the AI's findings
    are surfaced and the item **parks in `acceptance` on the ledger**
    (cheap, durable) until a human gives final acceptance from the
    console (the same `accept:<id>` valve action).

  There MUST be no "release with zero verification" — every acceptance
  carries at least one AI pass.
- **A FAILING AI acceptance pass under an AI-dispositive policy.** For an item
  whose effective `acceptance_policy` is `ai-only` or `ai-then-human`, a FAIL
  routes the item back to `active` for **fix-forward rework automatically — no
  human is consulted for a fail** — mirroring `reject (rework)`, but
  AI-initiated. Repeated failure on one item is bounded by
  `dispatcher.acceptance_rework_cap` (§"Dispatcher policy settings"): an item
  that exceeds the cap **escalates to `blocked` / `blocked_reason:
  needs-human`** rather than reworking again. The human `reject` valve is
  retained for human-judgment rejects.
- **A FAILING AI acceptance pass under `human-only`.** Under `human-only` the
  AI acceptance pass is **ADVISORY — it INFORMS, it never DECIDES**. On a FAIL
  it MUST NOT auto-rework the item and MUST NOT dispose of the item in any
  way: the failure is surfaced as an advisory **finding**, and the item
  **stays PARKED in `acceptance`** for the human, who accepts, or uses the
  existing `reject (rework)` / `reject (re-groom)` valve if they concur. An
  auto-rework IS the AI deciding, which is precisely what `human-only`
  reserves to the human; auto-reworking here would let the machine repeatedly
  bounce an item the human explicitly claimed, stripping their
  accept-vs-reject call. The pass still RUNS — it is what satisfies the "no
  release with zero verification" floor for this policy — because `human-only`
  means "no AI DECIDES this", NOT "no AI READS this". (Maintainer-declared
  2026-07-14.)
- **`reject` from `acceptance`** carries a corrective side-effect because
  the change is already live: `reject (rework) → active` is
  **fix-forward** (patch on top of the live change); `reject (re-groom) →
  backlog` is **revert the merged change + re-decompose**.

There is exactly ONE merge model (ship-on-green); the risk dial sits at **the `approve` gate + reversibility**, not a pre-merge acceptance hold. The AI
acceptance pass (the telemetry-reading reflector + a diff/criteria judge
against the merged ref) is an orchestrator-internal realization; it
defaults to read-and-judge + watch telemetry and is upgraded to a
sandboxed exploratory-execution pass only if a bug class is shown to slip
through.

### Consent boundary

These `admit` / `complete` / `accept` / `reject` writes are machine-path
dispositions of already-filed items and are EXEMPT from the
per-operation consent discipline by design (see §"Machine-path exemption
— the Dispatcher"). The Dispatcher MUST NOT create net-new work-items on
its own initiative.

The admission-valve, WIP-cap, and post-merge-acceptance behaviors are
exercised by `scenarios.md` (the WIP-capped top-ranked admission, the manual rest-at-`pending-approval`, the complete-merges-on-green, and the
accept-per-policy scenarios).


## Dispatcher policy settings

The Dispatcher's routine dispositions are governed by orchestrator-wide
`dispatcher.*` policy settings in the consumer project's `.livespec.jsonc`
(siblings of the existing `dispatcher.wip_cap` and `dispatcher.fabro_bin`
keys). Each setting is a **global default**; a **per-item ledger label
overrides the global default for that one work-item** — the per-item label
WINS over the global, and an item that carries no such label inherits the
global. The settings are **independent**: no setting implies another, and
there is no master switch. This section composes — never contradicts —
§"Admission valve (`ready → active`)", §"Post-merge acceptance (`acceptance →
done`)", §"Dispatcher grooming behavior", and §"Store-write consent
discipline".

The rationale is granular, orthogonal operator control: the operator can
delegate routine admission while keeping human acceptance (or the reverse),
each setting carrying its own risk, and every safety floor below holds under
every setting independently. Design record: repo `thewoolleyman/livespec`,
`plan/archive/autonomous-mode/handoff.md`, the "SESSION UPDATE — 2026-07-14 (cont. 12)" section
(THE RE-LOCKED DESIGN), together with its "CORRECTION / ADDENDUM" section, which
records the maintainer's ruling that every setting is per-item overridable
EXCEPT `wip_cap`.

### The three policy settings

Each is a global default with a per-item label override, and each defaults to
its SAFE value:

- **`dispatcher.auto_approve_ready`** (boolean, default **`false`**) — the
  global default for an item's effective `admission_policy` when the item
  carries no explicit `admission_policy` label: `true` ⇒ `auto` (auto-approve
  `pending-approval → ready` without a human); `false` ⇒ `manual` (rest at
  `pending-approval` for the human's explicit `approve`). Per-item override:
  the existing `admission_policy` label — a stored `manual` label holds the
  item at `pending-approval` even when the global is `true`. The Dispatcher
  MUST NOT auto-approve a **design-human-gated (spec-change-tier) item**
  regardless of this setting or of any label (§"Grooming and slice-size
  calibration"; `spec.md` §"Terminology"); such an item stays escalated.
- **`dispatcher.acceptance_mode`** (enum `ai-only` | `ai-then-human` |
  `human-only`, default **`ai-then-human`**) — the global default for an
  item's effective `acceptance_policy` (§"Post-merge acceptance (`acceptance →
  done`)"). Per-item override: the existing `acceptance_policy` label.
- **`dispatcher.merge_on_review_cap`** (boolean, default **`false`**) — the
  global default for the in-factory review gate's past-cap behavior: `true` ⇒
  ship the PR anyway (the escape hatch for a misbehaving reviewer); `false` ⇒
  **escalate the item to `blocked` / `blocked_reason: needs-human`** — a
  terminal state that is NOT eligible for auto-approve, so it cannot loop.
  Per-item override: a per-item merge-on-review-cap label. The design record
  for the blocking default is the maintainer's verbatim rationale in
  §"Work-item state semantics" ("…or even worse if the review gate is
  automated, pushing it all to production").

### The two rework caps

Each is a global default with a per-item label override, and each bounds one
of the two INDEPENDENT rework loops:

- **`dispatcher.review_fix_cap`** (integer, default **`3`**) — the INNER,
  pre-merge review fix-round budget. At the cap, a still-blocking review is
  disposed by the item's effective `merge_on_review_cap`.
- **`dispatcher.acceptance_rework_cap`** (integer, default **`2`**) — the
  OUTER, post-merge budget: how many times a single item's FAILED AI
  acceptance pass MAY route back to rework before the item **escalates to
  `blocked` / `blocked_reason: needs-human`** instead of reworking again. This
  is the bound that prevents an unbounded post-merge rework loop.

### `wip_cap` — the one setting with no per-item override

`dispatcher.wip_cap` (existing, default `5`, §"Per-repo WIP cap") is likewise
an API-settable setting, surfaced under the console Settings surface. It is
the ONE setting with **no per-item override**: it is a per-repo concurrency
ceiling, so a per-item value is structurally meaningless. Its value semantics
are unchanged. Design record: repo `thewoolleyman/livespec`,
`plan/archive/autonomous-mode/handoff.md`, the "SESSION UPDATE — 2026-07-14 (cont. 12)"
section, together with its "CORRECTION / ADDENDUM" section (`wip_cap` is NOT
per-item overridable).

### Every needs-human escalation still reaches a human

No policy setting MAY auto-dispose a **truly-unresolvable decision** (`spec.md`
§"Terminology"). The Dispatcher MUST NOT auto-resolve a `blocked_reason:
needs-human` item; it MUST surface every such item to a human. A decision that
is human-gated BY DESIGN — drift acceptance, a spec-change slice, a regroom /
backlog bounce, or a `human-only` acceptance — MUST stay escalated even when
the Dispatcher is fully confident. The "no release with zero verification"
floor of §"Post-merge acceptance (`acceptance → done`)" MUST hold under every
setting: every acceptance carries at least one AI pass. The Dispatcher MUST
NOT create net-new work-items when applying a setting — every setting-driven
write is a disposition of an already-filed item (§"Machine-path exemption —
the Dispatcher").

### Control surface and audit

Every setting MUST be settable via the orchestrator API and, through it, the
Control-Plane console. The orchestrator OWNS the setting state — the
`.livespec.jsonc` keys and the per-item ledger labels; the console only
commands and observes, and holds no setting state of its own.

Every auto-disposition a setting enables — an auto-approve, an AI auto-accept,
an AI-fail auto-rework, a ship-on-cap, a cap-exceeded escalation — MUST be
journaled on the existing Dispatcher journal (the same journal → Honeycomb leg
used for calibration telemetry), carrying at minimum the work-item id, WHICH
setting governed the disposition, and the disposition itself. No
auto-disposition MAY be silent. That journal is this plugin's PUBLISHED
per-decision audit surface: the console reads each auto-disposition and each
escalation from it (through this plane's published read surface) and surfaces
the escalations as in-console needs-attention rather than re-deriving them.

Three console surfaces follow from this ownership split, and the console MUST
carry all three:

1. **Per-setting write commands.** The console writes each setting through the
   orchestrator API's per-setting write surface, exposed as a Settings row.
   There is no single arming command that flips several settings at once.
2. **The factory-drain launcher argv.** The console's factory-drain path
   invokes the Dispatcher `loop` with NO per-run policy flag: the Dispatcher
   reads the `dispatcher.*` settings from `.livespec.jsonc` itself. The
   launcher MUST NOT pass a policy-arming argument — the Dispatcher's argument
   parser recognizes none, and an unrecognized argument fails the run.
3. **Ordinary recorded Settings writes.** Enabling an individual dangerous
   setting is an ordinary Settings write, recorded like any other; it carries
   no type-the-repo-name arming ceremony.

### API-configurable completeness

Anything configurable via the orchestrator API MUST appear, in lockstep, in
THREE places: (1) a row under the console **Settings** surface, (2) the TUI
**inline / context help**, and (3) the **settings doc** (Markdown in the app's
repo docs). A **mechanical completeness check** MUST fail if an
API-configurable key is missing from the Settings surface or from the settings
doc. Per the No-Circular-Dependency Directive that check lives on the CONSUMER
side (the console), reading the orchestrator's declared API-configurable-key
surface; the orchestrator MUST NOT read into the console.


## Dispatch-brief lessons injection

This section codifies the consumer half of the reflection gate's
human-ratified lessons loop (design-of-record:
`loop-reflection-gate/lessons.md` §"Ratification model — proposal →
PR → merge" and `loop-reflection-gate/best-practices-and-design.md`
§7 question 10; the proposer half is the reflector's `LessonsProposer`
seam). Ratification is a HUMAN act: the reflector proposes a lesson by
opening a PR that edits `loop-reflection-gate/lessons.md`, and a lesson
is ratified if and only if a human merges that PR. No autonomous path
MAY ratify a lesson.

- The Dispatcher's dispatch-brief composition MUST source lessons
  EXCLUSIVELY from the committed content of
  `loop-reflection-gate/lessons.md` as present in the working tree it
  dispatches from — the merged, human-ratified file.
- When that file carries at least one ratified lesson, every
  subsequently composed dispatch brief MUST include the ratified lesson
  text, carried in a clearly delimited lessons section of the brief.
- When the file is absent, or present but carrying NO ratified lessons
  (for example only its header and placeholder), brief composition MUST
  leave the brief unchanged: no lessons heading, placeholder text, or
  file boilerplate may bleed into the brief.
- A lessons file that cannot be read or parsed MUST be treated as
  absent (briefs unchanged). Lessons injection MUST NOT block, fail, or
  alter the disposition of any dispatch (fail-open), matching the
  reflection gate's stability posture that reflection never changes a
  dispatch verdict.
- Content proposed on an unmerged reflector PR — or any other
  uncommitted edit to the lessons file — MUST NOT influence brief
  composition.


## Beads connection model

The plugin reaches its tenant DB exclusively through the pinned `bd`
CLI in server mode with a FLAGS connection. This model is the verified
v1.0.5 surface; this section is the authoritative record of the
contract-level commitments (the original derivation research was
retired in livespec core's research consolidation):

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
the AUTHORITATIVE contract-level field map (originally derived in
livespec core's since-retired beads-schema-mapping research; this
section now stands alone). The logical work-item field set tracks the shared
`livespec_runtime.work_items.types.WorkItem` (the 7-state `status`,
required non-null `rank`, the `admission_policy`/`acceptance_policy`/
`blocked_reason` policy fields, the `factory_safety` runnability field,
reused `assignee`; `priority` dropped);
only the on-substrate home of each field differs. The materialized
work-item the skills read back carries the SAME logical fields the
plaintext sibling exposes, so cross-boundary consumers (doctor, the
ranker, the console) see a consistent shape.

> **Invariants (doctor-checkable; restated for the consumer):**
> `active ⟹ assignee` set; stored `blocked ⟹ blocked_reason ∈
> {needs-human, infra-external}`; reaching `ready` requires transiting `pending-approval` (the
> structural grooming gate); `admission_policy` governs only
> the `approve` routing (auto vs. human); the admission valve
> checks capacity, dependencies, assignee, and factory-safety; every live
> (head) issue has a real, non-sentinel `rank`. These are enforced by this
> plugin's `doctor` (the mapping prose only states the contract).

Logical field → beads home:

- `id` — beads issue `id`, supplied explicitly at `bd create --id` time.
  Format `<prefix>-<6-char-base32-suffix>` where `prefix` is the tenant's
  decoupled issue-prefix (bd's server-stored create-prefix, e.g.
  `bd-ib`), NOT the tenant DB name. The legacy `li-`-style random suffix
  is preserved as the beads suffix so cross-references survive.
- `type` — beads `issue_type`. Identity for `bug` / `feature` / `task` /
  `chore` / `epic`.
- `status` — the seven livespec lifecycle states
  (`backlog` · `pending-approval` · `ready` · `active` · `acceptance` ·
  `blocked` · `done`) map to beads as **5 custom statuses + 2 built-in
  reuses** (verified against the pinned beads v1.0.5 source):

  | livespec state | beads status | kind | category |
  |---|---|---|---|
  | `backlog` | `backlog` | custom | unspecified |
  | `pending-approval` | `pending-approval` | custom | unspecified |
  | `ready` | `ready` | custom | **active** |
  | `active` | `active` | custom | wip |
  | `acceptance` | `acceptance` | custom | wip |
  | `blocked` | `blocked` | built-in reuse (name already matches) | wip |
  | `done` | `closed` | built-in reuse (native closure: `closed_at`, `bd close`, done-hiding) | done |

  Only **`done` ↔ `closed`** needs an adapter name-mapping — the one
  place a livespec term differs from its beads term (exactly where
  backend terms are allowed to live). `ready` is the only `active`-category
  status, so native `bd ready` surfaces exactly the admission-eligible
  set (defense in depth — livespec computes real readiness in Python
  regardless). The legacy enum
  (`open`/`in_progress`/`blocked`/`closed`/`deferred`) is superseded by
  this 7-state encoding.

  Two realization consequences follow from the beads surface:

  - **Custom-status registration (per-tenant bootstrap).** A tenant MUST
    register the 5 custom statuses via
    `bd config set status.custom "backlog,pending-approval,ready:active,active:wip,acceptance:wip"`
    before any item can carry one. This is a per-tenant provisioning
    step performed at bootstrap.
  - **2-step `append_work_item`.** Because `bd create` forces an
    `open`/`deferred` initial status (it cannot create directly into a
    custom status), every initial-state write is a **2-step path**:
    `bd create` (lands `open`), then `bd update --status <state>` — even
    a plain `file`, since `backlog` is itself a custom status. The
    closure path stays the in-place `bd close` mapping livespec `done`
    onto beads `closed`.
- `title` — beads `title`. Identity.
- `description` — beads `description`. Identity.
- `rank` — beads `metadata.rank` (a structured value carried in the
  metadata JSON column, like `audit`). `rank` is the **sole ordering
  authority** — a strictly-required, non-null fractional/lexicographic
  `str`. Rank sorts ASCENDING: the lexicographically earliest key is
  the most urgent, and "top-ranked" throughout this spec means exactly
  that earliest key. A legacy beads issue whose `metadata` lacks `rank`
  reads back through the shared bottom-sentinel
  (`livespec_runtime.work_items.rank.BOTTOM_SENTINEL`) the store adapter
  substitutes, so it sorts strictly after every real key WITHOUT making
  the domain type nullable.
- `priority` — **REMOVED as a logical field** (`rank` is the sole order;
  two order sources would be two conflicting truths). A legacy beads
  issue keeps its native `priority` column harmlessly; the materialized
  work-item no longer reads it. The one-time L2 backfill seeds `rank`
  from the legacy `priority → captured_at → id` order.
- `assignee` — beads `assignee` (first-class field). Identity when
  present; absent when null. Reused in place as the claimed-by/owner
  field (beads has no native `owner`); the Dispatcher sets it on `admit`.
  **REQUIRED once `status == active`** (the `active ⟹ assignee`
  invariant).
- `admission_policy` — beads label `admission:<auto|manual>`;
  `acceptance_policy` — beads label `acceptance:<ai-only|human-only|ai-then-human>`;
  `blocked_reason` — beads label `blocked-reason:<needs-human|infra-external>`
  (the STORED reasons only; the third reason `dependency` is DERIVED and
  NEVER stored — it surfaces only as a rendered lane reason). An absent
  policy/reason label reads back `None` (inherit / the system safe
  default — the blessed optional-on-read pattern).
- `factory_safety` — beads label
  `factory-safety:<needs-host-secrets|mutates-host-machinery|needs-privileged-host>`.
  An absent label reads back `None`, meaning FACTORY-SAFE — the fleet is
  factory-safe BY DEFAULT and only an explicit reason opts out. The three
  reasons name work that genuinely cannot run in a sandbox executing
  agent-written code: `needs-host-secrets` (verification requires real
  secrets that must never enter such a sandbox), `mutates-host-machinery`
  (changes the live host substrate the factory itself runs on — systemd
  timers, credential wrappers, the plugin cache, Fabro servers, and
  executable CI configuration under `.github/workflows/`, which runs on
  the fleet's self-hosted runners), and
  `needs-privileged-host` (privileged provisioning — a Dolt server, a
  1Password environment, a per-tenant Fabro server). The sharp line:
  writing CODE for any of these (including the Dispatcher's own code) is
  factory-safe; APPLYING host state is host-only. Executable configuration
  that RUNS ON the host substrate is APPLYING host state, not writing code,
  however code-like its file format: editing `.github/workflows/` is
  host-only under this line, because the fleet's runners are self-hosted
  and those files are the factory's own gates.
- `origin` (`gap-tied` / `freeform`) — beads label `origin:<value>`.
- `gap_id` — beads label `gap-id:<id>`. Present iff `origin == gap-tied`;
  REQUIRED non-empty when present, absent when `origin == freeform`. The
  gap-id ↔ label exactly-once invariant is honored as exactly one
  `gap-id:` label per gap-tied issue.
- `status`/`assignee`/etc. unchanged on read — materialization parses
  the `bd` JSON (`status` mapped back through the `done`↔`closed`
  adapter; `rank` read from `metadata.rank` with the bottom-sentinel
  fallback).
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
  the logical `status == done` (stored as beads `closed`).
- `reason` — beads `close_reason` (set via `bd close --reason`).
  REQUIRED non-empty for closure records.
- `spec_commitment_hint` — beads native `spec_id` field. When non-null,
  carries the verbatim `id_hint` from a spec-side
  `spec_commitments.impl_followups[]` declaration (per
  `livespec/SPECIFICATION/contracts.md`). Absent for freeform items with
  no spec-side commitment.
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
written into `metadata`. A `done` (beads-native `closed`) issue is
terminal —
re-opening (`bd update --status open`) is ALLOWED but DISCOURAGED (the
right pattern is to file a new work-item with a fresh `id` that
references the closed one via `superseded_by` or `depends_on`). The
tenant DB's own version history is the immutable backing log behind the
in-place mutation; doctor's `no-orphan-blocker` invariant in `livespec`
reads materialized views, and readers of this plugin MUST do the same.

### `work_item_merge_evidence` static check

The check walks every materialized work-item from the configured store
descriptor (reading the `AuditRecord` from each closed issue's
`metadata` column) and applies the following rules. The check reads at
the SUBSTRATE layer: the beads-native rows, where the logical `done`
state appears as beads `closed`.

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
map already defined by livespec core's `constraints.md`, and reads
closed gap-tied items through the existing beads
reader (`bd` store). This check is enforced by
`just check-closed-item-integrity`.

Preconditions (recorded so the future revise/impl loop sees them, NOT as
separate invariants): the check requires (a) the `clauses[]`
gap-id→scenario map to be populated in `tests/heading-coverage.json` for
each gap-tied behavior clause (linking its gap-id to its acceptance
scenario's H2 section name) — this is the core `clauses[]` contract
(`constraints.md`, `non-functional-requirements.md`) that impl-beads
adopts; and
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

Per `livespec/SPECIFICATION/contracts.md`, every `livespec-impl-*` plugin MUST expose
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
  hardcoding the well-known file set (per the upstream Spec Reader
  required-capability surface, capability 1).
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

Per `livespec/SPECIFICATION/contracts.md`, every consuming project's
`.livespec.jsonc` declares a `compat` block for each active
impl-plugin. For
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
`contract-version-compatibility` invariant (upstream cross-boundary
doctor invariants).

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
`livespec/SPECIFICATION/contracts.md`) —
never direct CLI shelling-out to wrapper paths.

## Worker credential projection

The Dispatcher MAY authenticate a worker sandbox's coding-agent runtime from a
**projected provider-subscription credential** (for example a Claude subscription
or an OpenAI/ChatGPT subscription) as an alternative to a provider API key, so
workers MAY spend subscription quota rather than metered API billing.

The orchestrator host MAY hold provider-subscription credentials for more than one
provider at the same time, and the Dispatcher MAY project more than one of them
into a single worker sandbox — so one worker MAY authenticate more than one
coding-agent runtime (for example a Claude-subscription primary agent alongside an
OpenAI/ChatGPT-subscription runtime). Each projected credential MUST independently
satisfy the non-rotatability and host-ownership guarantees below.

The non-rotatability and host-ownership guarantees are provider-agnostic: they hold
for a Claude-subscription and an OpenAI/ChatGPT-subscription credential alike. The
projection **mechanism**, by contrast, MAY be provider-specific — the shape of each
projected credential MAY differ per provider — and is implementation-owned (see the
final paragraph).

Each projected worker credential MUST be **non-rotatable by the worker**: a worker
MUST NOT be able to mint or rotate any shared long-lived refresh credential. No
worker — including one whose run triggers a credential refresh — MAY invalidate a
credential for the orchestrator host or for any peer worker.

The Dispatcher MUST NOT dispatch a worker unless every projected credential covered
by the **freshness gate** has a usable lifetime that exceeds the worker's maximum
run budget. When the freshness gate cannot be satisfied, the Dispatcher MUST refuse
the dispatch and MUST surface that the host credential requires renewal, rather
than projecting a credential that MAY expire mid-run.

The orchestrator **host** MUST be the sole owner and refresher of each long-lived
provider refresh credential; worker sandboxes MUST be read-only consumers of the
projected snapshots.

The projection mechanism — the per-provider projection shape, which projected
credentials the freshness gate covers, the credential file or field layout, the
encoding that renders the snapshot non-rotatable, and the numeric freshness
threshold — is implementation-owned and MUST NOT be fixed by this contract. The
behavior is exercised by Scenario 18 and Scenario 19 in `scenarios.md`.
