# Reopening — what the first real consumers exposed, and the repair scope (2026-10-04)

This plan was archived on 2026-10-02 (PR #2544). The maintainer ruled on
2026-10-04 that the archive was PREMATURE and directed that the plan be
reopened and repaired. This note records why, from measurement, and cuts the
repair scope. Epic: `bd-ib-7sjdzv`.

## 1. Why the archive was premature

The archive rested on "children merged, CI green, independent review says
every requirement has a carrier". It did not rest on anyone exercising the
feature. No slice of this plan carries a Proof of Done record of its own, the
end-to-end leg was transferred to a carrier (`bd-ib-nfp3ux`) rather than run,
and the plan itself had no Definition of Done to be proved against. The
archive gate permitted all of that, which is the first finding below.

## 2. The evidence: every run that has been through the proof stages

Measured 2026-10-04 across the fleet (forge comment search plus `fabro inspect`
on hp for each run):

| Item | Run | Outcome |
| --- | --- | --- |
| `bd-ib-mxqrr4` (this repo, PR #2538) | `01M3WH8Z1027` | captured and verified, merged. The acceptance pass then returned NEEDS_ATTENTION with no reason recorded on the item; the dispatcher still reported `green`; the item has rested in `acceptance` with NO `## Proof of Done` pointer since 2026-10-01. |
| PR #2552 (this repo) | — | captured and verified, merged 2026-10-02. |
| `overseer-6ltxut` (PR #2335, draft) | `01M3WDN74ESC` | `proof_capture` found a real defect and routed to `fix`; the `fix` prompt knows only a red janitor, changed nothing and reported success; halted by its coordinator; run `failed` with "stage needs_human failed with no outgoing fail edge". Draft stranded since 2026-10-01, item `blocked` with no blocked reason. |
| `overseer-zyw474` (PR #2334, draft) | `01M3WGEFHGD1` | same route; run `failed` on a `fix` checkpoint commit; draft stranded, item left `active`. |
| `overseer-vgf6d3` (herdr plan slice 1) | `01M425FDCKP5` | `dod_gate` passed in 69 s; paused in `implement` by maintainer hold. |

The proof-to-fix handoff defect is already filed as `bd-ib-yastku` (ready).

## 3. Findings, by cause

**F1 — Done is defined per work item, but the maintainer's intent arrives per
plan.** A plan epic has no Definition of Done and no Proof of Done. The herdr
plan (`overseer-uzvcbn`, livespec-overseer) is the worked example: the
maintainer's stated definition of done — "you have run it directly yourself in
a herdr session and seen it work ... don't declare done until you have actually
used it" — lives only in that plan's research note and in the driving
session's promise. No work-item assertion carries it; its fourth slice says in
prose "coordinator owns that final acceptance". The machinery can close every
child and the archive gate can pass without that ever happening. This plan's
own problem statement was "plans are not done the way the maintainer intends",
and that half was not delivered.

**F2 — Authoring is unguided.** `prose/capture-work-item.md`,
`prose/capture-impl-gaps.md`, `prose/groom.md`, `prose/plan.md` and
`prose/implement.md` contain ZERO occurrences of "definition of done", "proof"
or "attested" (measured by `grep -c -i` on master `6513226b`). Enforcement
exists only at dispatch, so filers learn the rules from refusals.

**F3 — Tests are accepted as proof.** Both overseer items' entire Definition of
Done reads "tests prove X ...; the full just check aggregate passes", and their
proof assets are four pytest output files. The herdr slice's gate verdict
accepted its assertions as "exercisable in-sandbox via a local Unix-socket test
server and adapter regression tests". The capture prompt's "text-only
behaviour — the command and its real output" lets a suite run count. Where an
assertion named real behaviour (PR #2538) the proof was strong: real commands,
an independent second parse, and mutation checks with a landed-mutation
control. The original problem — "nothing in the loop ever exercises the
delivered behaviour" — therefore persists exactly when the assertion is written
about tests.

**F4 — Capability is checked in one direction only.** `dod-gate.md` check 3
rejects a `human_attested` assertion the sandbox could exercise. Nothing
rejects a `factory_captured` assertion the sandbox CANNOT exercise. The sandbox
image carries tmux (deliberately, for factory-tier acceptance tests on private
tmux sockets) and a headless browser, and carries no herdr; nothing declares
what it can exercise, so the gate reasons about capability from the item's own
prose.

**F5 — There is no honest mode for "needs the released build on a host".** The
closed enumeration is `factory_captured | human_attested`. A proof that needs
the released, normally installed build on the operator host is neither: an
agent can perform it, but not inside the sandbox and not before release. Today
it falls outside the system as prose.

**F6 — The spec reference need only resolve.** Any H2 passes ("Runtime
requirements", "Inherited from livespec"). Proof steps are not tied to the
referenced scenario's own Given/When/Then.

**F7 — The chain breaks under real use.** (a) proof-to-fix drops the finding
(`bd-ib-yastku`). (b) A NEEDS_ATTENTION acceptance verdict on a merged,
verified item records no reason, writes no pointer, and is reported `green`.
(c) The `needs_human` terminal fails the run with "no outgoing fail edge",
which presents a deliberate rest as a workflow error. (d) Halted runs leave
items `active` or `blocked` with no reason.

**F8 — The archive gate certifies coverage, not function.** It asks whether
every requirement has a closed child or a named carrier. It never asks whether
the plan's stated outcome was observed.

## 4. Repair scope — requirement carriers

- **R1** Plan-level Definition of Done and Proof of Done (F1, F8). A plan epic
  carries a Definition of Done whose assertions record the maintainer's stated
  done criterion; each plan assertion maps, in a scope event, to child
  assertions or to a plan-level proof; archive refuses without a verified
  plan-level Proof of Done record taken against the released build.
- **R2** A third proof mode, `host_captured` (F5): the proof needs the
  released, installed build or a host surface no sandbox has; an agent session
  captures it on the host in the same record format and an independent party
  replays it; the accept valve holds the item until the verified host record
  exists.
- **R3** Behaviour, not tests (F3): an assertion names an observable behaviour
  of the delivered artifact on a real surface; suite output alone proves only
  an assertion whose subject is itself a test or check; the gate reports
  test-existence assertions and the capture stage refuses suite-only proof.
- **R4** Declared sandbox capabilities, checked both ways (F4): the sandbox
  image publishes what it can exercise; a `factory_captured` assertion needing
  an absent capability is a gate finding naming both remedies.
- **R5** The reference governs the proof (F6): where a referenced heading is a
  scenario, capture steps exercise that scenario's own steps.
- **R6** Authoring guidance and a filing-time wall (F2): the capture, groom and
  gap-capture front-ends carry the rules of R2–R5 and report Definition-of-Done
  findings at filing, not first at dispatch.
- **R7** Chain repairs (F7): `bd-ib-yastku`; a recorded reason, a pointer and an
  honest non-green result for a NEEDS_ATTENTION verdict; the needs-human
  terminal reported as a rest, not a workflow error; no silently stranded item.
- **R8** herdr in the factory sandbox image (F4, and the herdr plan's own
  need), through the livespec-dev-tooling execution mirror, as tmux and the
  browser were added.
- **R9** The proof of this reopening: the held herdr plan resumes and completes
  with real records at every level — behavioural item proofs exercised against
  herdr in the sandbox, and a `host_captured` plan-level proof of the released
  build — and the two stranded overseer items replay to a clean end.

## 5. This plan's own Definition of Done (it has one now)

- Every requirement carrier R1–R8 is ratified where it changes the contract and
  landed through the factory with its own verified Proof of Done record.
- A plan created after R1 lands cannot be archived without a verified plan-level
  Proof of Done record, demonstrated by a refusal on a real plan.
- The herdr plan `overseer-uzvcbn` completes under the repaired machinery with
  a verified `host_captured` record showing the released overseer running in a
  real herdr session, daemon in the top pane and the agent in the bottom pane.
- The first merged proof-chain item (`bd-ib-mxqrr4`) carries its pointer and a
  recorded acceptance verdict.

Proof modes: the first two are `factory_captured` through their items; the last
two are `host_captured` and are taken on the operator host.

## 6. Explicit deferrals (unchanged from the 2026-09-30 scope event unless stated)

- Post-merge replay in a fresh sandbox: still deferred; `host_captured` covers
  the released-build case without it.
- An S3-class proof asset store; a bot GitHub browser session; native desktop
  proof: unchanged.
- Carriers filed at the first archive stay open and are re-adopted as children
  where they fall inside R1–R8: `bd-ib-ymy7xq`, `bd-ib-nfp3ux`, `bd-ib-qm4luz`,
  `bd-ib-pa73qh`, `bd-ib-gp2nt5`.
