---
topic: dispatcher-policy-settings
author: claude-opus-4-8
created_at: 2026-07-14T02:24:25Z
---

## Proposal: Independent dispatcher policy settings replace Full autonomous mode

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/constraints.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json (co-edit; spelled `../tests/heading-coverage.json` in
  `resulting_files[]` at revise time, since the wrapper joins `spec_target / path`)

### Summary

Retire the monolithic **Full autonomous mode** override (the
`dispatcher.autonomous_mode` config key, the `--mode autonomous` two-factor
dangerous arming, and Scenarios 33–37) and replace it with **independent,
orthogonal `dispatcher.*` policy settings**, each a **global default** settable via
the **orchestrator API and the console**, and each — with the single structural
exception of `wip_cap` — **overridable per work-item by a ledger label**. (`wip_cap`
is a per-repo concurrency ceiling, so a per-item value is meaningless.) The three
policy settings are `auto_approve_ready` (admission),
`merge_on_review_cap` (the in-factory review gate), and `acceptance_mode`
(post-merge acceptance); two configurable caps bound the two rework loops
(`review_fix_cap` inner / pre-merge, `acceptance_rework_cap` outer / post-merge);
the existing `wip_cap` becomes API-settable. This proposal also makes the
post-merge **AI acceptance pass real** (a read-and-judge-plus-telemetry pass/fail,
replacing today's hardcoded confirm) with an **AI-fail → auto-rework** route back
into the factory **in the AI-dispositive modes** (`ai-only` / `ai-then-human`; under
`human-only` the pass is ADVISORY — it informs, it never decides, and a failing pass
leaves the item parked for the human), makes the **in-factory review gate blocking**
(escalate-on-cap
unless `merge_on_review_cap`), and codifies a general **"anything configurable via
the orchestrator API must appear in console Settings, the inline/context help, and
the settings doc"** completeness principle with a mechanical check.

### Motivation

**Design record (recorded maintainer intent — the tiebreaker per `contracts.md`
§"Intent preservation"):** `thewoolleyman/livespec`
`plan/autonomous-mode/handoff.md` §"SESSION UPDATE — 2026-07-14 (cont. 12)" — THE
RE-LOCKED DESIGN, maintainer-declared 2026-07-14 (it explicitly supersedes the
older cont. 11 section in the same file). That session replaced cont.11's single
"autonomous master switch" with this orthogonal model after the first real armed
TUI dispatch exposed that the shipped acceptance "AI pass" is a hardcoded
`{"confirmed": true}` stub (`_dispatcher_completion.py`) — a spec↔code drift,
since the spec already describes a real read-and-judge pass.

The maintainer's verbatim rationale for a NON-automated review gate already lives
in `contracts.md` §"Work-item state semantics": *"If we don't respect the groomed
attribute and add autonomous execution, then the factory can just go wild and go
completely off track and never stop, Piling up a bunch of incorrect work that
should have never been performed at the review gates, or even worse if the review
gate is automated, pushing it all to production."* That is the cited design record
for making the review gate blocking-by-default.

The three-independent-settings model gives the operator granular, orthogonal
control (e.g. auto-approve routine work yet keep human acceptance) instead of one
dangerous all-or-nothing mode, drops the mode's riskiest behavior (the LLM guessing
human decisions on `needs-human` blocks), and preserves every safety floor
(spec-change-tier items never auto-approved; no release with zero verification;
every truly-unresolvable decision still escalates to a human).

### Proposed Changes

#### A. `SPECIFICATION/contracts.md`

1. **RETIRE the entire H2 section `## Full autonomous mode`** (the heading and
   everything through the end of its `### Autonomous-mode gap-detectable clauses`
   subsection — the section opening "Full autonomous mode is a global, dangerous,
   default-off override that collapses the two human-delegable gates…"). Its
   surviving substance is re-expressed by the new settings section (A.2) and the
   amended acceptance section (A.3): admission auto-approval → the
   `auto_approve_ready` setting; acceptance auto-confirm → the `acceptance_mode`
   setting; the auto-resolution journal → the per-setting audit in A.2; the
   spec-change-tier / `human-only` / truly-unresolvable escalation floor → the
   "always escalate needs-human" rule in A.2 and the amended Terminology (B.6).

2. **ADD a new H2 section `## Dispatcher policy settings`** (in the slot
   `## Full autonomous mode` vacated, between `## Dispatcher admission, WIP cap,
   and post-merge acceptance` and `## Dispatch-brief lessons injection`). It MUST
   state:

   - The Dispatcher's routine dispositions are governed by **orchestrator-wide
     `dispatcher.*` policy settings** in the consumer project's `.livespec.jsonc`
     (siblings of the existing `dispatcher.wip_cap` / `dispatcher.fabro_bin`). Each
     setting is a **global default**; a **per-item ledger label overrides the global
     default for that one work-item** — the per-item label WINS over the global, and
     an item with no label inherits the global. The settings are independent — no
     setting implies another; there is no master switch.
     **Cited design record (REQUIRED by §"Intent preservation" — every load-bearing
     semantic definition MUST carry its rationale AND cite its design record):** repo
     `thewoolleyman/livespec`, `plan/autonomous-mode/handoff.md` §"SESSION UPDATE —
     2026-07-14 (cont. 12)" (THE RE-LOCKED DESIGN) together with its
     §"CORRECTION / ADDENDUM … `wip_cap` is NOT per-item overridable", which records
     the maintainer's ruling that every setting is per-item overridable EXCEPT
     `wip_cap`. The ratified prose MUST carry this citation on the global-default +
     per-item-override scheme AND on the `wip_cap` exclusion; without it, both are
     uncited load-bearing definitions and doctor/critique will (correctly) flag them.
     *(Revise-note, NOT ratified spec text: this precedence is the INVERSE of the
     retired mode's, which overrode stored per-item labels. Do not carry a "retired
     mode" comparison into the ratified prose — it would leave an uncited dangling
     reference. State the precedence positively, as above.)*
   - The **three policy settings** (global default + per-item override), all
     defaulting to their SAFE value:
     - `dispatcher.auto_approve_ready` (boolean, default **`false`**) — the global
       default for an item's effective `admission_policy` when the item carries no
       explicit label: `true` ⇒ `auto` (auto-approve `pending-approval → ready`
       without a human), `false` ⇒ `manual` (rest at `pending-approval` for the
       human's explicit `approve`). Per-item override: the existing
       `admission_policy` label (a stored `manual` label holds the item even when
       the global is `true`). It MUST NOT auto-approve a **design-human-gated
       (spec-change-tier) item** regardless of this setting or any label (see
       §"Grooming and slice-size calibration" / `spec.md` §"Terminology"); that item
       stays escalated.
     - `dispatcher.acceptance_mode` (enum `ai-only` | `ai-then-human` |
       `human-only`, default **`ai-then-human`**) — the global default for an item's
       effective `acceptance_policy` (§"Post-merge acceptance"). Per-item override:
       the existing `acceptance_policy` label.
     - `dispatcher.merge_on_review_cap` (boolean, default **`false`**) — the global
       default for the in-factory review gate's past-cap behavior: `true` ⇒ ship the
       PR anyway (the escape hatch for a misbehaving reviewer); `false` ⇒
       **escalate the item to `blocked` / `blocked_reason: needs-human`** — a
       terminal state that is NOT eligible for auto-approve, so it cannot loop.
       Per-item override: a per-item merge-on-review-cap label. Cited design record
       for the blocking default: the maintainer quote in §"Work-item state
       semantics".
   - The **two configurable caps** (global default + per-item override), bounding
     the two INDEPENDENT rework loops:
     - `dispatcher.review_fix_cap` (integer, default **`3`**) — the INNER,
       pre-merge review fix-round budget (raised from the prior hardcoded 2). At the
       cap, a still-blocking review is disposed by `merge_on_review_cap`.
     - `dispatcher.acceptance_rework_cap` (integer, default **`2`**) — the OUTER,
       post-merge budget for how many times a single item's FAILED AI acceptance may
       route back to rework before the item **escalates to `blocked` /
       `needs-human`** instead of reworking again. This is the bound that prevents an
       infinite post-merge rework loop.
   - `dispatcher.wip_cap` (existing, default `5`, §"Per-repo WIP cap") is likewise an
     API-settable setting surfaced under Settings. It is the ONE setting with **no
     per-item override**: it is a per-repo concurrency ceiling, so a per-item value
     is structurally meaningless. Its value semantics are unchanged.
   - **Control surface + audit.** Every setting MUST be settable via the
     orchestrator API and, through it, the Control-Plane console; the orchestrator
     OWNS the setting state (the `.livespec.jsonc` keys and the per-item labels) —
     the console only commands and observes, holding no setting state of its own.
     Every auto-disposition a setting enables (an auto-approve, an AI auto-accept, an
     AI-fail auto-rework, a ship-on-cap, a cap-exceeded escalation) MUST be journaled
     on the existing Dispatcher journal (→ Honeycomb), carrying the work-item id,
     which setting governed it, and the disposition — no silent auto-disposition. The
     Dispatcher MUST NOT create net-new work-items when applying a setting.
   - **General completeness principle (normative):** anything configurable via the
     orchestrator API MUST appear, in lockstep, in THREE places: (1) a row under the
     console **Settings** surface, (2) the TUI **inline/context help**, and (3) the
     **settings doc** (Markdown in the app's repo docs). A **mechanical completeness
     check** MUST fail if an API-configurable key is missing from Settings or from
     the settings doc. Per the No-Circular-Dependency Directive the check lives on
     the CONSUMER side (the console), reading the orchestrator's declared
     API-configurable-key surface; the orchestrator MUST NOT read into the console.

3. **AMEND `## Dispatcher admission, WIP cap, and post-merge acceptance`:**
   - In `### Admission valve (`ready → active`)`, rewrite the **Permission** bullet.
     Three phrases in it become wrong or under-inclusive once the global default
     exists, and ALL THREE must change together:
     a. "with `None` inheriting the safe default `manual`" → "with `None` inheriting
        the global `dispatcher.auto_approve_ready` default (§\"Dispatcher policy
        settings\")".
     b. "`auto` auto-approves once into `ready` at capture/groom time" is now
        UNDER-INCLUSIVE — with a global default, the Dispatcher may also auto-approve
        an item already RESTING at `pending-approval` on a later pass (e.g. after the
        operator flips `auto_approve_ready` on; see D.11's first scenario). Generalize
        to: `auto` auto-approves into `ready` — at capture/groom time, or on a
        subsequent Dispatcher pass for an item resting at `pending-approval`.
     c. The FULL target phrase (quote it in full so a literal string-replace does not
        duplicate the trailing clause) is: "`manual` (the default, via inherit) rests
        at `pending-approval` until a human's explicit `approve`". It is now WRONG —
        `manual` is no longer "the default via inherit"; the global
        `auto_approve_ready` setting determines what an UNLABELED item inherits (and
        it merely DEFAULTS to the `manual`-equivalent `false`). Replace the whole
        phrase with: "`manual` (whether stored on the item or inherited from a `false`
        global `auto_approve_ready`) rests at `pending-approval` until a human's
        explicit `approve`".
     The spec-change-tier never-auto-approve rule is unchanged.
   - In `### Post-merge acceptance (`acceptance → done`)`, make the AI acceptance
     pass **real and pass/fail**, and add the AI-fail route:
     - Amend the `ai-only` and `ai-then-human` bullets so the AI pass is explicitly
       a **read-and-judge of the merged diff against the item's acceptance criteria
       plus a telemetry watch, yielding a PASS or FAIL verdict** — not a rubber
       stamp. Keep: `ai-only` PASS ⇒ `done`; `ai-then-human` PASS ⇒ park for the
       human `accept:<id>` valve; `human-only` ⇒ park for the human, AI pass
       advisory. Keep the "no release with zero verification — every acceptance
       carries at least one AI pass" floor.
     - Add, **SCOPED to the two AI-dispositive modes**: for an item whose effective
       `acceptance_policy` is `ai-only` or `ai-then-human`, **an AI acceptance pass
       FAIL routes the item back to `active` for fix-forward rework automatically (no
       human for a fail)** — mirroring `reject (rework)` but AI-initiated. Repeated
       failure is bounded by `dispatcher.acceptance_rework_cap` (§"Dispatcher policy
       settings"); an item that exceeds the cap **escalates to `blocked` /
       `needs-human`** rather than reworking again. The human `reject` valve is
       retained for human-judgment rejects.
     - Add, **the `human-only` carve-out (maintainer-declared 2026-07-14 — chose
       "stay parked; advisory only")**: under `human-only` the AI acceptance pass is
       **ADVISORY — it INFORMS, it never DECIDES.** On a FAIL it MUST NOT auto-rework
       and MUST NOT dispose of the item in any way; the failure is surfaced as an
       advisory **finding** and the item **stays PARKED in `acceptance`** for the
       human, who accepts or uses the existing `reject (rework)` / `reject (re-groom)`
       valve if they concur. An auto-rework IS the AI deciding, which is precisely
       what `human-only` reserves to the human; auto-reworking here would let the
       machine repeatedly bounce an item the human explicitly claimed, stripping their
       accept-vs-reject call. The pass still RUNS (it is what satisfies the "no release
       with zero verification" floor for this mode) — `human-only` means "no AI
       DECIDES this", NOT "no AI reads this".
     - Change the effective `acceptance_policy` default to inherit the global
       `dispatcher.acceptance_mode` setting (per-item label overrides).

4. **Drift sweep (contracts.md) — update every surviving reference to the retired
   mode:**
   - §"The skill surface" (~line 160), "governs the Dispatcher's autonomous path only
     (§\"Dispatcher admission, WIP cap, and post-merge acceptance\")" — reword to
     drop "autonomous path"; it names the Dispatcher's machine-driven dispositions,
     now governed by §"Dispatcher policy settings".
   - §"Store-write consent discipline" (~line 662), replace "and — ONLY under full
     autonomous mode's collapsed `approve` gate — the auto-`approve`
     (`pending-approval → ready`) disposition" with "and — when the effective
     `admission_policy` is `auto` (via `dispatcher.auto_approve_ready` or a per-item
     label) — the auto-`approve` (`pending-approval → ready`) disposition".
   - §"Dispatcher admission, WIP cap, and post-merge acceptance" (~line 1226),
     "Two human-delegable policy gates bracket the WIP-limited autonomous middle of
     the lifecycle" — reword "autonomous middle" to "machine-driven middle" (the word
     named the retired mode's framing).
   - **Cross-repo consequence to record (THREE console legs — all obsoleted by
     this retirement).** The retired §"Full autonomous mode" specified three
     Control-Plane console surfaces; ALL must retire in lockstep, or the console
     breaks against the new Dispatcher. Record all three in the new §"Dispatcher
     policy settings" control-surface paragraph so the cross-repo obligation is not
     lost, and carry them as `livespec-console-beads-fabro` work-items in the same
     epic:
     1. **The arming commands.** `factory.autonomous_mode_enable_requested` /
        `factory.autonomous_mode_disable_requested` (which mapped to writing the
        retired `dispatcher.autonomous_mode` key) are obsoleted by the Settings
        surface; the console MUST replace them with per-setting write commands.
     2. **The factory-drain launcher argv (BREAKING).** The retired §"Arming full
        autonomous mode" → "Loop launcher" bullet has the console's factory-drain
        path "read[] the persistent permission and, while it is enabled, pass[]
        `--mode autonomous` to the Dispatcher `loop` per run". Once the Dispatcher
        drops `--mode autonomous`, a console that still passes it sends an
        unrecognized argument and argparse REJECTS the run — every armed drain would
        land `failed`. The console's drain launcher MUST stop passing `--mode
        autonomous`; there is no per-run arming flag any more, because the
        Dispatcher now reads the `dispatcher.*` settings from `.livespec.jsonc`.
     3. **The TUI dangerous-arming confirm flow.** The type-the-repo-name
        acknowledgement that gated arming retires with the mode; enabling an
        individual dangerous setting is now an ordinary (recorded) Settings write.

#### B. `SPECIFICATION/spec.md`

5. **RETIRE / REPLACE the H2 section `## Full autonomous mode`** (from "Full
   autonomous mode is a global, DANGEROUS, DEFAULT-OFF override…" through the "wire
   surface" paragraph ending "…`constraints.md` §\"Full autonomous mode
   constraints\"."). Replace with a short H2 `## Dispatcher policy settings` at spec
   altitude: the Dispatcher's routine dispositions are governed by independent
   `dispatcher.*` settings (global default + per-item override), settable via the
   orchestrator API and the console; the wire surface, the caps, the AI acceptance
   pass, and the completeness principle are specified in `contracts.md`
   §"Dispatcher policy settings", the safety rails in `constraints.md` §"Dispatcher
   policy settings constraints"; every truly-unresolvable decision still escalates to
   a human and the "no release with zero verification" floor holds.

6. **AMEND `## Terminology`, the "Truly-unresolvable decision" entry.** The concept
   SURVIVES (it is now the residual class no policy setting may auto-dispose). Three
   edits inside the entry:
   - The opening "**Truly-unresolvable decision** — Under §\"Full autonomous mode\",
     a human-delegable decision the autonomous engine MUST NOT auto-resolve" →
     re-anchor to §"Dispatcher policy settings" and drop "the autonomous engine"
     (→ "a human-delegable decision the Dispatcher MUST NOT auto-dispose under any
     policy setting").
   - The clause "Truly-unresolvable decisions are the residual escalation class that
     even full autonomous mode still surfaces to a human — the sole exception to the
     mode's otherwise-total collapse of the human-delegable gates." → reword to drop
     "full autonomous mode" and "the mode's otherwise-total collapse" (→ the residual
     escalation class the Dispatcher always surfaces to a human, regardless of policy
     settings).
   - The closing sentence "…not by low confidence: full autonomous mode MUST leave
     them escalated as needs-attention…" → reword to "…no dispatcher policy setting
     may auto-dispose them; they MUST stay escalated as needs-attention…".
   - **Sweep the "the engine" residuals in the same entry.** Once the opening actor
     becomes "the Dispatcher", three surviving "the engine" references inside this
     entry dangle (they named the retired autonomous engine): "it requires
     information the engine cannot obtain" (~line 115); "stay human even when the
     engine is fully confident, because a human, not the engine, owns them" (~line
     124); "the engine MAY file impl→spec drift (the machine path), but only a human
     accepts it" (~line 127). Reword each to "the Dispatcher" so the entry has ONE
     consistent actor.
   - The three design-human-gated sources (drift acceptance, spec-change slices,
     regroom / backlog bounce) are otherwise unchanged, including the core "fully
     autonomous orchestrator" quote (that quote cites livespec-core and stays
     verbatim).

#### C. `SPECIFICATION/constraints.md`

7. **RETIRE / REPLACE the H2 section `## Full autonomous mode constraints`** with
   `## Dispatcher policy settings constraints`, keeping the surviving,
   mechanically-checkable rails re-expressed for the new model:
   - **Safe defaults.** `dispatcher.auto_approve_ready` and
     `dispatcher.merge_on_review_cap` MUST default to `false`;
     `dispatcher.acceptance_mode` MUST default to `ai-then-human`;
     `dispatcher.review_fix_cap` to `3` and `dispatcher.acceptance_rework_cap` to
     `2`. A dangerous non-default MUST be an explicit, recorded operator action —
     never inferred from context. (Replaces the old "Default-off, explicit,
     invocation-scoped" + "Explicit dangerous-mode confirmation" rails, now that
     there is no monolithic mode to arm.)
   - **Audit every auto-disposition.** Every auto-approve / AI auto-accept /
     AI-fail auto-rework / ship-on-cap / cap-exceeded escalation MUST be journaled
     and attributable (which setting, which item, the disposition) — extending the
     §"Forbidden patterns" no-silent-close rule to every setting-driven disposition.
   - **Still escalate the unresolvable.** No policy setting MAY auto-dispose a
     truly-unresolvable decision (confidence-bounded, or human-gated by design —
     drift acceptance, a spec-change slice, a regroom / backlog bounce, or a
     `human-only` acceptance); every such decision MUST block and surface to a human.
     The "no release with zero verification" floor MUST hold — every acceptance
     carries at least one AI pass.
   - **Completeness.** The console Settings surface, the inline/context help, and the
     settings doc MUST stay in lockstep with the API-configurable key set, enforced by
     the mechanical completeness check (`contracts.md` §"Dispatcher policy settings").

8. **Drift sweep (constraints.md):**
   - In `## Skill orchestration constraints` (~lines 137–138), the machine-path
     exemption bullet reads "…the `backlog` bounce, and — only under full autonomous
     mode's collapsed `approve` gate — the auto-approve disposition…". Replace the
     em-dashed clause with "— when the effective `admission_policy` is `auto` (via
     `dispatcher.auto_approve_ready` or a per-item label) —".
   - In `## Forbidden patterns` (~lines 202–205), the bullet "No silent or unbounded
     autonomous mode. Full autonomous mode (`contracts.md` §\"Full autonomous
     mode\") MUST NOT be enabled by default, MUST NOT auto-resolve a
     truly-unresolvable decision, and MUST NOT create net-new work-items; every
     auto-resolution MUST be journaled." references the RETIRED mode AND
     cross-references the DELETED heading. Re-express it for the new model: "No
     silent or unbounded auto-disposition. A dispatcher policy setting
     (`contracts.md` §\"Dispatcher policy settings\") MUST NOT default to its
     dangerous value, MUST NOT auto-dispose a truly-unresolvable decision, MUST NOT
     create net-new work-items, and MUST bound every rework loop by its configured
     cap; every auto-disposition MUST be journaled."

#### D. `SPECIFICATION/scenarios.md`

9. **AMEND Scenario 20 — including its H2 HEADING.**
   - **Rename the heading** `## Scenario 20 — Review gate routes a green build
     through advisory code review before PR` → drop "advisory" (the gate is now
     blocking by default), e.g. `## Scenario 20 — Review gate routes a green build
     through code review before PR`. Reword the Feature intent line "without ever
     blocking a mechanically-valid change" accordingly — the gate now blocks by
     default and ships-on-cap only when `merge_on_review_cap` is set.
   - Replace the third sub-scenario "A capped-out review ships rather than starving
     a valid change" (which Then's "the run ships to the PR stage anyway") with TWO
     sub-scenarios keyed on the effective `merge_on_review_cap`:
     - cap (`dispatcher.review_fix_cap`) reached, blocking finding remains, and
       `merge_on_review_cap` is TRUE ⇒ the run ships to the PR stage anyway (escape
       hatch).
     - cap reached, blocking finding remains, and `merge_on_review_cap` is FALSE
       (the default) ⇒ the change does NOT ship; the item transitions to `blocked` /
       `blocked_reason: needs-human` and is surfaced to a human.

10. **AMEND Scenario 25 — accept confirms post-ship per acceptance_policy.** Keep the
    existing `ai-then-human` park and `reject`-routing sub-scenarios; make the AI pass
    explicitly pass/fail and ADD **TWO** sub-scenarios (the FAIL route is MODE-SCOPED):
    - "The AI acceptance pass fails and routes the item back to rework" — Given an item
      in `acceptance` **whose effective `acceptance_policy` is `ai-only` or
      `ai-then-human`**, When the AI acceptance pass judges the merged artifact against
      its acceptance criteria and FAILS, Then the item transitions to `active` for
      fix-forward rework without a human, And repeated failure beyond
      `dispatcher.acceptance_rework_cap` escalates the item to `blocked` /
      `needs-human`.
    - "A human-only item's failing AI pass advises but never disposes" — Given an item
      in `acceptance` whose effective `acceptance_policy` is `human-only`, When the AI
      acceptance pass FAILS, Then the item **stays parked in `acceptance`** and the
      failure is surfaced to the human as an advisory finding, And the item is NOT
      auto-reworked, And the human retains the accept / `reject` decision.

11. **REMOVE Scenarios 33–37** (`## Scenario 33 — Full autonomous mode auto-approves
    a manual item` through `## Scenario 37 — Full autonomous mode is default-off and
    explicitly armed`) and **ADD replacement scenarios** in their place (reusing the
    33+ numbering so no gap is left):
    - **Auto-approve-ready: global default, per-item override, spec-change-tier
      exception.** Given `dispatcher.auto_approve_ready` is `true`, When the
      Dispatcher reaches a routine `pending-approval` item that carries NO explicit
      `admission_policy` label (it inherits the global), Then it is auto-approved into
      `ready` without a human; And an item carrying an explicit per-item
      `admission_policy: manual` label STILL rests at `pending-approval` (the per-item
      label beats the global); And a spec-change-tier (design-human-gated) item is
      NEVER auto-approved regardless of the setting or any label. (Replaces Scenario
      33. NOTE the deliberate semantic change from retired Scenario 33, which
      auto-approved items whose STORED policy was `manual` — the new model inverts
      that precedence: per-item wins.)
    - **Acceptance mode governs the acceptance leg.** With
      `dispatcher.acceptance_mode` = `ai-only`, a PASSING AI acceptance pass takes the
      item to `done`; = `ai-then-human` (default) it parks for the human `accept`
      valve; = `human-only` it parks for the human with the AI pass advisory; a
      per-item `acceptance_policy` label overrides the global; every path carries at
      least one AI pass. (Replaces Scenario 34, reframed from a "collapse" to a real
      AI-gated `ai-only`.)
    - **AI acceptance fail auto-reworks, bounded — but ONLY in the AI-dispositive
      modes.** For an item whose effective `acceptance_policy` is `ai-only` or
      `ai-then-human`, a FAILING AI acceptance pass routes the item to `active` rework
      with no human; exceeding `dispatcher.acceptance_rework_cap` escalates it to
      `blocked` / `needs-human`. For a `human-only` item the failing pass is ADVISORY:
      the item stays PARKED and the finding is surfaced to the human, who keeps the
      accept / `reject` decision. (New. MAY be folded into the Scenario 25 additions
      (D.10) instead of standing alone — the revise pass picks one home and does not
      duplicate it.)
    - **Every needs-human block always escalates.** The Dispatcher NEVER
      auto-resolves a `blocked_reason: needs-human` item; it always surfaces it to a
      human (this drops the retired mode's LLM-resolve behavior). A design-human-gated
      decision (drift acceptance, spec-change slice, regroom / backlog bounce,
      `human-only` acceptance) escalates by design even at high confidence. (Replaces
      Scenarios 35 + 36.)
    - **Safe defaults hold when nothing is configured (the new Scenario 37).** The
      old Scenario 37 (default-off / explicitly-armed) is dropped WITH the mode, but
      its INTENT — a dangerous behavior is never on by accident — survives and gets a
      scenario so it keeps a bound test. The scenario asserts what it actually means:
      **the DEFAULTS ALONE never arm anything.** It MUST therefore scope its Thens to
      UNLABELED items, because a per-item label legitimately BEATS a safe global (A.2's
      ratified precedence) — a per-item `admission_policy: auto` label auto-approves
      even under an all-default config, which is SURVIVING, unretired contract text
      (`contracts.md` §"Grooming and slice-size calibration" / the intake routing
      "approved on into `ready` when its effective `admission_policy` is `auto`") and
      MUST NOT be contradicted:
      > Given a `.livespec.jsonc` that sets no `dispatcher.*` policy settings
      > And no work-item carries a per-item policy label (`admission_policy`,
      >   `acceptance_policy`, or the merge-on-review-cap label)
      > When the Dispatcher runs
      > Then `auto_approve_ready` and `merge_on_review_cap` are `false`,
      >   `acceptance_mode` is `ai-then-human`, `review_fix_cap` is `3`, and
      >   `acceptance_rework_cap` is `2`
      > And no such unlabeled item is auto-approved, no past-cap review ships, and no
      >   acceptance reaches `done` without a human

      This asserts the `constraints.md` §"Dispatcher policy settings constraints"
      safe-defaults rail WITHOUT contradicting the per-item-override precedence.
      **Do NOT ratify a blanket "no item is auto-approved" Then** — it would be false
      in the presence of a per-item `auto` label and would contradict A.2, the
      Scenario-33 replacement, and the surviving intake/groom contract passages.
    - **Count check:** 5 scenarios are REMOVED (33–37) and 5 are ADDED, so the 33–37
      numbering is fully reused and NO gap is left. (The AI-acceptance-fail scenario
      is one of the five; if the revise pass instead folds it into Scenario 25 per
      D.10, it MUST renumber so no gap remains.)

#### E. `tests/heading-coverage.json` (co-edit — REQUIRED for every H2 change above)

12. Update the heading-coverage map in lockstep with the H2 set. In the revise
    payload this file's `resulting_files[]` path MUST be spelled
    **`../tests/heading-coverage.json`** (the wrapper joins `spec_target / path`, and
    `--spec-target` is the `SPECIFICATION/` tree; a bare `tests/heading-coverage.json`
    would wrongly resolve to `SPECIFICATION/tests/heading-coverage.json`).
    - **REMOVE** exactly these 8 entries (each entry is keyed by the
      `heading` + `spec_file` pair; all 8 currently carry the `TODO` test sentinel):
      the five `## Scenario 33 — …` through `## Scenario 37 — …` entries
      (`spec_file: scenarios.md`); ONE `## Full autonomous mode` entry with
      `spec_file: spec.md`; ONE `## Full autonomous mode` entry with `spec_file:
      contracts.md` (there is exactly ONE per file — two entries share that heading
      TEXT but differ by `spec_file`); and `## Full autonomous mode constraints`
      (`spec_file: constraints.md`).
    - **ADD** `TODO`-sentinel entries (the v064 pattern: `TODO` node id + a `reason`)
      for the new headings: `## Dispatcher policy settings` (contracts.md),
      `## Dispatcher policy settings` (spec.md), `## Dispatcher policy settings
      constraints` (constraints.md), and each new Scenario 33+ heading added in D.11.
    - **RENAME** the `heading` field of the Scenario 20 entry to match its new
      (de-"advisory"-ed) heading text from D.9 — a rename, not an add/remove.
    - **UPDATE** the `reason` text (not the node binding) for the amended headings
      whose behavior changed: `## Scenario 20 — …` (its existing reason explicitly
      describes "ship-on-cap edge behavior" and must be re-worded to the blocking
      gate), `## Scenario 25 — …`, and `## Dispatcher admission, WIP cap, and
      post-merge acceptance`.

### Notes for the revise pass

- Config-key names (`auto_approve_ready`, `merge_on_review_cap`, `acceptance_mode`,
  `review_fix_cap`, `acceptance_rework_cap`) are the maintainer-provisional
  "meaningful names" from the design record; keep them unless the maintainer renames
  at accept time.
- **Per-item override scope (maintainer-confirmed 2026-07-14):** ALL settings are
  per-item overridable EXCEPT `wip_cap`, which is a per-repo concurrency ceiling and
  structurally cannot be per-item. So the three policy settings AND both numeric caps
  each carry a per-item override label.
- The exact per-item label strings and the AI-acceptance-pass realization are
  implementation mechanism (architecture-not-mechanism): the spec fixes the pass/fail
  contract, the fail→rework route, the bound, and the escalation target — not the
  label strings or the judge's internals.
- This is ONE coherent change (the retirement and the replacement are inseparable):
  a single revise decision on the `dispatcher-policy-settings` topic.
- This proposal was adversarially reviewed by an independent Fable-model reviewer
  before ratification (the maintainer's standing rule), across multiple rounds. Every
  blocker it raised is fixed here. Its most consequential catches: a misattributed
  design-record cross-reference (which this proposal would have RATIFIED into the
  spec); a dangling reference to the deleted heading that the author's own drift sweep
  had missed; the console factory-drain launcher's `--mode autonomous` argv, which
  this retirement would otherwise BREAK; and an over-broad safe-defaults scenario that
  would have contradicted the very per-item-override precedence this proposal
  ratifies.
