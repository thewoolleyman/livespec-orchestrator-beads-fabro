# definition-and-proof-of-done — brainstorm record and design seed (2026-09-30)

Written by the `definition-and-proof-of-done` session on 2026-09-30 from
the maintainer's proposal, three read-only surveys (factory sandbox
capabilities, ledger prior art, spec contracts) and the brainstorm that
followed. Positions marked RULED are the maintainer's; positions marked
PROPOSED are the session's recommendations awaiting the scoping event.

## 1. The problem

Plans are not done the way the maintainer intends, or are done
incompletely, and require unnecessary oversight. This is contrary to the
livespec goal that intent is reliably transformed into implementation.
Today a factory run's "done" is: janitor green, reviewer approve, PR
merged, and a post-merge acceptance pass that is a KEYWORD MATCHER over
the merged diff (`_dispatcher_acceptance_ai.py` has no LLM in it; a
criterion passes when two of its significant words appear literally in
the diff). Nothing in the loop ever exercises the delivered behaviour.

## 2. The proposal (RULED, maintainer 2026-09-30)

1. A first-class **Definition of Done** and **Proof of Done** on every work
   item; an item cannot be declared done, handed to the human for
   approval, or leave the factory without both.
2. The Definition of Done is a REQUIRED FIRST HEADING in the description
   field, mechanically enforced, and kept current with reality.
3. Proof of Done is VISIBLE proof the Definition of Done happened: a
   screenshot for anything reachable through a GUI (web UI, native app,
   an observability report), a Markdown code block of captured output for
   terminal-only items.
4. Every proof carries explicit steps an agent or a human can follow to
   reproduce it, including which credentials are needed (by name, never
   value) and helper scripts where useful.
5. Three dedicated factory stages: an ENTRY gate validating the
   Definition of Done; a stage right after implement/fix that DRAFTS the
   proof steps, follows them verbatim and CAPTURES the proof; and an EXIT
   gate that REPLAYS the proof without any mandate to fix — failure
   routes back to fix.
6. The Definition of Done MUST reference an existing spec heading — a
   `## Scenario NN — …` in `scenarios.md` or an H2 in another spec file —
   validated by the entry gate.
7. Not every feature can be proven by the factory and not every chore
   cannot; the proof mode is an ENUMERATION (not a boolean), separate from
   other work-item metadata, whose values describe exactly the cases that
   exist, open to more nuance later.
8. Anything IN THE DELIVERABLE ITSELF must be factory-testable; only
   chore/devops-type work may take a human proof leg.
9. Do not commit proof binaries to the repository (bloat). GitHub
   release assets are acceptable as a FIRST PASS (a misuse of that API,
   noted); an S3-class store is the intended destination, with the
   private-repo ACL problem solved first.
10. The proof record lives as an APPEND-ONLY PR COMMENT per run (never
    edited); the bead carries a POINTER (PR, comment link, run id,
    timestamp, verdict), never a copy, so there is one source of truth.
11. A naming convention covers multiple images per proof per run.

## 3. What the factory can and cannot do today (surveyed)

Sandbox image `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.85.3`
(built in livespec-dev-tooling `docker/fabro-sandbox/{base,python,agent}`):

- Terminal proof: WORKS. Full outbound network (Docker bridge, no
  network table → AllowAll), `gh` 2.100, node 26, python 3.10, tmux.
- Screenshots: NO browser, display or screenshot tool in any layer.
- Honeycomb: network reaches it; NO key projected; the projected env set
  is fixed in code (`_dispatcher_overlay.py`) and the ratified dispatch
  credential set is closed (contracts.md L2284).
- Host Dolt / ledger writes: BLOCKED three ways, deliberately (no `bd`,
  no `BEADS_DOLT_PASSWORD`, 127.0.0.1 is the container). The established
  pattern is "the run emits, the host writes" (one-line stderr sentinels
  and pushed refs; the groom workflow files on the host).
- PR image attachment: `gh` cannot upload; GitHub's `user-attachments`
  endpoint is web-session-only.
- GitHub App token in the sandbox has `contents: write` and
  `pull_requests: write` → `gh pr comment` and `gh release upload` both
  work with the credential the sandbox already holds.
- Fleet visibility (MEASURED): openbrain, dolt-server and homelab are
  PRIVATE; the ten fleet repos and resume are public. So logged-out
  screenshots of GitHub pages are not a general mechanism, and image
  hosting must inherit the repo's ACL.

## 4. Prior art and binding rulings (ledger survey)

- Zero prior art for screenshot/browser/attachment proof anywhere in the
  tenant. The entire evidence prior art is diff-vocabulary + telemetry
  grading.
- Two OPEN plan epics own the defensive halves: `bd-ib-vq6z`
  acceptance-evidence-admissibility (unevidenceable ≠ failed; distinct
  verdict routed to a human; never a silent PASS; ratify before
  implementing; `.1` never authored) and `bd-ib-ehso7x`
  live-exercise-acceptance-admission (proposal in
  `SPECIFICATION/proposed_changes/live-exercise-acceptance-admission.md`,
  unrevised: PARK items whose criteria need a live exercise). This plan is
  the offensive form of both — the factory performs and records the
  exercise — and PROPOSES to absorb them.
- Evaluator defect family the proposal cures: `bd-ib-5z0g`, `tfpdya`,
  `99a1`, `vbm7`, `qx55` (9 false reworks / 8 items / 100% artifact rate
  in this tenant by 08-22).
- `bd-ib-ay5mtm`: the LEG 1 / LEG 2 split-acceptance convention for
  live-evidence items, unenforced, "rotted twice in six minutes".
- Binding: AI informs, never decides, under `human-only`; PASS needs every
  evidence leg OBSERVED (v072); NEEDS_ATTENTION parks and never consumes
  the rework cap; never make a failing check non-blocking without a
  control showing a genuinely unmet criterion still blocks; every
  auto-disposition journaled naming the governing setting; a criterion
  naming a `## Scenario NN` cannot pass the current matcher (AGENTS.md).
- Spec collisions to ratify through: the six ACP node names are fixed for
  registered variants (contracts.md L2390) and `dispatcher.node_timeouts`
  is a closed key list — new nodes change the reserved workflow; ONE
  criteria primitive (L3914) — the DoD heading must BE the criteria source
  through `effective_criteria`, not a second parser; "a factory run never
  awaits a human" (v093) — proof nodes never prompt; a new provider
  credential channel requires its own ratified change (L4958) and the
  capability rule (constraints.md L279–337) governs what may be projected.
- This repo has no `non-functional-requirements.md`; its spec files are
  `spec.md`, `contracts.md`, `constraints.md`, `scenarios.md`.
  `tests/heading-coverage.json` already enumerates every H2 of every spec
  file and is the registry the entry gate validates references against.

## 5. Design positions (PROPOSED unless marked RULED)

### Definition of Done as the criteria source
`## Definition of Done` is the required first heading (RULED). It becomes
the canonical source consumed by the existing `effective_criteria`
primitive; the native `acceptance_criteria` field is demoted to a legacy
fallback. Bullets are `- ` one-assertion lines ending in a period, in the
merged diff's vocabulary where the proof is a diff, and the scenario /
heading reference is a structured line the segmenter excludes from
gradeable assertions.

### Proof mode is per ASSERTION; the item's routing is derived
Values (RULED: an enumeration describing exactly the cases that exist):
- `factory_captured` — the factory captures the proof mechanically in the
  sandbox and `proof_verify` reproduces it before the run may exit.
- `human_attested` — the proof requires a surface no sandbox has; a human
  captures it against the same written steps; the item parks for that leg
  and cannot auto-close.
Default is `factory_captured` (the strict case is the zero-ceremony case).
Opting out is a `### Human-attested` sub-section with a mandatory
`Reason:` line naming the missing capability. The item-level answer ("who
must attest") is COMPUTED, never stored: all factory → `ai-only` legal;
any human → parks in `acceptance` for the human leg, `ai-only` refused.
Policy on top (RULED: deliverables must be factory-testable): the entry
gate refuses a human-attested assertion whose subject the sandbox could
exercise. Assigned by the entry gate, never self-assigned by the
implementer; separate from `factory_safety`, `admission_policy`,
`acceptance_policy`. A future `replayed_post_merge` value is the obvious
third.

### Graph shape
```
start → dod_gate → implement → diff-breaker → janitor ⇄ fix
      → proof_capture → review ⇄ (disposition → review_fix → janitor …)
      → proof_verify → pr → verify_pr → exit
```
- `dod_gate` (cheap tier): heading exists, references resolve against the
  heading registry, DoD coherent with title/description/scenario, proof
  modes assigned; failure returns the item to `pending-approval` with the
  finding (a Definition-of-Ready failure, not needs-human). The mechanical
  half also runs host-side as a pre-dispatch wall (exit-5 style) so a
  malformed item never spends a sandbox.
- `proof_capture` sits between janitor-green and review so the reviewer
  reviews the proof alongside the code; `review_fix` carries an explicit
  mandate to re-capture when it changes behaviour.
- `proof_verify` is a DIFFERENT agent with no fix mandate replaying the
  steps verbatim; failure routes to `fix`. Bounded by the existing
  visit-guard pattern.
- Post-merge (host): the Dispatcher writes the bead pointer and records
  the verify outcome as the acceptance evidence leg for factory-captured
  assertions; the keyword matcher stops grading them. A post-merge replay
  in a fresh sandbox against merged master is a deferred follow-on.
- Petri-compatibility (see plan `fabro-currency`, `bd-ib-6tcjfx`): plain
  ACP/command nodes, NO new templated attributes, no `inputs.*` tokens in
  conditions, credentials declared by name so they render as
  `secrets.NAME` tokens on the new engine.

### Proof carrier (RULED shape)
- Each `proof_capture` and `proof_verify` posts a NEW PR comment via
  `gh pr comment`, never edited: `Proof of Done — captured — run <id> —
  <UTC>` / `Proof of Done — verified|NOT REPRODUCED — run <id> — <UTC>`.
  For a mixed item the comment states "N of M assertions; K
  human-attested pending".
- The human leg posts its own comment (`Proof of Done — human-attested —
  <who> — <UTC>`), same step/image structure (drag-drop works in the web
  UI); the `accept:<id>` valve REFUSES until it exists (the provenance
  parity `bd-ib-vq6z.5` asks for, with a concrete artifact).
- Bead `## Proof of Done` = pointer only (PR, `#issuecomment-<id>`, run
  id, timestamp, verdict; both links for a mixed item), written by the
  host post-merge. `done` requires both legs.
- Images: first pass = assets on one standing prerelease `proof-assets`
  via `gh release upload` (documented API, CLI, existing App credential,
  inherits repo ACL, no git bloat), behind a `ProofAssetStore.put(name,
  bytes) → url` seam so an S3-class store can replace it; keep the
  GitHub-hosted store as the default for PRIVATE repos until the S3
  design solves ACL. The `proof-assets` release is a protected fixture.
- Naming (flat asset names):
  `<item-id>__<run-id>__<capture|verify>__<NN>__<slug>.<ext>`; each proof
  step names the image it produces so `verify-NN` compares to
  `capture-NN` one-to-one; run id makes every run's set disjoint.
- GitHub-page proofs default to `gh run view --log` / `gh api` code
  blocks (machine-checkable; App token reaches private repos); real
  GitHub screenshots need the bot-session slice and are deferred.

### Credentials
- Sandbox image gains a headless-chromium + playwright layer (cross-repo,
  livespec-dev-tooling, execution-mirror convention).
- Ratify a credential CLASS, "proof credentials": declared per repo in
  `.livespec.jsonc` as `{name, purpose, capability}` (names only),
  read-scoped and non-production, judged by the entry gate; a proof
  needing a write-scoped or production credential routes to
  `factory_safety: needs-host-secrets` (a human/host leg, NOT the chore
  exemption). Principle from the retired wrapper allowlist ruling
  (1password-env-wrapper `b69f37b`, 2026-09-12): a list of names is a weak
  boundary, a scoped capability handed to the sandbox is a strong one —
  MINT, DON'T COPY where the provider has a management API (GitHub App
  already does; Honeycomb and Supabase can). Transport is a rendering
  detail: inline overlay on the pinned build, `secrets.NAME` on the new
  engine. This slice sequences AFTER `fabro-currency` lands native secrets
  projection (which also retires the measured `inspect` exposure).
- Bot GitHub user session (private-repo GitHub screenshots,
  `user-attachments` uploads): its own later ratification, only if real
  items demand it.

## 6. Candidate slices (for the scoping event)

- S1 ratify (`propose-change`): DoD heading as criteria source; per-
  assertion proof-mode enumeration and its policy; the three nodes and
  the reserved-workflow node set; the PR-comment carrier and bead pointer;
  the proof-credential class; acceptance evidence leg from `proof_verify`;
  absorb `bd-ib-ehso7x`'s proposal and `bd-ib-vq6z.1`'s clauses; scenarios
  + heading-coverage co-edit.
- S2 host-side mechanical walls: DoD heading present, references resolve
  against the heading registry, proof modes parse; `effective_criteria`
  reads the DoD heading first.
- S3 `dod_gate` node + prompt + routing to `pending-approval`.
- S4 sandbox image layer: headless chromium + playwright (dev-tooling).
- S5 `proof_capture` node + prompt + `ProofAssetStore` (release assets) +
  PR comment format + naming convention.
- S6 `proof_verify` node + prompt + routing to `fix`; `review_fix`
  re-capture mandate; reviewer prompt reviews the proof.
- S7 host post-merge: bead pointer write; acceptance evidence leg; accept
  valve refuses without the human-leg comment for mixed items.
- S8 proof credentials (after `fabro-currency`).
- S9 migration: existing ready items without a DoD surface as hygiene
  facts (v111 UNRUNNABLE pattern), no exemption list.
- Deferred: post-merge fresh-sandbox replay; S3-class asset store with
  ACL; bot GitHub session; native-app proof.
