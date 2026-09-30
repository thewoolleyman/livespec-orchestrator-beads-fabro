---
topic: definition-and-proof-of-done
author: claude-fable-5.1 (definition-and-proof-of-done)
created_at: 2026-09-30T07:37:16Z
---

## Proposal: The Definition of Done is the required first heading and the canonical criteria source

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md

### Summary

Every work item dispatched on an implement-kind workflow MUST carry, as the first heading of its description, a `Definition of Done` section, and that section becomes the first resolution step of the one effective-criteria primitive, ahead of the native `acceptance_criteria` field and the legacy `Exit criteria` heading, which remain as fallbacks for already-filed items. The section carries one assertion per `- ` bullet and exactly one structured spec-reference line naming an existing H2 of the governed spec tree, validated against the spec files themselves. The reference line is never a gradeable assertion. A run that finds the Definition of Done wrong ends through the structured needs-human ending with the proposed amendment, so the section stays current by ledger edit and never by silent drift; groom-kind variants are exempt because they produce Definitions of Done rather than consume them.

### Motivation

Maintainer intent (2026-09-30, plan definition-and-proof-of-done, epic bd-ib-7sjdzv): plans are not done the way the maintainer intends, or are done incompletely, and require unnecessary oversight, which is contrary to the livespec goal that intent is reliably transformed into implementation. Today a factory run's 'done' is janitor green, reviewer approve, PR merged, and a post-merge acceptance pass that is a keyword matcher over the merged diff; nothing in the loop ever exercises the delivered behaviour. The maintainer requires a first-class Definition of Done and a visible, reproducible Proof of Done before any work item is declared done, handed to a human for approval, or leaves the factory. Research: plan/definition-and-proof-of-done/research/001-brainstorm-and-design-2026-09-30.md. The doctor post-step review of the first draft (33 findings, 2026-09-30) is applied in this text; the five design decisions it forced are recorded in the plan epic's scope comment. Points 1, 2 and 8 of the proposal. The single-primitive rule in §"Effective acceptance criteria" means the heading must BE the criteria source, not a second parser; the AGENTS.md rule that a criterion naming a scenario cannot pass the matcher is resolved by making the reference a structured line the segmenter excludes rather than an assertion.

### Proposed Changes

**Vocabulary used by every proposal in this file.** The *rendered goal* is the per-item brief the Dispatcher renders into the run goal (the same artifact §"Dispatch-brief lessons injection" calls the goal brief); the *dispatch-time snapshot* is the item record as read when that goal was rendered, which the acceptance pass grades against today. A *structured needs-human ending* is the existing failed outcome of an ACP node that the reserved workflow routes to its `needs_human` terminal (§"A factory run never awaits a human"), carrying a failure reason the Dispatcher records as the needs-human question. A *Definition-of-Done finding* is one line naming the item, the offending element of its Definition of Done section, and the remedy; it is surfaced on whichever of three surfaces first detects it — the host-side wall's refusal text, the `dod_gate` node's needs-human question, or the capture and groom displays — and is never a doctor finding. The *host-side wall* is the existing pre-dispatch and approve refusal machinery of §"Effective acceptance criteria"; the *gate* is the `dod_gate` node. The sandbox has no ledger write path — no store binary, no store credential, no route to the store — and this file ratifies that as a constraint rather than relying on it as an accident of the image; every ledger write the proposals describe is performed by the Dispatcher on the host from what the run emits.

Amend `contracts.md` §"Effective acceptance criteria" as follows.

**The Definition of Done section.** A work item's `description` MUST carry, as its FIRST heading, one whose title case-insensitively equals `Definition of Done` (any heading level; the reserved form is `## Definition of Done`); prose MAY precede the heading. Its body MUST consist of (a) one or more `- ` bullets, each carrying exactly one gradeable assertion ending in a period, optionally grouped under the `### Human-attested` sub-heading defined in Proposal 2; and (b) exactly one spec-reference line of the form `References: <heading>[, <heading>...]`, where each `<heading>` is the verbatim text of an existing H2 heading of a file in the governed spec tree — a `## Scenario NN — <title>` heading of `scenarios.md`, or an H2 of `spec.md`, `contracts.md`, `constraints.md`, or `non-functional-requirements.md` where the tree carries one. The reference line MUST be validated against the H2 set read from the spec tree's own files, never against a test fixture, so an adopter inherits no livespec-family artifact; in this repository `tests/heading-coverage.json` enumerates the same set and its check MAY cross-check the two. The reference line MUST NOT be counted as a gradeable assertion by any parse. A reference to a heading that does not exist MUST be reported as a Definition-of-Done finding naming the unresolved heading text.

**Resolution order.** The resolution order of the effective-criteria primitive becomes: (1) the item description's Definition of Done section when it yields gradeable content, reported as source `description-definition-of-done`; (2) the item's materialized criteria value as today, reported as `criteria-field`; (3) the description's `Exit criteria` section as today, reported as `description-exit-criteria`. Replace the sentence "The resolved source is reported as one of exactly two values: `criteria-field` (the merged value) or `description-exit-criteria`." with "The resolved source is reported as one of exactly three values: `description-definition-of-done`, `criteria-field` (the merged value), or `description-exit-criteria`." Sources (2) and (3) are LEGACY fallbacks: they resolve for any item so the displays can report the gap, but they are graded only for items already `active` or in `acceptance` when this change is ratified. The capture and groom front-ends MUST write new criteria into the Definition of Done section and MUST NOT write the native field for a newly filed item; an item resolved from a legacy source MUST be reported by the capture, groom and approve displays as `definition-of-done: missing` so it is repaired when next touched. No surface may parse the section by another path.

**Who must carry the section.** The section is required for every item whose effective workflow variant is implement-kind, under EVERY effective `acceptance_policy` including `human-only` — a human accepts against a stated definition, and the human-attested leg of Proposal 5 attests against this section. Amend the shared variant-aware acceptance-eligibility decision so that `human-only` remains eligible with respect to the gradeable-assertion COUNT (its existing carve-out) but is ineligible while the section is absent or carries no valid reference line, and so that a groom-kind variant is exempt from the section requirement entirely (its purpose is to produce Definitions of Done for the slices it cuts). Amend §"Work-item state semantics" where it prescribes `human-only` as the ungradeable-criteria remedy to add that the remedy does not waive the section.

**Host-side wall.** An item whose description carries no Definition of Done section, or whose section carries no valid reference line, MUST NOT enter `ready` (the `approve` transition of §"Work-item state semantics"), and the pre-dispatch wall MUST refuse it with exit code `5`. Amend §"Dispatcher exit codes" so `5` reads: `5` — effective-criteria refusal: the effective acceptance criteria are empty or ungradeable, or the Definition of Done section is absent or carries no valid reference line (§"Effective acceptance criteria"). Already-filed items are not backfilled or exempted: they stay in place, are excluded from every dispatch-candidate enumeration by the shared decision, and are surfaced by the existing `hygiene:unrunnable-acceptance:<work-item-id>` fact, whose remedy text MUST name authoring the Definition of Done section. Amend the `hygiene:unrunnable-acceptance` clause of §"Orchestrator-owned attention facts": a `human-only` item produces the fact when, and only when, its Definition of Done section is absent or carries no valid reference line; 'changes to `human-only`' is removed from the clearing conditions for that case; and the remedy sentence adds 'author the Definition of Done section'. These section-presence, reference and proof-mode checks are the mechanical form of the intake checklist's autonomously-verifiable gate; the intake gate count is unchanged.

**Kept current.** The Definition of Done is the statement the proof stages capture against and the acceptance pass grades against, read from the dispatch-time snapshot. A factory run MUST NOT deliver behaviour that differs from the Definition of Done it was dispatched with: when the implementer determines the section is wrong or incomplete, the run MUST end through the structured needs-human ending carrying the proposed amendment as its failure reason, the item rests at `blocked / needs-human` exactly as any needs-human outcome does, and the human edits the ledger and releases it through `resolve-blocked`. This is the ONE rest state for a wrong Definition of Done, whichever stage notices it (Proposal 3). Amend §"Work-item beads-issue mapping" so the `description` row records that the field's first heading is the Definition of Done section and that the host-written `## Proof of Done` section (Proposal 4) follows it.

**constraints.md.** Add to §"Factory sandbox credential constraints": a factory sandbox MUST NOT hold a store binary, a store credential, or a route to the work-items store; every ledger write that a run's outcome requires MUST be performed by the Dispatcher on the host from what the run emits (its sentinels, its pushed refs, and its forge records).

## Proposal: Proof mode is a per-assertion enumeration; the item's routing is derived from it

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Each Definition of Done assertion carries a proof mode from a closed enumeration whose values describe exactly the two cases that exist: `factory_captured` (the default — the factory captures the proof in the sandbox and replays it before the run may exit) and `human_attested` (the proof needs a surface no sandbox has; a human captures it against the same written steps). Opting out is explicit, sectioned and reasoned. The item-level answer — whether a human leg is required — is computed from the assertions and never stored. A policy on top forbids `human_attested` on any assertion the sandbox could exercise, so real deliverables cannot be exempted; the enumeration is separate from `factory_safety`, `admission_policy` and `acceptance_policy`, declared by the filer and validated by the gate, never changed by the implementer. This proposal supersedes the pending `live-exercise-acceptance-admission` proposal, which SHOULD be rejected at revise; its epic `bd-ib-ehso7x` closes as superseded when this file ratifies, with this file named as the successor.

### Motivation

Motivation as Proposal 1. Additionally: maintainer rulings 2026-09-30: proof mode is an enumeration, not a boolean, whose values describe exactly the two cases we have, kept separate from other work-item metadata; not every feature can be factory-proven and not every chore cannot, so the mode belongs on the assertion; anything in the deliverable itself MUST be factory-testable, and only chore/devops-type work may take a human leg. Absorbs the parking direction of `live-exercise-acceptance-admission` (epic bd-ib-ehso7x) and the LEG 1 / LEG 2 split-acceptance convention that bd-ib-ay5mtm records as unenforced.

### Proposed Changes

Add to `contracts.md` §"Effective acceptance criteria" a `###`-level clause "Per-assertion proof mode".

**Enumeration.** Every gradeable Definition of Done assertion carries exactly one proof mode from the closed enumeration `factory_captured` | `human_attested`. Values MUST be these self-describing names on every surface that renders, journals or configures them; a numbered or tiered label MUST NOT be used. `factory_captured` means the factory's `proof_capture` stage captures visible proof of the assertion inside the sandbox and the `proof_verify` stage reproduces it before the run may publish for merge. `human_attested` means the assertion's proof requires a surface no factory sandbox has, so a human captures it against the same written steps and records it on the pull request. The enumeration MAY gain values by ratification; a value not in the enumeration MUST be reported as a Definition-of-Done finding.

**Declaration.** An assertion's mode is `factory_captured` unless it appears under a `### Human-attested` sub-heading inside the Definition of Done section. That sub-heading MUST carry, before its first bullet, a line `Reason: <text>` naming the capability the sandbox lacks (for example a route to a production host, a session on an external administrative console, or a physical device). A `### Human-attested` sub-heading with no non-empty `Reason:` line MUST be reported as a Definition-of-Done finding by the host-side wall, and the item MUST NOT enter `ready` until repaired. The mode is declared by the filer at capture or groom time and validated by the gate (Proposal 3); an implementer MUST NOT change an assertion's mode, and a run that needs the mode changed ends through the structured needs-human ending with that amendment as its reason.

**The deliverable policy.** An assertion whose subject the factory sandbox could exercise — behaviour of the governed repository's own application, plugin, command-line surface, API, web interface, or test suite — MUST NOT be declared `human_attested`; the gate MUST refuse such a declaration naming the assertion and the sandbox capability that makes it factory-capturable. A `human_attested` declaration is legitimate only for an assertion whose proof genuinely requires a surface outside every sandbox. A proof that requires a write-scoped or production credential is NOT a reason to declare `human_attested`: such an item carries `factory_safety: needs-host-secrets` and is host-routed, where its proof is still captured mechanically.

**Derived routing, never stored.** No field, label or metadata key MAY store an item-level proof mode. The item-level consequence is computed by the shared variant-aware acceptance-eligibility decision from the assertions: when every gradeable assertion is `factory_captured`, the item MAY close under an `ai-only` policy on a PASSING post-merge pass whose criteria leg is the `verified` record (Proposal 5); when any gradeable assertion is `human_attested`, the item MUST park in `acceptance` for the human-attested leg after merge, an effective `acceptance_policy` of `ai-only` MUST be refused for it by the host-side wall with a message naming the human-attested assertions and the two remedies (declare `ai-then-human` or `human-only`, or make the assertion factory-capturable), and this ONE decision MUST be consumed by every dispatch entry path — direct `dispatch --item`, hand-picked, drained and autonomous-loop — so the same item receives the same verdict from each. This clause supersedes the pending proposal `live-exercise-acceptance-admission`: its text-matching admission predicate is replaced by the declared mode, and its three observations (refused before claim from both a direct dispatch and the autonomous loop; an ordinary item admitted; a parked-policy item admitted and parked) are carried by Scenario 132.

## Proposal: Three reserved-workflow stages and a draft publish validate the Definition of Done and capture and replay the Proof of Done

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md

### Summary

The reserved `implement-work-item` workflow gains three ACP nodes — `dod_gate` before `implement`, `proof_capture` between the green janitor and `review`, and `proof_verify` between review and `pr` — and one command node, `publish_draft`, between the green janitor and `proof_capture`, which pushes the publish branch and opens a DRAFT pull request so the proof records of Proposal 4 have a home before `pr` marks it ready. `dod_gate` validates the Definition of Done semantically and rests a malformed item at `blocked / needs-human` through the existing route; `proof_capture` drafts the reproduction steps, follows them verbatim, captures the proof and posts it; `proof_verify` is a different agent with no fix mandate that replays the steps and routes a non-reproducible proof back to `fix`, and the review-cap escape hatch now targets `proof_verify` so nothing ships unreplayed. The nine ACP nodes replace the six every registered variant must declare, the timeout table, adapter enumeration, built-in defaults and success-critical enumeration gain the three names, and the engine constraints that keep the graph loadable after the `fabro-currency` migration land in constraints.md.

### Motivation

Motivation as Proposal 1. Additionally: point 7 of the proposal: an entry gate, a capture stage right after implement/fix, and an exit gate that replays without a fix mandate and kicks back to fix. Capture sits before review so the reviewer reviews the proof with the code; verify sits after review so it replays the tree that will be published. The doctor review found the first draft's records had no pull request to land on, its escape hatch bypassed the replay, and its needs-a-human rest state was unratified; this text resolves each by design decision recorded on the plan epic.

### Proposed Changes

Add to `contracts.md` a `###`-level section "Definition-of-Done and Proof-of-Done stages" under §"Self-contained plugin dispatch", and amend the clauses named below.

**The stages.** The reserved `implement-work-item` workflow MUST carry three additional ACP nodes with these names and positions: `dod_gate`, the first node after `start` and before `implement`; `proof_capture`, entered only from `publish_draft` and exiting only to `review`; and `proof_verify`, entered from `review` and exiting to `pr` on success. It MUST also carry the command node `publish_draft`, entered only from a green janitor outcome and exiting to `proof_capture`, which MUST push the item's publish branch and, when no pull request for that branch exists, open one as a DRAFT; it MUST be idempotent across janitor re-entries and MUST fail closed to `needs_human` when origin cannot be reached. The `pr` node MUST mark that pull request ready and arm auto-merge rather than create it, MAY rewrite the run's own publish branch with a lease-guarded force push when it rebases (the branch is consumed by no one before it is marked ready) and MUST NOT rewrite any other ref, and the existing publish breaker (`verify_pr`) is unchanged. Each of the three ACP nodes selects its adapter through exactly the mechanism the existing six ACP nodes use, with its own adapter input (`dod_gate_adapter`, `proof_capture_adapter`, `proof_verify_adapter`), and migrates with them when that mechanism changes. Amend the variant clause of §"Self-contained plugin dispatch" so a registered variant MUST declare the same NINE ACP nodes — `dod_gate`, `implement`, `fix`, `review_fix`, `proof_capture`, `review`, `disposition`, `proof_verify`, `pr` — and reference the correspondingly widened `inputs.*` token set; a groom-kind variant MUST declare the nodes so the layers resolve but MAY leave `dod_gate`, `publish_draft`, `proof_capture` and `proof_verify` unreached by its edges. Amend §"ACP node timeouts" to add `dod_gate`, `proof_capture` and `proof_verify` to the key list with the same 1800-second default; amend the node list that opens §"ACP node adapter configuration" and the table of §"Built-in ACP node defaults" to add the three nodes, with `dod_gate` and `proof_verify` defaulting to the review tier and `proof_capture` to the implementer tier; and amend §"Factory-configurable ACP fallback priority" so the success-critical enumeration reads `dod_gate`, `implement`, `proof_capture`, `review`, `proof_verify`, and `pr` for the reserved workflow, each of which dominates every green terminal path, so admission and the idle-factory fact require a candidate for each; for a registered variant the success-critical set is the ACP nodes dominating that variant's own green terminal paths.

**`dod_gate`.** The node MUST verify, against the rendered goal, that the Definition of Done section exists and parses per §"Effective acceptance criteria", that every reference resolves, that every proof-mode declaration is valid under the deliverable policy, and that the assertions are coherent with the item's title, description and referenced headings — a Definition of Done that a competent engineer could not recognise as satisfied or unsatisfied from the referenced scenario is incoherent. On success it falls through to `implement`. On failure it MUST end through the structured needs-human ending whose failure reason is the list of Definition-of-Done findings, so the run terminates at the `needs_human` terminal and the Dispatcher rests the item at `blocked / needs-human` with the findings as the recorded question and `resolve-blocked:<id>:ready` as the remedy after the human edits the section. No new state transition, exit code or claim-release path is introduced. The mechanical half of this check (section present, references resolve, modes parse) MUST also run in the host-side wall so a malformed item never spends a sandbox; the semantic half runs only in the node.

**`proof_capture`.** For every `factory_captured` assertion the node MUST author the reproduction steps, execute them verbatim inside the sandbox, capture the proof they produce (a screenshot for anything reachable through a web interface, a terminal capture or a fenced code block of command output for text-only behaviour), and publish the record per Proposal 4 on the draft pull request. It MUST NOT modify the tree; a capture that requires a code change is an implementation defect and the node MUST end succeeded with `preferred_label=fix`, which routes to `fix`; a failed outcome routes to `needs_human` exactly as every other ACP node's does. It MUST state, in the record, which assertions are `human_attested` and therefore not captured. `review` MUST review the latest captured record alongside the code; because `review_fix` re-enters `janitor`, every accepted fix round re-enters `publish_draft` and `proof_capture` before `review`, and a captured record older than the tree under review is a blocking review finding.

**`proof_verify`.** The node MUST run on an adapter distinct from the implementer's, MUST replay the published reproduction steps verbatim on the tree it receives, and MUST NOT modify the tree, the steps, or the Definition of Done. It MUST publish its own record per Proposal 4 with the verdict `verified` when every `factory_captured` assertion reproduced, or `not_reproduced` naming each assertion that did not; the record header renders the verdict verbatim. `verified` routes to `pr`; `not_reproduced` routes to `fix` while the node's own visit count is below three, and the third `not_reproduced` routes to the existing `non_converged` terminal. A proof loop re-enters `review`, and those review visits count toward the review-fix budget like any other. The `review` node's ship-on-review-cap edge MUST target `proof_verify`, never `pr`, so `merge_on_review_cap` skips only the reviewer's approval and never the replay; amend the `merge_on_review_cap` bullet of §"Dispatcher policy settings" accordingly. No edge MAY route from `proof_verify` to `pr` on any verdict but `verified`.

**constraints.md.** Add to §"Fabro runtime constraints": the `dod_gate`, `publish_draft`, `proof_capture` and `proof_verify` nodes MUST NOT await a human, MUST NOT template any node attribute that the existing nodes of the same kind do not already template (`acp.command` for ACP nodes; `script` for command nodes), and MUST NOT reference an `inputs.*` token inside an edge condition; every routing decision MUST be expressed through the node's outcome and the `preferred_label` vocabulary already in use, so the graph remains loadable on the engine the `fabro-currency` plan migrates to. The `fabro-currency` proposal and this file SHOULD be ratified in the same revise or with `fabro-currency` first.

## Proposal: The Proof of Done record is an append-only pull-request comment per run with a pointer in the ledger

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Every proof stage publishes its record as a NEW comment on the item's draft pull request, never edited; the bead's `## Proof of Done` description section holds only a pointer (pull request, comment link, run id, timestamp, verdict) written by the host after merge, so there is exactly one source of truth and a stale pointer is detectable by construction. Binary proof is stored through a proof asset store whose one requirement is that an authorized viewer of the pull request sees the proof inline; the first implementation MAY be the release assets of a per-repository standing prerelease where that requirement is met, chosen because it is a documented API, driven from the sandbox's existing GitHub App credential, adds nothing to the git tree, and inherits the repository's access control — which matters because three governed repositories are private. Asset names follow one flat convention that keeps every run's set disjoint and lets a verify capture be compared to its capture one-to-one.

### Motivation

Motivation as Proposal 1. Additionally: points 3-6 and the maintainer's 2026-09-30 rulings: do not commit proof binaries to the repository; release assets are acceptable as a first pass with an S3-class store as the intended destination; the GitHub record is an append-only comment per run, with the bead carrying the link and timestamp as a sanity check rather than a copy; a naming convention for multiple images per proof per run. The doctor review flagged that a private repository may not render a release-asset image inline through the forge's image proxy; the store requirement below makes that a measured precondition of the implementing slice rather than an assumption of this contract.

### Proposed Changes

Add to `contracts.md` a `###`-level section "Proof of Done record" beside the stages section of Proposal 3.

**The record.** Each execution of `proof_capture`, `proof_verify`, and each human-attested leg MUST publish exactly one NEW comment on the work item's pull request, whose first line is `Proof of Done — <captured|verified|not_reproduced|human_attested> — run <run-id or human identity> — <UTC timestamp>`. A record comment MUST NOT be edited after posting; a correction is a new record. The body MUST contain, per assertion in Definition of Done order: the assertion text, its proof mode, the numbered reproduction steps (naming every credential by environment-variable name and the wrapper that supplies it, never a value), and the proof — an inline image reference for each screenshot and a fenced code block for each text capture. A `captured` or `verified` record on an item with `human_attested` assertions MUST list those assertions under a heading stating they are pending human attestation. The human-attested record MUST be posted by the attesting human on the same pull request in the same structure; images MAY be attached through the forge's own upload.

**The pointer.** After merge, the Dispatcher MUST write a `## Proof of Done` section into the item's description, after the Definition of Done section and preserving it byte-for-byte, containing only: the pull request number, the comment link of the latest `verified` record, its run id and timestamp, its verdict, and — when the item has `human_attested` assertions — the comment link of the human-attested record once it exists. The section MUST NOT copy proof content. A pointer whose run id or comment id does not match the latest record on the pull request is stale and MUST be surfaced by `needs-attention` as a hygiene fact naming the item and the pull request.

**The proof asset store.** Binary proof MUST be stored through one implementation-owned store seam. The store MUST satisfy one requirement: a viewer authorized on the repository sees each image inline in the record comment, and no unauthorized viewer can fetch it; a store that fails the second half MUST NOT be selected for that repository, and the implementing slice MUST measure the requirement on a private repository before selecting a store. Where no API-drivable store satisfies the first half for a repository, the record MUST carry one authenticated link per image in place of the inline reference, the inline half is waived for that repository, and the waiver MUST be journaled per repository naming the store measured; the proof itself is never waived. Where it satisfies the requirement, the first implementation MAY be the release assets of one standing prerelease per governed repository, whose tag is the committed `dispatcher.proof_assets_release_tag` (default `proof-assets`; committed-configuration-only, not a console setting); the prerelease MUST be marked prerelease so it is never the repository's latest release, MUST NOT be deleted while any record references it, and MUST be created by the Dispatcher before the first dispatch of a repository whose item carries a `factory_captured` assertion — a dispatch whose target lacks it after that attempt MUST refuse before any run exists, naming the tag. Proof binaries MUST NOT be committed to the repository tree.

**Naming.** Every asset name MUST have the form `<work-item-id>__<run-id>__<capture|verify>__<NN>__<slug>.<ext>`, where `NN` is the two-digit ordinal of the proof within that stage's record and `slug` is a short lowercase-kebab description; a reproduction step MUST name the asset ordinal it produces, so a `verify` asset compares to the `capture` asset of the same ordinal. Because the run id is part of the name, no run MAY overwrite another run's asset.

## Proposal: The verified proof is the acceptance evidence for factory-captured assertions and the human record gates the accept valve

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The post-merge acceptance pass's criteria leg for a `factory_captured` assertion is the observed `verified` record of the run that merged, not a keyword match over the merged diff; an item with `human_attested` assertions parks in `acceptance` until its human-attested record exists, and the `accept:<id>` valve refuses until then. The PASS bullet of the evidence rule is amended so a mixed item can PASS its factory leg with the human leg listed as pending. This replaces the merged-diff keyword grading for proof-bearing assertions, carries the admissibility direction plan bd-ib-vq6z was to ratify, and makes `done` mean both legs observed.

### Motivation

Motivation as Proposal 1. Additionally: the current pass grades a criterion by whether two of its significant words appear literally in the merged diff, which the ledger records producing nine false reworks on eight items in this tenant (bd-ib-5z0g, bd-ib-tfpdya, bd-ib-99a1, bd-ib-vbm7, bd-ib-qx55). A replayed proof is observed evidence in the sense of §"Post-merge acceptance (`acceptance → done`)" → "The evidence rule"; the keyword match is not. bd-ib-vq6z.5 asks for accept-valve provenance parity; the human-attested record is the concrete artifact that provides it. Plan bd-ib-vq6z's ratification child is bd-ib-vq6z.1.

### Proposed Changes

Amend `contracts.md` §"Post-merge acceptance (`acceptance → done`)".

**The proof evidence leg.** For every effective assertion whose proof mode is `factory_captured`, the acceptance pass MUST take as its criteria-leg evidence the `proof_verify` record of the run whose pull request merged, observed from the pull request: the assertion is judged passing when that record's verdict is `verified` and the assertion is listed as reproduced, failing when the record lists it as not reproduced, and UNOBSERVED — yielding NEEDS_ATTENTION per the evidence rule — when no `verified` record exists for the merging run. The pass MUST NOT apply merged-diff vocabulary matching to an assertion that carries a proof mode; vocabulary matching remains only for items resolved from a legacy criteria source, which after ratification are only items already in flight, and the implementing slice SHOULD record the date after which that leg can be retired. The merged-diff leg and the run/telemetry leg keep their existing semantics. Amend the PASS bullet of §"Post-merge acceptance (`acceptance → done`)" → "The evidence rule": for an item with `human_attested` assertions, PASS requires every `factory_captured` assertion passing and lists the human-attested assertions as pending; the human-attested leg is graded by the `accept` valve, never by the AI pass. The journal record of the pass MUST name, per assertion, the evidence leg it used and the record comment it read.

**The human-attested leg.** An item with at least one `human_attested` assertion MUST rest in `acceptance` after its factory-captured assertions pass, regardless of policy, until a human-attested record exists on its pull request. The `accept:<id>` valve MUST refuse such an item while that record is absent, naming the assertions awaiting attestation and the record format; `needs-attention` MUST surface the pending leg as an attention item carrying the pull request link. `done` for such an item means both records observed. Under `human-only` the AI pass remains advisory and never disposes, as today.

**Unevidenceable assertions.** An assertion that is neither `factory_captured` with a record nor `human_attested` with a record is unevidenced, not failed: the pass MUST yield NEEDS_ATTENTION naming it, MUST NOT consume an `acceptance_rework_cap` attempt for it, and MUST NOT pass it silently. An assertion about another work item, a specification scenario, or a plan file is out of scope for this item's evidence and MUST be reported as a Definition-of-Done finding by the host-side wall and the gate rather than graded. These clauses carry the direction of plan `acceptance-evidence-admissibility` (bd-ib-vq6z); its unauthored ratification child bd-ib-vq6z.1 is satisfied by this proposal and closes as superseded when this file ratifies.

## Proposal: Proof credentials are a ratified, repository-declared, capability-scoped credential class

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md

### Summary

A governed repository MAY declare, in committed configuration and by name only, the credentials its proof stages need to exercise the deliverable's backing services, each with a stated purpose and a capability from a closed self-describing enumeration whose only value today is `read_only`. The Dispatcher projects only declared names, through whatever channel projects the dispatch credential set (never a second one), refuses any declaration that names a withheld capability, carries a credential-shaped value, or fails the sandbox capability rule, and prefers a per-run minted credential over a copied one where the provider can mint. The transport is implementation-owned so the same declaration renders as an inline overlay value on the pinned engine and as a vault token reference after the `fabro-currency` migration.

### Motivation

Motivation as Proposal 1. Additionally: deliverables in the private adopter repositories need their backing services from inside the sandbox, and today no repository can declare an extra secret: the projected set is fixed in code and §"ACP node adapter configuration" says a new provider credential channel requires its own ratified change. The retired wrapper allowlist (1password-env-wrapper b69f37b, 2026-09-12) established that a list of names is a weak boundary and a scoped capability handed across is a strong one; constraints.md §"Factory sandbox credential constraints" requires refusal predicates scoped to capability. The maintainer asked that this be got right rather than improvised (2026-09-30).

### Proposed Changes

Add to `contracts.md`, beside §"Worker credential projection", a `##`-level section "Proof credential projection", and add a paragraph to `constraints.md` §"Factory sandbox credential constraints".

**Declaration.** A governed repository MAY declare `dispatcher.proof_credentials` as a list of objects `{ "name": <environment variable name>, "purpose": <one sentence>, "capability": <value> }`. The key is committed-configuration-only and does not trigger the console Settings lockstep. `capability` MUST be a value of the closed enumeration whose only member today is `read_only`, meaning the credential can observe the named service and cannot create, modify, delete, or spend; the enumeration MAY gain values by ratification and MUST use self-describing names, never tiers. The declaration MUST carry names only; a declaration whose `name` or `purpose` contains a credential-shaped value MUST be refused before any run exists by the same scan that refuses credential-shaped adapter configuration.

**Projection.** The Dispatcher MUST project a declared proof credential into the sandbox only when the value is present in the Dispatcher's own environment as supplied by the target's configured `credential_wrapper`, MUST project it through the same channel that projects the dispatch credential set rather than a second channel, and MUST refuse the dispatch — before any run exists, naming the declaration — when a declared name is one of the withheld dispatch credentials (the store credential, the durable App private key, any long-lived personal access token, or any host provider refresh credential), when the value is absent (naming the target's `credential_wrapper`), or when the declaration's capability would let the sandbox execute code on the host substrate or modify a gate that validates the factory's own output. Where the provider offers a management interface that can mint a scoped, expiring credential, the Dispatcher SHOULD mint one per run and revoke it afterwards rather than copy the host's credential, and the dispatch journal MUST record per declaration whether the projected credential was minted or copied. Journals and records MUST carry names, never values.

**Scope.** A proof that requires a capability outside the enumeration — any write, or any production-scoped credential — is not a proof credential: the item MUST carry `factory_safety: needs-host-secrets` and be host-routed, where its proof is still captured mechanically. The rendering transport of a projected proof credential is implementation-owned: an inline value in the uncommitted run-configuration overlay on an engine with no secret reference syntax, or a by-name vault reference on an engine that resolves one in the worker; a change of transport MUST NOT change the declaration.

**constraints.md.** Add to §"Factory sandbox credential constraints": a proof credential declared per §"Proof credential projection" is subject to every rule of this section; the capability rule is judged against the declared `capability` value AND the observed grant, and a credential observed holding more than its declared capability is a violation regardless of run outcome.

## Proposal: Scenarios binding the Definition of Done gate, the proof stages, the mixed item, and proof credentials

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Four new scenarios bind the behaviour above: the host-side wall refuses a malformed Definition of Done and the gate rests an incoherent one at needs-human while a coherent one proceeds; a factory-captured proof is captured on a draft pull request, reviewed, replayed and published, a non-reproducible proof routes to fix, and a stale pointer is a hygiene fact; a mixed item is refused ai-only from every entry path, parks for its human-attested leg, and the accept valve refuses until the human record exists; a declared proof credential is projected by name and a withheld, absent, credential-shaped or over-scoped declaration is refused before any run exists. At revise, `tests/heading-coverage.json` gains one entry per new scenario heading and per new `## ` heading this file adds to `contracts.md`, each MAY be an owned TODO naming the implementing child of epic bd-ib-7sjdzv.

### Motivation

Motivation as Proposal 1. Additionally: load-bearing behaviour MUST be stated as a clause AND a Gherkin scenario, and every revise that adds a `## ` heading MUST update `tests/heading-coverage.json` in the same change. Behaviours of Proposals 1-6 with no scenario step below are bound by the implementing children's tests and named in their descriptions.

### Proposed Changes

Append to `scenarios.md`, continuing the numbering after Scenario 129, each heading un-backticked with a blank line before its fence in the form of Scenario 129.

## Scenario 130 — The Definition of Done gate admits a coherent item, refuses a malformed one host-side, and rests an incoherent one at needs-human

```gherkin
Feature: Definition of Done is validated before any implementation spend
  Scenario: A malformed Definition of Done is refused host-side
    Given a ready item whose description has no Definition of Done section
    When the Dispatcher evaluates it for dispatch
    Then the pre-dispatch wall refuses with exit code 5 naming the missing section
    And no factory run is created
  Scenario: An unresolved reference is a finding
    Given a ready item whose Definition of Done references a scenario heading that does not exist
    When the pre-dispatch wall evaluates it
    Then the refusal names the unresolved heading text
  Scenario: A Human-attested sub-heading without a Reason line blocks ready
    Given an item whose Definition of Done carries a Human-attested sub-heading with no Reason line
    When the approve valve is driven
    Then the item does not enter ready and the refusal names the missing Reason line
  Scenario: An incoherent Definition of Done rests the item at needs-human
    Given a ready item whose Definition of Done parses but whose assertions cannot be judged from its referenced scenario
    When the dod_gate node evaluates the rendered goal
    Then the run ends through the structured needs-human ending carrying the findings
    And the Dispatcher rests the item at blocked with reason needs-human and the findings as the recorded question
    And no human decision waits inside the run
  Scenario: An implementer that finds the Definition of Done wrong takes the same route
    Given a running implement node that determines the Definition of Done is incomplete
    When the node ends through the structured needs-human ending carrying the proposed amendment
    Then the item rests at blocked with reason needs-human and the amendment as the recorded question
    And no code that differs from the Definition of Done is published
  Scenario: A coherent Definition of Done proceeds to implement
    Given a ready item with a well-formed Definition of Done referencing an existing scenario
    When the dod_gate node evaluates it
    Then the run proceeds to the implement node
```

## Scenario 131 — A factory-captured proof is captured on a draft pull request, reviewed, replayed and published

```gherkin
Feature: Proof of Done is captured and independently reproduced before publication
  Scenario: A draft pull request exists before the first capture
    Given an item whose Definition of Done assertions are all factory_captured
    And the janitor is green
    When the publish_draft node runs
    Then the publish branch is pushed and a draft pull request exists for it
    And a second janitor-green entry does not open a second pull request
  Scenario: Capture after a green janitor
    Given the draft pull request exists
    When the proof_capture node runs
    Then it posts one new Proof of Done captured comment naming every assertion, its steps and its proof
    And every image is stored through the proof asset store under the asset naming form
    And the tree is unchanged
  Scenario: Verify replays after review
    Given review approved the tree and the captured record exists
    When the proof_verify node replays the steps on an adapter distinct from the implementer's
    Then it posts one new Proof of Done verified comment and routes to pr
    And the pr node marks the pull request ready and arms auto-merge
  Scenario: A non-reproducible proof routes to fix
    Given the proof_verify replay fails to reproduce one assertion
    When the node ends
    Then it posts a not_reproduced record naming that assertion and routes to fix
    And no edge routes the run to pr
  Scenario: The review-cap escape hatch still replays
    Given merge_on_review_cap is enabled and the review-fix budget is exhausted with a fix verdict
    When the review node ends
    Then the run proceeds to proof_verify and not to pr
  Scenario: The pointer is written after merge
    Given the pull request merged with a verified record
    When the Dispatcher completes the item
    Then the description carries a Proof of Done section holding only the pointer to that record after an unchanged Definition of Done section
    And the acceptance pass grades each factory-captured assertion from that record and not from diff vocabulary
  Scenario: A stale pointer is a hygiene fact
    Given an item whose Proof of Done pointer names a run id that is not the latest verified record on its pull request
    When needs-attention composes hygiene facts
    Then exactly one fact names the item and the pull request as carrying a stale proof pointer
```

## Scenario 132 — A mixed item is refused ai-only from every entry path, parks for its human-attested leg, and the accept valve refuses until the record exists

```gherkin
Feature: Human-attested assertions require a human record before done
  Scenario: Declaration and routing
    Given an item whose Definition of Done has three factory_captured assertions and one assertion under a Human-attested sub-heading with a Reason line
    When the shared acceptance-eligibility decision evaluates it under an ai-only policy
    Then the host-side wall refuses ai-only naming the human-attested assertion and both remedies
    And a direct dispatch --item and the autonomous loop return the same refusal for the same item
  Scenario: A parked policy admits the item
    Given the same item under ai-then-human
    When the shared decision evaluates it
    Then it is admitted and is recorded as parking for its human-attested leg after merge
  Scenario: Parking after merge
    Given the same item merged with a verified record for its three factory-captured assertions
    When the acceptance pass runs
    Then the pass reports PASS for the factory leg with the human-attested assertion listed as pending
    And the item rests in acceptance and needs-attention surfaces the pending human-attested leg with the pull request link
    And the accept valve refuses naming the assertion awaiting attestation
  Scenario: Done after the human record
    Given a human posts a Proof of Done human_attested comment on the pull request
    When the accept valve is driven
    Then the item closes to done and its pointer carries both record links
  Scenario: An unevidenced assertion parks without consuming the rework cap
    Given a merged item whose factory_captured assertion has no verified record for the merging run
    When the acceptance pass runs
    Then the verdict is NEEDS_ATTENTION naming that assertion and the rework counter is unchanged
  Scenario: The deliverable policy refuses a lazy opt-out
    Given an item declaring a web-interface behaviour of its own application as human_attested
    When the dod_gate node evaluates it
    Then it refuses naming the assertion and the sandbox capability that makes it factory-capturable
```

## Scenario 133 — A declared proof credential is projected by name and a withheld, absent, credential-shaped or over-scoped declaration is refused

```gherkin
Feature: Proof credentials are declared by name and bounded by capability
  Scenario: A read-only credential is projected
    Given a repository declaring one proof credential with capability read_only whose value the credential wrapper supplies
    When an item of that repository is dispatched
    Then the sandbox environment carries that name and the dispatch journal records the declaration by name and whether it was minted or copied
  Scenario: A withheld credential is refused before any run
    Given a repository declaring the store credential as a proof credential
    When an item of that repository is dispatched
    Then the Dispatcher refuses before creating a run, naming the declaration
  Scenario: An absent value is refused
    Given a declared proof credential whose value the wrapper does not supply
    When an item is dispatched
    Then the Dispatcher refuses naming the missing name and the target's credential wrapper
  Scenario: A credential-shaped declaration is refused
    Given a declared proof credential whose purpose text contains a credential-shaped value
    When an item is dispatched
    Then the Dispatcher refuses before creating a run, naming the declaration and the position of the value
  Scenario: An over-scoped declaration is refused
    Given a declared proof credential whose capability would let the sandbox execute code on the host substrate
    When an item is dispatched
    Then the Dispatcher refuses before creating a run, naming the declaration and the capability
```

At revise, `tests/heading-coverage.json` MUST gain one entry per new scenario heading above and one entry per new `## ` heading this file adds to `contracts.md` ("Proof credential projection"), in the same change; each MAY be `TODO` with a non-empty reason and `work_item` naming the implementing child of epic bd-ib-7sjdzv.
