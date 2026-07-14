---
topic: retire-mode-flag
author: claude-opus-4-8
created_at: 2026-07-14T17:07:54Z
---

## Proposal: Retire the `--mode` run-mode flag: `loop` drains the ranked queue by default

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Retire the Dispatcher `loop` subcommand's `--mode` run-mode flag entirely, and with it the run-mode term "shadow". The flag carried THREE jobs and all three are re-homed rather than dropped: (a) ARMING is simply gone (Full autonomous mode was already retired from this spec at v034, and `contracts.md` §"Dispatcher policy settings" already forbids any per-run policy-arming argument); (b) queue-drain SCOPE is re-homed onto the surface itself — `loop` now DRAINS THE RANKED QUEUE BY DEFAULT (bounded by `--budget` and the per-repo `wip_cap`), and a new `--dry-run` flag plans that same ranked selection while dispatching nothing; (c) the fail-closed cost gate is re-keyed onto the PRESENCE of `--item` rather than onto a mode — no `--item` means an unattended queue drain with no human present, so an unobservable per-run cost is a fail-closed REFUSAL, whereas `loop --item <id>` is a human hand-picked dispatch, so the same condition is a WARNING. This preserves today's cost-gate semantics exactly. The proposal adds one new H2, `## Dispatcher loop invocation surface`, which is the first contract this spec carries for the `loop` CLI surface and for the cost gate at all; amends the one contracted argv that names `--mode shadow`; and adds three scenarios. The "shadow LEDGER" vocabulary is a DIFFERENT concept and is deliberately left VERBATIM — only the RUN MODE dies.

### Motivation

Design record (recorded maintainer intent — the tiebreaker per `contracts.md` §"Intent preservation"): repo `thewoolleyman/livespec`, `plan/autonomous-mode/handoff.md`, the "SESSION UPDATE — 2026-07-14 (cont. 14)" section, under "FOUR NEW MAINTAINER DECISIONS — locked 2026-07-14", decisions 1, 2, and 3. Decision 1 retires `--mode` entirely and kills the run-mode term "shadow" (the maintainer volunteered that they always hated it: "nonintuitive, don't know what it means"), makes `loop` drain the ranked queue by default honoring `--budget` + `wip_cap`, and adds `--dry-run`; it carries an explicit CAVEAT that `--mode` carried THREE jobs and that the flag must NOT be "just deleted". Decision 2 re-keys the fail-closed cost gate onto `--item` presence rather than a mode, and records that this CORRECTS the literal text of the option the maintainer first picked ("a real run is always fail-closed"), which would have flipped hand-picked dispatch from warn to refuse — and, since Fabro per-run cost is currently UNOBSERVABLE, would have made every dispatch refuse for anyone on the `enforce` cost posture. Decision 3 confirms the "shadow ledger" vocabulary STAYS ("a completely different use of the term. It is fine and appropriate").

Two statements ALREADY in this spec corroborate the change rather than conflict with it, which is why the retirement is a de-drifting rather than a new direction. `contracts.md` §"Grooming and slice-size calibration" (touchpoint 3, "Dispatch (unattended, exceptions only)") already says "The Dispatcher drains `ready` slices into Fabro sandboxes by dependency layer" — an unconditional drain, with no named-items precondition. And `contracts.md` §"Dispatcher policy settings" already requires that the console's factory-drain path "invokes the Dispatcher `loop` with NO per-run policy flag" and that "the Dispatcher's argument parser recognizes none, and an unrecognized argument fails the run". The spec therefore already describes a Dispatcher with no run-mode argument that drains by default; the surviving `--mode shadow` in the one contracted argv is the last spec-side residue of the retired mode, and this proposal removes it and contracts the surface positively.

### Proposed Changes

### Scope note — what this proposal does NOT touch

- **`SPECIFICATION/spec.md` and `SPECIFICATION/constraints.md` are DELIBERATELY UNCHANGED.** Neither file mentions `--mode`, a run mode, or the cost gate (verified: the string "shadow" does not occur in either file, and no statement in either is falsified by this change). `spec.md` §"Dispatcher policy settings" already states the settings model at spec altitude with no mode concept, and `constraints.md` §"Dispatcher policy settings constraints" already carries the settings' safety rails. Adding a constraints rail for the cost gate was CONSIDERED and rejected: the gate's severity is governed by an always-wired lever (below), so any rail would have to be qualified down to a restatement of the contract. This is a deliberate non-change, not an omitted sweep.
- **The "shadow LEDGER" vocabulary STAYS VERBATIM** (design record, decision 3 — "a completely different use of the term"). The revise pass MUST NOT touch `contracts.md` §"The two seams and the no-shadow-ledger rule" (the H2/H3 heading text `### The two seams and the no-shadow-ledger rule`), the phrase "work queue that shadows the ledger" in that section, or the `check-no-shadow-ledger-body-identical` gate. Only "shadow" AS A RUN MODE dies. After this change, `grep -rn "shadow" SPECIFICATION/ --exclude-dir=history` MUST return EXACTLY those two hits and nothing else.
- **`SPECIFICATION/history/**` is immutable and out of scope.**

---

#### A. `SPECIFICATION/contracts.md`

**A.1 — AMEND §"The skill surface" (the `drive` dispatch argv).** This is the ONLY place the spec contracts `--mode`.

Replace-target (exists verbatim, currently at contracts.md:226–231):

```
`drive` executes only the selected action. For a selected impl dispatch
action (`impl:<work-item-id>`, marked `factory_safe: true`) it invokes
the existing Dispatcher/Fabro loop with `--mode shadow --budget 1
--parallel 1 --item <work-item-id> --json`, then summarizes the
Dispatcher status, exit code, stdout JSON, stderr, and the selected
work-item id.
```

Replacement:

```
`drive` executes only the selected action. For a selected impl dispatch
action (`impl:<work-item-id>`, marked `factory_safe: true`) it invokes
the existing Dispatcher/Fabro loop with `--budget 1 --parallel 1 --item
<work-item-id> --json`, then summarizes the Dispatcher status, exit code,
stdout JSON, stderr, and the selected work-item id. There is no run-mode
flag: `--item` ALONE scopes the run to that one work-item, and its
presence is what marks the dispatch as human hand-picked (§"Dispatcher
loop invocation surface").
```

The rest of that paragraph (the `factory_safe` forward-reference sentence beginning "The `factory_safe` marking itself is produced by whichever surface emits the action-id") is UNCHANGED.

**A.2 — ADD a new H2 section `## Dispatcher loop invocation surface`,** inserted immediately BEFORE the existing H2 `## Dispatcher admission, WIP cap, and post-merge acceptance` (so the Dispatcher sections read in order: how the loop is invoked and what it selects → how it admits, caps, and accepts → which policy settings govern its dispositions). It MUST state:

- **CLI surface.**

  `loop --repo <path> --budget <count> [--parallel <count>] [--item <work-item-id>]... [--dry-run] [--json]`

- **This grammar is NOT exhaustive of the flags `loop` accepts.** It names the flags this contract GOVERNS — those that determine WHAT the run selects, how far it goes, and how it reports. `loop` additionally carries OPERATIONAL flags that tune HOW a dispatch executes rather than what it selects (the workflow file, the Fabro binary, the janitor ref, the journal path, the PR-merge poll bounds, close-on-merge, and the ledger pre-check). Those are IMPLEMENTATION SURFACE: this section neither enumerates nor freezes them, and their presence is NOT a spec→impl gap.

- **No run-mode flag.** The surface carries NO run-mode argument: there is no arming flag and no scope-selecting mode. The Dispatcher's dispositions are governed by the `dispatcher.*` policy settings (§"Dispatcher policy settings"), which it reads from `.livespec.jsonc` itself — never by a per-run mode argument. This is the same rule §"Dispatcher policy settings" already imposes on the console's factory-drain launcher (which "invokes the Dispatcher `loop` with NO per-run policy flag").

- **Default selection (no `--item`): drain the ranked queue.** With no `--item`, `loop` MUST select dispatch-eligible items from the ranked queue — the same single ranking authority the `next` surface advertises, so the drain order never diverges from what `next` reports (§"Work-item beads-issue mapping") — and dispatch them, subject to `--dry-run` below (which plans the identical selection but dispatches nothing). This unattended drain is the factory's steady-state path; it is what the console's factory-drain launcher invokes.

- **`--budget <count>` (REQUIRED) bounds one invocation.** The Dispatcher MUST dispatch at most `budget` items in a single `loop` run. It is a per-run ceiling on how many items the run takes on, NOT a concurrency limit.

- **`--parallel <count>` (default `1`) bounds concurrency within the invocation.** It MUST NOT raise the per-repo WIP cap: the drain stays bounded by `wip_cap` (§"Per-repo WIP cap"), which remains the authority on how many items may be `active` at once.

- **`--item <work-item-id>` (repeatable) scopes the run to hand-picked items.** One or more `--item` flags RESTRICT the selection to exactly the named work-items. `--item` NARROWS the ranked selection; it never bypasses it — a named item that is not dispatch-eligible (dependencies unclear, no resolvable assignee, no free WIP slot, or resting at `pending-approval` under an effective `admission_policy` of `manual`) MUST NOT be dispatched, exactly as if it were not named (§"Dispatcher admission, WIP cap, and post-merge acceptance"). The presence of `--item` is ALSO the contract's marker that a human hand-picked the dispatch and is present — the fail-closed cost gate below keys on it. This is the path the `drive` `impl:<work-item-id>` action invokes (§"The skill surface").

- **`--dry-run`: plan the selection, dispatch nothing.** `--dry-run` MUST compute and report exactly the selection the same invocation would dispatch — honoring `--budget`, the WIP cap, and any `--item` scoping — and MUST NOT launch a Fabro run, MUST NOT mutate the ledger, and MUST NOT write the work-item store. It is READ-ONLY with respect to the work-item store: the "what would this drain do?" surface. (Journaling the planned selection is permitted — the journal is an append-only audit record, not the work-item store.) Because a `--dry-run` invocation launches no run, it produces no per-run cost signal and therefore no cost-gate verdict (below).

**A.3 — within that new section, ADD an H3 subsection `### Fail-closed cost gate (keyed on `--item` presence)`.** (An H3, so it adds no H2 to the heading-coverage map.) It MUST state:

- **Gate coverage — which runs are gated at all.** The Dispatcher observes a per-run cost signal ONLY for a dispatched run that BOTH reached a successful terminal outcome AND carries a confirmed run record (a run id resolvable against the cost source). Two classes of run are therefore NOT gated, and this contract NAMES them rather than papering over them:
  - A run that did NOT reach a successful terminal outcome yields no cost observation and no gate verdict — even though such a run MAY have consumed spend.
  - A run whose id CANNOT be resolved against the cost source MUST be journaled as a **skipped** gate record naming the work-item and the unresolvable-run-id reason, and MUST NOT refuse. This disposition is **FAIL-OPEN** — deliberately, and it stays fail-open even under the `enforce` posture with no `--item`.

  This coverage is UNCHANGED by this proposal, and that is a deliberate scoping decision, not an oversight. The design record locks only the verdict KEYING and states that the re-keying "preserves today's semantics exactly"; it is SILENT on gate coverage, and silence is not license to widen. Ratifying a broader gate here would hand the implementer a contract that the shipped gate violates in three ways with no work-item filed against it. Widening the gate to cover failed runs or unresolvable run ids is a SEPARATE decision, and it is NOT a consequence of retiring `--mode`.
- **Verdict keying (this is the change).** For a GATED run whose cost signal is **UNOBSERVABLE** (no cost is readable for the run), the verdict is keyed on **whether the invocation named an `--item`** — the contract's proxy for whether a human is present:
  - **No `--item` — an unattended queue drain, no human present.** An unobservable cost is a **fail-closed REFUSAL**: the Dispatcher MUST stop picking rather than keep dispatching cost-blind.
  - **One or more `--item` — a hand-picked dispatch, a human present.** The same condition is a **WARNING**, never a refusal.
- **An OBSERVED cost never trips this gate.** Cost-VALUE enforcement (per-run and per-session spend ceilings) is a separate concern; this gate fires only on the unobservable condition.
- **Journaling.** Every GATED run MUST produce a gate record on the existing Dispatcher journal, carrying at minimum the work-item id, the run id, whether the cost was observable, the severity, and whether the run refused; an unresolvable run id MUST produce the skipped record above. No gated run goes unrecorded.
- **Enforcement posture (the always-wired severity lever).** Whether a keyed verdict is DERIVED and APPLIED is governed by the `LIVESPEC_COST_MODE` environment variable, whose only recognized values are `report` and `enforce`. In `report` (the **DEFAULT** — the subscription-billing posture, under which provider-side spend limits already bound spend, so a fail-closed dollar gate is the wrong model) a gate record MUST still be journaled, carrying the observability of the cost signal — but NO keyed verdict is derived and none is applied: the record's severity is `report`, and the Dispatcher MUST NOT refuse and MUST NOT apply a cost cap. In `enforce` (the opt-in posture for metered API billing) the keyed verdict above MUST be derived and the fail-closed refusal MUST be applied. An unset or unrecognized value MUST resolve to `report`. The lever is a SEVERITY switch, not a wiring carve-out — the cost signal is still observed and a gate record is still journaled regardless of its value. (This is the same always-wired-lever shape §"Closed-item-integrity check" uses for `LIVESPEC_CLOSED_ITEM_INTEGRITY`.)

*Authoring note for the revise pass, NOT ratified spec text:* the gate-coverage bullet and the enforcement-posture bullet are REQUIRED for correctness, not optional commentary. Each guards against the SAME failure: asserting a universal that the shipped gate falsifies. A blanket "the Dispatcher observes a cost signal for each run it dispatches", "no silent verdict", "an unattended drain refuses", or "the verdict is derived and journaled" would each be FALSE against the shipped gate — which gates only successful runs with a resolvable run id, skips fail-OPEN on an unresolvable id, and in the DEFAULT `report` posture derives no keyed verdict at all. The design record itself relies on the posture distinction (decision 2 reasons about what "anyone enabling `LIVESPEC_COST_MODE=enforce`" would experience). With these two bullets, the Summary's claim that the change "preserves today's cost-gate semantics exactly" is TRUE.

**A.4 — Drift sweep (contracts.md): NO other edit is required, and the following statements are CORROBORATING, not conflicting — the revise pass MUST leave them as they are.** Each was read (not merely grepped) and re-checked against the change:

1. §"Grooming and slice-size calibration", touchpoint 3 ("**Dispatch (unattended, exceptions only).** The Dispatcher drains `ready` slices into Fabro sandboxes by dependency layer, gates each on `just check` + `/livespec:doctor`, merges, and closes…") — already contracts an unconditional drain with no named-items precondition. CONSISTENT with the new default; no edit.
2. §"Dispatcher policy settings", console surface 2 ("**The factory-drain launcher argv.** The console's factory-drain path invokes the Dispatcher `loop` with NO per-run policy flag: the Dispatcher reads the `dispatcher.*` settings from `.livespec.jsonc` itself. The launcher MUST NOT pass a policy-arming argument — the Dispatcher's argument parser recognizes none, and an unrecognized argument fails the run.") — already forbids a per-run mode argument. CONSISTENT; no edit. Note the drain launcher passes no `--item`, so it is precisely the unattended, fail-closed-eligible case of the cost gate.
3. §"Dispatcher admission, WIP cap, and post-merge acceptance" opening ("Two human-delegable policy gates bracket the WIP-limited machine-driven middle of the lifecycle…") — already de-"autonomous"-ed at v034. No edit.
4. §"The skill surface" → `next` ("Cross-reference: cross-repo dispatch is the Dispatcher's concern (`dispatcher.py` `dispatch` / `loop`; see README)… the Dispatcher consumes this ranking and handles sequencing externally.") — the new default-drain selection consumes exactly that ranking. CONSISTENT; no edit.
5. `SPECIFICATION/README.md` ("An `impl:<work-item-id>` action dispatches that existing item through Dispatcher/Fabro with the default small budget") — still true (`--budget 1`), and it never mentions `--mode`. No edit.

#### B. `SPECIFICATION/scenarios.md`

APPEND three new scenarios after the current final scenario (`## Scenario 42 — list-plan-threads enumerates unarchived plan threads`). The highest existing scenario number is 42, so these take 43–45 and leave no gap. No existing scenario is amended or removed: no current scenario mentions `--mode`, a run mode, `--dry-run` on `loop`, or the cost gate.

**B.1 — ADD `## Scenario 43 — loop drains the ranked queue by default`:**

```gherkin
Feature: The dispatch loop drains the ranked queue with no mode flag
  As the Dispatcher draining ready work unattended
  I want the loop to drain the ranked queue by default
  So that an unattended drain needs no arming argument and no run mode

Scenario: An invocation with no --item drains the ranked queue within budget
  Given a ranked queue of dispatch-eligible ready items
  When the Dispatcher loop is invoked with --budget and no --item and no --dry-run
  Then it selects items from the ranked queue in the same order the next surface advertises
  And it dispatches at most --budget items in the run
  And the drain stays bounded by the per-repo wip_cap regardless of --parallel
  And no run-mode argument is passed or recognized

Scenario: --item narrows the ranked selection without bypassing admission
  Given a ranked queue of dispatch-eligible ready items
  And a work-item that is NOT dispatch-eligible because it rests at pending-approval under an effective admission_policy of manual
  When the Dispatcher loop is invoked with --item naming that ineligible work-item
  Then it is not dispatched
  And the run dispatches only named items that are themselves dispatch-eligible
```

**B.2 — ADD `## Scenario 44 — --dry-run plans the ranked queue and dispatches nothing`:**

```gherkin
Feature: The dispatch loop can plan a drain without performing it
  As an operator inspecting what the factory would do
  I want a dry run that plans the identical selection and dispatches nothing
  So that a drain can be previewed without launching a run or mutating the ledger

Scenario: A dry run reports the selection it would dispatch and launches nothing
  Given a ranked queue of dispatch-eligible ready items
  When the Dispatcher loop is invoked with --dry-run
  Then it reports exactly the selection the same invocation would dispatch, honoring --budget, the wip_cap, and any --item scoping
  And it launches no Fabro run
  And it mutates no work-item and writes no work-item store
  And it produces no per-run cost signal and therefore no cost-gate verdict
```

**B.3 — ADD `## Scenario 45 — Unobservable cost fails closed on an unattended drain and warns on a hand-picked dispatch`:**

```gherkin
Feature: The fail-closed cost gate keys on --item presence, not on a run mode
  As the Dispatcher protecting unattended spend
  I want an unobservable per-run cost to refuse only when no human is present
  So that an unattended drain never burns spend cost-blind, while a hand-picked dispatch is not blocked by a dark cost signal

Scenario: Unobservable cost on an unattended drain refuses under the enforce posture
  Given LIVESPEC_COST_MODE is enforce
  And the Dispatcher loop was invoked with no --item (an unattended queue drain)
  And a dispatched run reached a successful terminal outcome and its run id resolves against the cost source
  When that run's per-run cost signal is unobservable
  Then the gate verdict is a fail-closed refusal and the Dispatcher stops picking
  And a gate record is journaled with the work-item id, the run id, the severity, and the refusal

Scenario: Unobservable cost on a hand-picked dispatch warns rather than refusing
  Given LIVESPEC_COST_MODE is enforce
  And the Dispatcher loop was invoked with --item naming a single work-item (a human is present)
  And that run reached a successful terminal outcome and its run id resolves against the cost source
  When that run's per-run cost signal is unobservable
  Then the gate verdict is a warning and the Dispatcher does not refuse
  And a gate record is journaled

Scenario: An observed cost never trips the unobservable gate
  Given LIVESPEC_COST_MODE is enforce
  When a gated run's per-run cost signal is observable
  Then the unobservable-cost gate does not refuse, whether or not --item was passed

Scenario: An unresolvable run id is journaled as a skipped gate and is fail-open
  Given LIVESPEC_COST_MODE is enforce
  And the Dispatcher loop was invoked with no --item (an unattended queue drain)
  And a dispatched run's run id cannot be resolved against the cost source
  When the cost gate runs
  Then the run is journaled as a skipped gate record naming the work-item and the unresolvable-run-id reason
  And the Dispatcher does not refuse, because this disposition is deliberately fail-open

Scenario: A run that did not reach a successful terminal outcome is not gated
  Given LIVESPEC_COST_MODE is enforce
  And a dispatched run did not reach a successful terminal outcome
  When the cost gate runs
  Then that run yields no cost observation and no gate verdict
  And the Dispatcher does not refuse on its account

Scenario: The default report posture journals a gate record but derives no keyed verdict
  Given LIVESPEC_COST_MODE is unset, empty, or unrecognized, so it resolves to report
  And the Dispatcher loop was invoked with no --item
  When a gated run's per-run cost signal is unobservable
  Then the cost signal is still observed and a gate record is still journaled, carrying the observability of the signal
  And no keyed verdict is derived, the record's severity is report
  And the Dispatcher does not refuse and applies no cost cap
```

#### C. `tests/heading-coverage.json` (co-edit — REQUIRED, same revise payload)

The H2 set CHANGES (four H2 headings are ADDED; none is removed or renamed), so this file MUST be co-edited in the SAME revise payload so the accept is atomic. In `resulting_files[]` its path MUST be spelled **`../tests/heading-coverage.json`** — the wrapper joins `spec_target / path` and `--spec-target` is the `SPECIFICATION/` tree, so a bare `tests/heading-coverage.json` would wrongly resolve to `SPECIFICATION/tests/heading-coverage.json`.

**ADD exactly these four entries** (no REMOVE, no RENAME), each following the established `TODO`-sentinel pattern (`"spec_root": "SPECIFICATION"`, `"test": "TODO"`, plus a `reason`):

1. `"heading": "## Dispatcher loop invocation surface"`, `"spec_file": "contracts.md"`
2. `"heading": "## Scenario 43 — loop drains the ranked queue by default"`, `"spec_file": "scenarios.md"`
3. `"heading": "## Scenario 44 — --dry-run plans the ranked queue and dispatches nothing"`, `"spec_file": "scenarios.md"`
4. `"heading": "## Scenario 45 — Unobservable cost fails closed on an unattended drain and warns on a hand-picked dispatch"`, `"spec_file": "scenarios.md"`

Each entry's `heading` MUST match the ratified heading text BYTE-FOR-BYTE (including the em dash `—` in the scenario headings). If the revise pass rewords any heading text, the co-edit MUST track it.

### Notes for the revise pass

- This is ONE coherent change: the `--mode` retirement and the re-homing of its three jobs are inseparable (deleting the flag without re-homing the drain scope would leave `loop` selecting nothing, and without re-homing the cost gate would leave the gate keyed on a value that no longer exists). A single revise decision on the `retire-mode-flag` topic.
- **Do NOT "just delete the flag"** — the design record says so explicitly. All three jobs are re-homed above.
- **The word "shadow" MUST NOT appear anywhere in the new or amended text.** After the revise, `grep -rn "shadow" SPECIFICATION/ --exclude-dir=history` MUST return EXACTLY two hits, both in `contracts.md` and both the untouched no-shadow-ledger vocabulary: the `### The two seams and the no-shadow-ledger rule` heading, and the phrase "work queue that shadows the ledger".
- The new section states the surface POSITIVELY ("the surface carries no run-mode argument") rather than by comparison to the retired flag. Do NOT carry a "formerly `--mode shadow`" or "the retired mode" comparison into the ratified prose — it would leave a dangling reference to a concept the spec no longer defines.
- The exact `--dry-run` output SHAPE, the per-item label strings, and the cost-signal source are implementation mechanism (architecture-not-mechanism): the spec fixes the selection rule, the read-only guarantee, the gate's keying, the journal obligation, and the lever's severity contract — not the internals.
- Impl consequence to carry (NOT ratified spec text, recorded so it is not lost): the shipped `loop` argparse still declares `--mode {shadow,autonomous}` with a `shadow` default, and `_dispatcher_cost.cost_gate_decision` still keys on `mode == "autonomous"`. Both become spec→impl gaps the moment this is ratified, and they are already carried as separate impl work-items in this epic (the O2 leg). This proposal is spec-side ONLY.
- **Gate coverage is contracted AS-IS and is knowingly narrower than a fail-closed ideal.** The shipped gate covers only successful runs with a resolvable run id, and skips FAIL-OPEN on an unresolvable one. A.3 names both gaps in the ratified text rather than hiding them, because the design record locks only the verdict KEYING and is silent on coverage. If the maintainer wants the gate widened (to cover failed runs that burned spend, or to fail CLOSED on an unresolvable run id under an unattended drain), that is a SEPARATE decision needing its own design record and its own work-item — do NOT fold it into this accept.
- **Review history.** This proposal was adversarially reviewed by an independent Fable-model reviewer before ratification (the maintainer's standing rule). Round 1 returned TWO blockers, both fixed here: (1) the A.3 cost-gate section asserted three universals the shipped gate falsifies — that every dispatched run is observed, that no verdict is silent, and that the `report` posture still derives the keyed verdict; (2) the lever-precedent citation pointed at `constraints.md` §"Closed-item integrity" instead of the section that actually contracts the lever, `contracts.md` §"Closed-item-integrity check" — a citation that would have resolved mechanically (the heading exists in-tree) and so would have ratified silently. Round 1 explicitly CLEARED the enforcement-posture lever paragraph as faithful to both the shipped resolver and the design record's own reasoning, and verified replacement-target fidelity, the drift sweep, and the criterion-2 grep as clean.
