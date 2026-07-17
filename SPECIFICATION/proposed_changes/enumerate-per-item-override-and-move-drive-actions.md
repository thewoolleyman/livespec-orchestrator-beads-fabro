---
topic: enumerate-per-item-override-and-move-drive-actions
author: claude-opus-4-8
created_at: 2026-07-17T04:47:48Z
---

## Proposal: Enumerate the three per-item cap-override drive actions (with clear-to-inherit) and the guarded operator `move`

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/README.md
- SPECIFICATION/scenarios.md
- ../tests/heading-coverage.json

### Summary

De-drift the `drive` action-id grammar so `contracts.md` enumerates the operator drive actions AS THEY ARE SHIPPED. PR #707 added FOUR new operator actions to the `drive` command — the three per-item cap-override verbs (`set-merge-on-review-cap`, `set-review-fix-cap`, `set-acceptance-rework-cap`) and the guarded queue-control `move` — WITHOUT amending the spec, and this branch adds a fifth behavior: a reserved `clear` value on the three cap verbs that REMOVES a per-item override so the item reinherits the global default. The spec still says `drive` accepts "the five human operator action ids" and enumerates only `approve` / `accept` / `reject` / `set-admission` / `set-acceptance`, in THREE places (`contracts.md` §"The skill surface" primary paragraph, `contracts.md` §"`drive`" grammar sentence, `contracts.md` §"Machine-path exemption — the Dispatcher"), plus once in `SPECIFICATION/README.md`. Each of those enumerations is now falsified — a wrong count and an incomplete list. This change amends all four enumerations to the TEN current action ids — the four shipped in `b620304` + this branch (the three cap verbs and `move`) PLUS `resolve-blocked:<work-item-id>:ready|backlog`, a `needs-human` block-clear valve shipped even earlier (commit `69c3ef6`) that the independent review found was likewise never enumerated — names the separate `config` action family in the §"`drive`" grammar sentence so that enumeration is not falsely exhaustive, states the exact value grammars for the three cap verbs (boolean `true|false`, positive-int caps) plus the `clear` sentinel and its inherit-from-global semantics, states the guarded `move` allowed/forbidden target sets and the ship-guard, and preserves the label-only + status-unchanged write guarantee (extending it from the two policy edits to the three cap overrides, and adding the status-only guarantee for `move`). It APPENDS two scenarios (46, 47) and co-edits `tests/heading-coverage.json` for the two new H2 headings. It fixes the action-id grammar, the allowed/forbidden sets, and the write guarantees — not the internal store or label mechanism.

Critically, the orchestrator side is correctly THREE named per-cap verbs, NOT one parameterized `set-override`. The ratified console spec (`thewoolleyman/livespec-console-beads-fabro`) fixes ONE parameterized per-item override command that FANS OUT to these three named orchestrator actions — the one console command that does NOT map 1:1 onto a `drive` action-id. This proposal preserves that shape and does not collapse the three verbs.

### Motivation

This is a DE-DRIFTING change: the actions already shipped and the spec merely catches up. Design records (the tiebreaker per `contracts.md` §"Intent preservation"):

- **The ratified operator-console spec** in the sibling repo `thewoolleyman/livespec-console-beads-fabro` fixes the console→orchestrator mapping this amendment must stay consistent with. `SPECIFICATION/scenarios.md:328` states the Work-item Lifecycle vocabulary is "six commands, five of them mapping 1:1 onto the orchestrator's `drive` action-id surface" — the sixth, the per-item override command, is the one that does NOT map 1:1: it fans out. `SPECIFICATION/contracts.md:479` fixes that the override command "sets, or with a null `value` clears, ONE per-item override", and `SPECIFICATION/contracts.md:487` fixes that it "maps onto the orchestrator's published PER-SETTING override action for that key" and "serves `merge_on_review_cap`, `review_fix_cap`, and `acceptance_rework_cap`" — the three settings whose overrides are NOT the established `set-admission` / `set-acceptance` commands. The console's `value: null` is exactly the `clear` this branch adds on the orchestrator side.
- **The maintainer's 2026-07-17 "broad moves, keep ship-guard" decision** for the `move` action: an operator may move a selected item broadly among `backlog` / `ready` / `blocked` / `active` for hands-on queue control, but `done` still requires the accept-from-acceptance path — no force-shipping unverified work — and `acceptance` / `pending-approval` are entered only on their own guarded/entry paths.
- **The realized code**: `thewoolleyman/livespec-orchestrator-beads-fabro` master commit `b620304` ("feat(drive): per-item cap-override actions and guarded operator move") landed the three cap verbs plus `move`; this branch's commit `1194f33` ("feat(drive): clear-to-inherit for the per-item cap-override verbs") added the `clear` sentinel. The shipped `_drive_policy_valves.py` fixes the cap-verb → setting-key → label-prefix mapping (`merge-on-review-cap:` / `review-fix-cap:` / `acceptance-rework-cap:`), the `clear` sentinel, and the move-allowed frozenset `{backlog, ready, blocked, active}` with `done` / `acceptance` / `pending-approval` refused.
- **The `resolve-blocked` valve** — action `resolve-blocked:<work-item-id>:ready|backlog`, handler `resolve_blocked_item` (`_drive_policy_valves.py`), shipped in commit `69c3ef6` ("feat: add dispatcher needs-human blocked path") ahead of 0.42.0 — moves a `blocked` item whose blocked-reason is `needs-human` to `ready` or `backlog` and is refused for any other source state. The Dispatcher may NOT auto-resolve a `needs-human` block (that is exactly what "needs human" means), so it is a human-triggered operator command, and belongs in the same human-valve enumeration as the others; it was omitted from the spec at the same time the caps and `move` were.

Two facts ALREADY in this spec CORROBORATE the change rather than conflict with it, which is why this is de-drifting rather than a new direction. `contracts.md` §"Dispatcher policy settings" already establishes the five overridable `dispatcher.*` settings, each a global default with a per-item ledger-label override that WINS over the global — the three cap verbs are exactly the operator-facing write path for the three of those (`merge_on_review_cap`, `review_fix_cap`, `acceptance_rework_cap`) that previously had no drive action. And `contracts.md` §"`wip_cap` — the one setting with no per-item override" already fixes that `wip_cap` admits NO per-item override — so the deliberate ABSENCE of a `set-wip-cap` action from the cap-override set is required by, not in tension with, the existing spec.

### Proposed Changes

#### Scope note — what this proposal does NOT touch

- **`SPECIFICATION/spec.md` and `SPECIFICATION/constraints.md` are DELIBERATELY UNCHANGED.** Neither enumerates the `drive` operator action-ids or states a count of them (verified: no "five human", no `set-admission`/`set-acceptance` enumeration, and no `move:` grammar occurs in either), so no statement in either is falsified by adding these actions. This is a deliberate non-change, not an omitted sweep.
- **Scenario 31 stays VERBATIM.** It exercises the original five actions and is not falsified; the new actions get their own Scenarios 46–47. Only the cross-reference to it inside the amended §"The skill surface" paragraph is EXTENDED to also cite 46–47.
- **`SPECIFICATION/history/**` is immutable and out of scope.**

#### A. `SPECIFICATION/contracts.md`

**A.1 — AMEND §"The skill surface" (the `**Human valve actions.**` paragraph).** This is the PRIMARY replace-target and the authoritative enumeration.

Replace-target (exists verbatim, currently at contracts.md:238–269):

```
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
```

Replacement:

```
**Human valve actions.** `drive` additionally accepts the ten human
operator action ids (the two human-delegable gate commands, the
corrective `reject:`, the blocked-resolution `resolve-blocked:`, the two
admission/acceptance policy edits, the three per-item cap overrides, and
the guarded queue-control `move`) — `approve:<work-item-id>` (the human
approval act: transitions an
effective-`manual` item from `pending-approval` to `ready`; admission to
`active` then follows mechanically when a WIP slot frees, dependencies
are clear, and an assignee resolves), `accept:<work-item-id>` (the human
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
```

The rest of §"The skill surface" (the `Codex and other non-Claude runtimes MUST use the same Python CLI…` paragraph that follows) is UNCHANGED.

**A.2 — AMEND §"`drive`" (the action-id grammar sentence).** This sentence names the count and lists the action-id families; it now reads "five", omits the four newer cap/move actions PLUS `resolve-blocked`, and does not name the separate `config` family at all.

Replace-target (exists verbatim, currently at contracts.md:176–180):

```
it is a pure executor of its own **action-id grammar** — an `impl:`
dispatch action or one of the five human valve/policy actions
(`approve:` / `accept:` / `reject:` / `set-admission:` /
`set-acceptance:`). It MUST NOT duplicate ranking or composition logic
from any `next` surface, and it MUST NOT create net-new work-items.
```

Replacement:

```
it is a pure executor of its own **action-id grammar** — an `impl:`
dispatch action, one of the ten human valve/policy actions
(`approve:` / `accept:` / `reject:` / `resolve-blocked:` /
`set-admission:` / `set-acceptance:` / `set-merge-on-review-cap:` /
`set-review-fix-cap:` / `set-acceptance-rework-cap:` / `move:`), or a
config action (`config` / `config-manifest` /
`set-config:<key>:<value>`). It MUST NOT duplicate ranking or
composition logic from any `next` surface, and it MUST NOT create
net-new work-items.
```

**A.3 — AMEND §"Machine-path exemption — the Dispatcher" (the human-triggered-commands enumeration).** This inline list names the human-triggered operator commands to exclude them from the machine-path exemption; it now omits the four newer cap/move actions PLUS `resolve-blocked`, wrongly implying they might be machine-path dispositions.

Replace-target (exists verbatim, currently within contracts.md:672):

```
The human-triggered operator commands (`drive` `approve:`/`accept:`/`reject:`/`set-admission:`/`set-acceptance:` action ids, per §"`drive`") are NOT machine-path dispositions
```

Replacement:

```
The human-triggered operator commands (`drive` `approve:`/`accept:`/`reject:`/`resolve-blocked:`/`set-admission:`/`set-acceptance:`/`set-merge-on-review-cap:`/`set-review-fix-cap:`/`set-acceptance-rework-cap:`/`move:` action ids, per §"`drive`") are NOT machine-path dispositions
```

The remainder of that sentence ("— their consent is the operator's explicit action selection.") is UNCHANGED.

#### B. `SPECIFICATION/README.md`

**B.1 — AMEND the `drive` overview enumeration.** The README lists the human valve/policy actions and omits the four newer cap/move actions plus `resolve-blocked`.

Replace-target (exists verbatim, currently at README.md:68–70):

```
the human valve/policy
actions (`approve:` / `accept:` / `reject:` / `set-admission:` /
`set-acceptance:`) apply the corresponding ledger disposition.
```

Replacement:

```
the human valve/policy
actions (`approve:` / `accept:` / `reject:` / `resolve-blocked:` /
`set-admission:` / `set-acceptance:` / `set-merge-on-review-cap:` /
`set-review-fix-cap:` / `set-acceptance-rework-cap:` / `move:`) apply the
corresponding ledger disposition.
```

#### C. `SPECIFICATION/scenarios.md`

APPEND two new scenarios after the current final scenario (`## Scenario 45 — Unobservable cost fails closed on an unattended drain and warns on a hand-picked dispatch`). The highest existing scenario number is 45, so these take 46–47 and leave no gap. No existing scenario is amended or removed.

**C.1 — ADD `## Scenario 46 — Per-item cap overrides set a label or clear to reinherit the global default`:**

```gherkin
Feature: Per-item cap overrides set one label and clear-to-inherit removes it
  As the operator (or the console acting on the operator's behalf)
  I want the three per-item cap-override actions to set or clear exactly one override
  So that a work-item can override, then reinherit, a global dispatcher cap without any status change

Scenario: set-review-fix-cap writes the override without touching the status
  Given a ready work-item carrying no per-item review_fix_cap override
  When the operator invokes `drive --action set-review-fix-cap:<work-item-id>:5`
  Then the item's per-item review_fix_cap override becomes 5
  And the item's status is unchanged
  And the journal records the actor

Scenario: set-merge-on-review-cap takes a boolean value
  Given a work-item carrying no per-item merge_on_review_cap override
  When the operator invokes `drive --action set-merge-on-review-cap:<work-item-id>:true`
  Then the item's per-item merge_on_review_cap override becomes true
  And the item's status is unchanged

Scenario: clear removes the override so the item reinherits the global default
  Given a work-item carrying a per-item acceptance_rework_cap override
  When the operator invokes `drive --action set-acceptance-rework-cap:<work-item-id>:clear`
  Then the per-item acceptance_rework_cap override is removed
  And the item reinherits the global dispatcher.acceptance_rework_cap default
  And the item's status is unchanged

Scenario: clearing an already-absent override is a green no-op
  Given a work-item carrying no per-item review_fix_cap override
  When the operator invokes `drive --action set-review-fix-cap:<work-item-id>:clear`
  Then the action succeeds without error
  And the item still carries no per-item review_fix_cap override
  And the item's status is unchanged
```

**C.2 — ADD `## Scenario 47 — The guarded move relocates within the operator-movable statuses only`:**

```gherkin
Feature: The guarded move performs operator queue control without force-shipping
  As the operator commanding hands-on queue control
  I want move to relocate a selected item only among the operator-movable statuses
  So that queue control writes only the status and never force-ships unverified work past the acceptance ship-guard

Scenario: move relocates an item to an allowed status and writes only the status
  Given a work-item at backlog
  When the operator invokes `drive --action move:<work-item-id>:ready`
  Then the item's status becomes ready
  And nothing other than the item's status is changed
  And the journal records the actor

Scenario: move to done is refused
  Given a work-item the operator wants to force to done
  When the operator invokes `drive --action move:<work-item-id>:done`
  Then the action is refused with a clear error
  And the item's status is unchanged
  And done stays reachable only by accepting from acceptance

Scenario: move to acceptance or pending-approval is refused
  Given a work-item at active
  When the operator invokes `drive --action move:<work-item-id>:acceptance`
  Then the action is refused with a clear error
    And when the operator instead invokes `drive --action move:<work-item-id>:pending-approval`
  Then that action is also refused with a clear error
  And acceptance and pending-approval are entered only on their own guarded or entry paths
```

#### D. `tests/heading-coverage.json` (co-edit — REQUIRED, same revise payload)

The H2 set CHANGES (two H2 headings are ADDED; none is removed or renamed), so this file MUST be co-edited in the SAME revise payload so the accept is atomic. In `resulting_files[]` its path MUST be spelled **`../tests/heading-coverage.json`** — the wrapper joins `spec_target / path` and `--spec-target` is the `SPECIFICATION/` tree, so a bare `tests/heading-coverage.json` would wrongly resolve to `SPECIFICATION/tests/heading-coverage.json`.

**ADD exactly these two entries** (no REMOVE, no RENAME), each following the established `TODO`-sentinel pattern (`"spec_root": "SPECIFICATION"`, `"test": "TODO"`, plus a `reason`):

1.
```json
{
  "heading": "## Scenario 46 — Per-item cap overrides set a label or clear to reinherit the global default",
  "spec_root": "SPECIFICATION",
  "spec_file": "scenarios.md",
  "test": "TODO",
  "reason": "TODO: bind to an INTEGRATION-TIER-or-above test (never a unit-tier test — a scenario describes user-observable behavior, per `SPECIFICATION/constraints.md` §\"Heading taxonomy\"). Added by the enumerate-per-item-override-and-move-drive-actions revise: the three per-item cap-override drive verbs (set-merge-on-review-cap boolean, set-review-fix-cap / set-acceptance-rework-cap positive-int) write a per-item cap label without touching status, and the reserved `clear` value removes the label so the item reinherits the global dispatcher.* default, with clear-when-absent a green no-op. The exercising test binds through drive.run_action and the FakeBeadsClient-backed store seam (b620304 + the clear-to-inherit commit)."
}
```
2.
```json
{
  "heading": "## Scenario 47 — The guarded move relocates within the operator-movable statuses only",
  "spec_root": "SPECIFICATION",
  "spec_file": "scenarios.md",
  "test": "TODO",
  "reason": "TODO: bind to an INTEGRATION-TIER-or-above test (never a unit-tier test — a scenario describes user-observable behavior, per `SPECIFICATION/constraints.md` §\"Heading taxonomy\"). Added by the enumerate-per-item-override-and-move-drive-actions revise: the guarded move drive action writes ONLY the item's status among the operator-movable set {backlog, ready, blocked, active} and refuses done / acceptance / pending-approval with a clear error, preserving the accept-from-acceptance ship-guard. The exercising test binds through drive.run_action and the FakeBeadsClient-backed store seam (b620304)."
}
```

Each entry's `heading` MUST match the ratified `## ` heading text BYTE-FOR-BYTE (including the em dash `—`). If the revise pass rewords either scenario heading, the co-edit MUST track it. (`contracts.md` §"The skill surface", §"`drive`", §"Machine-path exemption — the Dispatcher", and `README.md` add/remove/rename NO H2 heading — the amendments are all in-paragraph — so those files need no heading-coverage entry.)

#### E. Drift sweep — corroborating statements the revise pass MUST leave alone

Each was read (not merely grepped) and re-checked against the change. No further edit is required; the following statements CORROBORATE the amendment rather than conflict with it:

1. §"Dispatcher policy settings" → "The three policy settings" / "The two rework caps" — already establishes the five overridable `dispatcher.*` settings, each a global default with a per-item ledger-label override that WINS over the global. The three new cap verbs are precisely the operator-facing write path for the three of those (`merge_on_review_cap`, `review_fix_cap`, `acceptance_rework_cap`) that had no `drive` action. CONSISTENT; no edit.
2. §"`wip_cap` — the one setting with no per-item override" — fixes that `wip_cap` admits NO per-item override. The deliberate ABSENCE of a `set-wip-cap` verb from the cap-override set is REQUIRED by this section; there is no drift. CONSISTENT; no edit.
3. §"Dispatcher policy settings" → "Control surface and audit", console surface 1 ("Per-setting write commands… There is no single arming command that flips several settings at once.") — CORROBORATES the per-setting granularity: the orchestrator side is three named per-cap verbs, not one arming command. CONSISTENT; no edit.
4. §"Dispatcher policy settings" → "Control surface and audit" (the per-disposition audit journal) — each operator write here is human-TRIGGERED (not an auto-disposition) yet still writes through the store seam with the journal recording the actor, exactly as A.1 states. CONSISTENT; no edit.
5. §"Store-write consent discipline" — the new actions are per-operation-consented human writes whose consent is the explicit action selection; A.3 keeps them out of the machine-path exemption. CONSISTENT; no edit.
6. `scenarios.md` Scenario 31 ("drive human valve actions") — exercises the original five and is not falsified; the new actions are covered by Scenarios 46–47. The only touch to Scenario 31 is the extended cross-reference INSIDE the amended A.1 paragraph. No edit to Scenario 31 itself.
7. The sibling console spec (`thewoolleyman/livespec-console-beads-fabro`, `SPECIFICATION/scenarios.md:328`, `SPECIFICATION/contracts.md:479`, `:487`) — CORROBORATES via the design record: one parameterized console override command fanning out to the three named orchestrator actions, with `value: null` ⇒ `clear`. A different repo; not edited here.
8. §"Scope asymmetry with the spec-side `next`" (contracts.md ~506–514, "it deliberately EXCLUDES the impl-side human valves … it misses the impl-side human valves") — references "the impl-side human valves" as a work-item-STATE category (items resting at `pending-approval`, `acceptance`, or `blocked` awaiting a human), NOT an enumeration or count of the `drive` action-ids. Adding the new action verbs does not falsify it. CONSISTENT; no edit. (Re-swept after adding `resolve-blocked`: the ONLY action-id enumerations/counts in the live spec tree are the four amended here — contracts.md:177–179 [A.2], :238–269 [A.1], :672 [A.3], and README.md:68–70 [B.1]; no fifth enumeration and no stray "ten" statement is introduced anywhere else.)

### Notes for the revise pass

- **This is ONE coherent de-drifting change.** The four already-shipped actions plus the `clear` form are enumerated AS THEY ARE; the spec merely catches up to `b620304` + the clear-to-inherit commit. A single revise decision on the `enumerate-per-item-override-and-move-drive-actions` topic.
- **The three cap verbs' SHAPE is UNCHANGED and MUST NOT be collapsed.** The orchestrator correctly exposes THREE named per-cap actions (`set-merge-on-review-cap`, `set-review-fix-cap`, `set-acceptance-rework-cap`), NOT one parameterized `set-override`. The single parameterized override lives on the CONSOLE side and fans out to these three (the one console command that does not map 1:1 onto a `drive` action-id, per the ratified console spec). Do NOT "simplify" the three verbs into one.
- **Heading-coverage IS co-edited** — but ONLY because section C adds two `## Scenario` H2 headings. The contracts.md and README.md amendments (A.1–A.3, B.1) change NO H2 heading (all in-paragraph), so they contribute no heading-coverage entry. The two entries in section D MUST land in the SAME revise payload via `resulting_files[]` with the path spelled `../tests/heading-coverage.json`, and each `heading` must match the ratified scenario heading byte-for-byte (em dash included).
- **Architecture-not-mechanism.** The spec fixes the action-id grammar, the allowed/forbidden `move` target sets, the `clear` sentinel and its inherit-from-global semantics, and the label-only + status-only write guarantees — NOT the store internals or the exact label-string encoding. Naming the realized label forms (`merge-on-review-cap:` / `review-fix-cap:` / `acceptance-rework-cap:`, alongside the existing `admission:` / `acceptance:`) mirrors the pattern the section already uses and is intentional, not over-specification.
- **Count fidelity.** The amendment states "ten human operator action ids". The ten families are: `approve`, `accept`, `reject`, `resolve-blocked`, `set-admission`, `set-acceptance`, `set-merge-on-review-cap`, `set-review-fix-cap`, `set-acceptance-rework-cap`, `move`. The `config` family (`config` / `config-manifest` / `set-config:<key>:<value>`) is a SEPARATE category — named only in the A.2 grammar sentence for accuracy, NOT part of the human-valve count and NOT added to A.1/A.3/B.1 or a scenario. If the revise pass adds or removes any action family, the count word and all four enumerations (A.1, A.2, A.3, B.1) MUST be kept in lockstep.
- **Independent Fable review precedes ratification** (the maintainer's standing rule): the reviewer should verify that each of the four replace-targets (A.1, A.2, A.3, B.1) exists verbatim in the live files, that the enumeration count and members agree across all four plus the two new scenarios, that the `clear` semantics and the `move` allowed/forbidden sets match `_drive_policy_valves.py` (`_CAP_ACTIONS`, `_CLEAR_SENTINEL`, `_MOVE_ALLOWED`), and that the console-fan-out claim matches the cited console-spec lines.
