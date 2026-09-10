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

### Heavyweight authored skills

Each heavyweight op decomposes into (a) a SHARED, harness-neutral prose
artifact at `.claude-plugin/prose/<op>.md` carrying the consent flow,
the multi-step dialogue, the `livespec_orchestrator_beads_fabro.*`
package calls, and the JSON / handoff semantics, and (b) thin
per-runtime SKILL.md bindings — one per supported agent runtime — that
resolve the plugin root, read `prose/<op>.md` in full, and map its
harness-neutral vocabulary to the runtime's tools — adding no operation
behavior of their own (per `constraints.md` §"Skill orchestration
constraints"). This mirrors livespec CORE's prose + thin-Driver-binding
architecture (`livespec/SPECIFICATION/spec.md`). The heavyweight ops are
`capture-impl-gaps`, `capture-spec-drift`, `capture-work-item`,
`implement`, `groom`, `plan`, and `discuss-work-item`. The authoritative skill inventory is
the set of operations shipped under `.claude-plugin/skills/`, each
classed by one of this chapter's three class sections; other sections
and files reference the classes and the shipped set rather than
restating counts or totals. `groom` is the one new maintainer front-end catalogued under
§"Skills — augmented versus new", and is detailed in §"Grooming and
slice-size calibration" → "The four maintainer touchpoints"
(touchpoint 2) — see that section for its read-only-draft /
human-approves contract. `plan` is the Orchestrator-Plane realization of
the Planning Lane and is detailed in §"Planning Lane realization" — see
that section for its create/resume API, the `plan/<slug>/` plan
store, the ledger-held handoff persistence, the scoping event, and the
archive-on-epic-close transition. The remaining ops (`capture-impl-gaps`,
`capture-spec-drift`, `capture-work-item`, `implement`, and the
`discuss-work-item` interactive stand-by skill over the `context` read
primitive) are detailed in the subsections that follow.

#### `capture-impl-gaps`

Surface untracked spec clauses as candidate work-items by invoking the
sibling `/livespec-orchestrator-beads-fabro:detect-impl-gaps --json`
thin-transport skill (no in-skill duplication of the detection logic;
both this skill and doctor consume the same canonical surface).

**Naming note.** Despite the `-impl-gaps` name, this operation performs
NO spec↔impl comparison. `detect-impl-gaps` (below) enumerates ratified
MUST/SHOULD clauses from spec TEXT alone and never reads implementation
state, so a clause it surfaces may already be fully implemented. A
returned gap-id means "this clause is not yet tracked by a work-item",
never "this clause is verified absent from the implementation" — that
comparison, when one exists, is a per-clause human judgement or a cited
executable check, not this operation's mechanism.

The returned gap-ids are presented to the user one at a time; on
consent, a new work-item is created in the tenant DB via `bd create`
carrying the `origin:gap-tied` and `gap-id:<stable-id>` labels.
Detection state is in-memory and discarded at skill exit — no
persistent intermediate artifact. Re-running the skill is idempotent:
an already-tracked gap-id is detected as "already filed" and not
re-prompted unless the user explicitly asks for a refresh.

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

`capture-spec-drift` MUST also accept an optional `--for-work-item <id>`
flag selecting a TARGETED mode instead of the whole-tree survey above.
`implement`'s gap-tied closure gate (§"`implement`" → "gap-tied
completion") invokes this mode when a gap-tied work-item's recorded
check file was modified since the baseline blob hash recorded when it
was cited. In this mode the skill MUST NOT run the whole-tree survey
above; it presents exactly ONE candidate — framed from the diff
between the check file's current content and its recorded baseline —
asking whether the spec clause the check settles needs to change to
match. On consent it reuses the SAME cross-boundary propose-change
handoff as the whole-tree mode. On the resulting proposed-change
landing, the caller records its canonical topic onto the work-item
(`gap_drift_propose_change` metadata), which is what the closure gate
checks before allowing closure to proceed.

#### Detection coverage records and staleness facts

Detection runs are RECORDED, and their recency is COMPUTED, never
remembered:

- **Records.** Every invocation of `capture-impl-gaps` or
  `capture-spec-drift` MUST append an attributed ATTEMPT record
  (operation, declared scope, invoker, outcome) to the repository's
  designated detection-coverage anchor — a ledger item provisioned once
  by the operator through `capture-work-item`, its id committed in
  `.livespec.jsonc`. A COMPLETED-coverage record — carrying the coverage
  point: the ratified spec revision the gap capture ran against, or the
  default-branch merge SHA the drift pass ran through — MUST be appended
  ONLY when the run reached a successful terminal outcome over its
  declared scope with EVERY surfaced candidate durably disposed
  (consented-and-filed, consented-and-handed-off, or explicitly declined
  on the record). A non-zero exit, an interruption, an unresolved
  candidate, or a partial range MUST NOT write a completed record: the
  prior completed point stands, and a complete successful pass clears
  staleness while an aborted or partial pass does not.
- **The self-bookkeeping exception, scoped.** Appending these two
  record types to the designated anchor is the ONLY ledger write the
  detection operations may perform outside their consent flows: no
  work-item create, no disposition, no edit of any other record.
  `capture-spec-drift`'s ledger-intent scan remains read-only; this
  exception covers exclusively its own run's records.
- **Gap-capture staleness (the Step 13 BACKSTOP).** When the newest
  ratified spec revision is newer than the last COMPLETED gap-capture
  coverage point, the needs-attention snapshot MUST carry a
  gap-capture-staleness fact whose handoff names `capture-impl-gaps`
  with the stale range. This fact is the BACKSTOP to livespec core's
  revise Step 13 post-step — the every-revise binding, which remains the
  one binding — and exists for the runs Step 13 cannot guarantee: a
  skipped, interrupted, or bypassed post-step. It MUST NOT trigger any
  run itself.
- **Drift staleness.** When the count of default-branch merges since the
  last COMPLETED drift coverage point is at or past the effective
  `dispatcher.drift_capture_merge_threshold`, the snapshot MUST carry a
  drift-staleness fact whose handoff names `capture-spec-drift`. Merge
  counting excludes nothing silently: if a class of commits is excluded,
  the exclusion is stated on the fact.
- **`dispatcher.drift_capture_merge_threshold`** (sourced from this
  repo's `.livespec.jsonc`, positive integer, default **1**) — the
  merge-count trigger. Declared **API-configurable**: it appears in the console
  Settings surface per §"API-configurable completeness" (the
  consumer-side legs belong to the console's own specification). No
  per-item override — detection recency is a repository property.
- **Consent is untouched.** Both skills remain consent-gated attended
  dialogues. A staleness fact is a surfaced, owned TRIGGER carrying a
  handoff; nothing in this section runs a detector headlessly, and no
  policy setting MAY do so.

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

- **gap-tied completion** — closure is anchored to a CHECK PATH recorded
  on the work-item's own metadata (`gap_check_path`), never to `gap_id`
  (a `gap_id` hashes a hard-wrapped source line and re-keys on reflow,
  so it cannot anchor a closure that must survive the clause being
  edited). The check path is recorded the first time it is cited for
  this work-item — at latest, `implement` MUST ask the user which
  executable check settles the clause and record it (with its current
  blob hash as the closure-drift baseline) before evaluating closure at
  all, if no check has been recorded yet; a work-item reaching closure
  with no recorded check path is refused. Closure requires BOTH legs
  once a check is recorded: the recorded check passes, AND
  its negative control fails (a passing check with no failing control
  proves nothing). If the check file was modified since the baseline
  recorded when it was cited, closure is refused until a targeted
  `capture-spec-drift --for-work-item <id>` run produces a
  propose-change covering the modification. Close with
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
gap-tied check-path verification, the Red → Green evidence) is the
closure's verification consent.

#### `discuss-work-item`

CLI surface: `discuss-work-item <plan_slug | work_item_id> [--project-root <path>]`.

`discuss-work-item` is a heavyweight authored skill (a shared
`.claude-plugin/prose/discuss-work-item.md` prose artifact plus thin
per-runtime bindings, per this section's decomposition): the interactive skill
layered over the `context` read primitive, serving as the maintainer's
day-to-day session and the console's future chat pane. It MUST assemble its
subject's context through `context` (§"Thin-transport skills") rather than a
hand-rolled per-item read. It STANDS BY: it answers questions about the item,
drafts research notes, and records maintainer rulings as plan scope events
through the Planning Lane primitives (a consented store write, per §"Store-write
consent discipline"), and it MUST drive a lifecycle action only on explicit
maintainer instruction — an implicit or ambiguous request MUST NOT trigger a
drive. It MUST resume a plan from the `context` envelope alone, without chat
history. It MUST be registered under the name `discuss-work-item`; it MUST NOT
be named `plan` (which collides with the Claude Code built-in on autocomplete).
Plan mechanics that need no operation (epic creation, research-directory and
anchor scaffolding, the archive move) MAY be offered by this skill; doctor
reports what is missing. Scenario 115 exercises this surface.

### Operator skill

#### `drive`

Permanent minimal operator **executor** surface. `drive` executes exactly
one operator action, identified by its action-id, against the target
repo. The skill is a thin binding over
`.claude-plugin/scripts/bin/drive.py` and the shared
`commands/drive.py` implementation. `drive` composes and ranks NOTHING:
it is a pure executor of its own **action-id grammar** — an `impl:`
dispatch action, one of the thirteen human valve/policy actions
(`approve:` / `accept:` / `reject:` / `resolve-blocked:` /
`set-admission:` / `set-acceptance:` / `set-factory-safety:` / `set-workflow-scope-override:` / `set-merge-on-review-cap:` /
`set-review-fix-cap:` / `set-acceptance-rework-cap:` / `set-merge-hold:` /
`move:`), or a
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

**Human valve actions.** `drive` additionally accepts the thirteen human
operator action ids (the two human-delegable gate commands, the
corrective `reject:`, the blocked-resolution `resolve-blocked:`, the two
admission/acceptance policy edits, the factory-safety opt-out assertion, the
workflow-scope assertion, the three
per-item cap overrides, the per-item merge hold, and
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
status-independent factory-safety opt-out assertion
`set-factory-safety:<work-item-id>:needs-host-secrets|mutates-host-machinery|needs-privileged-host`
(sets the intrinsic `factory_safety` field with a journaled reason;
§"Per-state operator verb vocabulary"), the
workflow-scope assertion
`set-workflow-scope-override:<work-item-id>:citation-only`, the
three per-item cap-override actions
`set-merge-on-review-cap:<work-item-id>:true|false|clear`,
`set-review-fix-cap:<work-item-id>:<positive-int>|clear`, and
`set-acceptance-rework-cap:<work-item-id>:<positive-int>|clear` (each a
per-item override of the correspondingly-named `dispatcher.*` policy
setting, §"Dispatcher policy settings"), and the guarded queue-control
action `move:<work-item-id>:backlog|ready|blocked|active`. The per-item
merge hold action `set-merge-hold:<work-item-id>:on|off` writes or removes
the item's `merge-hold:` label (§"Dispatcher policy settings" → "The
per-item merge hold") and, as its one other effect, arms or disarms the
pull request's auto-merge request on the forge. A policy-edit,
workflow-scope assertion, cap-override, OR merge-hold action MUST modify
ONLY the named policy, override, cap, or hold field of
an existing item (realized on beads as the `admission:` / `acceptance:`
policy label, the `merge-on-review-cap:` / `review-fix-cap:` /
`acceptance-rework-cap:` cap label, or the `merge-hold:` hold label,
through the store seam) and MUST NOT
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
blocked-resolution, the policy-edit actions, the three cap overrides, the
merge hold, and the guarded `move` (§"Dispatcher
admission, WIP cap, and post-merge acceptance"); the console never writes
the ledger directly. The console's single per-item override command FANS
OUT to the three named per-cap actions above — sending `clear` when that
command carries a null value — so it is the ONE console command that does
NOT map 1:1 onto a `drive` action-id; the orchestrator side is correctly
three named cap verbs, never one parameterized `set-override`. The
operator-action behavior is exercised by `scenarios.md` Scenario 31 (the
two gates, `reject:`, and the two policy edits), Scenario 46 (the cap
overrides and clear-to-inherit), Scenario 47 (the guarded `move`), and
Scenario 119 (the merge hold).

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

### Thin-transport skills

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

#### `list-plans`

CLI surface: `list-plans [--json] [--project-root <path>]`. No
`--filter` flag — the skill emits the complete set of open (unarchived)
plans.

`--project-root <path>` — override the base whose `plan/` plan store
is enumerated. Default: `Path.cwd()`. Used by the awareness surface's
(and any other consumer's) cross-boundary handoffs to invoke this skill
from outside the consumer project root.

This skill is the plan enumerator sibling of `list-work-items`: a
pure read-and-emit pass-through that enumerates the open plans
under the governed repo's `plan/` plan store (per §"The
`plan/<slug>/` plan store"). It exists so the read/awareness surface
can compose "plans" (per §"`next`" scope-asymmetry) from a single
canonical primitive rather than re-scanning `plan/` inline.

The skill MUST enumerate exactly one entry per **unarchived** plan
directory — every direct child directory of `plan/` EXCEPT the archive
subtree `plan/archive/` — in ascending lexicographic slug order. An
**archived** plan (`plan/archive/<slug>/`) MUST NOT surface. The scan
is directory enumeration only: it MUST NOT read plan contents, rank,
filter beyond the unarchived/archived split, or consult the ledger —
whether a plan's anchoring epic state matches its archived/unarchived
placement remains the Conformance Pattern's concern (§"Archive on epic
close"), not this skill's.

`--json` output: a top-level JSON object with one key, `plans`,
whose value is an array of unarchived plan slug strings (the plan
directory names) in ascending lexicographic order:

```json
{
  "plans": ["alpha-topic", "beta-topic"]
}
```

Default human output: one line per plan slug. Each slug `<slug>` is
the natural key from which a consumer derives the plan path
(`plan/<slug>/`) and the `/livespec-orchestrator-beads-fabro:plan
<slug>` handoff; the skill emits neither derived form (per
`constraints.md` §"Forbidden patterns" no-off-substrate / derive-on-read
discipline).

Degrade-on-missing: a missing or empty `plan/` directory MUST yield
`plans: []` and MUST exit `0` — an absent plan store is a valid
zero-plan state, never an error. This is the same per-source degraded
tolerance the ranking and listing primitives already carry.

The skill MUST NOT mutate any store: it MUST NOT write the tenant DB,
MUST NOT write or reorder the `plan/` plan store, and MUST NOT prompt
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
3. Break ties among equal-`rank` items deterministically. An item that has
   been ready longer than `dispatcher.ready_aging_threshold_hours` MUST be
   ordered ahead of newer equal-`rank` items, oldest-ready first; equal-`rank`
   items that have not passed that bound — and any item whose ready instant is
   unknowable — retain the `id` lexicographic tiebreak. Ready-age MUST be
   measured from the durable, clone-independent instant of the item's latest
   transition into `ready` (the same instant the ready-work aging surfacing
   reads), never from a machine-local dispatch journal. This is a tiebreak
   strictly WITHIN a `rank` tier; it MUST NOT promote an item across `rank`
   tiers, so a higher-`rank` item is never overtaken by a lower-`rank` aged
   item and `rank` remains the sole primary ordering authority. The bound
   reuses the existing `dispatcher.ready_aging_threshold_hours` setting; this
   ordering behavior adds NO new config key and NO per-item override.
4. Apply `--offset` and `--limit` to produce the returned slice.

This ranking IS `ready_sort_key` from
`livespec_runtime.work_items.lifecycle` — `rank` first, then the equal-`rank`
ready-age tiebreak above (past `dispatcher.ready_aging_threshold_hours`), then
`id`; `next` is the single ranking authority and the Dispatcher composes it.
The aging-aware ordering MUST live in that one `livespec_runtime`-owned key:
`next` and the Dispatcher MUST compose the identical key and MUST NOT introduce
a second, divergent sort key — in particular the Dispatcher MUST NOT re-sort
ready work by age on its own. Because `ready_sort_key` is owned by
`livespec_runtime`, delivering this tiebreak depends on a `livespec_runtime`
change and MUST be delivered through that key rather than a plugin-local
re-sort.

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
human-valve lanes via `list-work-items`, plans via
`list-plans`, plus hygiene) in the read/awareness surface
(`needs-attention`), NOT here. No caller
SHOULD rebuild the incomplete two-`next` composition (the retired
`orchestrate plan`, per §"`drive`"): the composition role belongs to the
awareness surface, and `next` MUST remain a pure `implement`-only ranker.

#### `detect-impl-gaps`

CLI surface: `detect-impl-gaps [--spec-target <path>]
[--project-root <path>] [--since-version <vN>] [--json]`. No `--filter`
flag — the skill emits the complete current gap-id set.

**Naming note.** This is a spec-clause enumerator, not a spec→impl
comparator — despite the `-impl-gaps` name, it never reads
implementation state (see the `capture-impl-gaps` naming note above,
which this section's own mechanics substantiate).

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

**Caller caution.** This is NOT "clauses added since `<vN>`" — a file
that changed for any reason resurfaces EVERY live MUST/SHOULD clause it
contains, including clauses that predate `<vN>` and were untouched by
the edit. A caller (the `revise` operation's Step 13 post-step included)
MUST NOT read this flag's output as a diff of newly-introduced clauses.

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
- The heavyweight `implement` skill's gap-tied closure verification is
  check-path-anchored (§"`implement`" → "gap-tied completion") and does
  NOT invoke this skill at closure — a `gap_id` is unsound as a closure
  anchor (it hashes a hard-wrapped source line and re-keys on reflow).

The skill MUST NOT mutate any impl-side store; it MUST NOT write to the
tenant DB; it MUST NOT prompt the user. It is a pure read-and-emit
pass-through over the Spec Reader's output and the gap-rule enumeration.

#### `needs-attention`

CLI surface: `needs-attention [--project-root <path>] [--repo-name <name>] [--work-items-path <path>] [--json]`.

The read/awareness surface: it composes the spec, implementation,
human-valve, plan, and hygiene gather primitives into an operator
attention list — Markdown by default for operator reading, `--json` for
the machine envelope — as a thin pass-through over
`.claude-plugin/scripts/bin/needs_attention.py` and the shared
`commands/needs_attention.py` implementation. Its operator semantics
are the peer contract stated under §"Operator skill": `needs-attention`
and `drive` are peers coupled ONLY by the shared action-id grammar —
`needs-attention` composes and emits action-ids, executes nothing, and
creates no work-items.

#### `context`

CLI surface: `context <plan_slug | work_item_id> [--json] [--work-items-path <path>] [--project-root <path>]`.

`context` is a query-only read primitive in the family of `list-work-items`
and `needs-attention`: it MUST NOT mutate the work-items store. Given a
`plan_slug` (matching a plan epic's `plan_slug` metadata) OR a work-item id,
it deterministically assembles one structured envelope for that item and, with
`--json`, emits it as a single JSON object. The envelope MUST carry: the
resolved epic or work-item record; its comments; its children — unioned across
BOTH the dotted-id hierarchy AND the `parent-child` dependency edge, so that
neither linkage is dropped (per §"Work-item beads-issue mapping" child
enumeration); its dependency edges; its typed `next_action`; the linked
research directory path when an `associated_work_item_id` anchor resolves one;
and the spec clauses the item cites. Resolution MUST be order-independent and
side-effect-free: two `context --json` invocations against an unchanged store
MUST emit byte-identical envelopes. An absent id or `plan_slug` MUST fail with
a not-found error naming the missing key, never an empty envelope. `--json` is
the machine surface; `--project-root` and `--work-items-path` carry the same
semantics as for `list-work-items`. The interactive `discuss-work-item`
heavyweight skill (§"Heavyweight authored skills") is the stand-by front-end
layered over this primitive. Scenario 114 exercises this surface.

### The needs-attention machine envelope

`needs-attention --json` MUST emit a single JSON object
`{"attention": [<item>...]}` with deterministic serialization (stable
key ordering). Each item carries exactly these fields, whose TYPES,
`kind` vocabulary, and stable-`id` grammar are owned by the
`livespec-runtime` attention-surface baseline (ratified there as v012)
and consumed here by vendored release — this section ratifies the WIRE
ENVELOPE and its guarantees, never a fork of the runtime-owned
definitions:

- `id` — the stable natural key (runtime-owned grammar). Stable across
  compositions for the same underlying fact; a consumer MAY diff
  snapshots by `id`.
- `kind` — the routing category (runtime-owned vocabulary). Consumers
  MUST treat `kind` as an open string set on the wire: an unknown
  `kind` is a well-formed item.
- `urgency` — `high` | `medium` | `low`.
- `summary` — one-line human-readable statement of the fact.
- `source_ref` — `{repo, work_item?, path?}`: where the fact came from;
  `repo` always present.
- `handoff` — `{kind, command, action_id?}`: the action payload a
  caller can render without backend knowledge.

**Per-item field stability and the consumer-tolerance posture.** The
field guarantees above hold PER ITEM. A consumer MUST be able to skip
an item it cannot parse — malformed fields, or an unknown `kind` it
chooses not to render — while consuming the rest of the envelope,
surfacing what it skipped; a consumer whose parse discards the WHOLE
envelope on one bad item is non-conforming (one malformed item blinding
the entire inbox is the failure mode this posture exists to forbid).
This posture binds this repository's own consuming surfaces and is the
producer-declared contract downstream consumers pin.

**Producer-side validation is loud.** The producer MUST NOT emit an
item that fails the runtime validator, and MUST NOT silently omit a
candidate that failed validation: a composition-time validation failure
MUST surface as a visible failure alongside the valid items. Absence of
an attention item MUST NOT be manufacturable by a validation failure —
absence reads as resolution downstream. (The runtime baseline ratifies
the matching composition-completeness invariant; its implementation
carrier is runtime-side — this clause binds THIS producer regardless.)

**Wire evolution is additive.** New item fields and new `kind` values
MAY appear in a release (consumers tolerate both per the posture
above). An existing field's removal, rename, or change of type or
meaning is a breaking change that MUST ride a propose-change here plus
a coordinated, ratified change to the runtime-owned definitions in
`livespec-runtime` FIRST, released and consumed by pin bump — never a
plugin-local fork of the shared shape.

**Executable as advertised.** Every emitted `handoff` MUST be
executable as advertised at composition time: a `drive`-kind handoff's
`action_id` MUST be one `drive` would accept for the item's state, and
equivalent fidelity holds for the other handoff kinds. (The runtime
baseline's own Handoff rule — "an executable action, never a bare
pointer" — is the type-level half; this is the producer-truth half.)
The advertiser and the enforcer MUST be bound mechanically (a test that
renders advertised handoffs and proves the enforcer accepts them, with
the NEGATIVE control: a state the enforcer refuses is never advertised).
Design record: `bd-ib-dohu2g`, whose defect — advertising an `approve`
valve the enforcer refuses by construction — survived four careful
human sweeps precisely because no mechanical binding existed.

**Ownership cut (recorded).** `livespec-runtime` owns the attention
item types, `kind` vocabulary, stable-ID grammar, validator, and any
pure normalizer over injected facts. THIS repository owns the fact
derivations, their persistence and thresholds, this envelope, and the
handoff commands. New fact classes PREFER existing broad kinds with
additive stable-ID forms; a new kind, grammar form, or field ratifies
in `livespec-runtime` first.

### Orchestrator-owned attention facts

The snapshot MUST compose every operational fact family below. Each fact
rides the ratified runtime ID grammar's three-part
`hygiene:<type>:<resource>` form under the existing `hygiene` kind, as a
FLAT item conforming to §"The needs-attention machine envelope" — no
runtime kind, grammar, or field is changed by this section, and a
dedicated fact kind, if ever wanted, ratifies in `livespec-runtime` first
(§"The needs-attention machine envelope" → ownership cut). No fact in
this section carries a structured payload: where per-subject detail is
required, it composes as its OWN item with its own stable `id`,
`summary`, and `handoff`, and a consumer diffs by `id`.

**Capacity single authority (unconditional).** The admission accounting's
verdict is the SINGLE authority on this repository's capacity. Every
surface that reports capacity — status, doctor, attention, or a refusal
message — MUST read that verdict and MUST NOT re-derive capacity from raw
work-item statuses. The verdict MUST be read through a SIDE-EFFECT-FREE
projection: the thin-transport surfaces are query-only by contract, and
the shipped accounting entry point appends a `dispatch-claim-abandoned`
journal record on every call, so composing from it would put audit
records in the published journal behind which no dispatcher decision
stands (§"Control surface and audit"). Such a projection is a
PREREQUISITE for the capacity fact below; until it exists the fact MUST
NOT be composed from a mutating path. What counts is COUNTED CLAIMS, not
rows at status `active` (§"Per-repo WIP cap"). A surface reporting the
count MUST identify the value as the cap that §"Per-repo WIP cap"
defines, MUST state that host-run concurrency is governed separately
(§"Host concurrency belongs to the Fabro scheduler") and is not what it
reports, and MUST scope the count to the cap-enforcing admission paths —
a hand-picked `dispatch --item` bypasses the cap and is not counted
against it.

**Capacity residue fact (`hygiene:capacity:<repo>`, plus
`hygiene:capacity-hold:<work-item-id>` per actionable hold).** The
snapshot MUST carry a capacity fact when, and only when, the cap is
reached AND at least one counted hold is not backed by a live, watchable
run. The aggregate item's `summary` MUST be a deterministic one-line
statement of the counted holds and the free-slot count; each actionable
hold composes as its own item naming the holder and WHY it counts, with
an inspection handoff. Where every counted hold is backed by a live
watchable run, capacity is legitimately busy and NO capacity item is
emitted — an attention list is not a dashboard. This fact MUST NOT
re-compose the lock-less stranded population, which §"Rework-pending
re-dispatch" → "Stranded-state discrimination" already composes under its
own kind and stable id with its own owner; one work-item MUST NOT produce
two ids of two kinds for the same underlying fact. No capacity handoff
MAY advertise a status-move action against a claim whose dispatch
evidence shows a merged pull request — the ratified reconciliation route
is `reconcile-merged`, and a move-to-`ready` handoff would re-queue
merged work.

**The accounting's exposed classes, and the rework ordering
dependency.** The accounting today exposes THREE hold-and-exclusion
classes: a live dispatch lock, an unreadable dispatch journal, and a
green-terminal exclusion. The `rework:pending` class ratified by
§"Rework-pending re-dispatch" is not yet materialized. When it is, the
ACCOUNTING MUST expose it and the snapshot MUST consume that verdict; the
snapshot MUST NOT re-derive the rework class from the raw ledger label,
which would breach the single authority above. A clause of this section
that names an accounting class the accounting does not expose is
unimplementable and MUST NOT be satisfied by re-derivation.

**Ready-work aging (`hygiene:ready-aging:<repo>`).** When at least one
admission-eligible `ready` item has waited past the effective
`dispatcher.ready_aging_threshold_hours` AND no dispatch for this
repository is in flight, the snapshot MUST carry an aging fact naming the
count of aged items, the oldest age, and an unblock handoff (the drain,
or the owning plan's worker). The fact clears when a dispatch is in
flight or no eligible item exceeds the threshold. THE CLOCK: the age is
measured from the item's latest transition INTO `ready`, which MUST be
read from a durable, clone-independent record. The machine-local dispatch
journal MUST NOT be that source — it is absent on a fresh clone, and its
absence is silent, so an aging fact that depended on it would vanish
while items aged, the absence-reads-as-resolution direction §"The
needs-attention machine envelope" forbids. A durable ready-dwell instant
is a PREREQUISITE for this fact. AGE-UNKNOWABLE POSTURE: where the
instant cannot be determined for an admission-eligible `ready` item, the
snapshot MUST report that item as age-unknown and MUST NOT omit it. IN
FLIGHT means a live dispatch lock or a watchable run for this repository
— not a journal record, and not an ad-hoc process query.

**Idle-factory (`hygiene:idle-factory:<repo>`).** When, and only when, ALL THREE of the following hold for a repository, the snapshot MUST carry exactly one idle-factory fact: (a) the ready set is non-empty and at least one ready item is admission-eligible under the admission valve's non-capacity conditions -- the same eligibility the drain and `next` honor, capacity excepted; (b) the single-authority capacity verdict (this section's "Capacity single authority") reports ZERO counted claims for this repository, read through the SIDE-EFFECT-FREE capacity projection that clause requires and NEVER from a mutating accounting path; and (c) the per-node fallback preflight of §"Factory-configurable ACP fallback priority" leaves at least one candidate for every success-critical ACP node. The fact's `urgency` MUST be `high`. Its `summary` MUST be a deterministic one-line statement naming the count of admission-eligible ready items and the first ranked such id. Its single `handoff` MUST be a `drive`-kind handoff carrying `impl:<first-ranked-id>` for that first ranked item -- executable as advertised (§"The needs-attention machine envelope" → "Executable as advertised"): the `action_id` MUST be one `drive` would accept for that item's state. The fact rides the existing `hygiene` kind with the stable id `hygiene:idle-factory:<repo>`; it introduces NO new wire kind, grammar form, or field (§"The needs-attention machine envelope" → ownership cut). It is derived ONLY from this repository's own ledger, journal, and capacity verdict (this section's "The ownership boundary") -- it performs NO live credential probe and NO other external call, and two invocations against an unchanged store emit a byte-identical row. The fact CLEARS the instant any of (a), (b), or (c) fails: it does not appear when counted claims are non-zero (the factory is busy), when no admission-eligible ready item exists (there is nothing to dispatch), or when an observed availability hold exhausts a success-critical chain (that wait composes under §"Provider spend containment"). Like every fact in this section it composes existing reads, executes nothing, and creates no work-items.

**Wait completeness (enumerated, with forward registration).** Each
orchestrator-created wait state below MUST compose, each with its unblock
handoff: a capacity-deferred eligible item (waiting on a counted slot); a
NEEDS_ATTENTION-parked acceptance (§"The NEEDS_ATTENTION verdict"); a
`blocked`/`needs-human` item (`resolve-blocked`); a `pending-approval`
item under an effective `manual` admission policy (`approve`); a
factory-unsafe item surfaced for host routing, which stays `ready` and is
not `blocked` (§"Dispatcher admission, WIP cap, and post-merge
acceptance"); and an item for which unexpired observed availability holds
exhaust at least one success-critical ACP fallback chain, which likewise stays
`ready` (§"Provider spend containment" and §"Factory-configurable ACP fallback
priority"). An enumerated wait absent from the
snapshot is a composition defect, not a policy choice. FORWARD
REGISTRATION: any future contract that leaves work parked on a person or
a resource MUST register, in that contract, its attention derivation and
its unblock handoff. This enumeration is deliberately closed rather than
universal; a universal claim over an open population cannot be checked.
EXPLICITLY NOT A WAIT: a non-convergence `backlog` bounce, which routes
to re-decomposition (§"Grooming and slice-size calibration") rather than waiting on a person or a
slot.

**Parked-acceptance arity and distinguishability.** A
NEEDS_ATTENTION-parked acceptance composes as exactly ONE attention item,
through the existing composition classes and introducing no new kind, per
§"The NEEDS_ATTENTION verdict". Its single `handoff` carries the
`accept:<work-item-id>` action; its `summary` MUST name both
`reject:<work-item-id>:rework` and `reject:<work-item-id>:regroom` as the
alternative dispositions, and MUST distinguish a NEEDS_ATTENTION park
from a routine parking in `acceptance` by naming the verdict and the
absent evidence leg(s). A zero-change merged run parked NEEDS_ATTENTION
for an empty merged diff (§"Post-merge acceptance (`acceptance → done`)" → "The evidence rule" →
"Empty merged diff is ungradeable, not delivered") composes through this
same class as exactly one attention item — no new kind — and its `summary`
MUST name the empty-diff (merged-diff) evidence leg as the absent-evidence
leg, so a zero-change merge surfaces as one attention item with a handoff
rather than a silent `done`.

**The ownership boundary.** The snapshot composes ONLY waits the
orchestrator itself owns. Foreman and overseer wait states publish as
ledger state on their owning plan epics and reach the operator through
the snapshot's existing plan and blocked composition classes. The
orchestrator MUST NOT read overseer or foreman surfaces, and MUST NOT
emit an item whose derivation required one; whether such an item lands in
a console inbox is the console's own contract to ratify, and this section
creates no such route. A HOLDER is the work-item whose claim occupies a
counted slot, identified by its own id — never by an actor identity read
from another repository's surface. Rendering a foreman-attributed
assignee or invoker read from THIS repository's own journal is INSIDE the
boundary.

**`dispatcher.ready_aging_threshold_hours`** (sourced from this repo's
`.livespec.jsonc`, positive integer, default **24**) — the aging trigger.
Declared **API-configurable**: it appears in the console Settings surface
per §"API-configurable completeness". No per-item override — aging is a
repository property.

**The declared-API-configurable class.** A policy setting is
API-configurable when, and only when, this specification DECLARES it so
at the point it is defined. §"API-configurable completeness" and its
console lockstep bind that declared set alone; a key that is neither
declared API-configurable nor in the committed-only class is
committed-only by default. This clause defines the class the lockstep
already refers to.

## pi skill surface

The plugin's operation surface is ALSO exposed to the pi coding agent
(`@earendil-works/pi-coding-agent`) as a third per-runtime binding layer
over the SAME artifacts the Claude Code and Codex surfaces bind: the
wrapper CLIs under `.claude-plugin/scripts/bin/` and the harness-neutral
prose under `.claude-plugin/prose/`. livespec core owns the pi packaging
model for CORE's own operations and delegates this one: core's
`SPECIFICATION/non-functional-requirements.md` §"pi dogfooding
contracts" states that the detailed pi mapping for orchestrator-plugin
commands is owned by each orchestrator plugin's own spec. This section
is that mapping.

**Packaging.** The pi surface ships from THIS repository as a pi package
per pi's documented package model: a `pi` manifest block in a
`package.json` at the repository root, carrying the `pi-package` keyword
for gallery discoverability. The manifest declares exactly one resource
kind — `skills` — naming a NESTED bindings tree at
`.claude-plugin/.pi-plugin/skills/`, the pi sibling of the Codex
bindings' `.claude-plugin/.codex-plugin/skills/`. The nesting enforces
the same single-artifact discipline the Codex surface already follows:
the payload (`scripts/`, `prose/`, and the Claude bindings under
`skills/`) has exactly ONE home under `.claude-plugin/`, and each
runtime's bindings sit beside it rather than duplicating it. No prose
file, wrapper, schema, or template is duplicated for pi. A consumer
installs this repository as a pi git package — `pi install
git:github.com/thewoolleyman/livespec-orchestrator-beads-fabro@release
-l`, the same moving `release` channel the Claude and Codex
marketplaces track — and the resulting clone carries the payload the
bindings resolve.

**Skill names.** pi's skill namespace is FLAT. A pi skill name admits
only lowercase letters, digits, and hyphens (1–64 characters, no
leading or trailing hyphen, no consecutive hyphens) — pi's documented
name rules as of pi v0.84.1, anchored because they are a claim about an
external project no gate here watches, and to be re-verified on any pi
major-version bump — so the colon-qualified
`/livespec-orchestrator-beads-fabro:<op>` form the Claude and Codex
surfaces use cannot be expressed. The namespace is
therefore carried by a name PREFIX, exactly as core's pi Driver carries
`/livespec:<op>` as the pi skill name `livespec-<operation>`. Each of
this plugin's operations is exposed to pi as the skill named
`livespec-orchestrator-beads-fabro-<op>`: the plugin's own name,
UNABBREVIATED, followed by the operation name it carries on every other
runtime. Abbreviating the prefix is forbidden — two fleet repositories
end in the same `-beads-fabro` suffix, so a shortened prefix would name
an ambiguous surface.

The mapping is DERIVED, not enumerated: the pi surface exposes one skill
per operation this plugin ships as a Claude binding under
`.claude-plugin/skills/`, no more and no fewer, so an operation added or
retired there changes the pi surface in the same act rather than through
a separately-maintained list that can silently fall behind. Every name
this rule produces fits pi's 64-character limit; an operation name long
enough to breach that limit MUST be resolved through a propose-change
cycle here, never by silently abbreviating the plugin prefix. Each
binding's directory name under `.claude-plugin/.pi-plugin/skills/` MUST
equal its frontmatter `name`: pi tolerates a mismatch — observed on pi
v0.84.1, anchored because it is a claim about an external project no
gate here watches, and to be re-verified on any pi major-version bump —
the Agent Skills standard does not, and the tolerance is not a licence
to diverge.

**Thin-binding obligations.** Every pi binding carries pi-runtime
mechanics ONLY, under the same thinness discipline the Codex bindings
carry (`constraints.md` §"Skill orchestration constraints"). A pi
`SKILL.md` MUST NOT copy a Claude-specific or Codex-specific SKILL.md
body. Concretely:

- A thin-transport operation's pi binding resolves the plugin root and
  invokes that operation's `scripts/bin/<op>.py` wrapper. Ranking,
  listing, filtering, and output formatting stay in the wrapper; the
  binding surfaces the wrapper's stdout without re-interpretation.
- A heavyweight operation's pi binding reads its shared
  `.claude-plugin/prose/<op>.md` artifact COMPLETELY and executes it,
  binding the prose's harness-neutral vocabulary to pi's tools. It MUST
  NOT restate, summarize, or act on a partial read of that prose. The
  store-write consent discipline (§"Store-write consent discipline")
  binds it unchanged: pi has no structured-picker tool — an absence
  observed on pi v0.84.1, anchored for the same reason and to be
  re-verified on any pi major-version bump — so a consent turn is asked
  in plain prose, with the options stated explicitly, and answered
  before the write executes. Should a future pi release add a picker,
  using it is permitted, and only through a propose-change cycle here.
- The operator surface `drive` is a thin binding over `drive.py`, with
  the selected action executed by the shared CLI, and it composes and
  ranks nothing.
- Plugin-root resolution is realized ONCE, by a single shared resolver
  script in the pi bindings tree that every binding invokes; the ordered
  algorithm MUST NOT be restated inline in a SKILL.md. The sibling repo
  `thewoolleyman/livespec-driver-claude` carried its core-root
  resolution rule as one inline copy per operation binding, across all
  eight of the operations that Driver exposes; copies kept in agreement
  only by copying, so a single positional defect came to live in all
  eight bindings at once. The resolver's search order is: the
  `LIVESPEC_ORCH_PLUGIN_ROOT` explicit override; the governed project's
  own `.claude-plugin/` when that checkout IS this plugin (dogfooding);
  the project-scope pi clone under
  `.pi/git/github.com/thewoolleyman/livespec-orchestrator-beads-fabro/`;
  then the user-scope clone under the pi user-scope git root. A
  candidate counts as resolved ONLY when it actually carries the payload
  (`scripts/bin/`), so a half-fetched clone fails loudly instead of
  resolving to a path whose every subsequent read fails separately. On
  exhaustion the resolver MUST emit an install diagnostic naming every
  candidate it searched, and the binding MUST surface that diagnostic
  verbatim and stop rather than improvising a path.
- The pi package declares NO `extensions`. The sanctioned pi footgun
  guard is the pi DRIVER's, required of `livespec-driver-pi` by core's
  `SPECIFICATION/contracts.md` §"Driver-shipped hooks"; a second
  registration of the same `tool_call` handler from this package would
  double-guard the same tool calls without adding a control.

**Trust gate and the non-interactive caveat.** pi's project-trust
behavior is core's contract and is NOT restated here: per core's
`SPECIFICATION/contracts.md` §"Plugin distribution", pi package
enablement is project-scoped through a committed `.pi/settings.json`,
and a NON-INTERACTIVE pi invocation (`-p`, `--mode json`, `--mode rpc`)
silently ignores project-local settings and packages unless a trust
decision is pre-seeded. Any unattended pi drive of an operation from
this plugin MUST establish trust first, and a resolution failure under a
non-interactive run MUST be read as a possible trust gate before it is
read as a missing install. Mirroring the Codex claim discipline in
`constraints.md` §"Skill orchestration constraints", pi support is
CLAIMED only once the package registration is present AND a live pi
invocation drives one of this plugin's operations through it; the human
discoverability surface (pi's `/skill:<name>` command completion or the
startup skills listing) is verified SEPARATELY from model-visible skill
loading, because the two can diverge. A temporary local pi registration
used for testing is removed afterward unless the maintainer asks to
keep it.

## Interactive dialogue ownership (orchestrator-side)

The interactive gap/drift dialogue — per-finding human review and
consent — is OWNED BY THIS ORCHESTRATOR, not by livespec core or its
per-runtime Driver. This plugin ships its own runtime-specific
interactive front-ends to its capture CLIs: the consent-dialogue
skills `capture-impl-gaps`, `capture-spec-drift`, `capture-work-item`,
and `groom` (per §"Store-write consent discipline"), usable from every
supported agent runtime. These front-ends
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
dialogue is orchestrator-owned: this plugin's heavyweight
front-ends —
`capture-impl-gaps`, `capture-spec-drift`, `capture-work-item`,
`implement`, `groom`, `plan`, and `discuss-work-item` — are exactly those
front-ends and are the governed surface of this discipline. (`discuss-work-item`
is a consented store-writer: it records maintainer rulings as plan scope events
and MAY offer plan-scaffolding writes, each obtaining maintainer consent before
the write.) (`groom` is a consented
store-writer via `file_approved_slices` / `regroom.exit_regroom` — its approve-then-file step writes the regroomed slices (each transits `pending-approval`; an effective-`auto` slice approves on into `ready` at groom time, an effective-`manual` slice rests awaiting the human's explicit `approve`), so it
obtains maintainer approval before that write per §"Grooming and
slice-size calibration". `plan` is a consented store-writer via the
`capture-work-item` operation — it anchors a plan's ledger epic and
files matured pieces as work-items only through that consented seam,
never a direct store write, per §"Planning Lane realization".) Each
front-end's consent flow lives in the shared
`.claude-plugin/prose/<op>.md` artifact the per-runtime SKILL.md
bindings read (per §"Heavyweight authored skills").

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
  additionally require the recorded check to pass and its negative
  control to fail before the close).

### Operation-class waiver

The user MAY explicitly waive per-operation consent for a named operation
class (e.g. "file every detected gap without asking"). A waiver MUST be
explicit, MUST name the operation class it covers, and is scoped to the
current invocation. It MUST NOT be a default, MUST NOT be inferred from
context, and MUST NOT persist across sessions. Absent a waiver, per-operation
consent is required. One committed exception exists:
`dispatcher.groom_cut_approval: consensus` (§"Dispatcher policy settings" →
"The five policy settings") is a ratified standing consent for exactly one
operation class, the consensus tier's approval of a FIRST groom cut filed
under §"Grooming and slice-size calibration" → "Consensus-gated automated
groom cut", in the shape of livespec core's
`spec_governance.drift_acceptance_mode` opt-in; no other committed key MAY
stand in for a waiver, and a human operator's approval through
`resolve-blocked` is consent under the up-front operation decision form above,
not under this exception.

### Machine-path exemption — the Dispatcher

The Dispatcher (`dispatcher.py` `dispatch` / `loop`) writes to the work-items
store ONLY as machine-path dispositions of already-filed items — the lifecycle
verbs `admit` (`ready → active`), `complete` (`active → acceptance` on
confirmed merge, carrying PR-number and merge-sha audit evidence in the
`AuditRecord`), `accept` (`acceptance → done`, the AI leg of the item's
effective `acceptance_policy`), `reject` routing out of `acceptance`, the
non-convergence `backlog` bounce, the `regroom-out` disposition (closing a
groomed original as regroomed-out once its approved slices are filed by an
apply dispatch under §"Grooming and slice-size calibration" → "Consensus-gated
automated groom cut"), and — when the effective `admission_policy` is `auto`
(via `dispatcher.auto_approve_ready` or a per-item label, per §"Dispatcher
policy settings") — the auto-`approve` (`pending-approval → ready`)
disposition. These writes are EXEMPT from the per-operation consent discipline
by design — the Dispatcher acts on items a human or a consented front-end
already filed, and `--no-close-on-merge` disables the post-merge disposition
writes entirely. The exemption covers ONLY dispositions of already-filed
items; the Dispatcher MUST NOT create net-new work-items on its own
initiative. The Dispatcher's module docstring documents this boundary. The
human-triggered operator commands (`drive`
`approve:`/`accept:`/`reject:`/`resolve-blocked:`/`set-admission:`/`set-acceptance:`/`set-factory-safety:`/`set-workflow-scope-override:`/`set-merge-on-review-cap:`/`set-review-fix-cap:`/`set-acceptance-rework-cap:`/`set-merge-hold:`/`move:`
action ids, per §"`drive`") are NOT machine-path dispositions — their consent
is the operator's explicit action selection.

### Out-of-scope surfaces

The thin-transport skills (`list-work-items`, `next`,
`detect-impl-gaps`, `list-plans`, `needs-attention`) are query-only by
contract (per `constraints.md` §"Forbidden patterns") and never write to the
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

2. **Groom (the one new maintainer surface).** For a `backlog` item needing
   re-decomposition (an intake-routed epic or a non-convergence bounce) the
   maintainer runs the shipped groom front-end (`groom <id>`) — a read-only
   scoping conversation that DRAFTS a layered decomposition, each candidate
   slice pre-filled with acceptance / autonomy tier / dependency links / repo
   target / scope. The maintainer edits and approves (or sends it back to
   re-draft); on approval the front-end files the slices via the existing
   `capture-work-item` machinery with dependency edges linked; spec-change
   slices route to `/livespec:propose-change` rather than the factory. The
   draft is read-only until the human approves — it proposes; it files nothing
   until approval. The draft MAY instead be produced by a registered groom
   workflow variant through a journaled groom dispatch under §"Consensus-gated
   automated groom cut" below; the approval act, and who may perform it, are
   what that subsection governs.

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
authored skill (per §"Heavyweight authored skills"), so
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

### Consensus-gated automated groom cut

This subsection carries the values call livespec's spec-side-autonomy plan
resolved on 2026-08-03 (design record: repository `thewoolleyman/livespec`,
`plan/archive/spec-side-autonomy/research/brainstorm.md`, "Values calls",
item 2): the groom cut MAY leave the maintainer's hands, but automated
LAST and consensus-gated, for the cut only. What may be delegated to a
factory run is the DRAFTING of a decomposition; what may later be delegated
to the consensus tier is the approval of the FIRST cut of an intake-routed
epic, and nothing else. The re-groom of a Dispatcher non-convergence bounce
is a decision that is human-gated by design under §"Every needs-human
escalation still reaches a human", and this subsection leaves it so.

- **The groom dispatch is the door.** The `groom` front-end (touchpoint 2)
  MAY delegate its drafting to a registered groom workflow variant by
  performing a JOURNALED GROOM DISPATCH of the `backlog` item: a dispatch
  under which the item enters `active` from `backlog` under a dispatch
  claim (the defined `admit` verb stays `ready → active`), records
  the groom variant as the item's `dispatch_workflow` pin (§"Self-contained
  plugin dispatch" → "Named workflow variants"), and journals itself
  exactly as a factory dispatch does. A repository that grooms this way
  MUST register the groom variant through that registry; the reserved
  `implement-work-item` workflow MUST NOT groom, and a groom variant MUST
  NOT implement. A groom dispatch is the ONLY way a `backlog` item enters
  `active`, and the Dispatcher MUST NOT admit a `backlog` item on its own
  initiative: the front-end's operator performs it.
- **Two phases, never a waiting run.** A groom variant MUST be a two-phase
  run under §"A factory run never awaits a human". Its propose phase MUST
  draft the decomposition exactly as the `groom` front-end drafts it —
  candidate slices pre-filled with acceptance, autonomy tier, dependency
  links, repo target and scope, arranged into dependency layers — MUST
  file nothing, and MUST terminate at a needs-human outcome carrying the
  draft, so that the item rests at `blocked / needs-human`. When the
  Dispatcher journals that termination it MUST record the draft on the
  item as a ledger comment, beside the preserve-by-reference pointer; that
  comment is where the draft rests, and it is what the apply phase reads.
  The apply phase MUST run only on a later dispatch of the same item whose
  rendered goal carries a recorded approval, and MUST then file the
  approved slices exactly as touchpoint 2 files them on human approval:
  via `capture-work-item`, with dependency edges linked, spec-change slices
  routed to `/livespec:propose-change` rather than the factory, and the
  original regroomed-out. The apply run's terminal disposition of the
  original is the `regroom-out` disposition of §"Machine-path exemption —
  the Dispatcher": the original closes as regroomed-out once its approved
  slices are filed, and the dispatch claim ends with it.
- **The approval is the consent.** Approval of a drafted cut MUST arrive
  through the `resolve-blocked:<work-item-id>:ready` valve, MUST be
  recorded as a ledger comment on the item BEFORE the status transition,
  naming the approving invoker, and the Dispatcher MUST fold that comment
  into the item's next rendered goal. An item so approved rests at `ready`
  for its APPLY dispatch, not for implementation: a groom-pinned item at
  `ready` is authorized for its apply dispatch and carries the approved
  draft in place of an acceptance, its `dispatch_workflow` pin still names
  the groom variant, and the admission valve dispatches it under that
  variant through the recorded-pin step of the registry precedence. An
  apply dispatch of an item carrying an approved groom draft whose
  resolution is anything other than a registered groom variant — an
  explicit `--workflow-name` naming the reserved workflow or a non-groom
  variant, or a cleared pin that falls through to
  `dispatcher.default_workflow` — MUST be refused before any Fabro run
  exists, as a further cause of the journaled pre-run refusal of
  §"Self-contained plugin dispatch" → "Named workflow variants".
  `resolve-blocked:<work-item-id>:backlog` MUST send the draft back for
  re-drafting and MUST NOT file anything. The recorded approval IS the
  apply phase's consent under §"Store-write consent discipline": it is an
  up-front, per-operation decision the approving operator made through the
  valve, so the filing that follows is user-consented and needs no waiver.
  The filing seam (`file_approved_slices`) MUST require an approval record
  naming the approver identity and how the approval was obtained, MUST
  stamp that record on every filed slice and on the regroomed-out original
  in a field a later reader can query, and MUST refuse a call that carries
  none.
- **Human until the tier exists, and opted in even then.** Until livespec
  core ratifies the consensus tier, the approving invoker MUST be a human
  operator: the automated cut is permitted in principle and stays
  human-decided in fact. Once core ratifies the tier and its evidence is
  present, fresh and conforming, the tier MAY own the approval of a drafted
  cut ONLY where the governed repository has opted in through the committed
  policy setting **`dispatcher.groom_cut_approval`** (enum `human` |
  `consensus`, default **`human`**), a §"Dispatcher policy settings"
  setting whose per-item label override MAY only lower an item to `human`
  and MUST NOT raise one to `consensus`. Under that opt-in the tier MAY own
  only the FIRST CUT of an item that intake routed to `backlog` as an
  epic — an item for which no slice has yet been filed and which entered
  `backlog` only by intake routing, never by a Dispatcher bounce or a
  `reject:regroom`. Where the setting is `consensus`, the
  committed setting IS the standing consent for tier-approved first-cut
  filings: a ratified, explicit exception to the no-persist rule of
  §"Store-write consent discipline" → "Operation-class waiver", in the
  shape of livespec core's `spec_governance.drift_acceptance_mode` opt-in,
  covering exactly that one operation class and nothing else. It MUST NOT
  own the re-groom of an item the Dispatcher bounced to
  `backlog` on non-convergence, a spec-change slice, or any other decision
  that is human-gated by design; every such approval stays a human
  operator's.
- **Two rails, required.** When the consensus tier owns an approval, two
  rails are REQUIRED, not optional. Every slice the apply phase files MUST
  be at or below the calibrated ceiling of §"Gate type determines hard
  versus advisory"; the intake size gate stays ADVISORY for a human-approved
  cut exactly as that section says, and the ceiling becomes hard only for a
  tier-approved one, so while no ceiling has been calibrated and adopted
  the tier MUST NOT approve and the draft MUST rest for a human. A regroom
  cap, the committed policy setting **`dispatcher.automated_regroom_cap`**
  (integer, default **`2`**, with a per-item label override like the two
  rework caps), MUST bound how many times the tier may send one item's
  draft back for re-drafting; at the cap the draft MUST rest at
  `blocked / needs-human` for a human operator, who alone may approve it
  or send it back further.

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

A registered groom workflow variant, entered only by the groom front-end's journaled groom dispatch of a `backlog` item, MUST draft the decomposition and terminate at a needs-human outcome without filing anything, with the Dispatcher recording the draft on the item as a ledger comment; MUST file the approved slices only on a later dispatch under the item's groom-variant pin whose rendered goal carries an approval recorded as a ledger comment through `resolve-blocked:<work-item-id>:ready` naming the approving invoker, that approval being the filing's consent; MUST stamp the approval record on every filed slice and on the regroomed-out original and refuse a filing that carries none; and MUST accept only a human operator's approval until livespec core ratifies the consensus tier, after which the tier MAY approve only the first cut of an intake-routed epic, only under `dispatcher.groom_cut_approval: consensus`, and only behind the calibrated slice-size ceiling and `dispatcher.automated_regroom_cap`.

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
— operates on this plugin's filesystem plan store and ledger, is
Orchestrator-internal, and is therefore NOT part of `livespec`'s
functional cross-boundary contract. The architectural frame (the three
planes and the two seams) is `livespec`'s `spec.md`; what this section
adds is the realization: the
`plan` front-end and the `plan/<slug>/` plan store, the same cut as
grooming above.

### The `plan` front-end

`plan` is the SIXTH heavyweight authored skill (§"Heavyweight authored
skills"), so its orchestration follows the same shared
`.claude-plugin/prose/<op>.md` + thin per-runtime SKILL.md decomposition
as the other five. Unlike the one-shot `capture-*` family, a plan
is stateful and re-entered for the same slug, like `groom`. Its
invocation surface has two modes:

- **`plan` (no argument)** — the interactive entry. It lists the open
  plans (composed from the ledger's open planning epics via the
  `list-work-items` operation AND the on-disk `plan/<slug>/`
  directories) to resume, OR the maintainer describes a new plan and
  the front-end proposes a canonical dash-cased slug — using the SAME
  canonicalization the `propose-change` operation applies to a topic hint
  (lowercase; hyphenate runs of non-alphanumerics; strip; truncate to
  64) — confirms it, and on confirmation creates `plan/<slug>/` (write-once research plus
  the one write-once metadata anchor `associated_work_item_id`, written
  with the new epic's id) and anchors a ledger epic for the
  plan (filed through the `capture-work-item` operation). The human never hand-crafts the
  identifier.
- **`plan <slug>` (argument)** — strict resume. It MUST match an existing
  `plan/<slug>/` exactly, or it fails hard with an error listing the
  existing slugs. No fuzzy match and no create-on-typo; creation happens
  only through the no-argument interview path.

Each invocation MAY add write-once research, append a ledger handoff
entry (per §"Ledger-held handoff persistence"), run the scoping event,
route a now-ripe piece (to the `propose-change` operation for spec, or
the `capture-work-item` operation for ledger work filed as a child of
the plan's epic), or archive the plan on close.

### Plan identity: `plan_slug` and the `associated_work_item_id` anchor

Every ledger `epic` in a tenant MUST carry a metadata key `plan_slug`
whose value is a canonical dash-cased slug produced by the same
canonicalization the `propose-change` operation applies to a topic hint
(lowercase; each run of non-`[a-z0-9]` characters replaced by one
hyphen; leading and trailing hyphens stripped; truncated to 64
characters). An epic IS a plan: the slug is the human-readable handle
that listings, tooling, and the Control-Plane surface anchor to instead
of the short id, whether or not a `plan/<slug>/` directory exists for it.
`plan_slug` MUST be unique across all epics of a tenant, closed epics
included, so a retired slug is not reused while its epic remains. A
work-item that is not an epic MUST NOT carry `plan_slug`; its plan is its
parent chain. The one sanctioned non-epic reference is the metadata key
`plan_ref`, whose value MUST be tenant-qualified as `<tenant>/<slug>` and
which MAY appear only on an item that is not a child of the epic it
references. The `plan` front-end MUST write `plan_slug` when it anchors an
epic; every other epic-creating route (the `capture-work-item` operation,
grooming, cross-tenant filing) MUST write it too, deriving the slug from
the epic's title through the same canonicalization when the caller
supplies none. The existing plan-anchor marker `spec_commitment_hint =
plan:<slug>` remains a discriminator for "was this epic created by the
plan primitive"; it is NOT the identity carrier, and a reader resolving a
plan's epic MUST key on `plan_slug`.

The write-once metadata anchor that §"The `plan/<slug>/` plan store"
requires is the file `plan/<slug>/associated_work_item_id`. Its content
MUST be exactly one line holding either a same-tenant work-item id (the
anchoring epic) or the literal `unassigned`. `unassigned` is permitted
ONLY while no epic in the tenant carries `plan_slug` equal to the
directory name: it is the research-before-work-items state, in which a
directory of research exists but nothing has been filed. The anchor MUST
NOT be updated to mirror children, statuses, handoffs, readiness, or
archive state; the single sanctioned rewrite is `unassigned` to the id of
the epic that adopts the directory, which completes the anchor rather
than mirroring state. A plan opened through the `plan` front-end MUST be
written with the epic id, because that front-end creates the epic in the
same act — so the `unassigned` state arises ONLY for a directory of
standalone research that predates any epic, and once an epic is opened
for that slug the anchor MUST name it. The anchor is a re-derivable
pointer, not state: given the ledger and the directory name it can be
reconstructed, so it conforms to `constraints.md` §"Forbidden patterns"
(no off-substrate persistence) exactly as the plan store's research notes
do. A legacy `plan/<slug>/epic.md` is NOT an anchor and carries no
authority; where one exists it MAY remain as write-once historical
evidence, and the migration in §"Plan-record conformance checks" writes
the real anchor beside it.

Bidirectional matching is why the identity is carried on both sides, and
the two directions are stated here so the conformance checks below have a
clause to enforce: from the directory, the anchor's id MUST name an epic
whose `plan_slug` equals the directory name; from the epic, when a live
`plan/<slug>/` or archived `plan/archive/<slug>/` directory exists whose
name equals the epic's `plan_slug`, that directory's anchor MUST name
that epic. Design record: repo
`thewoolleyman/livespec-console-beads-fabro`,
`plan/retire-overseer-and-redesign-control-plane-around-console/research/redesign-brainstorm-and-decisions.md`
(decision D6); repo `thewoolleyman/livespec-orchestrator-beads-fabro`,
`plan/console-control-plane-primitives/research/charter-and-driving-model.md`.

### The `plan/<slug>/` plan store

A plan is a first-class directory `plan/<slug>/` anchored by a ledger
epic. The plan store MUST contain only write-once research inputs under
`plan/<slug>/research/` and exactly one write-once metadata anchor
written at plan open, the file `associated_work_item_id` defined in
§"Plan identity: `plan_slug` and the `associated_work_item_id` anchor".
The anchor names the ledger epic id, or the literal `unassigned` while no
epic carries the directory's slug, and MUST NOT
be updated to mirror children, statuses, handoffs, readiness, or archive
state. Plans created after ratification MUST NOT create a live
`handoff.md`, `supervisor-handoff.md`, mutable status file, or any other
mutable planning-state document in git. A young plan MAY be
research-only. A root `research/` tree MUST NOT exist: standalone
analysis lands in the plan store, and a living reference document lives
in `docs/`, `.ai/`, or a dedicated top-level topic directory (precedent:
`loop-reflection-gate/`).

Migration of a pre-existing live `handoff.md` MUST preserve it as a
write-once historical-evidence file under `plan/<slug>/research/` and
MUST NOT delete it from the git tip. A migration that relocates any plan
path MUST update, in the same change or an explicitly linked work-item,
every fleet-spec design-record citation naming the pre-relocation path.

### Ledger-held handoff persistence

Handoff persistence MUST be append-only, per-entry, individually
attributed, and timestamped. In this Beads/Dolt reference realization,
handoff entries are comments on the plan epic, and the ledger's
comment/timeline read path is the authoritative resume source — not git.
Each handoff entry carries only non-derivable content such as rationale,
warnings, abandoned attempts, and pointers; derivable state — children,
statuses, PR state, merge state, readiness — is queried fresh from the
ledger and git at resume time. The next action is NOT carried by a
handoff entry; it is the typed `next_action` metadata defined in
§"Typed `next_action` and `last_session`", and a handoff entry that
names a next step in prose MUST ALSO be written with a matching
`next_action` update by the same primitive call. Scope events (rulings,
deferrals) remain comments, because they are the part a human reads back.
Checklist items in planning artifacts are
session-local steps or pointers to real ledger ids, never a parallel
work queue that shadows the ledger.

A plan's SUPERVISOR role — the entity coordinating the plan across
worker-session restarts, distinct from the worker session itself — MUST
be attributable by a deterministic literal, not free text, mirroring an
archive entry's own attribution: an archive entry's body-parsed
`author:` field is the reserved literal `plan-archive`, computed by the
archiving primitive and never caller-supplied. Generalizing that same
rule, when a handoff entry is authored on the supervisor's behalf, the
ledger comment's body-parsed `author:` field MUST be exactly
`<slug>-supervisor`, where `<slug>` is the plan's slug — likewise
computed by the entry-writing primitive itself, never accepted as a
caller-supplied string. A "does this plan have a supervisor"
discriminator MUST scan the timeline for a body-parsed `author:` field
matching this literal — a plain string-equality check, never prose or
LLM interpretation of entry content. This check reads the body-parsed
`author:` field ONLY. It MUST NOT read Beads' own `--actor`
audit-trail field: that field is a separate, independently-settable
identity layer (e.g. a human runtime acting on the supervisor's behalf
carries its own `--actor` while the comment body still names the role),
and the two are permitted to diverge. Every free-text `author` a worker
session supplies through the general handoff primitive is unaffected by
this reservation; only the archive and supervisor literals are reserved.
Design record: repo `thewoolleyman/livespec-orchestrator-beads-fabro`,
work-item `bd-ib-8stn`, filed 2026-08-15; independently corroborated the
same date by repo `thewoolleyman/livespec-overseer`, work-item
`overseer-4bbnit`.

### Typed `next_action` and `last_session`

Every OPEN epic that has a live `plan/<slug>/` directory MUST carry a
metadata key `next_action` whose value is an object with exactly three
keys: `kind`, `ref`, and `text`. `kind` MUST be one of `impl`,
`spec-op`, `human`, or `none`. `impl` means the next step is factory
implementation of one work-item, and `ref` MUST be that work-item's id,
so the action executes as the `drive` operation's `impl:<ref>` action-id;
`spec-op` means the next step is a spec-lifecycle operation, and `ref`
MUST name the operation and its topic in the form `<operation>:<topic>`
(for example `propose-change:plan-slug-anchor-and-typed-next-action`);
`human` means the next step needs a person, and `ref` MAY be empty or MAY
name the attention item or question that carries the ask; `none` means
nothing is recorded, and `ref` MUST be empty. `text` MUST be one
imperative sentence a person can read without any other context. The same
epic MUST carry a metadata key `last_session`, a non-empty string naming
the session that last wrote `next_action` and the UTC timestamp of that
write. Both keys are updated IN PLACE: they are the one piece of
derivable-looking plan state the ledger holds as metadata rather than as
a comment, because they are a pointer to the NEXT step, not a record of
the steps taken. They MUST be written only through the plan primitives
(`append_handoff`, `append_supervisor_handoff`, and a dedicated
`set_next_action` primitive), never by hand-editing epic metadata. An
epic that is closed, or that has no live plan directory, MAY omit both
keys.

An unattended resume (the `resume_directive` path under
`LIVESPEC_PLAN_UNATTENDED`) MUST take its action from `next_action` and
MUST NOT parse handoff comment bodies for it. It MUST act without asking
only when `kind` is `impl` or `spec-op` and `ref` is non-empty; `human`
and `none` MUST raise the picker and report the `kind` as the reason. An
attended resume MUST present `next_action` as the default choice of its
picker. A prose marker line (`next action:`) MAY continue to appear in a
handoff comment for a human reader, but it carries no authority: when the
two disagree, the metadata wins, and the conformance checks in
§"Plan-record conformance checks" report the disagreement. This retires
the single-line marker parse as the resume authority; a next action
written as wrapped prose can no longer be silently truncated into a
fragment that an unattended resume executes. Design record: repo
`thewoolleyman/livespec-console-beads-fabro`,
`plan/retire-overseer-and-redesign-control-plane-around-console/research/redesign-brainstorm-and-decisions.md`
(decision D6, item 5).

### The scoping event

Before a plan epic takes implementation children, a scoping event MUST
cut every known requirement from the research prose into
requirement-carrier children under that epic, including requirements
deliberately deferred from the current implementation increment. A
requirement MUST NOT exist only in prose after that point. Deferral is
ledger state on the requirement-carrier child: an explicit `deferred`
disposition where the ledger supports that state, otherwise a sanctioned
label/state applied only through the admission valve — never
hand-edited.

### The two seams

The Planning Lane is Spec-Plane but touches the Orchestrator Plane at
exactly two explicit seams (the same cross-boundary discipline as the
Gap and Drift flows): (1) *plan ↔ ledger, via the sanctioned plan
surface only* — the plan surface appends and reads plan-epic ledger
handoff entries and reads ledger children (via the `list-work-items` /
`next` query surface) to resume work; (2) *plan → work* routes ripe work
into the ledger ONLY through the `capture-work-item` operation, never a
direct cross-plane store write. The plan surface MUST NOT write to
orchestrator-private storage outside those ledger-entry and
capture/admission surfaces.

### Archive on completion

A plan's lifecycle binds to its ledger epic, but an epic's closed status
is not by itself archive authority. `plan/<slug>/` remains active until
the plan's work is genuinely complete: implemented, merged, and, where a
release applies, shipped and verified. A status transition to closed can
also mean regroomed out, superseded, or otherwise retired without
completion, so whatever closes the epic MUST archive the directory only
when that completion evidence exists. The one exception is an explicit
handoff at archive time: every remaining piece of work MUST be
transferred to named follow-up plan(s) or work-item(s), and the archive
record MUST state those names exactly. Nothing is lost — the archived
plan stays under `plan/archive/` and in git history. Mechanical
enforcement of this corrected archive rule is tracked outside this repo
in `livespec-dev-tooling-5asgvm` and the related converse-gap item
`livespec-dev-tooling-q3emww`.

Archive requires BOTH legs. First, the mechanical leg: a plan epic MUST
NOT close or archive while any child requirement or implementation item
is undisposed. Second, the completeness leg: archive time MUST include a
separate, independent adversarial completeness review that reads the
plan's research documents against the epic's children and attests every
requirement — including deferred requirements — has a ledger carrier.

When a plan operation resumes or drives an archive attempt whose mechanical
child-disposition leg passes but whose ledger timeline has no valid independent
completeness-review evidence, the operation MUST commission a fresh independent
adversarial completeness reviewer. The reviewer MUST have had no role in that
plan's implementation, MUST compare every research requirement (including
explicit deferrals) against the complete child set, MUST spot-check closure
evidence against the forge, and MUST record its result durably. The plan MUST
remain unarchived until valid evidence exists. A self-review, a missing durable
evidence reference, or a review that does not attest complete requirement-carrier
coverage MUST NOT satisfy the completeness leg.

Archival MUST be TOTAL: the whole directory is relocated and NOTHING
remains at `plan/<slug>/` — no stub, terminal marker, forwarding note,
or other residue, and not the directory itself, even empty. The `plan`
operation MUST NOT create one, and MUST NOT treat one as an acceptable
outcome of an archive it performs.

This is a STATE invariant, not only a rule about the moment of archival:
in no committed tree, from this clause's ratification forward, may the
same slug exist at both `plan/<slug>/` and `plan/archive/<slug>/`. A
retired slug is consequently NOT reused for a new plan while its archive
remains — choose a new slug; or, if the new work genuinely continues the
old plan, REOPEN ITS EPIC, which unarchives the record by moving it
back. Moving an archived record back WITHOUT reopening its epic is
forbidden: it produces an active `plan/<slug>/` whose epic remains
closed, contradicting the lifecycle binding this section states.

The mechanism belongs with the rule. Control-Plane consumers of this
lane discover plans and test archival at DIRECTORY granularity, so
residue that keeps the live directory in existence makes a finished plan
read as ACTIVE, its mapping bookkeeping is never reclaimed, and it stays
eligible for nudges, wrap-up injection and RESTART.

When a plan would close with anything unresolved, exactly ONE of two
dispositions is sanctioned. Either the plan is LEFT UN-ARCHIVED — its
epic staying OPEN, so the lifecycle binding continues to hold — until
its blockers are resolved; or ALL of its blockers are TRANSFERRED to a
different or new NON-ARCHIVED plan and/or work-item, after which the
plan is archived whole. A work-item transfer goes through
`capture-work-item`, per the *plan → work* seam, never a direct
cross-plane store write; a transfer into another plan is an ordinary
plan-store edit and stays in-plane. Archiving the plan and leaving a
note saying what is left is not a third option.

Nothing here narrows the clauses beside it. Reopening an epic still
unarchives by moving BACK, which leaves nothing in the archive and is
not residue. The prohibition on a root `research/` tree and the
sanctioned relocation of a research note to a living home in `docs/`,
`.ai/`, or a dedicated top-level topic directory are all unaffected.

### Plan-record conformance checks

The plan-identity and typed-`next_action` contracts MUST be enforced by
named conformance checks, each reporting the check id below, the
offending epic id or directory path, and a remediation sentence. Each
verdict is `error` (the enforcement aggregate fails) or `warn` (reported,
never failing):

- `plan_slug_present` (error): an epic in the tenant lacks metadata
  `plan_slug`.
- `plan_slug_unique` (error): two or more epics in the tenant carry the
  same `plan_slug`.
- `plan_slug_canonical` (error): a `plan_slug` value is not equal to its
  own canonicalization.
- `plan_slug_on_non_epic` (error): a work-item that is not an epic
  carries `plan_slug`, or carries `plan_ref` whose value is not
  tenant-qualified or which references the item's own parent epic.
- `plan_anchor_present` (error): a direct `plan/<slug>/` or
  `plan/archive/<slug>/` directory has no `associated_work_item_id` file,
  or the file does not hold exactly one line that is a same-tenant
  work-item id or the literal `unassigned`.
- `plan_anchor_consistent` (error): the anchor's id names no epic, names
  a non-epic, or names an epic whose `plan_slug` differs from the
  directory name; or an epic's `plan_slug` names an existing directory
  whose anchor does not name that epic; or the anchor is `unassigned`
  while an epic in the tenant carries the directory's slug.
- `plan_lifecycle_parity` (error): a live `plan/<slug>/` directory
  anchors a closed epic, or an archived `plan/archive/<slug>/` directory
  anchors an open epic. This restates the invariant the fleet's
  `plan_epic_parity` check already enforces, so the family is complete;
  that existing check satisfies it.
- `plan_close_evidence` (error): an epic whose `plan_slug` names a live
  or archived directory is closed without a completeness-review evidence
  comment on its timeline (the archive gate's second leg, made visible
  after the fact).
- `plan_next_action_typed` (error): an open epic whose `plan_slug` names
  a live directory lacks `next_action`, or its `next_action` violates the
  typing rules in §"Typed `next_action` and `last_session`" (unknown
  `kind`, empty `ref` for `impl` or `spec-op`, non-empty `ref` for
  `none`, empty `text`), or lacks `last_session`.
- `plan_next_action_drift` (warn): the newest handoff comment names a
  next action in prose that does not match the epic's `next_action`.
- `plan_comment_rate` (warn): an epic accrued more comments on one UTC
  day than the record-rate threshold (the same threshold the record-rate
  guard applies; default 6).

These checks read ledger state and therefore MUST be armed-only in the
same way `plan_epic_parity` is: they self-skip unless their arming lever
and the tenant credential are present, and when armed they run inside
this repository's enforcement aggregate. Their realization MAY live in
the fleet's shared checks package (`livespec-dev-tooling`) beside
`plan_epic_parity`; it MUST NOT be added to `livespec` core's doctor,
which the repo-agnostic Planning Lane guidance keeps free of any plan
invariant. Each check MUST carry a positive control proving it can return
a hit.

A one-shot migration MUST be run once per family tenant before the
error-verdict checks arm there. For every epic lacking `plan_slug`, it
derives the slug from the existing `plan:<slug>` anchor marker when
present, else from a `plan_slug=<slug>` line in the epic's notes, else
from the canonicalized title, and writes it; a derived slug that collides
with an existing one MUST be reported and left unwritten for a human to
resolve. For every direct `plan/<slug>/` and `plan/archive/<slug>/`
directory it writes `associated_work_item_id` holding the id of the epic
whose `plan_slug` equals the directory name, or `unassigned` when no such
epic exists, and leaves an existing correct anchor untouched. For every
open epic that names a live directory and lacks `next_action`, it seeds
`next_action` from the newest handoff comment — `kind: impl` with the
work-item `ref` when the action names an `impl:<id>` route or a bare
work-item id, `kind: human` with the recorded text when it records one
prose action naming no work-item, and `kind: none` otherwise — and seeds
`last_session` with the migration's own identity and timestamp. The
migration MUST write ledger metadata only through the store bridge this
plugin already uses, MUST commit each repository's anchor files through
that repository's ordinary worktree → pull-request → merge discipline,
and MUST report per tenant what it wrote, what it skipped, and what it
refused. Running it twice MUST change nothing the second time. Design
record: repo `thewoolleyman/livespec-console-beads-fabro`,
`plan/retire-overseer-and-redesign-control-plane-around-console/research/redesign-brainstorm-and-decisions.md`
(decision D6, items 4 and 6).

### Planning Lane restraint budget

The Planning Lane realization adds at most one new front-end (`plan`)
and the `plan/<slug>/` (+ `plan/archive/`) plan-store path; it reuses the
`capture-work-item` machinery for every work-item write. Its ledger
footprint stays on a plain Beads `epic`: the plan anchors an `epic`, its
handoff and scope entries are ordinary ledger comments, and the D6
plan-identity contract adds only bounded, fixed-shape metadata KEYS on
that same epic — `plan_slug` (§"Plan identity: `plan_slug` and the
`associated_work_item_id` anchor"), and the typed `next_action` plus
`last_session` pointer (§"Typed `next_action` and `last_session`") — not
a new record type, table, or store. That metadata is deliberately in
scope: the maintainer ruled in decision D6 that epics ARE plans, so the
handle and the next-step pointer live on the epic rather than in a
shadow document. If the realization ever grew past roughly one new
front-end, the plan store, and this fixed-shape epic metadata, that is
the signal to stop and reconsider.


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
Mechanism) and set the sandbox's resolved `dispatcher.sandbox_exempt_marker`
(default `livespec.sandboxExempt`; concern #1 Exemption) as a projection of the
field per §"Repository integration contract", and it MUST then run the baseline
Verifiers over
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
checkout and no `pyproject.toml` / lockfile install step. That payload
MUST be a RELEASED version: one that has passed semantic-commit
versioning, the repository's CI gates, and the release cut. The
Dispatcher MUST NOT execute from an orchestrator working tree, and MUST
NOT treat the presence of a writable orchestrator checkout as a reason to
behave differently. Release pinning is the single execution mode — there
is no second, checkout-dependent mode to degrade from, and no override,
environment variable, or flag re-enables one.

The pin is the installed plugin payload the operator has provisioned (the
plugin root, `${CLAUDE_PLUGIN_ROOT}`), which is keyed by the released
commit. It satisfies the packaged-payload rule by construction: it
carries `scripts/bin/`, the vendored runtime, and the `.fabro/` workflow,
and it carries no `pyproject.toml` and no lockfile, so it cannot require
an install step. Because that payload is not a git working tree, no
promotion into it is possible and none is attempted.

Behaviors that presuppose fleet context MUST still degrade to clean
no-ops rather than failing the dispatch: the fleet-manifest sibling-clone
projection renders empty when no fleet manifest is present.

**Self-update triggers on a version comparison, and every promotion is
canaried.** When the Dispatcher considers updating itself it MUST compare
the RUNNING RELEASE against the latest available RELEASE. It MUST NOT
compare git commit SHAs, branch names, or merged file lists against a
local checkout — those are properties of a working tree, which the
Dispatcher no longer executes from.

The Dispatcher MUST NOT modify, promote into, or re-point its own
execution artifact. It never writes code, and no passing check causes it
to begin running a different payload than the one it started under. The
executing payload changes only when the process is restarted against a
newly provisioned one.

When a newer released payload is provisioned, the Dispatcher MUST canary
it before that payload is treated as usable. The canary MUST execute the
CANDIDATE ARTIFACT ITSELF, on the host that will run it, using the same
interpreter and the same packaged layout it will run under, and it MUST
exercise at minimum the candidate's import graph, its argument parsing,
and its check pipeline end-to-end. It MUST remain side-effect-free: no
real ledger, no engine run, no network.

A PASSING canary MUST surface that a RESTART IS DUE — the newer payload
is validated and will take effect on the next start. A FAILING canary
MUST keep the last-known-good payload running AND MUST alarm a human; it
MUST NOT be downgraded to a warning or skipped, and it MUST NOT cause the
candidate to be treated as usable.

Neither outcome moves the running process onto the candidate. Detecting,
canarying, and alarming is the whole of the Dispatcher's self-update
responsibility.

This restates, for the self-update path specifically, the rule above that
the Dispatcher MUST NOT treat the presence of a writable orchestrator
checkout as a reason to behave differently. Self-update MUST NOT branch
on whether its execution root is a writable checkout: under
release-pinned execution it never is, and a branch that skips the canary
when it is not is prohibited.

The Dispatcher MUST NOT infer that an update is unnecessary from an
unobservable signal: when it cannot determine the available release, it
MUST record that it could not determine it, distinctly from recording
that no update was available.

Operator consequence: a host-side dispatch runs the last RELEASE the
operator has provisioned, not the current working tree. An unreleased
local edit does NOT take effect on the dispatch path until it is released
and the operator's payload is updated. This is intended — a dispatcher
version becomes usable only once it is past versioning and the release
gates — and it applies to fleet members and adopters identically.

**The dispatch-admission path MUST NOT block on ambient release-staleness.**
The plugin-currency check that runs before a dispatch is admitted MUST NOT
refuse dispatch, and MUST NOT return a blocking exit code, on the sole
ground that a newer RELEASE exists than the executing operator-provisioned
build. Running the operator-provisioned payload is legitimate per this
section, so the comparand for any blocking decision MUST be the
operator-provisioned payload, NOT the instantaneous latest-release head
probed at dispatch time. A release published after a session starts MUST
NOT refuse that session's dispatches; freshness pressure is carried by
surfacing, not by refusal. When plugin currency cannot be determined — the
executing build identity or the available release is unobservable — the
check MUST record that it could not determine currency, distinctly from
recording that the build is current, and MUST proceed rather than refuse.

**Ambient staleness is surfaced, not enforced.** When the executing
operator-provisioned dispatcher build lags the latest available release,
the needs-attention snapshot MUST carry a non-blocking
dispatcher-currency-staleness fact stating how far the provisioned build is
behind — in released versions and/or elapsed time — and naming the
restart-and-update remedy, modeled on the detection-coverage staleness
facts in §"Detection coverage records and staleness facts". This fact is a
surfaced TRIGGER: it MUST NOT itself refuse or gate a dispatch, and it
composes with the already-required passing-canary "restart is due"
surfacing rather than replacing it.

**The sole blocking currency form is a deliberate operator floor.** The
dispatch-admission check MAY refuse dispatch fail-closed if and only if the
operator has committed a `dispatcher.minimum_release` floor in this repo's
`.livespec.jsonc` AND the executing release is below that floor. Absent
that key the check has no blocking authority over currency.
`dispatcher.minimum_release` (optional; when present, a released-version
identifier) is a human-chosen safety floor for a release known to be
safety-critical, never an ambient latest-release comparison. When the floor
is configured but cannot be evaluated because the executing or available
release is unobservable, the check MUST record that it could not determine
currency and MUST proceed, never fail open into a false refusal nor silence
the undetermined result into a pass.

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
(`<target>/.fabro/workflows/implement-work-item/`), and the Dispatcher
MUST resolve the committed workflow a dispatch runs in this order, most
specific first: (1) an explicit `--workflow <path>` argument, the
raw-path escape hatch; (2) the named variant selected per "Named
workflow variants" below, when that selection is not the reserved name;
(3) for the reserved name `implement-work-item`, the target's own
committed `<target>/.fabro/workflows/implement-work-item/` when it
exists, else the plugin payload's bundled workflow resolved via the
plugin root. Step (3) is the automatic target-local resolution this
paragraph previously reserved for a future amendment; it has been the
Dispatcher's behavior since 2026-07-20 and is ratified here as it runs.
Prepare steps remain TARGET-TOOLCHAIN facts, not fleet constants: the
typed integration inputs of §"Repository integration contract" express
them without a workflow copy, and an adopter that does carry its own
workflow keeps its own prepare chain in it, subject to the same
integration-input parity "Named workflow variants" below requires of a
registered variant. The resolved committed path MUST be journaled on
the dispatch record as `workflow_toml`.

**Named workflow variants.** A dispatch target MAY declare
`dispatcher.workflows`, a table mapping a variant name to a directory path
relative to the target repository root, and `dispatcher.default_workflow`, a
variant name. Both are OPTIONAL target-declared capabilities in the same class
as `dispatcher.acp_nodes` and `dispatcher.node_timeouts` — configuration the
target chooses to carry — and NOT integration points the orchestrator requires
of a governed repository, so the "One schema" and "One resolver" rules of
§"Repository integration contract" do not govern them, and the
members-and-adopters disposition of this addition under the closed-set clause
is: a repository that declares no registry, member or adopter, incurs no new
dispatch-time obligation, and the obligations below bind only a repository
that declares one. Each registered directory MUST hold a COMPLETE workflow —
`workflow.toml`, `workflow.fabro` and its prompt files — and the Dispatcher
MUST NOT merge a variant with the bundle or with another variant; a variant is
a whole directory, never a partial overlay. The name `implement-work-item` is
reserved: it is always defined, it resolves by step (3) above, and a registry
entry MUST NOT redefine it. The variant a dispatch uses MUST resolve, most
specific first: (a) an explicit `--workflow-name <name>` argument on
`dispatcher.py dispatch`, `dispatcher.py loop` and the `drive` operation's
`impl:<id>` action; (b) the name a prior dispatch of the same work-item
recorded in its `dispatch_workflow` metadata, so a retry re-runs the variant
the first attempt ran, provided that name is still registered or reserved; (c)
`dispatcher.default_workflow` when it names a registered entry; (d)
`implement-work-item`. The selector MUST NOT be read from an environment
variable: the per-dispatch value is a recorded argument, for the reason §"ACP
node adapter configuration" gives — an ad-hoc shell MUST NOT be able to change
which graph the factory runs with nothing in the committed record or the
journal to show for it. Every dispatch MUST write the resolved name to the
work-item's `dispatch_workflow` metadata, a top-level metadata key, and MUST
journal it as `workflow_name` on the dispatch record beside `workflow_toml`.
The Dispatcher MUST refuse the dispatch before any Fabro run exists, in the
same shape as the layer-names-an-absent-node refusal of §"ACP node adapter
configuration" — a journaled pre-run refusal whose stage names every cause
that applies — when: the selected name matches no registry entry and is not
the reserved name; the selected registry directory lacks `workflow.toml` or
`workflow.fabro`; or a registry entry is named `implement-work-item`; or the
work-item carries an approved groom draft awaiting its apply dispatch and the
selected name is not a registered groom variant (§"Grooming and slice-size
calibration" → "Consensus-gated automated groom cut"). These are not
`Defective` schema points and do not take the schema-validation exit-3 path,
because the keys are not schema fields.

**A registered variant is the reserved workflow's peer, not its
exception.** Every clause of this specification scoped to the
`implement-work-item` workflow by name — §"ACP node adapter
configuration", §"ACP node timeouts", and the typed-workflow-inputs
clause of §"Repository integration contract" — applies to every
registered variant exactly as it applies to the reserved workflow, and
each such clause's refusals fire for a variant on the same conditions. A
registered variant MUST declare the same six ACP nodes — `implement`,
`fix`, `review_fix`, `pr`, `review`, `disposition` — so that the
per-repository adapter layer, the `dispatcher.codex_models` expansion and
the per-node timeout table resolve against it without naming an absent
node; a variant differs from the reserved workflow in its graph edges,
retry and review discipline, prompts, run configuration and sandbox
image, never in the node names those layers address. A registered
variant MUST reference exactly the same `inputs.*` token set the
reserved workflow references, so the three-way set identity of the
seam-equivalence check holds per variant against the ONE set the
Dispatcher renders and every declared integration point reaches every
variant; a variant MUST NOT opt out of an integration input. The CI
seam-equivalence check, and the `check-no-fleet-toolchain-literals`
gate of the fleet-toolchain literal ban (`constraints.md`
§"Governed-repository integration constraints"),
MUST read the bundle AND every directory this repository registers under
its own `dispatcher.workflows`, and MUST fail rather than report clean
for a registered directory whose scan yields nothing to check, so a
registered variant is held to the same integration-input and
dispatch-path-seam parity as the bundle. (Implementation: plan epic
`bd-ib-yqpdrt`, children `bd-ib-27puvv`, `bd-ib-u7arwz` and
`bd-ib-asrazi`.)

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
- `active` — admitted into a WIP slot and being worked — or parked
  rework-pending: routed back from `acceptance` by a rework entry and
  awaiting its fix-forward re-dispatch (§"Rework-pending re-dispatch").
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
human; auto: automatic"). **Gradeable acceptance criteria
(AI-dispositive items):** an item whose EFFECTIVE `acceptance_policy` is
`ai-only` or `ai-then-human` and whose effective acceptance criteria
(§"Effective acceptance criteria") parse to zero gradeable assertions
MUST NOT enter `ready`: the human `approve` valve MUST refuse it and an
`auto` admission policy MUST withhold it, in both cases surfacing the
parse result, the item id, and the remedy (author criteria via groom or
edit; or set the item's `acceptance_policy` to `human-only` where
machine grading is genuinely inapplicable). The item RESTS where it is;
it is not moved to `backlog` or `blocked` on these grounds. Being in `ready` MEANS approved-to-start
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

### Per-state operator verb vocabulary

Which operator verbs are valid in which lifecycle state, which transition
each door owns, and when a policy dial still governs anything. This
vocabulary is OWNED here and consumed by console adopters:
`livespec-console-beads-fabro`'s own contract defers per-item verb
suppression to it explicitly ("depends on the per-state valid-verb
vocabulary, which is owned by `livespec-orchestrator-beads-fabro`"), so
until it existed no consumer could suppress a verb without inventing a
vocabulary it does not own. Design record: repo
`thewoolleyman/livespec-console-beads-fabro`,
`plan/console-happy-path-mvp/research/verb-vocabulary-brainstorm.md`
(seven maintainer-decided points, 2026-07-21..26, each recorded with its
source verification), with the filing draft at
`plan/operator-surface-redesign/research/verb-vocabulary-propose-change-draft.md`.

Rationale: an operator surface that offers a verb which is meaningless or
inert for the selected item's state cannot be told apart from a broken
one. The narrowings below exist so that every offered verb is actionable
and every transition is attributable in the journal.

#### Per-lane valid operator verb sets

| Lane | Valid operator verbs |
|---|---|
| `backlog` | groom (every backlog item, uniformly); move→ready (admission); move→blocked; set-admission; set-acceptance; merge-on-review-cap; review-fix-cap; acceptance-rework-cap |
| `pending-approval` | approve (the single door toward `ready`); reject (rework \| regroom); set-admission; move→backlog (withdraw); move→blocked (park); set-acceptance; review caps per the dial-window rule |
| `ready` | move→backlog (withdraw); move→blocked (park); driver-dispatch (host-only-refused items only); set-acceptance; set-workflow-scope-override (declared-workflow-edit refusals only); acceptance-rework-cap; merge-on-review-cap; review-fix-cap |
| `active` | observe only — no operator verbs beyond set-acceptance / acceptance-rework-cap per the dial-window rule; for an item carrying `rework:pending`, `dispatch --item` (the `drive` `impl:<work-item-id>` action) drives the pending rework |
| `acceptance` | accept (the single door into `done`); reject (rework \| regroom); move→backlog (de-scope); move→blocked (park) |
| `blocked` | move→ready (unblock); move→backlog (an item needing decomposition routes here first — groom is `backlog`-only) |
| `done` | nothing (but see "Status-independent verbs" below) |

**Status-independent verbs.**
`set-factory-safety:<id>:<needs-host-secrets|mutates-host-machinery|needs-privileged-host>`
is NOT lifecycle-gated and is therefore intentionally not enumerated per-row
above (including the `done` row): it
sets the intrinsic `factory_safety` runnability axis (orthogonal to both status
and `admission_policy`), so it is valid on a work-item in ANY lane. It is a
field-setter, not a transition or policy-window verb, so the per-lane narrowing
that keeps every enumerated verb actionable does not apply to it. Its clause is
below.

#### Door rules — every transition has exactly one journaled owner

- `ready` is entered by `approve` (from `pending-approval`) or by an
  operator move from `backlog`/`blocked`. The move from
  `pending-approval` to `ready` is REMOVED: it is an unjournaled
  duplicate of the `approve` valve, so the ledger cannot attribute the
  transition.
- `active` is entered ONLY by a journaled dispatch — factory dispatch,
  `driver-dispatch`, or the groom front-end's groom dispatch of a `backlog`
  item (§"Grooming and slice-size calibration" → "Consensus-gated automated
  groom cut") — OR by a rework return from `acceptance`, which is either the
  `reject:rework` valve or the Dispatcher's own `acceptance-auto-rework`
  disposition. Bare operator moves into `active` are removed from every lane.
  Both rework returns are journaled — the Dispatcher's
  `acceptance-auto-rework` disposition, and the valve's durable
  `human-valve-reject-rework` record (shipped as `bd-ib-ktxb`, PR #1048) — so
  every rework return into `active` is journaled and the one-journaled-owner
  rule holds for both. Both are named here because a door rule that omits a
  shipped writer is false, not merely incomplete.
- `done` is entered ONLY by `accept`. The move `acceptance → done` is
  REMOVED — it is an unjournaled duplicate of the accept valve.
- `pending-approval` is never a move target; it is entered only by
  intake Definition-of-Ready routing.
- `reject` is valid at the two human valves ONLY — `pending-approval`
  and `acceptance`. Its two kinds land in different lanes:
  `reject:rework` returns the item to `active`, and `reject:regroom`
  returns it to `backlog`. Mid-flight abort of an `active` run is NOT
  in this vocabulary: cancelling a running dispatch needs
  run-cancellation semantics, and journaling a rejection while the run
  continues would record an outcome that did not happen.
- The `reject:rework` valve MUST write a durable journal record for the
  `acceptance → active` transition it performs, carrying at minimum the
  acting party, the stage identifier, and the work-item id, symmetric
  with the Dispatcher's `acceptance-auto-rework` record. Emitting that
  object solely in the drive CLI's response payload MUST NOT be treated
  as satisfying this requirement: a response is transient and
  unattributable once the invocation returns, whereas the
  one-journaled-owner guarantee requires a durable record. This
  requirement is MET by the shipped valve (`bd-ib-ktxb`, PR #1048,
  integration-tested), and the `active`-entry rule above states without
  qualification that every rework return into `active` is journaled. The door is required to gain
  attribution rather than be removed because the Dispatcher already
  performs this same transition automatically under
  `acceptance-auto-rework`, and because `reject:rework` is the only
  operator route from `acceptance` back into work — `reject:regroom`
  routes to `backlog`, which would restore admission eligibility for
  work that has already merged.

#### Policy dial window

A policy dial is valid only while the decision it governs is still
ahead of the item:

- `set-admission` — through `pending-approval`.
- `merge-on-review-cap` and `review-fix-cap` — through `ready`. Both are
  snapshotted into the run at dispatch, so a change made while the item
  is `active` can never reach the in-flight run; offering them there
  would be inert.
- `set-acceptance` and `acceptance-rework-cap` — through `active`.
- Nothing on `done`.

#### `set-workflow-scope-override:<id>:citation-only`

This ready-lane-only operator assertion records that an item's mention of a
path under `.github/workflows/` is a citation rather than a declaration of
intent to edit that path. `citation-only` is the single allowlisted value.
Applying it writes the durable beads label
`workflow-scope-override:citation-only` without changing item status. The
assertion is valid only for an item whose published
`awaits_scope_override` signal is true; the alternative is to revise the
item's own scope with an inline negation declaration that makes the absence
of workflow edits explicit.

The admission predicate evaluates non-null `factory_safety` FIRST, before
consulting this override. Consequently the assertion can admit only an item
refused by the declared-workflow-edit heuristic and can never admit an
intrinsically host-only item. It is an explicit operator override of a
factory-boundary heuristic, not a general relaxation of factory safety. A
work-item introducing a first-class operator verb MUST include specification
coverage for that verb in its acceptance criteria, because the action-id
grammar is a consumer contract rather than an implementation-private parser.

#### `driver-dispatch:<id>`

A journaled dispatch door for work that the factory will not sandbox.
It is valid ONLY on `ready` items whose `factory_safety` is non-null —
exactly the set the admission valve already refuses and host-routes,
whose refusal already directs the operator to "host-route it to a host
sub-agent instead". It journals the actor and a driver-session
reference and moves `ready → active`; the driver session parks its
result at `acceptance`, where the normal accept valve applies.

Because the eligible set is precisely the set the Dispatcher refuses,
no dispatcher/driver race is possible and no claim mechanism is
required. That scope is load-bearing, not incidental: widening
`driver-dispatch` to any `ready` item WOULD require a claim mechanism,
and MUST NOT be done without one.

#### `set-factory-safety:<id>:<needs-host-secrets|mutates-host-machinery|needs-privileged-host>`

A status-independent operator verb that SETS the target work-item's
`factory_safety` field to the supplied host-only reason. The reason MUST be one
of the three canonical `factory_safety` values —
`needs-host-secrets`, `mutates-host-machinery`, or `needs-privileged-host`
(§"Work-item beads-issue mapping") — exactly as the field's own closed enum
defines them; an out-of-enum or empty reason is refused. A null `factory_safety`
— the default — remains factory-eligible;
opting an item out of factory eligibility MUST go through this verb, so the
reason is recorded on the item in the journal, rather than through a raw
`bd label add` that leaves no attributable record. Because `factory_safety` is an
INTRINSIC runnability axis orthogonal to lifecycle status, the verb is valid on a
work-item in ANY lane — it is not gated to a single lifecycle state. It does NOT
change item status and MUST NOT alter `admission_policy`, the orthogonal
human-approval axis. Once set, the admission predicate — which evaluates non-null
`factory_safety` FIRST — host-routes the item, and `driver-dispatch:<id>` becomes
the applicable door. A work-item introducing a first-class operator verb MUST
include specification coverage for that verb in its acceptance criteria.

`groom` needs no door — a groomed item remains `backlog` throughout the
drafting conversation, and the groom exit is a close-regroomed-out into
replacement slices.

### Journal invoker attribution

Every record the Dispatcher's journal append path writes MUST carry two
fields stamped ONCE by the append layer and inherited by every writer
above it: **`invoker`** (a non-empty opaque identity string) and
**`invoker_source`** (exactly one of `flag`, `env`, `fallback`). Writers
MUST NOT stamp these fields themselves; a record supplied with either
field is refused by the append layer as a programming error, so the
attribution cannot be forged one caller at a time. EVERY journal write
MUST route through the append layer: writing the journal path directly
is forbidden, the two shipped direct writers (the acceptance-rework
disposition writer and the ledger-close status-normalization writer,
which today bypass the layer and carry no timestamp) are migration
obligations of this contract's implementation, and a mechanical control
MUST prove no code appends to the journal path outside the layer —
without this, the stamped-once guarantee governs only part of the
journal, and the bypassed acceptance-rework record is the very
provenance carrier §"Rework-pending re-dispatch" designates.

The identity enters on the published CLI surface and resolves in this
order:

1. `--invoker <id>` on the invocation (`invoker_source: flag`) —
   accepted by every published state-changing entry point
   (`dispatcher.py` `loop` / `dispatch` / `reconcile-merged`, the
   `drive` operation's valve actions, and the `probe` subcommand once
   ratified — every later-ratified state-changing entry point inherits
   this input as a filing obligation of its own proposal).
2. Otherwise the `LIVESPEC_INVOKER` environment variable, when set and
   non-empty (`invoker_source: env`).
3. Otherwise the derived fallback `unattributed:<os-user>@<hostname>`
   (`invoker_source: fallback`). The fallback is a MARK, not an
   identity: it records that no caller asserted who acted.

Identity strings are opaque to this contract; the RECOMMENDED convention
is `<role>:<name>` (for example `human:<name>`, `session:<session-name>`,
`foreman:<seat>`, `console:<principal>`), and callers acting on a
human's explicit order SHOULD carry that human in the identity they
assert. Where a ratified door already journals a door-specific actor
field (the v051 valve records), that field remains; `invoker`/
`invoker_source` is the uniform envelope-level attribution.

**`dispatcher.require_invoker`** (boolean, committed `.livespec.jsonc`,
default **`false`**) governs the fallback: when `true`, a published
state-changing invocation whose identity would resolve by `fallback`
MUST be refused at startup as a precondition error (exit `3`), naming
the two accepted inputs — BEFORE any store mutation, journal write, or
run creation, so no act is half-performed and no attribution gap is
created by the refusal itself. When `false`, the fallback applies and
the record is written marked `invoker_source: fallback`. This setting
has NO per-item override (attribution is a property of the invocation,
not the item) and is deliberately NOT API-configurable: it MUST NOT be
editable through the console Settings surface or any remote API,
because a dial that relaxes attribution MUST NOT be reachable over the
surface whose acts it attributes (§"Control surface and audit").
Read-only invocations (`--dry-run`, status reads) resolve and stamp
identity identically when they journal, but are never refused on
attribution grounds.

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
  the counted-claim bound — NOT a count of items at status `active`.
- **`--item <work-item-id>` (repeatable) scopes the run to hand-picked
  items.** One or more `--item` flags RESTRICT the selection to exactly the
  named work-items. `--item` NARROWS the ranked selection; it never bypasses
  it — a named item that is not dispatch-eligible (dependencies unclear, no
  resolvable assignee, no free WIP slot, resting at `pending-approval`
  under an effective `admission_policy` of `manual`, or carrying a non-null
  `factory_safety` — or, for an item carrying `rework:pending`, the rework
  re-dispatch eligibility of §"Rework-pending re-dispatch", through which a
  marked item is eligible rather than as an exception to this rule) MUST
  NOT be dispatched,
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
  per-run cost signal and therefore no cost-gate verdict (below). The
  Dispatcher MUST additionally report, for every work-item that was `ready`
  and considered but NOT selected, that item's identifier together with a
  single machine-stable exclusion reason. The reason MUST be drawn from a
  closed set naming at least: the WIP cap or budget being reached, an
  unsatisfied blocking dependency, and exclusion by an explicit `--item`
  filter. A ready item that was considered and not selected MUST NOT be
  omitted silently from the report. The exclusion report MUST accompany the
  selection in the same invocation's output under `--json` and on stdout,
  and MUST be distinguishable from the selection rather than merged into it,
  so a caller can tell "would be dispatched" from "was ruled out, and why".
  The exclusion report MUST NOT change what `--dry-run` selects, and this
  reporting obligation does NOT relax the read-only requirement above.
  Journaling the exclusion report alongside the planned selection is
  permitted, on the same footing the selection is granted: the journal is an
  append-only audit record and MUST NOT be the only surface carrying the
  exclusions. Where an item is excluded for more than one reason, the
  Dispatcher MUST report the reason that actually governed the exclusion
  decision rather than an arbitrary member of the set, so that acting on the
  reported reason is sufficient to change the outcome.

The Dispatcher's guarded recovery surface for an already-merged item is
`reconcile-merged --repo <path> --item <work-item-id> [--json]` and, only after
an operator has confirmed the original dispatcher process is dead,
`reconcile-merged --repo <path> --item <work-item-id> --force [--json]`. It MUST
refuse unless the named item is currently `active`, because this valve exists
only for a dispatch whose merged PR did not complete post-run disposition.
It MUST additionally refuse ANY item carrying the `rework:pending` label,
whatever its status: such an item's dispatch COMPLETED its post-run
disposition — the disposition's outcome was rework — and the remedy is the
rework route of §"Rework-pending re-dispatch" (the next drain pass, or
`dispatch --item`), which the refusal message MUST name. `--force` MUST NOT
bypass this refusal: reconciling a rework-pending item would re-run a
disposition that already ran.

A live dispatch MUST hold a dispatch-scoped ownership lock for the whole
dispatch, including the post-merge janitor and disposition window. The lock
content MUST include at least the dispatcher process id, a start timestamp, the
work-item id, and the dispatch id when one is available. Before resolving the PR
or provisioning any janitor checkout, `reconcile-merged` MUST read that lock and
refuse by default when the lock exists and its process id is alive. The refusal
message MUST report the lock age and tell the operator to confirm liveness with
`fabro ps`, wait for the janitor window to close, or use `--force` only after
confirming the original dispatcher process is dead. A stale lock whose process
id is no longer alive MUST NOT block reconciliation, because that is the
stranded-dispatch case this valve exists to recover. `--force` bypasses only the
live-lock refusal; it MUST NOT bypass source lane checks, merged-PR resolution,
post-merge janitor execution, or acceptance journaling.

The reconcile valve MUST use a janitor checkout path that is distinct from the
normal dispatch loop's `janitor-<work-item-id>` path, such as
`janitor-reconcile-<work-item-id>`. This path ownership rule is independent of
the liveness lock: even if a guard is stale, absent, or bypassed with `--force`,
a reconcile run MUST NOT preclean or remove the live dispatch's janitor
checkout. The post-merge janitor MAY still hold a per-checkout lock before
precleaning or provisioning, and that lock MUST continue to block concurrent
callers that target the same checkout path.

The valve MUST resolve the PR number and merge SHA from GitHub, by the expected
`feat/<work-item-id>` branch first or a merged PR title/search match carrying the
work-item id only when that fallback is unambiguous on the default branch. The
fallback search MUST include a default-branch base filter. If multiple merged PR
candidates survive filtering, the valve MUST refuse with a clear ambiguous-PR
error listing the candidates rather than silently choosing the first result. The
valve MUST NOT require or trust ledger audit metadata for that resolution. After
a merged PR resolves, the valve MUST NOT launch Fabro and MUST NOT rebuild the
change; it reruns the same post-merge janitor used by the dispatch engine
against a fresh checkout of the merged ref. A green janitor MUST enter the
existing post-merge acceptance path unchanged, including the `active ->
acceptance` ledger-complete write, acceptance journal records, and
policy-governed `acceptance -> done` auto-accept when applicable. A red janitor,
missing merged PR, wrong source lane, ambiguous merged PR, or held janitor
checkout lock MUST leave the item `active` and report the failed guarded
precondition or janitor stage. This is a distinct guarded entry path and does
not widen the `drive move` target set; `acceptance`, `done`, `pending-approval`,
and `active` remain forbidden `move` targets.

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
  (`counted_claims < wip_cap`, §"Per-repo WIP cap"; a rework re-dispatch's
  capacity condition excludes the item's own parked row — §"Rework-pending
  re-dispatch").
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
- **Required ACP chains not observed exhausted:** resolve each node's ordered
  candidates against versioned observed availability holds as §"Factory-configurable
  ACP fallback priority" requires. An item is not admitted only when at least
  one success-critical node has no remaining candidate. A hold covering one
  primary MUST NOT refuse admission while its chain has an eligible fallback.
  The item is NOT marked `blocked` on these grounds and MUST NOT be
  auto-disposed; it remains `ready` for a subsequent pass.

The Dispatcher MUST, when a WIP slot frees — AFTER any rework-pending
re-dispatch has consumed the freed capacity (§"Rework-pending
re-dispatch": finishing admitted work precedes admitting new work) —
admit the **top-ranked**
(lexicographically earliest `rank`, per §"Work-item beads-issue
mapping") admission-eligible `ready` item (eligible = dependencies clear
AND an assignee is resolvable AND `factory_safety` is null AND every
success-critical ACP node retains a candidate after observed-hold filtering —
`admission_policy` plays no part at this valve), set its `assignee` (the reused field, not a new `owner`), and
transition it to `active`. The Dispatcher MUST NOT auto-approve
(`pending-approval → ready`) an item whose effective `admission_policy`
is `manual`; it MUST surface the resting item for the maintainer's
explicit `approve` on every pass (independent of capacity).

### Rework-pending re-dispatch

The two rework entries of §"Post-merge acceptance (`acceptance → done`)"
(the under-cap dispositive FAIL, and the human
`reject:<work-item-id>:rework` valve) route an item to `active` and stamp
the ledger-held **`rework:pending`** label. That label is the
Dispatcher's selection input for executing the promised fix-forward
rework; the dispatch journal remains the audit trail of WHICH entry
stamped it. Exactly those two entries MAY stamp the label; no other
machinery may.

- **Selection.** On every drain pass, the Dispatcher MUST drive `active`
  items carrying `rework:pending` and holding no live dispatch lock into
  available capacity BEFORE admitting any new `ready` item, in `rank`
  order (ties by `id` — the same ordering authority as admission). The
  rework dispatch is **fix-forward**: it patches on top of the
  already-merged, live change; it MUST NOT revert the merged change
  (reverting belongs to `reject:regroom`).
- **Marker lifecycle.** Starting a rework dispatch MUST journal the
  rework admission before launching the run and MUST NOT clear the
  `rework:pending` label at launch: the label clears only at the rework
  dispatch's TERMINAL disposition (the completion path that moves the
  item to `acceptance`, an over-cap escalation, or a terminal close).
  The double-selection guard is the live dispatch lock, never the label:
  a marked item holding a live dispatch lock MUST NOT be re-selected. A
  rework dispatch that dies BEFORE publishing therefore leaves the item
  marked and lock-less — re-selectable by a later drain, self-healing
  rather than re-stranded. Any transition that moves the item out of
  `active` MUST also clear the label; the standing invariant is that an
  item whose status is not `active` MUST NOT carry it.
- **Mechanical preconditions.** A rework re-dispatch MUST satisfy the
  same mechanical eligibility conditions as the admission valve — a
  resolvable assignee, `factory_safety` null, at least one unheld candidate for
  every success-critical ACP node, and every other ratified admission
  precondition — EXCEPT `ready` membership and the status transition:
  the item is already `active` and already approved. Rework is a
  machine-path CONTINUATION of the admitted work; it MUST NOT re-enter
  `pending-approval`, MUST NOT require a fresh `approve`, and no
  `admission_policy` value plays any part in it.
- **Capacity.** A rework re-dispatch re-occupies the WIP slot the item's
  own `active` row already holds, so the capacity condition EXCLUDES that
  row: the re-dispatch MUST NOT start unless the COUNTED-CLAIM total
  (§"Per-repo WIP cap"), excluding any claim held by the re-dispatched
  item's own row, is below `wip_cap`. The sanctioned `wip_cap: 0`
  dispatch-off posture is preserved (no count is below zero), and the
  `wip_cap: 1` self-deadlock — where the parked item's own row saturates
  the count that must be under the cap — cannot arise.
- **Operator override.** `dispatch --item` MUST accept an item carrying
  `rework:pending` — driving its rework immediately, subject to the SAME
  mechanical eligibility and capacity conditions as the drain path (per
  §"Dispatcher loop invocation surface", `--item` narrows the selection
  and never bypasses it) — and MUST continue to refuse every other
  non-`ready` item as a precondition error. The refusal for a bare
  `active` item SHOULD name the rework route when the item's journal
  shows an unactioned rework disposition but the label is absent (a
  repair hint, not a selection input).
- **`next` is deliberately unchanged.** The `next` surface remains a
  ready-only ranking (§"`next`"); it MUST NOT include rework-pending
  items. The Dispatcher composes rework sequencing externally, per the
  existing "the Dispatcher consumes this ranking and handles sequencing
  externally" cross-reference. Pending rework is visible via
  `list-work-items` (the `rework_pending` field, §"Work-item beads-issue
  mapping") and via the attention surface's composition of
  orchestrator-owned waits.
- **Claim accounting.** An `active` item carrying `rework:pending` with
  no live dispatch lock MUST be classified by the admission accounting
  as **rework-pending**: excluded from the capacity count AND NOT
  recorded as an abandoned claim. It is a sanctioned parked state, not a
  leak.
- **Stranded-state discrimination.** Any surface that derives a
  stranded, abandoned, or leaked-claim finding from "`active` with no
  live dispatch lock" MUST treat `rework:pending` and the `merge-hold:`
  label (§"Dispatcher policy settings" → "The per-item merge hold") as
  discriminators and MUST NOT report a marked or held item as stranded.
  (Coordination:
  `bd-ib-zp3u7y` owns the stranded-dispatch population; the two markers
  partition the populations cleanly.)
- **Vocabulary non-extension.** `blocked_reason` remains exactly
  `needs-human` | `infra-external`, and the rendered `lane_reason`
  vocabulary (`needs-human` / `infra-external` / `dependency`, computed
  by the shared `livespec_runtime.work_items.lifecycle.lane_of`
  authority) MUST NOT gain a `needs-rework` member. Rework-pending is an
  `active`-lane condition, not a block: `blocked` stays reserved for
  external impediments, and the shared runtime and console vocabularies
  stay untouched.

### Per-repo WIP cap

The WIP cap is **per-repo**, sourced from this repo's `.livespec.jsonc`
(the `livespec-orchestrator-beads-fabro.dispatcher.wip_cap` key), default
**5** — NOT a single fleet-wide number. Total LEDGER-level fleet concurrency is the
sum of the per-repo caps. The Orchestrator owns NO host-level ceiling on
concurrently in-flight dispatches; that ceiling belongs to the Fabro
server's own scheduler (§"Host concurrency belongs to the Fabro
scheduler").

`wip_cap` bounds COUNTED CLAIMS ("counted claims" or `counted_claims`
below), which is NOT the same set as rows at status `active`. A row at
status `active` counts against `wip_cap` when, and only when, either of the
following holds:

1. it holds a dispatch lock whose recorded process identifier — that of the
   LOCAL dispatching process — belongs to a live process; or
2. it does NOT hold such a lock, is NOT classified rework-pending (a
   lock-less row carrying `rework:pending` is a sanctioned park, EXCLUDED
   unconditionally per §"Rework-pending re-dispatch" and Scenario 66's
   third sub-scenario — even when its journal is unreadable), and its
   dispatch journal could not be READ.

A row at status `active` that satisfies neither MUST NOT be counted. In
particular, a row whose dispatch reached a green terminal outcome is
reclaimed and MUST NOT be counted, so a repository MAY hold more rows at
status `active` than `wip_cap` without any admission having exceeded the
bound. Every surface that reports capacity MUST NOT present "rows at status
`active`" as if it were the counted quantity.

Term 2 is FAIL-CLOSED BY DESIGN and MUST remain so: an unreadable journal
MUST cause the predicate to count MORE rows, never fewer, so that losing the
journal cannot silently over-admit. A change making an unreadable journal
reduce the count MUST NOT land without a propose-change explicitly retiring
this clause.

The bound governs the Dispatcher's AUTOMATIC admission path — the drain, and
any targeted invocation that enforces the cap (a rework re-dispatch of an
already-`active` parked item drives no ADDITIONAL item into `active` and is
bounded by §"Rework-pending re-dispatch"'s capacity condition instead). It is
NOT absolute. The hand-picked operator path (`dispatch --item`) is a
sanctioned override that admits a single named work-item WITHOUT enforcing
`wip_cap`; this is intended behavior, not a defect, per the 2026-07-30
maintainer ruling. A consumer of this contract MUST NOT treat an over-cap
admission arising from that override as a violation of this section, and any
surface asserting cap conformance MUST scope its assertion to the enforcing
paths.

The counted-claim bound is TENANT-scoped: it MUST count claims across every
checkout of this repository (worktrees, janitor checkouts, and fresh clones
alike), not only the invoking process's own checkout. A checkout holding a
live dispatch lock (term 1 above) registers itself, keyed by the tenant its
committed `.livespec.jsonc` declares, so a claim held live by ANY checkout of
the tenant is visible from every checkout's own admission check — closing
the specific divergence `bd-ib-snyquw.6` measured and tracked (two checkouts
of one tenant reporting disjoint live-claim counts against the same ledger),
where N checkouts could admit independently up to N × `wip_cap`. The
journal-unreadable term (term 2) and the terminal-outcome classification it
depends on (green-terminal reclamation, abandoned-claim detection) remain
per-checkout by design — each checkout reads only its own dispatch journal —
which does not reopen the over-admission divergence just closed: it biases
toward counting MORE from a given checkout's own view, never fewer, matching
term 2's existing fail-closed guarantee. Per-checkout counting REMAINS the
implementation of term 2 and its dependents; tenant-scoping applies fully to
term 1 and MUST NOT be read as extended to those by this section.

`wip_cap`'s value domain is a **non-negative integer**: `0` is a valid
committed value, and it is the sanctioned consumer-project DISPATCH-OFF
posture value. Under a `wip_cap` of `0` the admission valve's capacity
condition (`counted_claims < wip_cap`, §"Admission valve (`ready →
active`)") holds for no item, so the Dispatcher admits nothing. Every
surface that validates or reads `wip_cap` MUST accept `0`: a read of a
committed `0` MUST resolve to `0` — it MUST NOT be treated as
out-of-domain and fall back to the default. `0` is valid for `wip_cap`
ONLY. Every other integer setting remains a POSITIVE integer: the
per-item-overridable caps (`review_fix_cap`, `acceptance_rework_cap`,
§"Dispatcher policy settings") remain positive integers, and `wip_cap`
has no per-item override and no `clear` sentinel, so no sentinel
ambiguity arises. A schema or validation change that imposes a minimum
above `0` on `wip_cap` MUST NOT land without a propose-change that
explicitly retires this clause.

Every operator-facing surface that reports `wip_cap`, or that refuses a
dispatch on capacity grounds, MUST identify the value as this repo's
PER-REPO CLAIM cap rather than by the unqualified word "cap". Such a
surface MUST NOT present the value in a form readable as a host-wide or
per-server ceiling. A capacity refusal MUST state that host-run concurrency
is governed separately (§"Host concurrency belongs to the Fabro scheduler")
and is NOT what the refusal reports. These requirements bind the refusal
text and any status, doctor, or attention surface that echoes the cap; they
do NOT change what is counted, which this section already governs.

### The loop probe (`probe --item`)

`probe --repo <path> --item <work-item-id> [--json]` demonstrates the
steady-state loop by driving ONE designated, ALREADY-FILED work-item
through the entire cycle — admission, factory run, merge, post-merge
acceptance, terminal `done` — through the SAME published machinery every
ordinary dispatch uses, never a parallel path, with assertions at each
stage. The probe:

- MUST refuse to run without `--item`, and MUST NOT create, file, or
  clone any work-item under any circumstances: the designated item is
  filed by the operator through `capture-work-item`, where consent and
  Definition-of-Ready evaluation are native. §"Consent boundary" applies
  to the probe unchanged and without exception.
- MUST refuse a designated item whose EFFECTIVE `acceptance_policy` is
  not `ai-only`, naming the label to set at filing: under the default
  `ai-then-human` (and under `human-only`) a passing item PARKS in
  `acceptance` awaiting the human `accept` valve, so terminal `done` is
  machine-reachable only for an `ai-only` item. The operator grants that
  policy when filing the probe item — the probe itself sets nothing.
- Each invocation CONSUMES its designated item (driven to terminal
  `done`); a standing health cadence therefore files a fresh probe item
  per run through `capture-work-item` — the per-run filing consent is
  intended, not incidental — and consumers report against the LATEST
  probe outcome.
- MUST run with an asserted invoker identity and MUST FAIL when its own
  journaled records resolve to a fallback-derived identity (§"Journal
  invoker attribution") — a probe is an operator act, and an
  unattributed probe proves nothing about attribution.
- MUST assert, in stage order: the designated item's effective
  acceptance criteria (§"Effective acceptance criteria") parse non-empty
  BEFORE dispatch; every journaled preflight and post-merge step outcome
  in the probe cycle is a pass (any warn-and-proceed, skipped-step, or
  failed-step record FAILS the probe); the acceptance verdict is
  grounded in observed evidence; and the item reaches `done`.
- **Reserved identifiers.** At start the probe MUST journal a probe run
  identifier of the form `probe:<work-item-id>:<utc-start-timestamp>`;
  the probe's reserved identifier set is that run identifier plus the
  designated item's id, and every hard residue assertion below keys on
  that set.
- **Sanctioned target path.** The designated probe item's change MUST
  confine itself to the `.livespec-probe/` directory at the governed
  repository's root. Confinement is asserted BEFORE the merge: the
  driven cycle MUST verify the change's paths and FAIL WITHOUT MERGING
  when the change escapes the directory. The post-merge diff check
  remains as the backstop; if an escaping change nonetheless merged, the
  probe MUST FAIL naming the merged commit and the revert obligation
  (the operator reverts it — the probe mutates nothing beyond its
  cycle). Probe artifacts are inert: the artifact is a single file the
  next probe's change replaces, deleting the directory MUST never break
  the governed repository, and the operator MAY remove it at any time —
  removal after a pass is the sanctioned cleanup and no surface may
  complain about its absence. This is what makes the merge-by-design
  safe to aim at a real default branch.
- **Residue assertions, scoped.** The probe MUST snapshot the attention
  surface and the ledger state BEFORE the cycle and again AFTER. HARD
  assertions key on the reserved identifier set only: the designated
  item reached `done`, and no attention item referencing the reserved
  identifiers remains. The unrelated before/after delta is REPORTED,
  never asserted: over a cycle spanning admission to acceptance,
  unrelated attention items legitimately appear and resolve through
  concurrent operator activity, and failing on their movement would be
  the mirror image of the global-emptiness assertion this contract
  forbids. The probe MUST NOT assert global attention emptiness, MUST
  NOT require any unrelated state to be absent, and MUST NOT require any
  unrelated state to be preserved — it reports the unrelated delta for
  the operator. An attention or ledger source that cannot be read at
  either snapshot FAILS the probe with a source-unavailable outcome:
  unavailability MUST NOT be read as emptiness, resolution, or success.
- **Failure leg.** On any stage failure the probe MUST report the stage
  reached, the item's current lifecycle state, and the named remedy, and
  MUST leave the item in whatever state the ordinary machinery put it —
  visible and disposable through the normal valves and recovery
  surfaces, never auto-deleted, never auto-closed, never hidden.
- **Fixture-creating probes.** Any probe variant that CREATES its
  fixture — including defect-seeding negative controls such as an
  empty-criteria item — MUST run only against the hermetic fake backend
  or a disposable test tenant, never through the live Dispatcher against
  a live tenant.

The probe is a demonstration and health primitive: a passing probe is
evidence the composed loop is live; consumers that report loop liveness
SHOULD condition on a passing probe rather than on documents.

### Dispatch preflight and post-merge step discipline

This section governs a NAMED, CLOSED step set, each step carrying a
stable identifier: `source-checkout` and `master-ci` (pre-dispatch
preflights), `janitor-bootstrap` (the post-merge janitor's bootstrap
of the governed repository's commit-refuse hooks), and the governed-repo
integration points the up-front validation pass below checks —
`janitor-check-suite` (the janitor's check-suite invocation),
`janitor-core-provisioning` (the livespec-core clone the janitor
provisions), and the factory-sandbox toolchain premises dispositioned as
declared-and-validated below. The set is extensible only by ratification. Gauge and observability postures ratified
elsewhere — the fail-closed cost gate's hand-picked warn posture, and
any storage-headroom gauge posture — are NOT steps of this section and
are unaffected by it.

A PRE-DISPATCH step has exactly THREE sanctioned outcomes:

1. **Pass**, journaled.
2. **Refusal**: a pre-dispatch step that fails, or cannot verify what it
   exists to verify, MUST refuse the dispatch as a precondition error
   (exit `3`), journaled with the step's identifier, naming the missing
   piece and its remedy. Absence of proof is refusal, never
   proceed-and-hope.
3. **Waived proceed**: a step covered by an explicit committed waiver
   proceeds, and the waived failure is journaled AS waived — visible,
   never silent.

A POST-MERGE step, which can only OBSERVE its failure after the merge,
has exactly three sanctioned outcomes: **pass**, **waived proceed**, or
a first-class **DEGRADED outcome** recorded on the dispatch's outcome
record, carrying the step's structured identifier (never only free
prose), the missing required integration point, and the remedy. For
either class there is no further outcome: a silent warn-and-proceed
branch on a named step is forbidden.

A degraded outcome PERSISTS:

**Cross-dispatch persistence.** When the journal's outcome history for
the repository names a missing REQUIRED integration point (a degraded
post-merge outcome, e.g. the governed repository no longer providing its
commit-refuse-hook bootstrap recipe), the Dispatcher MUST refuse the
NEXT dispatch for that repository at the pre-dispatch gate — exit `3`,
naming the missing integration point, the originating outcome record,
and the remedy — until either:

- a pre-dispatch RE-VERIFICATION of that specific integration point
  observes it provided (every step of the closed set MUST have a
  pre-dispatch verification for the integration points its degraded
  outcomes can name; for `janitor-bootstrap` that is the resolvability of
  the governed repository's DECLARED hook-install recipe
  (`dispatcher.janitor_bootstrap.recipe`, or the fleet default convention
  when undeclared), per "Janitor-bootstrap recipe resolution" below) — and
  the passing
  re-verification MUST journal a CLEARING record naming the step
  identifier and the degraded outcome record it clears, so the refusal's
  end is as durable as its start; or
- a committed waiver covers the step.

A repository that fails to provide a required integration point
therefore stops the factory FOR THAT REPOSITORY, visibly, with the
remedy named — it does not degrade silently on every dispatch forever.
The hard refusal IS the mechanism that makes the adopter provide the
missing piece.

**`dispatcher.step_waivers`** (committed `.livespec.jsonc`; a list of
waiver entries, each carrying `step` — one of this section's stable step
identifiers, `owner` — a named responsible party, and `reason` —
non-empty prose). A waiver is scoped to its named step only. The setting
joins the ratified COMMITTED-CONFIGURATION-ONLY class (§"Control surface
and audit"): a dial that relaxes a safety refusal is committed
configuration with a reviewable diff, never a remote toggle. An expired
rationale is the owner's to retire; the journal records every waived
proceed with the waiver's owner, so a standing waiver is visible on
every use.

**`dispatcher.janitor_bootstrap`** (committed `.livespec.jsonc`; a
`recipe` key — the command the post-merge janitor invokes to bootstrap the
governed repository's commit-refuse hooks, and whose resolvability the
pre-dispatch re-verification checks). The key describes the repository's
hook-install topology, has no per-item override, and joins the ratified
COMMITTED-CONFIGURATION-ONLY class (§"Control surface and audit").

**Master-CI pipeline resolution.** The master-CI preflight MUST resolve
the repository's default-branch pipeline from what the repository
DECLARES: the committed `dispatcher.master_ci` key (`workflow` — the
workflow display name or file name; `job` — the aggregate green job
name). The BRANCH is never configured or hard-coded: the preflight MUST
resolve the target default branch per §"Self-contained plugin
dispatch"'s default-branch-resolution rule (the shipped `--branch
master` literal is a violation of that ratified rule this clause's
implementation retires). When the key is absent, the preflight MUST use
the default convention (workflow `CI`, aggregate job `ci-green`) — a
declared default, not a silent assumption: the refusal text for an
unresolvable pipeline MUST say which resolution was attempted (declared
or default) and name the key that declares it. A pipeline that cannot be
resolved — undeclared and not matching the default convention, or
declared but not found — is a journaled precondition refusal;
declaration changes WHAT is looked up, never WHETHER absence of proof
refuses.

**Janitor-bootstrap recipe resolution.** The `janitor-bootstrap` step MUST
resolve the governed repository's commit-refuse-hook install recipe from
what the repository DECLARES: the committed `dispatcher.janitor_bootstrap`
key's `recipe` value. The post-merge janitor MUST invoke that declared
recipe to bootstrap the hooks, and the pre-dispatch re-verification named
above MUST check that the declared recipe is resolvable in the governed
repository (present and invokable) — the integration point whose provision
clears a prior degraded outcome and whose absence refuses the next
dispatch. When the key is absent, resolution MUST use the fleet default
convention (`just install-commit-refuse-hooks`) — a declared default, not a
silent assumption: a refusal for an unresolvable recipe MUST say which
resolution was attempted (declared or default) and name the key that
declares it. Declaration changes WHAT recipe is bootstrapped and
re-verified, never WHETHER absence of proof refuses; a repository whose
declared or default recipe is unresolvable is a journaled degraded/refused
outcome under the rules above, and an adopter that genuinely provides no
such recipe carries a `janitor-bootstrap` step waiver (the sanctioned
escape, unchanged). This is the same declaration-over-assumed-tooling shape
the "Master-CI pipeline resolution" rule above gives the `master-ci` step.

This clause RETIRES the three shipped fail-open cases the current
preflight documents ("no `gh` binary, no stored `gh` credential, or no
master CI runs yet" proceed unchecked today): each becomes an unprovable
refusal naming its remedy (install or authenticate `gh`; or commit a
`master-ci` step waiver, the sanctioned escape for a repository that
genuinely cannot verify). A still-pending latest run remains an
unprovable refusal (retry when the run concludes). `dispatcher.master_ci`
describes the repository's CI topology, has no per-item override, and
joins the ratified committed-configuration-only class.

**Janitor check-suite resolution.** The janitor's check-suite invocation
— the command the post-merge janitor runs in its fresh checkout (host
side) AND the equivalent in-sandbox janitor hard-gate the factory workflow
runs against the governed-repo clone — MUST resolve from what the
repository DECLARES: the committed `dispatcher.janitor.check_suite` key.
The declared command is invoked VERBATIM; the orchestrator MUST NOT
prepend `mise exec --` or any other tool wrapper of its own to a declared
command (imposing the fleet's invocation wrapper on someone else's command
is the same assumed-tooling defect the `janitor-bootstrap` clause retires
one layer down). When the key is ABSENT — presence tested directly, so a
key written as JSON `null` is a present declaration that names nothing and
REFUSES rather than sliding onto the convention — resolution MUST use the
fleet default convention (`mise exec -- just check-no-workflow-edits
install-worktree-pack check` for the host janitor, and the equivalent
in-sandbox check for the workflow gate) — a declared default, not a silent
assumption. A refusal for an unresolvable check-suite MUST say which
resolution was attempted (declared or default) and name the key.
Declaration changes WHAT check-suite runs, never WHETHER absence of proof
refuses. The uncommitted per-invocation `--janitor` override MUST NOT
displace a committed `dispatcher.janitor.check_suite` declaration: an
uncommitted per-invocation argv silently overriding committed policy is
exactly what the committed-configuration-only class forbids (§"Control
surface and audit") — a dial that overrides a safety-relevant committed
policy is committed configuration with a reviewable diff, never an
uncommitted per-invocation argv; where `--janitor` remains it is scoped
to a repository that has declared no check-suite. `dispatcher.janitor`
describes the repository's
check topology, has no per-item override, and joins the ratified
committed-configuration-only class.

**Janitor-core provisioning resolution.** The livespec-core clone the
janitor provisions into its checkout resolves its REF from the
already-required `livespec-orchestrator-beads-fabro.compat.pinned`
declaration (§"`compat` block"). The Dispatcher MUST NOT silently
substitute a moving branch tip for that declaration: when `pinned` is
absent or unreadable in a governed repository, janitor-core provisioning
is a journaled degraded/refused outcome that names the missing
declaration, NOT a silent fall-through to a bare `master`/`main` tip that
can move under an in-flight dispatch. This forbids only the SILENT
DEFAULT, not a declared value: a repository MAY still declare
`pinned: "master"` during bootstrap — the existing ratified state that
fires doctor's `contract-version-compatibility` `warn` (§"`compat`
block") — because that is a value the repository explicitly chose, not an
unstated default the Dispatcher imposed. The clone's REPOSITORY URL,
hardwired today, gains a committed declaration under the same `compat`
block — `core_repo` (optional; when absent, the fleet livespec-core
repository) — so an adopter can point core provisioning at its own mirror;
the fleet default applies only when `core_repo` is undeclared, and a
present-but-unusable `core_repo` is a defect that refuses rather than
sliding onto the fleet default. `compat.core_repo` describes the
repository's core-provisioning topology, has no per-item override, and
joins the ratified committed-configuration-only class.

**Factory-sandbox toolchain disposition.** Every factory-sandbox prepare
premise that today assumes the fleet toolchain — `mise` / `.mise.toml`
resolution, the `lefthook` Red-Green-Replay gate installation, the
`livespec_dev_tooling` package prepare steps and the `livespec-step-timer`
wrapper, and the node-prompt tool wrappers (`mise exec -- git …`,
`mise exec -- just check`) — MUST be EITHER declared-and-validated (an
integration point checked by the validation pass below) OR
ratified-as-no-op by a named clause. A prepare or node-prompt premise that
is neither MUST NOT silently degrade for an adopter that lacks it: silent
behavioral divergence between a member and an adopter at a dispatch-path
seam is forbidden. §"Self-contained plugin dispatch" → "Target-local
workflow" already ratifies that a repository's prepare chain is a
target-toolchain fact and that an adopter MAY carry its own
`implement-work-item` workflow; this clause additionally requires that
where the plugin-default workflow imposes a fleet-toolchain premise on the
governed repo, that premise is a declared, validated integration point
rather than an unstated assumption.

**Up-front integration-contract validation pass.** The Dispatcher MUST run
a single validation pass over the COMPLETE set of governed-repo
integration points declared or defaulted by this section — `master-ci`,
`janitor-bootstrap`, `janitor-check-suite`, `janitor-core-provisioning`,
and every factory-sandbox toolchain premise dispositioned as
declared-and-validated above — at the first dispatch admitted against a
repository, and again whenever the executing plugin build or the
repository's declaration changes. When any point is unmet the pass MUST
refuse the dispatch as a pre-dispatch precondition error (exit `3`,
journaled) BEFORE any dispatch, merge, or factory run, and the refusal
MUST enumerate EVERY unmet point in one message — not the first failure
alone. Each point is thereby met, declared-and-met, or a named refusal
item; there is no per-instance discovery one broken dispatch at a time, no
post-merge stranding of an item on an integration premise, and no silent
degrade. A committed step waiver (this section's `dispatcher.step_waivers`)
covering a named point proceeds it AS waived, visibly.

**Contract versioning.** When an upgraded plugin build ADDS an
integration-point expectation to this set, the validation pass MUST fail
fast for a repository that has not yet declared or satisfied it, naming the
new point, and MUST NOT strand an already-admitted, mid-pipeline item on an
expectation that did not exist when its dispatch was admitted. This
generalizes the cross-dispatch-persistence guarantee above from the single
`janitor-bootstrap` integration point to the whole set.

**Post-merge and reconcile janitor venue.** The post-merge janitor and the
reconcile-merged janitor MUST provision their fresh checkout at the target
repository's DEFAULT-BRANCH TIP that contains the item's merge — resolved
per §"Self-contained plugin dispatch" → "Default-branch resolution" — NOT
at the item's historical merge commit. Pinning the venue to the historical
merge sha makes a janitor-environment fix that lands AFTER an item's merge
unable to ever clear that item, a deterministic reconcile deadlock whose
only in-band exit is a one-off `--janitor` override. Provisioning at the
merged tip lets a later environment fix clear historical items on the next
reconcile, while the venue still proves the item's merge is present because
the tip contains it; the janitor MUST confirm the resolved tip contains the
item's merge, and a resolved tip that does NOT contain it is a DEGRADED
post-merge outcome under this section's post-merge outcome rules (carrying
the step's structured identifier, the missing point, and the remedy),
never a silent proceed. This clause changes only the janitor's provisioning
VENUE; it is not a new step of the closed set and adds no pre-dispatch
refusal — a failed venue-provisioning is handled exactly as any other
post-merge janitor failure (§"Dispatcher admission, WIP cap, and post-merge
acceptance"), leaving the item as the existing failed-janitor contract
leaves it. If a future change deliberately retains merge-sha pinning
anywhere for reproducibility, this section MUST state how a post-merge
environment fix clears an earlier item without a manual override.

**Merge-strategy resolution.** The strategy by which a dispatched item's
approved pull request lands on the default branch is the schema field
`dispatcher.merge_mode`, resolved through the one generic resolver and read as
the SEMANTICS of that field. It is a DEFAULTED field: an absent key resolves to
the `FleetDefault` value `rebase`, preserving today's behaviour, and a present
key MUST be one of the closed enum `rebase` or `squash` — any other value
resolves to `Defective` naming `dispatcher.merge_mode`. A true merge commit is
NOT an admitted value: two post-merge paths read the merge commit directly and
break on its combined diff — acceptance's fallback merged-diff read
(`git show --format= <merge_sha>`, empty for a clean merge) and the
`reject:regroom` revert (`git revert --no-edit <merge_sha>`, which needs an `-m`
parent selector on a merge commit) — so admitting `merge` is a separate
obligation that must ratify those changes. The resolved value projects, per
"Resolve once, project everywhere", into BOTH the Dispatcher's auto-merge argv
(the `gh pr merge` method flag) and the `pr.md` prompt variable the in-run agent
uses to arm auto-merge — two seams of one resolved object, neither authoritative,
kept in agreement by the seam-equivalence check — and it is one of the fields
that check ranges over. Only the merge-METHOD flag is projected; the branch
rebases the workflow performs onto the default branch before pushing are a
different operation unaffected by this field.

**Sandbox commit-refuse exemption resolution.** A Fabro sandbox is a fresh full
clone, structurally indistinguishable from a primary checkout, so a governed
repository's commit-blocking hooks would refuse the sandbox's Red-Green-Replay
commits. The git-config marker key that exempts those commits is the schema field
`dispatcher.sandbox_exempt_marker`, resolved through the one generic resolver and
read as the SEMANTICS of that field. Its admitted value space is CLOSED to the
single `FleetDefault` value `livespec.sandboxExempt`; any other declared value
resolves to `Defective` naming `dispatcher.sandbox_exempt_marker`, because the
canonical commit-refuse hook body reads that key literally and a divergent key
would be set but never honored. The resolved value has two ratified halves.
First, the orchestrator MUST set that marker to `true` in the sandbox before any
Red-Green-Replay commit, as a PROJECTION of the field into the prepare step,
never a hardcoded literal. Second, a governed repository's COMMIT-BLOCKING hooks
MUST HONOR the marker: when the resolved marker key reads `true` in the sandbox's
git config, the hook MUST NOT refuse a commit on primary-checkout-detection
grounds, while every Red-Green-Replay gate the hook delegates still fires. Honor
is a governed-repository obligation the adopter fixture (§"Governed-repository
integration constraints") exercises. The marker is local git config only and
never leaves the ephemeral sandbox (a push carries refs, not config).

**Members-and-adopters-identical audit of the step and preflight set.**
Every obligation in the named closed step set, and the dispatch-time
preflight chain that feeds it, is dispositioned here against the principle
that members and adopters consume the orchestrator IDENTICALLY
(§"Self-contained plugin dispatch"):

- `source-checkout` (pre-dispatch): adopter-neutral as written. It verifies
  the presence of a source checkout — a generic git fact carrying no
  fleet-toolchain assumption. No change.
- `master-ci` (pre-dispatch): made declaration-based by v074 via
  `dispatcher.master_ci` with a declared default convention.
  Adopter-neutral. No further change.
- `janitor-bootstrap` (post-merge, with pre-dispatch re-verification): made
  declaration-based by this clause via `dispatcher.janitor_bootstrap` with a
  declared default convention.
- `janitor-check-suite` (post-merge host janitor + in-sandbox workflow gate):
  made declaration-based by "Janitor check-suite resolution" via
  `dispatcher.janitor.check_suite` with a declared default convention; the
  uncommitted `--janitor` override no longer displaces committed policy.
- `janitor-core-provisioning` (post-merge): made declaration-based by
  "Janitor-core provisioning resolution"; the repo URL gains a declaration
  surface and the ref default stops being a moving branch ref.
- Factory-sandbox toolchain premises (`mise`/`.mise.toml`, `lefthook`
  gates, the `livespec_dev_tooling` prepare steps and `livespec-step-timer`
  wrapper, and the node-prompt tool wrappers): dispositioned by
  "Factory-sandbox toolchain disposition" as declared-and-validated
  integration points OR ratified-as-no-op — never a silent degrade; under
  §"Repository integration contract" both arms are schema fields read by
  the one generic resolver, the no-op arm as an explicit `FleetDefault`
  value.
- The dispatch-time baseline conformance gate (§"Dispatch-time baseline
  conformance gate"): its `uv sync` prepare step, its `livespec_dev_tooling`
  Verifiers, and the canonical commit-refuse hook it installs are the FLEET
  toolchain realization. §"Self-contained plugin dispatch" → "Target-local
  workflow" already ratifies that prepare steps are target-toolchain facts
  and that an adopter MAY carry its own `implement-work-item` workflow with
  its own prepare chain; the declared `dispatcher.janitor_bootstrap.recipe`
  is the janitor-side analogue of that already-ratified disposition. Already
  dispositioned; no change here.
- `merge-strategy` (post-merge auto-merge method): made declaration-based by
  "Merge-strategy resolution" via `dispatcher.merge_mode` with a declared
  `FleetDefault` of `rebase`. A fleet member that declares nothing keeps rebase
  (satisfying this repo's inherited member-scoped "rebase-merge-only master"
  constraint, `constraints.md`); an adopter that merges by squash declares
  `squash`. Neither carries a divergent workflow fork for the merge method.
- `sandbox-exempt-marker` (in-sandbox commit-refuse exemption): made
  declaration-based by "Sandbox commit-refuse exemption resolution" via
  `dispatcher.sandbox_exempt_marker` with a declared `FleetDefault` of
  `livespec.sandboxExempt` and a value space closed to that one value. A fleet
  member honors it through the canonical commit-refuse hook body; an adopter MUST
  honor the same resolved marker in its own commit-blocking hooks, and the
  adopter fixture fails if it does not.

- Every step and preflight, by construction: under §"Repository
  integration contract" each integration point is a schema field, read
  through the one generic resolver and validated against the adopter
  fixture, so a new obligation cannot be dispositioned differently for a
  member and an adopter without failing the adopter leg.

The set is closed: extending it, or adding a new dispatch-time or post-merge
obligation, requires ratification and MUST carry its own
members-and-adopters disposition at that time.

**Scoped checks report vacuity, not success.** A file-scoped check — a
janitor or otherwise scoped check that selects the diff files it inspects
— whose scope MATCHED ZERO files in the diff under judgment MUST report a
distinct vacuous-match outcome, NOT a pass. A vacuous-match outcome is not
failure evidence either: it composes as "this check observed nothing", and
a gate MUST NOT count a vacuous-match outcome toward passing (nor toward
failing). This is the janitor-gate analogue of the acceptance evidence
rule (§"Post-merge acceptance (`acceptance → done`)" → "The evidence rule"): a check that
observed nothing has produced no evidence, so reading its zero matches as
green is a pass manufactured from absent evidence. A zero-change merged
diff is the case that makes this observable — a file-scoped check over an
empty diff matches zero files by construction — and it is exactly how a
scoped `check-no-workflow-edits` passed vacuously over an empty merge for
all four review rounds.

### Repository integration contract

The set of integration points the orchestrator requires of a governed
repository is an API, and it is typed. This subsection supersedes the
per-key MECHANISM of "Master-CI pipeline resolution", "Janitor-bootstrap
recipe resolution", "Janitor check-suite resolution" and "Janitor-core
provisioning resolution" above — each of those clauses remains ratified as
the SEMANTICS of the corresponding schema field and is read as such — and
it absorbs "Up-front integration-contract validation pass" and "Contract
versioning" as the schema-validation rule below. It ALSO supersedes the
mechanism of "Factory-sandbox toolchain disposition": that clause's
declared-and-validated arm is realized as schema fields read by the generic
resolver, and its ratified-as-no-op arm is expressed as a schema field
whose `FleetDefault` is an explicit no-op VALUE — never an absent key, so
the no-op is declared and validated like every other point rather than
inferred from silence. No committed key is introduced or renamed by this
subsection. Of the v090 implementation followups, the merged
`declared-janitor-check-suite` is MIGRATED onto the generic resolver, while
the unmerged `declared-core-provisioning`, `dispatch-integration-validation-pass`
and `declared-sandbox-toolchain` followups are SUPERSEDED by this
subsection's own followups and are not to land as further per-key
resolvers.

**One schema.** Every integration point the orchestrator requires of a
governed repository MUST be a field of a single versioned, machine-readable
`RepoIntegrationContract` schema shipped in the plugin payload: the
check-suite per venue (host janitor and in-sandbox gate), the bootstrap
recipe, the master-CI pipeline, the core-provisioning repository and ref,
the prepare-toolchain premises, the default branch, the post-merge merge
strategy, and the sandbox commit-refuse exemption marker. An integration
point that is not a schema field is not a requirement the orchestrator may
impose. Commands MUST be typed as argv arrays, never shell strings. Where a
point legitimately differs by venue, the venue MUST be an explicit schema
dimension, never two divergent literals.

**One resolver, no silent path.** Every integration point MUST be read
through one generic, schema-driven resolver whose result is the sum type
`Declared(value) | FleetDefault(value) | Defective(key, reason)`. The
schema declares, PER FIELD, whether a fleet default exists: on a DEFAULTED
field a truly ABSENT key resolves to `FleetDefault`, while on a REQUIRED
field — one whose ratified semantics admit no safe default, such as
`compat.pinned`, where the only substitutable value would be the moving
branch tip its own clause forbids — an absent key resolves to `Defective`
naming the absence. A present-but-unusable key resolves to `Defective` on
every field, and no code path MAY substitute a default for a `Defective`. The existing committed keys (`dispatcher.master_ci`,
`dispatcher.janitor_bootstrap.recipe`, `dispatcher.janitor.check_suite`,
`compat.pinned`, `compat.core_repo`) and their ratified
absent/default/defective semantics are PRESERVED as schema fields, so no
adopter declaration migrates; the per-key resolver modules are retired in
favor of the generic one.

**Resolve once, project everywhere.** The Dispatcher MUST resolve the
contract exactly once per dispatch, on the host, at plan-build time, into a
frozen `ResolvedIntegrationContract` that is journaled with the dispatch
record and carried on the dispatch plan. Every seam — the host janitor
argv, the fabro run inputs, prompt variables, prepare-step parameters —
MUST be a PROJECTION of that resolved object. No seam MAY re-derive an
integration value from configuration or from a literal at a later point;
the sandbox receives values and never resolves. This generalizes the rule
that ACP adapters ride the plan because re-deriving at launch is how the
record and the run come to disagree.

**Typed workflow inputs and the seam-equivalence check.** The
`implement-work-item` workflow payload MUST declare every input it consumes
with a type and a default. The set of `inputs.*` tokens the workflow
references, the set of inputs the Dispatcher renders from the
`ResolvedIntegrationContract`, and the schema's projectable fields MUST be
identical. The identity ranges over the integration inputs. Two further
disjoint families share the workflow's input table and the check MUST
classify each explicitly and hold it to the same resolved-position rule:
the ACP-adapter inputs of §"Codex ACP node model pins", and the PER-ITEM
POLICY INPUTS — the review-fix visit cap, the merge-on-review-cap outcome,
and `merge_hold` (§"Dispatcher policy settings" → "The per-item merge
hold") — which are not schema fields but projections of the item's
effective policy, resolved host-side at plan-build time and journaled on
the dispatch record so the record and the run agree. A declared input
belonging to none of the three families MUST fail the check.
Every token MUST additionally sit in a position RESOLVED BEFORE
THE SANDBOX EXECUTES IT, and exactly two resolvers are admitted: the ENGINE,
which renders declared graph-node attributes at run-create time; and the
Dispatcher's run-config OVERLAY, which substitutes resolved contract values
into the committed run config host-side before the run is submitted. A token
in a position resolved by NEITHER MUST fail the check. A CI check MUST
enforce this equivalence, so a templating question is answered statically
rather than by a production dispatch.

The check MUST be resolver-aware rather than resolver-blind. For each
admitted position the check MUST record which resolver it depends on, and an
overlay-resolved position MUST be backed by an actual host-side substitution
in the Dispatcher — so that removing that substitution turns the position
back into a failing one rather than leaving a silently false classification.
The engine-resolved set MUST remain evidence-bearing: a position enters it
only on recorded evidence that the pinned engine build expands that
attribute, and a numeric or otherwise typed attribute MUST NOT be admitted on
the grounds that it looks like a string. Overlay substitution MUST be a
projection of the SAME `ResolvedIntegrationContract` the `fabro run --input`
pairs are rendered from, so the run config and the run's bound inputs cannot
disagree, and a substituted value MUST be escaped for the syntactic context
it lands in.

This check answers the templating question statically only for positions
whose resolver is known; it CANNOT establish that the pinned engine actually
renders a position. That obligation belongs to recorded evidence about the
engine build, and a change of the pinned engine invalidates it.

**Contract version is schema version.** The executing plugin build MUST
name the contract schema version it requires. At the first dispatch
admitted against a repository, and again whenever the executing build or
the repository's declaration changes, the Dispatcher MUST validate the
repository's declaration against that version and MUST refuse the dispatch
as a pre-dispatch precondition error (exit `3`, journaled) enumerating
EVERY `Defective` point in one message; an already-admitted, mid-pipeline
item MUST NOT be stranded on an expectation added by a later build. No
hand-maintained list of keys exists anywhere: a schema field is how an
already-RATIFIED obligation is realized, and adding one means the
validation pass, the seam check, and the governed-repository fixtures
(`constraints.md` §"Governed-repository integration constraints") pick it
up without further edits. This does not relax the closed-set rule above:
a NEW dispatch-time or post-merge obligation still requires ratification
with its own members-and-adopters disposition, and a schema field MUST NOT
be added for an obligation this specification has not ratified.

### Host concurrency belongs to the Fabro scheduler

The Orchestrator owns **no** host-level dispatch concurrency limit. The number
of factory runs permitted to execute concurrently on the shared host is the
Fabro server's own `server.scheduler.max_concurrent_runs` — host-scoped
configuration read by the long-lived daemon that actually owns runs. The
Orchestrator MUST NOT duplicate, re-implement, configure, or enforce that
ceiling, and MUST NOT expose a committed configuration key that purports to
bound host-wide dispatch concurrency.

Consequently the Dispatcher MUST NOT refuse a dispatch on host-concurrency
grounds, and MUST NOT maintain any host-global admission gauge, claim, or lock
artifact for that purpose. A dispatch attempted while the host is already at
the scheduler's limit MUST proceed to submission: the Fabro server accepts the
run and holds it in its own queue, promoting waiting runs in FIFO order as
capacity frees. Queueing at the scheduler is the sanctioned behavior; a
client-side refusal is not. Reconciling an orphaned run under §"A factory
run never awaits a human" is not a host-concurrency refusal and not a
host-global gauge: it releases capacity the ledger already says is unowned,
and it never refuses, defers, or counts a dispatch.

`wip_cap` (§"Per-repo WIP cap") is therefore the ONLY concurrency control the
Orchestrator owns. It bounds this repo's COUNTED CLAIMS (§"Per-repo WIP
cap") at the Ledger level — NOT its rows at status `active` — and MUST NOT
be read as, or extended into, a host-wide bound. A single
repo consequently tops out at its own `wip_cap` even when the host scheduler
would permit more; the remaining host capacity is reachable when another repo
dispatches. This is intended, not a defect to be corrected by re-adding a
host-level key.

The Orchestrator MUST NOT report the Fabro scheduler's
`server.scheduler.max_concurrent_runs` as its own bound, and MUST NOT derive
available capacity from it on any surface. Reading that value to reason
about this repo's admission is a category error: the two ceilings govern
different objects and coincide in value only by accident. A surface that
names host capacity at all MUST attribute it to the Fabro server and MUST
NOT imply the Orchestrator enforces it.

The counted-claim bound (§"Per-repo WIP cap") is TENANT-scoped and MUST be
computed from this repository's own state ONLY — its ledger rows, its
dispatch locks, and its dispatch journal, across every checkout of the
tenant. It MUST NOT be read as licensing any observation of the Fabro host
or of any OTHER repository's state. Tenant-scoped bookkeeping across this
repository's own checkouts is NOT host observation and is NOT barred by this
section; the two are independent, and a future change making the count
genuinely tenant-wide does not require retiring this clause. Separately, the
fact that a claim can stop being counted while its remote Fabro run
continues to execute is a KNOWN and ACCEPTED consequence of counting
dispatch-lock liveness rather than remote run status, not a defect to be
corrected by teaching the counter about remote run liveness — correcting
THAT would require host observation, which this section forbids; any such
change MUST NOT land without a propose-change explicitly retiring this
clause.

### Provider spend containment

The factory spends a metered, exhaustible allowance on every model provider it
dispatches against, and those allowances are NOT interchangeable: the fleet
holds a single OpenAI Codex subscription against several Anthropic
subscriptions, so an hour of Codex allowance is the scarce resource and an hour
spent producing nothing is not recoverable. Containment is therefore a stated
obligation of the Dispatcher, not a tuning preference.

**No dispatch into a known-exhausted candidate chain.** Before claim, the
Dispatcher MUST filter every success-critical node's ordered candidates by the
versioned observed availability holds of §"Factory-configurable ACP fallback
priority". It MUST refuse only when at least one such chain is empty. A known
dead primary with an eligible fallback therefore does not refuse the run; a
known-exhausted complete chain does.

**No cross-vendor burn on a dead implementer.** Once a run's implementer node
has terminated without producing any change to the worktree relative to the
dispatch base, the workflow MUST NOT continue to spend a SECOND vendor's
allowance evaluating its absent output. Review, review-fix, and disposition
rounds against a tree byte-identical to the dispatch base MUST NOT be executed.
The run is finalized with the implementer's own failure as its surfaced cause.

**Observed, not predicted.** A hold MUST derive from a real candidate attempt:
either the typed condition on a terminal failed run or an idempotently projected
`agent.acp.failover` event from a run of any eventual outcome. The latter is
load-bearing: a primary may report an eligible failure before its fallback
succeeds, and the successful run still records that observation. A hold MUST NOT
derive from credential material, catalogs, a host-side probe, or provider reset
claims. Host and sandbox credential state diverge by construction under
§"Worker credential projection".

**Every observed availability record is scoped, versioned, and expires.** A
current record MUST carry `scope`, opaque non-secret `hold_key`, optional
`candidate_key`, stable `observation_id`, occurrence time, and bounded expiry.
Expiry is computed from occurrence, never later ingestion. A record MUST NOT be
permanent, whatever provider, account, router, or hosting arrangement it names.
Provider timing MAY be retained only as unverified provenance and MUST NOT
become the expiry. Legacy provider-only records remain readable and effective
until retirement as domain holds against candidates whose built-in compatibility
alias names that provider, plus identity-less legacy candidates under
§"Factory-configurable ACP fallback priority", which every live legacy record
covers; they MUST NOT be ignored or broadened to unrelated explicitly identified
candidates. Typed candidate evidence wins over legacy cause-text attribution when
a chain executed.

**A record is falsifiable only by later matching execution.** A node attempt
that starts after a domain observation and completes successfully against that
same hold key retires only the older domain record. A later successful attempt
by the exact `(availability_key, candidate_key)` retires only the older
candidate record. Overall run success is insufficient: it MUST NOT clear a
skipped or failed primary. The same node-level success remains valid evidence
when a later node makes the overall run fail. Expiry and attributed operator
clearance are the two other retirement routes.

**An operator may retire a record early.** The Dispatcher MUST offer an exact
scope/key clearance for current records and retain the existing provider valve
for legacy records only. Both require asserted identity and a non-blank reason,
refuse a target with no matching live record before writing, and APPEND an audit
record containing the exact identity, actor, time, and reason. They MUST NOT
rewrite or delete the original observation. Automated callers may clear only
when they assert identity; unattributed invocation is refused unconditionally.

**The admission-time credential-probe refusal re-probes rather than exiting.** A `loop` invocation (§"Dispatcher loop invocation surface") whose admission is refused by the admission-time credential-usability probe -- the projected worker credential returning a provider-limit or rate-limit condition BEFORE any sandbox is launched -- MUST NOT exit on that refusal while its `--budget` is unspent. It MUST re-run the probe on a bounded cadence and resume normal admission on the first usable probe result, subject to every other admission-valve condition (§"Admission valve (`ready → active`)"). The cadence is a committed-only `dispatcher.credential_reprobe_interval_seconds` (positive integer, default **300**); it is NOT declared API-configurable and is therefore committed-only per §"Orchestrator-owned attention facts" → "The declared-API-configurable class". Each refused probe MUST be journaled as one record under §"Control surface and audit" -- the re-probe wait is not silent. This clause governs ONLY the loop's response to a probe refusal; it creates NO new availability-record retirement route. A usable probe result MUST NOT retire an unexpired observed record: the three ratified retirement routes -- bounded expiry, matching execution (this section's "A record is falsifiable only by later matching execution"), and operator clearance -- stand unchanged, because a live credential probe is a non-dispatch-outcome host signal. Where observed holds exhaust a success-critical chain, admission remains refused until at least one candidate becomes eligible; a hold covering only the primary does not defeat an eligible fallback. The re-probe keeps the loop alive rather than substituting for record retirement.

For a new-grammar-enabled chain, a provider-limit/rate-limit probe refusal is an
ephemeral candidate-local skip for that admission evaluation only. It creates no
durable hold and MUST NOT enter the re-probe wait while an eligible fallback
keeps every success-critical chain viable. The re-probe posture above applies to
the legacy single-candidate route and to a genuinely empty required chain.

**The probe refusal's remedy carries no timing claim as an instruction.** The credential-probe refusal surfaced to the operator MUST NOT present a provider-stated reset instant as an instruction to wait until a clock time. The same principle (this section's "Every observed availability record is scoped, versioned, and expires") already applies to the observed record, and it now applies to the probe refusal: a provider's timing claim MUST NOT be adopted as an instruction and MUST NOT gate the re-probe cadence; if the provider's refusal carried such a claim it MAY be recorded as provenance, clearly marked as an unverified provider claim rather than as an observation. The probe's OWN next result is the retirement signal for the loop's wait, not a clock.

**No silent containment.** A refusal to admit on containment grounds, and a
truncation of a run under the dead-implementer rule, are each auto-dispositions
and MUST be journaled under §"Control surface and audit". Neither MAY be silent.
The two carry DIFFERENT fields, because they are not governed by the same
observation:

- A containment refusal MUST carry at minimum the work-item id, governing
  condition, exhausted success-critical node, scoped hold identities, and their
  expiries. At least one observed record governs it by construction.
- A dead-implementer truncation MUST carry at minimum the work-item id and the
  governing condition. It fires on ANY implementer termination that produced no
  change to the worktree, whatever the cause — a provider ceiling, a crash, a
  malformed configuration — so no observed availability record need exist, and
  scoped hold identity or expiry fields MUST NOT be required of it. Where an
  observed availability record did govern the run, naming it is permitted and
  useful.

**Relationship to the human-gate floor.** This section does NOT relax §"Every
needs-human escalation still reaches a human". Refusing to dispatch is not
auto-resolving an item: the item stays open, stays `ready`, and stays surfaced
through the needs-attention awareness surface. No containment refusal MAY
dispose of a `blocked_reason: needs-human` item.

**Relationship to host concurrency.** A provider allowance is not a host
resource, so this section does NOT reintroduce the host-level dispatch
concurrency ceiling that §"Host concurrency belongs to the Fabro scheduler"
forbids. That section's prohibition binds refusals on HOST-CONCURRENCY grounds;
this one refuses on the ground that the work cannot succeed because the
provider's allowance is gone. The Fabro scheduler enforces no provider-quota
precondition — it accepts the run and the run then fails inside the sandbox —
so this precondition duplicates nothing.

### Effective acceptance criteria

Exactly ONE public primitive resolves a work-item's effective acceptance
criteria, and every producer and consumer gate MUST use it — the capture
and groom front-ends' parse display, the entry-to-`ready` wall (§"Work-item
state semantics", the `approve` transition), the pre-dispatch wall below,
and the post-merge acceptance pass. No surface may re-derive criteria by
another path. The resolution order:

1. The item's MATERIALIZED criteria value — the merged store read the
   acceptance pass already uses, in which the native `acceptance_criteria`
   field wins over a metadata-held one and a criteria field held only in
   metadata by an older writer is NOT treated as absent — when it yields
   gradeable content. (This is ONE step, not two: the materialization IS
   the merged read; no surface re-reads raw metadata separately.)
2. Otherwise the item description's "Exit criteria" section (a heading
   whose title case-insensitively equals "Exit criteria"; the section
   body is the criteria text).

The resolved source is reported as one of exactly two values:
`criteria-field` (the merged value) or `description-exit-criteria`.

Gradeability is defined at the ASSERTION level: an effective-criteria
set is empty when it contains zero gradeable assertions. A physical-line
parse that counts wrapped continuation fragments as assertions is a
known-defective approximation of this definition (`bd-ib-tfpdya`; the
shipped parser already joins indented continuations and drops
header-only lines — non-indented wraps survive); the walls MUST NOT be
implemented against a parse that counts non-assertable fragments as
gradeable. The completion criterion for that gate is mechanical: the
walls MAY land once (a) a formatting-independence test exists proving
the same criteria text reflowed to different column widths yields the
same gradeable-assertion count, and (b) the discriminating control holds
— a genuinely unmet real criterion still fails while a wrapped fragment
no longer does.

**The pre-dispatch wall.** The Dispatcher MUST refuse to dispatch an
AI-dispositive item whose effective acceptance criteria parse to zero
gradeable assertions — before any factory run is created, for both the
drain and the hand-picked `dispatch --item` path. The refusal MUST name
the work-item id, state that the effective acceptance criteria are empty
or ungradeable, and exit with the dedicated documented exit code `5`
(§"Dispatcher exit codes"), distinct from the precondition exit `3`.
Already-filed items that predate this wall are LEFT TO REFUSE ON CONTACT
— no backfill pass and no exemption list; the capture, groom, and
approve surfaces display the parse so each item is repaired when it is
next touched.

**Advise at capture and groom.** The capture and groom front-ends MUST
display the effective-criteria parse result (the gradeable-assertion
count, and the resolved source) whenever they create or redraft an item,
and MUST NOT refuse on an empty parse — filing remains consent-gated and
criteria MAY legitimately arrive at groom time.

**Change-implying criteria and the empty-diff refusal.** Every gradeable
effective acceptance criterion MUST be treated as CHANGE-IMPLYING by
default: an AI-dispositive item with a non-empty gradeable effective
criteria set is presumed to require file changes, so the empty-merged-diff
refusal (§"Post-merge acceptance (`acceptance → done`)" → "The evidence rule" → "Empty merged
diff is ungradeable, not delivered") applies to it. The ONLY exemption is
an item explicitly declared CHANGE-OPTIONAL — a `change-optional`
(no-change-expected) marker on the item, distinct from its
`acceptance_policy` — for which an empty merged diff MUST route to the
item's normal grading path rather than to the empty-diff refusal. An item
MUST NOT be silently exempted: the change-optional property MUST be a
declared property of the item, and the acceptance pass MUST record in its
journal both the change-implying/change-optional classification it used
and, when the refusal fires, the empty-diff evidence leg. Absence of a
declared change-optional marker resolves to change-implying; a malformed
or unknown marker value resolves to change-implying (fail-closed toward
refusing an empty diff, never toward accepting one).

### Dispatcher exit codes

`0` — success / all dispatched green. `1` — non-skipped findings present
or any terminal failed dispatch. `2` — usage error. `3` — precondition
error (missing repo / workflow / item not ready). `4` — dispatch
completed with the work-item routed to the ledger's human gate
(`blocked / needs-human`) and no terminal failures; the run itself has
terminated (§"A factory run never awaits a human").
`5` — ungradeable-acceptance-criteria refusal (§"Effective acceptance
criteria"). `skipped`-severity findings never flip the exit code.

### Post-merge acceptance (`acceptance → done`)

Acceptance is **post-merge / in-production** (observability + reversibility).
The deterministic `just check` stays the HARD **pre-merge** floor (the
in-sandbox janitor gate, which already executes the suite); acceptance
verifies *fit + real behavior* against the **shipped** artifact:

- **`complete` (`active → acceptance`)** MUST **merge-on-green**: the
  Fabro impl run merges via `gh pr merge` with the resolved
  `dispatcher.merge_mode` method (default `rebase`) and `--auto`; entering
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
  plus a telemetry watch, yielding a PASS, FAIL, NEEDS_ATTENTION, or
  NO_CHANGE_NEEDED verdict** — never a rubber
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

  **The evidence rule.** A verdict MUST NOT be manufactured from absent
  evidence. The pass judges three evidence legs — the merged diff, the
  effective acceptance criteria (§"Effective acceptance criteria"), and
  the run/telemetry outcome — and:

  - **PASS** requires every leg OBSERVED and passing: an observed green
    outcome, a gradeable merged diff, and a non-empty effective-criteria
    check set with every check passing.
  - **FAIL** requires OBSERVED failing evidence: an observed failing
    outcome, or at least one effective criterion judged failing against
    observed evidence. A FAIL is dispositive rework input (the FAIL
    route below).
  - **NEEDS_ATTENTION** is the verdict when the pass CANNOT OBSERVE what
    a judgment needs: the merged diff is unobservable or ungradeable,
    the effective criteria parse to zero gradeable assertions, or the
    run/telemetry leg is unobservable (distinct from observed-failing).
    Absence of evidence is never failure evidence and never passing
    evidence.
  - **NO_CHANGE_NEEDED** requires OBSERVED evidence that the item's
    change is no longer applicable — already present on the default
    branch, or superseded — and, under a to-`done` policy, closes the
    item with resolution `no-longer-applicable` (the shipped, tested
    auto-close branch). It is a disposition verdict, not a judgment that
    work was done well; it MUST NOT be reached from absent evidence.
    (The verdict is currently UNREACHABLE through the acceptance pass —
    the pass emits only the other three — and this contract gives it
    ratified semantics rather than leaving an undocumented dead branch;
    wiring a reachable producer is implementation work.)

  **Empty merged diff is ungradeable, not delivered.** A merged diff that
  changes zero files — zero hunks under the merged ref — is, for a work
  item whose effective acceptance criteria are change-implying
  (§"Effective acceptance criteria" → "Change-implying criteria and the
  empty-diff refusal"), an UNGRADEABLE merged-diff leg, NOT an observed
  gradeable diff: an empty diff carries no evidence that any
  change-implying criterion is met. The acceptance verdict for such an
  item MUST be NEEDS_ATTENTION, with the merged-diff leg named as the
  absent-evidence leg, and MUST NOT be PASS — grading an empty diff PASS
  is exactly a verdict manufactured from absent evidence, which the
  evidence rule forbids. An empty diff alone MUST NOT be read as
  NO_CHANGE_NEEDED either: "nothing changed in this merge" is not the
  OBSERVED "already present on the default branch, or superseded" that
  NO_CHANGE_NEEDED requires. The only exemption is a work item declared
  change-optional (§"Effective acceptance criteria" → "Change-implying
  criteria and the empty-diff refusal"), for which an empty merged diff
  routes to the item's normal grading path rather than to this refusal.
- **A FAILING AI acceptance pass under an AI-dispositive policy.** For an item
  whose effective `acceptance_policy` is `ai-only` or `ai-then-human`, a FAIL
  routes the item back to `active` for **fix-forward rework automatically — no
  human is consulted for a fail** — mirroring `reject (rework)`, but
  AI-initiated. The under-cap FAIL disposition MUST stamp the ledger-held
  `rework:pending` label on the item in the same disposition, and the
  dispatch process then ends; EXECUTING the rework is owned by
  §"Rework-pending re-dispatch". "Automatically" in this clause means no
  human is consulted for the ROUTING decision — it does not mean the
  disposing process performs the rework itself. Repeated failure on one item is bounded by
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
  **fix-forward** (patch on top of the live change) and MUST stamp the same
  `rework:pending` label, so the human rework path is selectable by the
  identical machinery — the two rework entries MUST NOT diverge in
  selectability (the valve's durable journal record carries the
  provenance; the label is a presence marker); `reject (re-groom) →
  backlog` is **revert the merged change + re-decompose**.

### The NEEDS_ATTENTION verdict

Under EVERY effective `acceptance_policy` — `ai-only`, `ai-then-human`,
and `human-only` alike — a NEEDS_ATTENTION verdict MUST park the item in
`acceptance` for a human and MUST NOT dispose of it: it MUST NOT accept
the item to `done`, MUST NOT route it to rework, MUST NOT stamp the
`rework:pending` marker, MUST NOT move it to `blocked`, and MUST NOT
consume `dispatcher.acceptance_rework_cap`. A cannot-judge verdict is a
truly-unresolvable decision in the sense of §"Every needs-human
escalation still reaches a human": no policy setting MAY auto-dispose
it, including `ai-only` — the delegation `ai-only` grants is the
authority to act ON evidence, not the authority to act without it.

The parking MUST be journaled with the verdict and the absent evidence
leg(s), MUST be surfaced (the existing parked-in-acceptance surfacing),
and the parked item is an orchestrator-owned human wait for the
attention surface — composed through the EXISTING composition classes (a
parked acceptance awaiting the human `accept`/`reject` valves); this
clause introduces no new attention kind. The human disposes of the
parked item with the existing `accept:<work-item-id>` and
`reject:<work-item-id>:rework|regroom` valve actions.

The pass itself still satisfies the "no release with zero verification"
floor: a NEEDS_ATTENTION verdict is a completed AI pass whose finding is
that the evidence was unobservable — it is not a skipped pass.

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
EXCEPT `wip_cap`, whose rationale is that a concurrency ceiling is not a
per-item property. `dispatcher.require_invoker` (§"Journal invoker
attribution") is a committed attribution-integrity dial, not a policy
setting of this section: it has no per-item override and is deliberately
not API-configurable.

### The five policy settings

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
- **`dispatcher.groom_cut_approval`** (enum `human` | `consensus`, default
  **`human`**) — who may approve a drafted groom cut under §"Grooming and
  slice-size calibration" → "Consensus-gated automated groom cut": `human` ⇒
  only a human operator's `resolve-blocked` answer approves; `consensus` ⇒ the
  ratified consensus tier MAY approve the first cut of an intake-routed epic,
  and only that. Per-item override: a per-item label that MAY only lower an
  item to `human` and MUST NOT raise one to `consensus`. Until livespec core
  ratifies the tier, `consensus` behaves as `human`.
- **`dispatcher.answer_disposition`** (enum `human` | `consensus`, default
  **`human`**) — who may answer an **attention item**: a work-item resting at
  `blocked` / `blocked_reason: needs-human` — the parked-on-a-question state
  under §"A factory run never awaits a human". `human` ⇒ only a human
  operator's `resolve-blocked … --answer` press answers; `consensus` ⇒ the
  ratified consensus tier — the successor to the removed foreman valve
  disposition — MAY also answer. Per-item override: a per-item
  `answer:<human|consensus>` label, written at capture or groom time exactly as
  the `admission_policy` / `acceptance_policy` labels originate; it MAY only
  lower an item to `human` and MUST NOT raise one to `consensus`. Until
  livespec core ratifies the consensus tier, `consensus` behaves as `human`.
  This setting adds NO new `drive` valve — the thirteen human valve actions of
  §"`drive`" remain thirteen — because the per-item override is a label, not a
  runtime valve press.

An item's **effective answer disposition** resolves as its
`answer:<human|consensus>` label when present, else the global
`dispatcher.answer_disposition`. `drive` MUST refuse a
`resolve-blocked:<work-item-id>:ready|backlog` press carrying `--answer` that
the effective answer disposition does not admit — under `human`, an
automated/non-human disposition's press is refused — and the refusal MUST name
the work-item and the effective disposition, mirroring the effective-manual
`approve` refusal (§"`drive`"). The `needs-attention` `resolve-blocked` lane
MUST NOT advertise an answer handoff the effective disposition would refuse (the
advertiser-and-enforcer binding), and `needs-attention --json` MUST carry each
attention item's effective answer disposition; until a first-class field
ratifies in the `livespec-runtime`-owned attention envelope (§"The
needs-attention machine envelope"), the effective disposition MAY ride the
existing per-item `summary` string. Scenario 122 binds this behavior.

### The three rework caps

Each is a global default with a per-item label override, and each bounds one
of the three INDEPENDENT rework loops:

- **`dispatcher.review_fix_cap`** (integer, default **`3`**) — the INNER,
  pre-merge review fix-round budget. At the cap, a still-blocking review is
  disposed by the item's effective `merge_on_review_cap`. A fix round has
  two separate steps — a disposition stage adjudicates each blocking
  finding (accept, or reject with rationale) and a fix stage implements
  only the accepted findings (Scenario 20); a round whose findings are all
  rejected re-reviews directly, and every reviewer-granted round consumes
  this budget either way. Design record for the split:
  `plan/factory-success-rate-remediation/research/review-fix-split-design.md`
  (ledger `bd-ib-o35rcx`, maintainer directive 2026-07-23).
- **`dispatcher.acceptance_rework_cap`** (integer, default **`2`**) — the
  OUTER, post-merge budget: how many times a single item's FAILED AI
  acceptance pass MAY route back to rework before the item **escalates to
  `blocked` / `blocked_reason: needs-human`** instead of reworking again. This
  is the bound that prevents an unbounded post-merge rework loop.
- **`dispatcher.automated_regroom_cap`** (integer, default **`2`**) — how many
  times the consensus tier MAY send one item's drafted groom cut back for
  re-drafting before the draft rests at `blocked` / `blocked_reason:
  needs-human` for a human operator (§"Grooming and slice-size calibration" →
  "Consensus-gated automated groom cut"). It is inert while
  `dispatcher.groom_cut_approval` is `human`.

### The per-item merge hold

A merge hold is a per-item policy field with NO repository-level default:
it is set on one item, by a person, for one merge, and it is the one field
in this section that exists only per item. It does not weaken the
`wip_cap` clause below, which is about settings that lack a per-item
override; the hold is not a setting.

- **`merge_hold`** (boolean, per item only, default **`false`**) — while
  `true`, the item's approved pull request MUST NOT be merged by any
  automated path. It is set and released through the human valve action
  `set-merge-hold:<work-item-id>:on|off` (§"`drive`"), realized on beads
  as the `merge-hold:` label through the store seam: `on` writes the label,
  `off` removes it, and the label's presence is the hold. Like every policy
  edit it MUST modify only that field of the ledger record and MUST NOT
  change the item's status; unlike the other policy edits it ALSO performs
  one forge write, arming or disarming the pull request's auto-merge
  request, and that write is the action's only other effect.
- The Dispatcher MUST render the item's effective `merge_hold` as the
  workflow input `merge_hold`, a member of the per-item policy-input family
  that §"Repository integration contract" → "Typed workflow inputs and the
  seam-equivalence check" names, beside the review-fix visit cap and the
  merge-on-review-cap outcome inputs, and the token MUST sit in a position
  resolved before the sandbox executes it exactly as that clause requires of
  every input. The bundled workflow MUST declare it with its default, and a
  registered variant MUST declare it too, because the seam check holds a
  variant to the bundle's token set.
- While the hold stands, the pr stage MUST push the branch and open the
  pull request exactly as it does today, MUST NOT arm auto-merge, MUST
  verify that no auto-merge request exists on the pull request, and MUST
  report `MERGE_HOLD=held` beside the PR-number line the pr stage already
  reports in its final reply. The Dispatcher's auto-merge argv (the
  `gh pr merge` method flag of "Merge-strategy resolution") MUST NOT arm
  auto-merge for a held item either. Both seams read the one rendered value;
  neither is authoritative.
- A held item's run terminates green at the pr stage; the run never waits
  (§"A factory run never awaits a human"). The item MUST remain `active`,
  and its green terminal run is reclaimed under §"Per-repo WIP cap" exactly
  as every green terminal outcome is, so a held item holds NO capacity
  slot. A terminal run whose item is `active` under a matching journaled
  run id is not an orphan, so reconciliation MUST leave it alone; and the
  `merge-hold:` label is a discriminator for §"Rework-pending re-dispatch"
  → "Stranded-state discrimination", so a held item is never reported as
  stranded, abandoned, or leaked.
- Every held item MUST be surfaced by `needs-attention` under the
  existing `hygiene` kind as `hygiene:merge-hold:<work-item-id>`, per
  §"Orchestrator-owned attention facts", with a `summary` naming the pull
  request and a `handoff` naming `set-merge-hold:<work-item-id>:off` as
  the release. A hold MUST NOT become invisible: the attention row stands
  until the hold is released or the item leaves `active`, and it is the
  ONLY attention id a held item produces for the hold.
- Releasing the hold (`set-merge-hold:<work-item-id>:off`) against an item
  whose pull request is open and unmerged MUST arm auto-merge from the host
  with the merge method of the `ResolvedIntegrationContract` journaled with
  the dispatch that opened the pull request (never re-derived from
  configuration), and MUST NOT re-dispatch; the merge then lands
  server-side and the existing post-merge path — the post-merge janitor,
  `reconcile-merged`, acceptance — proceeds unchanged. Releasing a hold on
  an item that has no open pull request changes only what the next dispatch
  renders. Setting the hold on an item whose pull request is already armed
  MUST disarm the auto-merge request; setting it on a merged item is refused
  as a no-op naming the merge.

### `wip_cap` — the one setting with no per-item override

`dispatcher.wip_cap` (existing, default `5`, §"Per-repo WIP cap") is likewise
an API-settable setting, surfaced under the console Settings surface. It is
the ONE setting among this section's policy settings with **no per-item
override**: it is a per-repo concurrency
ceiling, so a per-item value is structurally meaningless. Its value semantics
are unchanged. Design record: repo `thewoolleyman/livespec`,
`plan/archive/autonomous-mode/handoff.md`, the "SESSION UPDATE — 2026-07-14 (cont. 12)"
section, together with its "CORRECTION / ADDENDUM" section (`wip_cap` is NOT
per-item overridable).

### Every needs-human escalation still reaches a human

No policy setting MAY auto-dispose a **truly-unresolvable decision** (`spec.md`
§"Terminology"). The Dispatcher MUST NOT auto-resolve a `blocked_reason:
needs-human` item; it MUST surface every such item to a human. A decision that
is human-gated BY DESIGN — a spec-change slice, a regroom / backlog bounce, or
a `human-only` acceptance — MUST stay escalated even when the Dispatcher is
fully confident. Drift acceptance is human-gated by the same default and MUST
stay escalated unless the governed repo has opted in to the consensus tier
through livespec core's `spec_governance.drift_acceptance_mode`; under that
opt-in the consensus tier MAY own a drift acceptance, and only on unanimous
cross-vendor evidence that is present, fresh and conforming. No other setting,
and no `delegated` value, MAY accept drift, and the Dispatcher itself MUST NOT
accept a drift-origin proposal under any setting. The "no release with zero verification"
floor of §"Post-merge acceptance (`acceptance → done`)" MUST hold under every
setting: every acceptance carries at least one AI pass. The Dispatcher MUST
NOT create net-new work-items when applying a setting — every setting-driven
write is a disposition of an already-filed item (§"Machine-path exemption —
the Dispatcher").

### A factory run never awaits a human

The needs-human gate has two halves, and only the ledger half is a gate.
The item resting at `blocked / blocked_reason: needs-human` is the ONLY
place a human decision waits. A factory run is never that place.

- A needs-human outcome inside a factory run MUST terminate the run
  non-green and MUST preserve the run's work by reference (a pushed ref
  and/or the preserve-by-reference pointer) before terminating. The run
  MUST NOT enter a human-input-required state, and the workflow MUST NOT
  carry an interactive human-decision node whose answer resumes the run.
  The human's answer — retry, re-implement, or abandon — is expressed
  through ledger valves (`resolve-blocked`, the rework path, or leaving
  the item blocked), never by attaching to a run.
- The Dispatcher MUST reconcile every configured factory's non-terminal
  run inventory against the ledger. The invariant: on every factory
  declared under `dispatcher.factories`, the set of non-terminal runs
  equals the set of work-items that are `active` under a live dispatch
  claim whose journaled run id is that run. Any other non-terminal run is
  an ORPHAN — its item is not `active`, or is `active` under a different
  journaled run id, or is absent from the ledger — and the Dispatcher
  MUST reconcile it without a human: EXPORT its record first (write and
  read back the preserve-by-reference pointer), THEN terminate it, and
  journal one record per reconciliation naming the run id, the factory,
  the run's status kind, the item and its status, the orphan reason, and
  the termination route. The export is the precondition, not a courtesy:
  a termination whose export was not read back MUST NOT proceed.
- Reconciliation runs on every Dispatcher loop tick and in the dispatch
  preamble, and MUST also be runnable standalone (a scheduled sweep) so
  that an item closed by any route while no Dispatcher process is alive —
  a hand landing, a hand `bd close`, another session — still releases its
  run. A run whose item is `active` with a matching journaled run id is
  NOT an orphan even when no Dispatcher process is watching it.
- A run that has nonetheless parked in a human-input-required state (a
  run created before this contract, or by a foreign workflow) whose item
  is still live MUST NOT hold its slot indefinitely: after
  `dispatcher.blocked_run_grace_seconds` (default `1800`) the Dispatcher
  MUST export it and terminate it by answering its own abandon option, so
  that Fabro's record carries the intent. The item is left exactly as it
  was.
- Reconciling or terminating a run MUST NOT change the item's status,
  `blocked_reason`, or labels, and MUST NOT auto-resolve any decision.
  §"Every needs-human escalation still reaches a human" and Scenario 36
  hold verbatim: the decision stays in the ledger and reaches a human.
- Every reconciliation surface (loop, preamble, standalone sweep,
  `needs-attention`) MUST address each factory by its declared server
  target; a read against an undeclared or default target is not a
  reconciliation of that factory.

Design record: plan `ledger-is-the-only-gate` (epic `bd-ib-n77djm`),
`plan/ledger-is-the-only-gate/research/001-design-and-slice-plan.md`.

### The human answer route: marker, poison preflight, run account, and write-before-transition ordering

The human's answer to a `blocked / blocked_reason: needs-human` item travels one
route — a `resolve-blocked:<work-item-id>:ready|backlog` press carrying `--answer`
that lands the answer as a ledger comment (§"The five policy settings",
Scenario 122). Four mechanism facts of that route are load-bearing for a consumer
and are ratified here.

- **Answer marker.** The answer comment MUST open with the stable marker line
  `livespec-human-answer (<invoker> via <source>, <at>, <action-id>):` on its own
  line, followed by the operator's answer verbatim. The attribution and timestamp
  are written INTO the comment body — the invoker the drive surface resolved, its
  source, the write instant, and the answering valve action id — because the
  shared bd connection user in the tenant's own columns names no operator. The
  re-dispatched run's goal brief MUST carry this comment verbatim so the next run
  reads who answered and what they said.
- **Poison preflight refusal.** Before the answer comment is written, the answer
  MUST be preflighted with the shared template-opener detector. An answer carrying
  a goal-template opening delimiter MUST be REFUSED: nothing is written — not the
  comment, not the journal line — and the item does NOT transition. Because a
  ledger comment is append-only and the goal brief renders it verbatim, an opener
  admitted here would poison every future goal render and cost the item its
  dispatchability permanently; the writer that feeds the brief therefore refuses
  exactly what would refuse the dispatch.
- **Run account in the valve summary.** The `needs-attention` valve item for a
  `blocked / needs-human` item MUST carry the terminated run's account in its
  summary: the run id, the factory name and its server, that a `needs_human`
  termination routed the decision to this valve, why it terminated, what the run
  reported, the preserved reference to its work, and the available valve actions.
  The enrichment MUST fail soft: an unreadable config or an unreachable factory
  costs the ENRICHMENT and never the valve — the valve item is surfaced regardless,
  and each factory is addressed by its declared server target.
- **Write-before-transition ordering.** The answer comment MUST be written BEFORE
  the item's status transition. A comment write that is refused or fails MUST NOT
  transition the item, so a delivered answer always precedes the unblock and no
  transition is recorded for an answer that did not land.

Design record: the route shipped in `bd-ib-aqith2` (PR #2168) and `bd-ib-uuohty`
(PR #2200); ratified here per `bd-ib-rh3iyd.7`. Scenarios 124 and 125 bind it.

### Temporary setting postures carry an owned restore item

A deliberate TEMPORARY posture change to any committed dispatcher
setting — lowering `wip_cap` for a canary, committing a step waiver
intended to be short-lived, tightening a cap for an experiment — MUST be
accompanied by an owned ledger work-item, filed through
`capture-work-item` by the operator making the change (consent is native
there; the Dispatcher itself files nothing, per §"Consent boundary").
The restore item MUST name:

- the setting and the value to restore (the restore target),
- a named owner, recorded queryably as an `owner:<name>` ledger label on
  the restore item (prose alone is not queryable),
- the restore condition, written as gradeable acceptance criteria
  (§"Effective acceptance criteria" defines gradeability) — the
  condition lives WITH the obligation, authored by the operator who
  knows it, never interpreted by the orchestrator,
- a dependency edge to the ledger item the restore waits on, whenever
  that trigger is ledger-tracked.

A configuration comment is NOT a carrier for a restore obligation:
nothing reads comments, and this rule exists because a committed comment
is where exactly this obligation went to die. The restore item is
ordinary ledger work — ranked, listed, and composed by the existing
status and attention surfaces; no new configuration schema, no
restore-condition evaluation vocabulary, and no new dispatcher settings
key is added by this contract, and none of the ratified settings gains a
"temporary" variant. (Consequently the console Settings-surface lockstep
of §"API-configurable completeness" is not triggered: there is no key to
expose.)

### Control surface and audit

Every POLICY SETTING of §"Dispatcher policy settings" MUST be settable via
the orchestrator API and, through it, the Control-Plane console. Keys
ratified as COMMITTED-CONFIGURATION-ONLY (`dispatcher.require_invoker`,
§"Journal invoker attribution"; `dispatcher.fabro_bin` and
`dispatcher.codex_models` by shipped precedent; any key a later
ratification adds to this class) are deliberately outside the
API-configurable key set, and the lockstep of §"API-configurable
completeness" applies to the API-configurable set only. The orchestrator
OWNS the setting state — the
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

The two spend-containment dispositions of §"Provider spend containment" — a
provider-exhaustion admission refusal and a dead-implementer run truncation —
are journaled on that same journal under the same no-silent-disposition rule,
with the per-disposition fields that section names. They are NOT setting-enabled:
each is an unconditional obligation rather than something a setting turns on, so
each records the GOVERNING CONDITION in place of a governing setting.

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


## Codex ACP node model pins

The factory's Codex-backed ACP nodes run a model the Dispatcher CHOOSES, not one
the sandbox happens to resolve. This section is the wire contract for that
choice: a reader MUST be able to predict the literal adapter string a dispatch
will carry from this section alone, and check its clear command/args plus the
digest of the complete rendered bytes against the redacted `run_turn.command`
record the factory emits. Raw env values MUST NOT ride that trace. Each class is Codex-backed ONLY when the dispatch
target pins it; absent that pin the implementer class runs the Claude ACP adapter
described under "The implementer default is the Claude adapter" and the publish
class runs the Claude ACP adapter described under "The publish default is the
Claude adapter", both below.

**Every Codex ACP candidate is pinned.** The Dispatcher MUST pin BOTH the model
and the reasoning effort on every primary or fallback Codex ACP adapter it
renders. Emitting an unpinned adapter as the DEFAULT or a fallback is forbidden.
The existing explicit empty-model opt-out remains the one exception. The reason is specific rather than
stylistic: the sandbox image bakes a `codex-acp` build whose models-manager
cannot decode the current model catalog, so an unpinned adapter falls back to a
baked static list. Its effective model is then the residue of a decode failure,
and it will drift silently whenever either the catalog or the baked adapter
changes.

**The pin is per node CLASS, not per node.** Two classes exist and the Dispatcher
MUST render one adapter for each:

- The **implementer** class, rendered into the workflow's `acp_adapter` input and
  consumed by the `implement`, `fix` and `review_fix` nodes. These nodes carry
  design judgement.
- The **publish** class, rendered into the `pr_adapter` input and consumed by the
  `pr` node, which executes a fixed `git`/`gh` recipe with no design judgement in
  it and therefore takes a cheap model — the Claude Haiku default described under
  "The publish default is the Claude adapter" below, or a cheaper explicit
  override.

The remaining ACP nodes — `review` and `disposition` — are NOT Codex-backed and
are outside this section.

**The implementer default is the Claude adapter.** When the dispatch target's
`dispatcher.codex_models` block carries NO `implementer` entry — the block is
absent, the `implementer` key is absent, or the entry is not a table — the
Dispatcher MUST render the `acp_adapter` input as the Claude ACP adapter pinned
to Claude Opus 5 at high effort. The rendered form, literally, is:

    ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high npx -y @agentclientprotocol/claude-agent-acp

The model and effort MUST ride the adapter's own environment as leading
`KEY=value` assignments, exactly as the `review_adapter` input already pins its
model, because Fabro rejects `model` and `reasoning_effort` as ACP node
attributes. The Dispatcher MUST NOT apply a context-window suffix such as `[1m]`
to the default Opus 5 model name; whether Opus 5 accepts one is established from
a run transcript, never assumed in a default. A `dispatcher.codex_models.implementer`
entry that IS a table — whether it names a model or carries the empty-string
opt-out — MUST route the implementer class to the Codex adapter under the
existing rules of this section, so a repository stays on Codex by writing the
entry and moves to the default by removing it. The `pr` class behaves
symmetrically: absent a `dispatcher.codex_models.pr` table it renders the Claude
publish default described next, and a table routes it to the Codex publish
adapter specified below.

The Dispatcher SHOULD treat the first dispatch after a change to the default
implementer adapter as a verification run: the run transcript's resolved model
MUST be checked against the pinned model and the result recorded on the
work-item that changed the default, because earlier `claude-agent-acp` versions
ignored `ANTHROPIC_MODEL` and silently ran a smaller model.

**The publish default is the Claude adapter.** When the dispatch target's
`dispatcher.codex_models` block carries NO `pr` entry — the block is absent, the
`pr` key is absent, or the entry is not a table — the Dispatcher MUST render the
`pr_adapter` input as the publish default it inherits from the workflow, which is
the Claude ACP adapter pinned to Claude Haiku 4.5 at high effort (a higher-layer
`dispatcher.acp_nodes.pr` override still wins per §"ACP node adapter
configuration", exactly as it does for the implementer class). The rendered form,
literally, is:

    ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high npx -y @agentclientprotocol/claude-agent-acp

The model and effort MUST ride the adapter's own environment as leading
`KEY=value` assignments, exactly as the implementer default and the
`review_adapter` input already pin their model, because Fabro rejects `model`
and `reasoning_effort` as ACP node attributes. The Dispatcher MUST NOT apply a
context-window suffix to the default Haiku model name. As with the implementer
default, the Dispatcher SHOULD treat the first dispatch after a change to this
default as a verification run whose resolved model is checked against the pinned
model, because earlier `claude-agent-acp` versions ignored `ANTHROPIC_MODEL` and
silently ran a smaller model. A `dispatcher.codex_models.pr` entry that IS a
table MUST route the publish class to the Codex adapter under the existing rules
of this section, so a repository stays on (or moves to) Codex by writing the
entry and takes the Claude default by removing it — exactly symmetric with the
implementer class. This is the change from the prior contract, under which the
`pr` class defaulted to a baked Codex publish pin: that pin was a single OpenAI
model whose availability is a runtime property of the ChatGPT-account catalog,
so when the catalog dropped it every unconfigured repository failed at the
publish stage. A Claude default removes that exposure from the default path.

**Tiers resolve from the dispatch target's own configuration.** The Dispatcher
MUST read the pins from the dispatch target's `dispatcher.codex_models` block,
and MUST carry a built-in fleet default so that a repository which has not opted
in still inherits a pinned adapter — the Claude default for the implementer
class, and the Claude publish default (Claude Haiku 4.5) for the `pr` class.
Within a tier entry that IS a table, resolution MUST degrade per key rather than
wholesale: an absent `model` or `reasoning_effort` key MUST fall back to that
tier's built-in Codex default for exactly what is missing, leaving any sibling
override in force. A partial override is legal. An absent or non-table
`implementer` entry resolves to the Claude implementer default adapter as a
whole, not to the Codex defaults; likewise an absent block, an absent `pr`
entry, or a non-table `pr` entry resolves to the Claude publish default (the
workflow's `pr_adapter` input, the pinned Claude Haiku 4.5 adapter) as a whole,
not to the Codex defaults. A `pr` entry that IS a table routes the publish class
to the Codex adapter under the per-key degradation just described.

**An empty model is a legal explicit opt-out.** A tier whose `model` is the empty
string MUST render the adapter BYTE-IDENTICALLY to the un-pinned base string,
carrying NO `model` key and NO `model_reasoning_effort` key inside `CODEX_CONFIG`
rather than carrying either with an empty value. The opt-out MUST be
spelled as an empty value rather than a removed key, so an operator can disable
the pin without deleting the surrounding documentation, and it MUST be a true
no-op rather than a differently-spelled default.

**There is no environment override.** The pins MUST NOT be overridable by an
AD-HOC SHELL environment variable read from the orchestrator host's ambient
environment. They are a steady-state cost policy read once per dispatch
on the orchestrator host; such a seam would let an ad-hoc shell re-tier
the whole factory with nothing in the committed record to show for it.

This rule does NOT constrain an adapter's OWN DECLARED `env` map. That map is
committed configuration, resolved through the three layers of §"ACP node adapter
configuration", rendered into the recorded adapter string with each VALUE
preserved byte-for-byte through shell tokenization. The dispatch journal stores
the env KEY, supplying layer, and digest of the exact rendered bytes but MUST
NOT store the value — so it leaves a verifiable committed record
an ambient seam would destroy. The distinction is load-bearing rather than
pedantic: the pins below ride the adapter's declared environment, and reading
this rule as a ban on environment assignments generally would forbid the very
channel this section specifies.

**The rendered form, literally.** The adapter command is the successor
`codex-acp` package invoked AT ITS BAKED PATH:

    /opt/livespec/codex-acp/bin/codex-acp

Its settings ride the command as leading `KEY=value` ENVIRONMENT assignments in
sorted key order, exactly as §"ACP node adapter configuration" requires of every
node's `env` map. Two assignments are defined here. `CODEX_CONFIG` MUST carry a
JSON object merged into the adapter's session configuration; `INITIAL_AGENT_MODE`
MUST carry `agent-full-access` for the implementer and publish classes, and
`read-only` for a node that performs no writes. The settings MUST ride the
environment rather than an ACP node attribute because Fabro REJECTS `model` and
`reasoning_effort` as node attributes, so neither a node attribute nor a model
stylesheet is available here. Because the rendered adapter string is
SHELL-TOKENIZED before execution, the `CODEX_CONFIG` value MUST be shell-quoted:
an unquoted JSON object does not survive that tokenization — every quote
character is stripped and the adapter fails to parse its own configuration. The
quoting is part of the byte-identity referent below, so an implementation
rendering bare JSON is NOT byte-identical to the base string.

**The UN-PINNED BASE STRING, spelled out.** The posture keys are ALWAYS present:
an adapter carrying no pin still declares its sandbox and approval posture, just
as the retired `-c` form carried `sandbox_mode` and `approval_policy` on every
rendered string. The un-pinned base string for a write-capable node is therefore,
literally:

    CODEX_CONFIG='{"approval_policy":"never","sandbox_mode":"danger-full-access"}' INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp

and for a node that performs no writes it is that string with
`INITIAL_AGENT_MODE=read-only`. This is the ONE referent of "the un-pinned base
string" everywhere in this section. Spelling it out is load-bearing rather than
decorative: the opt-out below is defined as byte-identity against it, and the
posture keys live inside `CODEX_CONFIG` rather than on the command, so a reader
cannot reconstruct the un-pinned string from the bare path alone.

**A PINNED adapter is the un-pinned base string with `model` and
`model_reasoning_effort` ADDED inside `CODEX_CONFIG`**, the object's keys
remaining in sorted order. Pinning adds keys to that object and changes nothing
else: it never alters `INITIAL_AGENT_MODE`, never reorders the environment
assignments, and never appends an argument.

**The adapter is identified by its baked path, never by package name.** The
invocation MUST NOT be resolved through `npx` by package name. The baked path
preserves every property the previous `npx --no-install` form was chosen for —
it is version-free, it performs no npm registry round-trip so it runs under
`--network none`, and the baked image remains the single source of truth for the
adapter version — and it adds the one property that form lacked: an unambiguous
IDENTITY. `npx` resolves a package's bin through the SHARED global bin link, so
where two `codex-acp` packages are installed, invoking either package NAME runs
whichever package owns that link. A renderer using the name can therefore emit a
string naming one package while executing another, which defeats this section's
opening claim that a reader can predict the literal adapter string and verify its
command/args plus digest against `run_turn.command`. Relying on package-name resolution to distinguish the
successor from the predecessor is FORBIDDEN.

**The built-in fleet defaults.** Absent any `dispatcher.codex_models` override
the tiers MUST resolve to:

| class | model | reasoning effort |
|---|---|---|
| implementer (`implement`, `fix`, `review_fix`) | Claude adapter, `claude-opus-5` | `high` (via `CLAUDE_CODE_EFFORT_LEVEL`) |
| publish (`pr`) | Claude adapter, `claude-haiku-4-5` | `high` (via `CLAUDE_CODE_EFFORT_LEVEL`) |

So a default dispatch renders BOTH class adapters as Claude strings: the
implementer adapter as the Claude string given above, and the publish adapter as:

    ANTHROPIC_MODEL=claude-haiku-4-5 CLAUDE_CODE_EFFORT_LEVEL=high npx -y @agentclientprotocol/claude-agent-acp

A repository that pins its publish class to Codex with the FORMER default (before
this contract moved the `pr` default off Codex) would write
`dispatcher.codex_models.pr = { "model": "gpt-5.4-mini", "reasoning_effort": "high" }`,
which renders the publish adapter as the Codex string:

    CODEX_CONFIG='{"approval_policy":"never","model":"gpt-5.4-mini","model_reasoning_effort":"high","sandbox_mode":"danger-full-access"}' INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp

and a repository that pins its implementer to Codex renders the implementer
adapter as, for example:

    CODEX_CONFIG='{"approval_policy":"never","model":"gpt-5.5","model_reasoning_effort":"low","sandbox_mode":"danger-full-access"}' INITIAL_AGENT_MODE=agent-full-access /opt/livespec/codex-acp/bin/codex-acp

These values are stated here so the section satisfies its own opening claim: a
reader can reconstruct the literal strings and check their clear command/args
plus digest against the redacted `run_turn.command` without reading the implementation. The implementer class
carries design judgement and runs the strongest available model by default; the
`pr` node runs a scripted recipe and takes a cheap model — the Claude Haiku
default — by default, with Codex or any other model available as an explicit
per-repository override.

**Reachable tiers are bounded by the baked adapter.** The set of models this
adapter can actually reach is a property OF THE BAKED ADAPTER VERSION, not of
this specification: the adapter vendors a Codex generation, and a model the
vendored generation does not know is refused by the backend rather than silently
substituted. A pin naming an unreachable model terminates that candidate; only
an exact eligible diagnostic may advance an explicitly configured chain under
§"Factory-configurable ACP fallback priority". Without such a chain it still
fails every dispatch that uses it.

Therefore the reachable-tier set MUST be RE-MEASURED from the sandbox against the
real projected credential whenever the baked `codex-acp` version changes, and any
recorded tier table MUST NAME the adapter version it was measured against. A
table attributed to a version the image no longer bakes MUST NOT be carried here:
it reads as current, and a pin chosen from it fails at dispatch time with nothing
in the table to explain why. The concrete post-succession table is produced by
ledger item `bd-ib-nr3pon` and is not asserted by this section. The Claude default adapter is fetched by `npx -y` rather
than baked into the sandbox image, exactly as the review adapter is, and
authenticates with the `CLAUDE_CODE_OAUTH_TOKEN` the Dispatcher already projects
for the review node.

Making every node's adapter, model and effort configurable at the workflow,
per-repository and per-dispatch layers — including arbitrary adapter commands
for open-weight and local models — is a separate amendment tracked by ledger
item `bd-ib-tsna`; this section changes only the implementer default.

## ACP node adapter configuration

Every ACP node of the `implement-work-item` workflow — `implement`, `fix`,
`review_fix`, `pr`, `review`, `disposition` — runs an adapter the Dispatcher
RESOLVES FROM CONFIGURATION, never from a code-level provider choice.
Switching any node to any model behind any provider protocol, open-weight and
local models included, MUST be a configuration change with no code change.

**The per-node value.** A node's adapter configuration is a table with three
fields: `command` (string; the ACP adapter command, e.g.
`npx -y @agentclientprotocol/claude-agent-acp` or
`/opt/livespec/codex-acp/bin/codex-acp`), `env` (table of string to
string; environment assignments prefixed onto the command as leading
`KEY=value` pairs, the mechanism Fabro already parses), and `args` (array of
strings; appended to the command verbatim, e.g. `-c model_provider=<name>`). Model and
reasoning effort are NOT fields of their own: they ride in `env` for adapters
that read them from the environment (`ANTHROPIC_MODEL`,
`CLAUDE_CODE_EFFORT_LEVEL` on the Claude adapter, `CODEX_CONFIG` on the Codex
adapter), and MAY ride in `args` for an adapter whose own interface takes them
on the command line. No adapter this specification pins uses the `args` route
for model or effort today; both read them from the environment. A provider behind
an Anthropic-Messages or OpenAI-compatible endpoint is expressed the same way —
`env` carries `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_MODEL`
on the Claude adapter, `args` carries `-c model_provider=<name>` and its
provider definition on the Codex adapter — so the shape is provider-agnostic
by construction. The rendered adapter string MUST be exactly: the `env` pairs
in sorted key order, then `command`, then `args` in order, single-space
separated. Each `env` VALUE MUST be shell-quoted such that POSIX shell
tokenization of the rendered string recovers that value BYTE-FOR-BYTE. This is
stated as a round-trip property rather than as a literal quote-wrap because the
values are operator-supplied and unvalidated: a naive wrap in single quotes is
defeated by a value containing an apostrophe, which closes the quote early and
yields an unparseable command string rather than a wrong-but-parseable one.

**Three resolution layers, most specific wins.** Each node's value MUST
resolve through, in ascending precedence: (1) the WORKFLOW DEFAULTS — the
declared inputs and their defaults in the workflow's own `workflow.toml`
(`acp_adapter`, `pr_adapter`, `review_adapter`, `disposition_adapter` today),
so a vendored workflow carries its own defaults and the built-in fleet
defaults of §"Codex ACP node model pins" are expressed there; (2) the
PER-REPOSITORY LAYER — the `dispatcher.acp_nodes` table in the dispatch
TARGET's `.livespec.jsonc`, keyed by node name, read from the target
repository exactly as the tiers are; (3) the PER-DISPATCH LAYER — an explicit
`--acp-node <node>=<value>` argument on `dispatcher.py dispatch`,
`dispatcher.py loop` and the `drive` operation's `impl:<id>` action.
Resolution is per node and per FIELD: a more specific layer that sets
`command` or `args` REPLACES that field; `env` MERGES with the more specific
layer's keys winning. A layer that names a node not present in the workflow
MUST refuse the dispatch before any run exists, naming the node.

**`dispatcher.codex_models` is the per-repository shorthand for the Codex
tiers and remains valid.** At the per-repository layer it expands into the
`implement`/`fix`/`review_fix` and `pr` entries exactly as §"Codex ACP node
model pins" specifies, and an explicit `dispatcher.acp_nodes` entry for the
same node wins over the expansion only for the primary `command`, `env`, and
`args` fields it actually sets. Identity-only and fallback-only fields attach
after shorthand expansion and MUST NOT shadow it. That section's rendering rules for a
Codex-pinned tier are unchanged by this one.

**The per-dispatch layer is a recorded argument, never an environment
variable.** The no-environment-override rule of §"Codex ACP node model pins"
holds for every layer: an ad-hoc shell MUST NOT be able to re-tier the factory
with nothing in the committed record or the journal. The per-dispatch value
MUST be journaled on the dispatch record as its redacted structural
representation plus digest, not as raw env values. This argument is an OPERATOR
argument: the console's factory-drain launcher of §"Control surface and audit"
passes NO per-run argument, and this section does not change that.

**The supplying layer is visible in the run record.** For every node the
Dispatcher MUST journal, on the dispatch record, the adapter's command/args,
each env KEY and its supplying layer, and a deterministic digest of the exact
rendered adapter bytes. It MUST NOT journal raw env values. This redacted
structural form lets a reader distinguish workflow default, repository override,
and per-dispatch override without re-deriving it while preserving the secret
floor of §"Factory-configurable ACP fallback priority".

**Keys are committed-configuration-only.** `dispatcher.acp_nodes` joins
`dispatcher.codex_models` in the committed-configuration-only class of
§"Control surface and audit"; it is outside the API-configurable key set and
does not trigger the console Settings lockstep.

**Verification.** A negative control per layer MUST exist: for each of the
three layers, a test that sets a value at that layer and a conflicting value
at every less specific layer, and asserts the more specific value renders.
Proving that an arbitrary adapter with an `env` map and a provider definition
renders and takes precedence MUST be done hermetically — a stub endpoint or
the fake backend — and MUST NOT require network reachability of any real
provider from the factory.

Implemented by ledger item `bd-ib-tsna`; `bd-ib-un226z` (per-node provider
assignment) is superseded by this section.

## Factory-configurable ACP fallback priority

An ACP node MAY carry an ordered, provider-generic candidate chain so an
observed allowance outage or exact model removal does not make one configured
adapter a single point of failure. This is an additive configuration feature:
when no fallback metadata is present, or `fallbacks` is an empty array, adapter
resolution and rendered command bytes MUST remain byte-identical to §"ACP node
adapter configuration". In particular, the unconfigured `pr` node remains the
Claude Haiku 4.5 default ratified in v107, and an explicit
`dispatcher.codex_models.pr` entry remains candidate zero.

**Resolve the primary before attaching the chain.** The Dispatcher MUST first
resolve candidate zero through the existing workflow-default, `codex_models`,
explicit repository `command`/`env`/`args`, and per-dispatch layers in their
current order. Only then may repository identity metadata and `fallbacks` be
attached. A fallback-only `acp_nodes` table MUST NOT shadow a `codex_models`
primary or restore the workflow default. Built-in identity metadata applies only
while the finally resolved adapter matches that built-in; a fallback-enabled
arbitrary primary MUST carry explicit identity and MUST NOT retain the replaced
built-in's identity.

An identity-less arbitrary single-adapter override with no fallback metadata
retains the v107 containment path and cannot mint or consume current typed
holds. It is conservatively covered by every unexpired legacy provider record
and continues to mint legacy records through v107 cause-text attribution;
declaring explicit identity is the only route out of that blanket. Identity MUST
NOT be inferred from command text.

Every explicitly identified candidate, and every candidate in a fallback-enabled
chain, carries non-empty, non-secret `display_name`, `candidate_key`, and opaque
`availability_key`. Display text is never a machine key. The pair
`(availability_key, candidate_key)` identifies one candidate entitlement and MAY
be repeated across nodes when that identity is truly shared; different accounts
or routers MUST use different keys. A fallback entry additionally carries a
complete `command`; omitted `args` and declared adapter `env` mean empty values.
It MUST NOT inherit another candidate's command, args, declared env, model,
identity, signatures, or pricing. Container-level credentials remain shared by
the existing Worker credential projection; this clause promises no candidate-
level secret isolation.

For a fallback-enabled node, `command`, `args`, and `env` are public committed
data and MUST contain no literal credential, token, or secret reference.
Candidate credentials MUST arrive only through §"Worker credential projection";
the projected key is supplied through the uncommitted overlay directly to the
child process and omitted from the rendered adapter string, run input, run
record, and trace. A new provider credential channel requires its own ratified
change. A no-fallback legacy node retains v107's arbitrary-adapter env behavior
and Scenario 88 unchanged. Execution still receives the exact
resolved adapter bytes, but the existing journal rule is narrowed for secrets:
journals, traces, events, diagnostics, and refusals MUST store a redacted
structural form containing command/args, env key names and supplying layers plus
a deterministic digest, never raw env values or the full candidate chain.

The legacy string-valued `--acp-node NODE=ADAPTER` remains valid for a node with
no new-grammar metadata. It MUST refuse before claim on a new-grammar-enabled node,
because it carries no stable candidate/domain identity; it MUST NOT become hold-
exempt, retain stale metadata, or infer identity from command text. A future
structured chain override requires separate ratification. A new-grammar-enabled
dispatch MUST also refuse before claim when the Dispatcher or pinned Fabro build
does not advertise this capability. Unknown, duplicate-key, incomplete,
wrong-typed, or conflicting fallback configuration refuses before claim or run.

"New-grammar-enabled" means identity, signature, pricing, or a non-empty fallback
field is present; `fallbacks: []` alone remains the byte-identical no-op. The
enabling repository MUST commit `dispatcher.minimum_release` at or above the
first fallback-capable plugin release; this existing operator floor makes older
Dispatchers refuse rather than silently ignore the feature. From that release
onward every unknown `acp_nodes` key refuses before claim. Fabro capability is
read from the dispatch's resolved factory server, never a local binary. The
existing `acp_nodes`-wins rule applies only to primary `command`/`env`/`args`
fields actually set; identity-only and fallback-only fields attach after the
`codex_models` shorthand resolves.

**The availability-signature grammar is closed.** Candidate objects use this
shape, with unknown object keys refused:

```jsonc
{
  "display_name": "operator text",
  "candidate_key": "stable-candidate",
  "availability_key": "default-domain",
  "command": "adapter",
  "args": ["literal", "non-secret"],
  "env": {"NAME": "non-secret value"},
  "pricing": {
    "model": "exact-emitted-model",
    "input_usd_per_million": 0.0,
    "output_usd_per_million": 0.0,
    "cache_write_usd_per_million": 0.0,
    "cache_read_usd_per_million": 0.0
  },
  "availability_signatures": [
    {
      "source": "protocol.machine_code",
      "machine_code": "exact.nonempty.code",
      "cause": "model_unsupported",
      "scope": "candidate"
    },
    {
      "source": "protocol.message",
      "all_literals": ["usage limit", "requested model"],
      "exit_code": 1,
      "cause": "quota",
      "scope": "availability-domain",
      "hold_key": "optional-domain-override"
    }
  ]
}
```

`source` is exactly `protocol.machine_code`, `protocol.message`, or
`process.terminal_diagnostic`. `cause` is exactly `quota`, `rate_limit`,
`provider_capacity`, `provider_server_unavailable`, `model_unavailable`,
`model_not_found`, `model_unsupported`, or `model_not_entitled`. `scope` is
exactly `availability-domain` or `candidate`. A machine-code source requires one
non-empty exact `machine_code` and forbids `all_literals`; the other sources
require a non-empty array of non-empty `all_literals` and forbid `machine_code`.
An optional `exit_code` is an integer from 1 through 125 and only refines the
required discriminator; it is never sufficient by itself. Domain scope MAY
carry a non-empty opaque `hold_key`, defaulting to `availability_key`. Candidate
scope forbids `hold_key` and keys exactly on
`(availability_key, candidate_key)`. Duplicate identities within one node chain
and statically identical conflicting signatures MUST refuse the complete
configuration; cross-node identity reuse is intentional. A candidate belongs to
its `availability_key` domain plus every override `hold_key` declared by its
domain signatures. If distinct signatures nevertheless match one runtime
diagnostic with different cause/scope/key dispositions, the failure is
non-eligible and surfaced as ambiguous, and it creates no hold; runtime first-
match choice is forbidden.

Text matching is a conjunction after Unicode case-folding and whitespace
normalization, never a regular expression. It reads only the named ACP protocol
field or separately captured terminal adapter startup/termination diagnostic,
never an arbitrary exec-output tail, agent response, prompt, tool/test/review
output, or run log. Structured machine codes take precedence. Authentication,
command-not-found, cancellation, node deadline or stall expiry, generic HTTP
400/404, remote-compaction 404, malformed command/configuration, signal exit,
unattributed sandbox/DNS/transport failure, code/test/review/tool failure, and
non-convergence are non-eligible before configured matching and MUST terminate
with their original identity. A mere pre-turn failure is not provider evidence.

Built-in Claude and Codex candidates MUST carry exact, measured mappings for
stable diagnostics exposed by the pinned adapters, including the recorded
ChatGPT-account diagnostic that names the requested model as unsupported. The
generic HTTP 400 remains non-eligible; the exact model-naming discriminator is
candidate-scoped. Every Codex primary or fallback continues to obey the v107
pin, posture, baked-path, and empty-model opt-out rules. Consequently the v107
reachability statement is narrowed: an unreachable pin terminates that
candidate and advances only when its exact typed cause is eligible; otherwise it
still fails the node. Verification-run guidance applies to every new or changed
candidate.

**Preflight consumes versioned observed holds.** A current record carries at
least `scope`, opaque `hold_key`, optional `candidate_key`, stable
`observation_id`, occurrence time, bounded expiry, and explicit
`schema_version: 1`. Unknown versions MUST be preserved and surfaced as
unobservable, never interpreted as v1, rewritten, or allowed to mint a hold. A domain record skips
every candidate covered by its selected hold key; a candidate record skips only
the exact identity pair. Legacy provider-only records remain readable,
clearable by the legacy valve, and effective until retirement against built-in
candidates whose compatibility alias names that provider plus identity-less
legacy candidates, which every live legacy record covers. Explicitly identified
candidates MUST NOT be broadened to unrelated identities. Typed candidate evidence takes
precedence over legacy cause-text attribution when a chain executed.

A hold MUST come from an actual candidate attempt: a typed terminal failure or
an idempotently projected `agent.acp.failover` event from a run of any eventual
outcome. Expiry is computed from occurrence time and never from ingestion. No
hold may come from credentials, catalogs, host probes, predicted health, price,
model strength, or provider reset claims. The Dispatcher MUST retain configured
order after filtering.

The workflow MUST expose the ACP nodes that dominate every green terminal path.
Those success-critical nodes are admission-required; for the current graph they
are `implement`, `review`, and `pr`. Admission and rework admission refuse before
claim only when at least one such chain has no candidate. A conditional repair
or adjudication node may have an empty filtered chain at preflight, but if
reached it MUST terminate the run before starting an adapter with the typed
availability cause surfaced. It MUST NOT traverse a continuation/failure edge
into janitor, non-convergence, or `needs_human`, and the Dispatcher MUST NOT
reclassify it as deterministic work failure. An unsupported or
ambiguous workflow graph MUST refuse fallback-enabled dispatch instead of
guessing. Idle-factory and wait attention consume this identical verdict.

The admission-time credential probe creates no observed record. For a fallback-
enabled chain, a provider-limit/rate-limit probe refusal is an ephemeral
candidate-local skip for that one admission evaluation; the Dispatcher
continues in order and MUST NOT hold the loop while a success-critical chain is
viable. If all candidates are locally unusable, admission may refuse for the
empty chain but no durable hold is minted. The re-probe wait applies to a legacy
single candidate and a genuinely exhausted fallback chain, never a primary-only
probe refusal with a viable fallback.

Bounded expiry, later matching execution, and operator clearance are the only
hold-retirement routes. A node attempt that starts after a domain observation
and succeeds against the same hold key retires only that older domain record; a
later success by the exact candidate identity retires only its older candidate
record. A successful fallback MUST NOT clear its skipped or failed primary, even
when the whole run succeeds. An exact scope/key clearance valve MUST be
attributed, reason-required, append-only, and refuse a nonexistent live target;
the legacy provider valve addresses legacy records only.

**Reactive fallback is one bounded node visit.** The externally observable
integration is one run id, one sandbox identity, one node deadline, no
predecessor-node replay, ordered candidate attempts, and normal workflow
continuation on success. The Fabro repository owns the internal handler and this
repository consumes a capability-bearing pinned release. The scope boundary in
§"Provider-limit permanence and root-cause surfacing" is narrowed only for this explicit integration:
that section still does not govern Fabro generally, but the fallback-enabled
node MUST exhibit these observables.

Every candidate shares the node's original wall-clock deadline and receives
only its remaining time; timeout derivation MUST remain one node timeout, never
candidate count multiplied by timeout. Within one engine handler attempt each
candidate is tried at most once in order. `engine_attempt` and
`candidate_index` are distinct. Before any failover, an existing outer retry for
a non-eligible transient failure MAY retry the preflight-selected candidate.
After the first reactive transition the node visit is non-retryable: neither an
outer retry nor checkpoint/resume may replay any attempted or skipped candidate.
The attempted set, original deadline, and event ids MUST survive resume.
Exhaustion is a typed, non-retryable node outcome preserving the final cause.

Sandbox-local partial changes MAY pass to the successor with the original task
and a delimited recovery preamble that names the interrupted attempt and
requires inspection of current state. This is permitted only with durable proof
that every completed tool operation was sandbox-local and no external effect
began. A side-effect ledger MUST write onset before issuing an external mutation;
missing, incomplete, or unknown evidence is fail-closed and terminates without
fallback. Transition after onset additionally requires declared durable
idempotent/resumable semantics plus the idempotency key, resume identity, and
observed remote state. The current `pr` node MUST NOT fall back after push,
publication, or auto-merge arming begins until those guarantees exist. For the
current `pr` node, a publish branch or its pull request present on the remote at
takeover proves onset; inability to make that observation is treated as already
past onset.

**Events and projection are compatible, idempotent, and leak-free.** The feature
MUST NOT reuse Fabro's existing incompatible native-API `agent.failover` event.
Each reactive or actually executed preflight transition emits a versioned
`agent.acp.failover` event with `schema_version: 1`, stable event id, occurrence time, node visit,
engine attempt, candidate indexes and durations, from/to display and machine
identities, selected hold key, typed cause/scope, primary-generation
fingerprint, and separate full-chain digest. It MUST contain no command, env
value, credential, prompt, raw error, or unredacted diagnostic. Existing
`agent.failover` events and stored-run consumers remain unchanged and require
historical/native round-trip controls.
Unknown versions MUST be round-tripped byte-for-byte and surfaced as
unobservable; they MUST NOT mint a hold or silently disappear.

The Dispatcher MUST fetch events from the run's resolved factory target,
project by stable event id, calculate holds from occurrence time, and replay
projection during reconciliation. Read failure is not absence. It emits exactly
one flat fact per run/node with id
`hygiene:model-fallback-projection:<repo>:<run>:<node>`, existing `hygiene`
kind, `high` urgency, source reference to repository and dispatch journal, a
deterministic run/node/factory/error summary, and a `shell` handoff containing
the same executable server-qualified inspection command reconciliation uses.
Repeated failures aggregate into that id; it clears only after successful
idempotent projection for the run/node or an attributed, reason-required,
append-only operator clearance naming that exact fact id. Clearance retires the
fact only and MUST NOT mint, retire, or reinterpret a hold; run absence alone is
never resolution.

While any projection-failure fact remains unresolved, an unattended loop MUST
stop further picking for that repository. A human-attended `--item` dispatch MAY
proceed only after the high-urgency warning is surfaced before claim and does
not clear the fact.

Every actually executed non-primary candidate appends one idempotent journal
record and yields one aggregate attention fact per repository/node with id
`hygiene:model-fallback:<repo>:<node>`, existing `hygiene` kind, valid urgency,
source reference, and executable inspection handoff. The newest unresolved
observation supplies the deterministic summary. Later run failure does not
erase it, and it never refuses or disposes work. A primary node attempt clears
only a warning from the same primary-generation fingerprint when its attempt
began after the warning and completed successfully, regardless of the overall
run's later outcome. Older concurrent success, unrelated success, probes, and
unexecuted preflight selection cannot clear it. Primary replacement retires the
prior warning as append-only `superseded`; non-primary chain changes alter only
the full-chain digest, not the primary generation, so they do not strand the
warning.

**Cost follows every attempt in a successful fallback run.** Token use and
elapsed time MUST be attributed and summed per candidate attempt, including
failed attempts before the successful fallback. Emitted model identity,
normalized only by stripping one trailing `-YYYYMMDD` date suffix (any broader
prefix match is not exact identity), selects built-in pricing only for
the matching built-in candidate and endpoint. For an arbitrary candidate its
matching explicit table takes precedence. Candidate pricing, when present, MUST be an
all-or-none table naming the exact model and finite non-negative USD-per-million
input, output, cache-write, and cache-read prices, and applies only when emitted
identity matches. If any nonzero usage component cannot be priced, the whole run
cost is unobservable, not a known partial subtotal; §"Fail-closed cost gate
(keyed on `--item` presence)" remains authoritative. An unknown model MUST NOT
be priced as an unrelated default or treated as free. Terminally unsuccessful
runs retain the existing no-cost-observation/no-gate posture.

## ACP node timeouts

Every node timeout of the `implement-work-item` workflow, and the run's stall
watchdog, MUST resolve from configuration rather than from literals hard-coded
in the workflow graph.

**Keys.** `dispatcher.node_timeouts` is a table keyed by node name
(`implement`, `fix`, `review_fix`, `pr`, `review`, `disposition`, `janitor`)
whose values are positive integers of seconds; `dispatcher.stall_timeout_seconds`
is a positive integer of seconds for the run-level stall watchdog. A node with
no configured value MUST resolve to **1800** seconds; the stall watchdog with
no configured value MUST resolve to **7200** seconds. A non-positive or
non-integer value MUST be rejected before any run exists, naming the key. Both
keys are committed-configuration-only, alongside `dispatcher.codex_models` and
`dispatcher.acp_nodes`, and do not trigger the console Settings lockstep.

**Resolution layers.** The same three layers and precedence as §"ACP node
adapter configuration" apply: the workflow's own declared defaults, the
dispatch target's `.livespec.jsonc`, then a per-dispatch
`--node-timeout <node>=<seconds>` argument that MUST be journaled on the
dispatch record; the record MUST name the supplying layer per node.

**Rendering, literally.** The pinned Fabro build types a quoted duration
attribute at parse time and its template expansion never re-types a rendered
string, so a templated `timeout` attribute silently becomes NO timeout. The
Dispatcher therefore MUST NOT template a timeout attribute from a workflow
input. It MUST write each resolved value into the self-contained dispatch
payload's workflow graph as a literal duration (`timeout="1800s"`,
`stall_timeout="7200s"`) before invoking `fabro run`, and a test MUST assert
that no timeout attribute in the rendered graph contains a template opener.

**The subprocess ceiling follows the graph.** The Dispatcher's `fabro run`
subprocess ceiling MUST be derived from the resolved node timeouts and the
resolved stall timeout — the graph's worst-case path plus a fixed margin —
rather than from a hard-coded constant, so that lengthening a node cannot
outrun the poller and shortening one is not masked.

**The 30-minute default is a deliberate reduction.** It lowers `implement`
from the previously shipped 14400 seconds and `janitor`/`fix` from 3600
seconds, against recorded legitimate turns near 120 minutes. A repository that
needs longer turns sets them; the default is the maintainer's ruling and the
reduction is recorded in the implementing item's triage record.

**Codex compaction limit.** A Codex-backed node's `model_auto_compact_token_limit`
is an adapter argument and rides the node's `args` under §"ACP node adapter
configuration"; this section adds no separate key for it.

Implemented by ledger item `bd-ib-cnkf`.

## Provider-limit permanence and root-cause surfacing

A model provider that refuses on a usage or spend ceiling has not failed
transiently. Retrying cannot succeed, and it spends an allowance that is already
gone. This section binds how the Dispatcher classifies and surfaces such a
refusal.

**A cause retrying cannot resolve is a permanent failure.** When a failure's
cause chain carries a cause that retrying CANNOT resolve, the Dispatcher MUST
classify the failure as permanent rather than as transient infrastructure, and
MUST carry that reclassification into the failure signature as well as the
category, so a consumer keying on either sees the same verdict.

Two classes of such cause are recognised today, and BOTH reclassify:

- A **provider usage or spend ceiling**. This holds for EVERY model vendor, not
  only the one whose ceiling is currently scarce, and it is the class this
  section is principally about.
- A **remote-compaction 404** — the agent runtime's own conversation-compaction
  endpoint returning not-found. Retrying re-issues the same doomed request.
  Measured 2026-08-22: 2 of the 13 diagnosable causes across 53 failed runs.

The TYPED provider-limit state described below is set by the FIRST class only. A
remote-compaction 404 reclassifies the category and signature without setting it,
which is correct: it is permanent, but it is not a spend ceiling and the
admission gate MUST NOT treat it as one.

**The surfaced cause is the permanent one, else the ROOT of the chain.** A Fabro
cause chain is ordered outermost-first, so the element carrying the provider's
payload is the LAST one. Where the chain carries a permanent cause the Dispatcher
MUST surface THAT element, wherever in the chain it sits, because it is the one
naming the fault. Otherwise the Dispatcher MUST surface the innermost element and
MUST NOT surface the outermost one as the fault. Measured over every failure block in the 53
failed runs on the `hp` factory (2026-08-22): all 17 blocks carry exactly two
causes and `causes[0]` is the literal constant `"ACP protocol error"` in 17 of
17 — a fixed wrapper naming the transport, never the fault.

**The provider's own sentence is what surfaces.** Where the provider embeds its
message inside a structured payload, the Dispatcher MUST surface that embedded
message rather than the raw enclosing text. The raw form leads with an internal
path and buries the sentence that names the ceiling and its reset instant, which
is the only part an operator can act on.

**The condition is typed, not re-matched.** The Dispatcher MUST carry the
provider-limit condition as typed state on the failure detail. A consumer —
notably the admission gate of §"Provider spend containment" — MUST be able to
read that state directly, and MUST NOT be required to re-match the cause text for
itself. Detection MUST prefer the provider's own STRUCTURED machine token over
prose matching, and MAY fall back to prose hints when that token is absent: prose
hints are locale- and wording-fragile, and a near-miss variant has already been
observed to defeat a substring match that omitted one word.

**CONTROL — an ordinary failure keeps its classification.** A failure whose cause
chain carries NO permanent cause of either class above MUST retain the category
and signature it arrived with. A rule that reclassified every failure as
permanent would not be a discrimination rule; it would disable retries
wholesale.

**SCOPE BOUNDARY — this binds the Dispatcher, and one retry still happens.** Two
layers classify the same refusal and they disagree. Measured 2026-08-23 on run
`01M0PYKEEC26SRSG8W16HB2NWP`: the Fabro NODE layer recorded
`node_outcomes.implement.failure.category` as `transient_infra`, while the
Dispatcher recorded `deterministic` for the same failure in the same minute. The
node layer, having judged the ceiling transient, RETRIED — the checkpoint records
`node_retries.implement` of 1 — straight back into a window that could not clear
for four days. That classifier runs inside the sandbox and is NOT governed by
this specification. This section therefore MUST NOT be read as preventing that
retry: until the upstream classifier is corrected, ONE wasted attempt per
exhausted-window dispatch is expected behaviour, and the admission gate of
§"Provider spend containment" — not this section — is what prevents the dispatch
from being attempted at all. The explicit same-node integration in
§"Factory-configurable ACP fallback priority" is the sole carve-out: it binds
that fallback-enabled node's observable transition semantics without otherwise
placing Fabro's classifier under this specification.

**The reset instant is not a machine timestamp.** The provider's message names
when the window reopens, and that is the most useful thing in it. It is rendered
in the CALLER's locale: for one measured refusal the Codex CLI printed `5:33 AM`
host-local while Fabro's payload rendered the same instant as `3:33 AM` UTC. Any
consumer that parses it into a machine timestamp MUST resolve which timezone it
is in; surfacing the sentence verbatim carries no such obligation.


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

- **Pinned lifecycle-guarded entry point.** The underlying `bd` binary is
  pinned to v1.0.5 (sha256-verified release tarball). The plugin invokes it
  through a managed public entry point resolved from configuration (the
  `LIVESPEC_BD_PATH` environment variable, or a configured default). When a
  lifecycle guard is installed, that path MUST resolve to the guard
  (`/usr/local/bin/bd` on the reference fleet host) and MUST NOT resolve to
  the guard's private delegate executable. A repository's mise configuration
  MUST NOT declare or install `bd`, because an activated mise tool or
  regenerated shim can shadow the public guard.
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
`blocked_reason` policy fields, the `factory_safety` runnability field, the
`awaits_scope_override` refusal-remedy signal, reused `assignee`; `priority`
dropped);
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
  - **Adoption of a row a non-lifecycle writer left `open` assigns it a
    real rank.** A row left at the beads-native `open` status by ANY
    writer that performs no second step — a CI or off-host SSH write
    ingress, or a raw `bd create` run outside the 2-step path above — is
    NOT a livespec lifecycle state and MUST NOT rest there. The
    Dispatcher's ledger normalization MUST adopt such a row: `open` →
    `backlog`, and `in_progress` (the status a raw `bd --claim` stamps)
    → `active`. On adoption, if the row's `rank` reads back through the
    shared bottom-sentinel fallback (`metadata` carries no real `rank`),
    the normalization MUST ALSO assign it a real, non-sentinel
    `metadata.rank` — a single bottom-of-order insert — so the adopted
    row satisfies the "every live (head) issue has a real, non-sentinel
    rank" invariant without an on-demand `rebalance-ranks`. This is a
    single insert performed AT adoption; it does NOT change the standing
    decision that the bulk `rebalance-ranks` command is on-demand only
    and NEVER auto-fires. `deferred` stays parked and is never
    auto-remapped; every OTHER non-lifecycle status (hooked, pinned, or
    any ad-hoc or unknown value) is residual drift, left untouched and
    surfaced only by the ledger status-conformance check, never
    auto-remapped. This normalization runs at four cadences: the
    dispatch loop (`dispatcher.py loop`), the single-dispatch path
    (`dispatcher.py dispatch`), the standalone `dispatcher.py
    ledger-normalize` CLI (an operator self-heal needing no dispatch),
    and the always-run pre-push `dispatcher.py ledger-normalize --gate`
    mode.
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
  `rework_pending` — beads label `rework:pending` (a boolean logical field
  carried on the materialized work-item: present ⟺ the label is present;
  stamped and cleared only per §"Rework-pending re-dispatch", so the
  selection, accounting, and discrimination clauses there read a
  first-class field rather than a raw label);
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
  timers, credential wrappers, the plugin cache, and Fabro servers — or
  changes external merge-gate machinery under `.github/workflows/`), and
  `needs-privileged-host` (privileged provisioning — a Dolt server, a
  1Password environment, a per-tenant Fabro server). The sharp line:
  writing CODE for any of these (including the Dispatcher's own code) is
  factory-safe; APPLYING host or external factory-gate state is host-only.
  Editing `.github/workflows/` remains host-routed even while ordinary CI
  runs on GitHub-hosted capacity, because those files are the factory's own
  executable merge gates and an agent must not rewrite its own examiner.
- `awaits_scope_override` — boolean read from the presence of the beads label
  `awaits-scope-override`. It is `true` only after a dispatch attempt is
  refused by the declared-workflow-edit arm while `factory_safety` is null,
  meaning `set-workflow-scope-override:<id>:citation-only` is the applicable
  remedy. It is distinct from `factory_safety`: a non-null `factory_safety`
  item is never awaiting this override because predicate ordering guarantees
  the override cannot admit it. The Dispatcher MUST set the label on that
  specific refusal and MUST clear it when the override is applied or when the
  item's current text no longer triggers the declared-workflow-edit arm, so
  consumers may treat the signal as current state rather than history.
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

`pinned` is ALSO the ref the post-merge janitor provisions its
livespec-core clone at (§"Dispatch preflight and post-merge step
discipline" → "Janitor-core provisioning resolution"): the Dispatcher
MUST NOT silently substitute a moving branch tip for a missing `pinned`,
though a repository's explicitly-declared `pinned: "master"` bootstrap
value is honored as declared. `core_repo` (OPTIONAL) declares the
repository URL the janitor clones livespec-core from; when absent the
fleet livespec-core repository is used, and a present-but-unusable
`core_repo` refuses rather than sliding onto that fleet default.

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
environment variable (the managed public entry point to the pinned `bd`
binary, resolving to the lifecycle guard when installed) and
`LIVESPEC_BEADS_FAKE` likewise overlay this block at runtime and are not
committed config keys.

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
