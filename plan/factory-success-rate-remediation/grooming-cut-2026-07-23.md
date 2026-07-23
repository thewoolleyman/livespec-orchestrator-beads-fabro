# Grooming cut — factory-success-rate-remediation queue (2026-07-23)

This document is the groomed cut for epic `bd-ib-cvgjop`, prepared for
supervisor review per the 2026-07-23 brief. NOTHING in it has been
promoted: every proposed status change, rank, and new slice in §5 waits
for the supervisor's approval of this cut. The o35rcx design slices in
§1 were explicitly pre-authorized and are already FILED (none `ready`).

**One operational caveat on the stop-before-ready gate.** This repo's
`.livespec.jsonc` runs `auto_approve_ready: true`, so any item resting
in `pending-approval` is auto-promoted to `ready` by the next
Dispatcher drain. Two of the filed o35rcx slices rest in
`pending-approval` — they are additionally held by open dependency
edges, so they cannot dispatch regardless — but the practical promotion
gate for this cut is: RUN NO DRAIN until the cut is approved. The
manual cross-track serialization protocol already forbids an
unclaimed drain, so this adds no new obligation.

Notation used below:

- **factory-safe** — in-repo, dispatchable Python/config work the dark
  factory can implement (`dispatcher.py dispatch/loop`); it touches
  nothing the sandbox credential cannot push (in particular nothing
  under `.github/workflows/`).
- **hand / supervised** — work performed from an attended host session
  (outward-facing fork work, host operations, or verification that
  observes the factory itself). On approval these items get a non-null
  `factory_safety` marker so the admission valve refuses them
  mechanically (that refusal is already implemented and tested —
  `_dispatcher_host_only.py`, Scenario 48 first scenario).
- **verify-first** — the item is old enough that later work plausibly
  fixed part of it; its first acceptance criterion is a cheap
  verification step that either narrows the scope or closes the item
  with evidence. Verification evidence is journaled on the item.

## 1. The o35rcx restructure (maintainer-decided; slices filed)

Decision (2026-07-23, relayed): restructure by SPLITTING
finding-disposition and fix-implementation into separate,
independently promptable, independently model-selectable steps of the
`implement-work-item` graph. Design record (authoritative):
`research/review-fix-split-design.md`. `bd-ib-o35rcx` and epic
`bd-ib-cvgjop` bodies now cite it.

Filed slices (already in the ledger, per the pre-authorization):

| Slice | Id | Filed state | Routing |
|---|---|---|---|
| S1 spec amendment (Scenario 20) | `bd-ib-t5u62i` | `blocked` (needs-human) | maintainer-gated (spec-change tier) |
| S2 the split: graph + prompts + `disposition_adapter` + telemetry parser | `bd-ib-fe574e` | `pending-approval`, depends on S1 | factory-safe |
| S3 live-exercise evidence journaled on `bd-ib-o35rcx` | `bd-ib-p3sjiy` | `pending-approval`, depends on S2 | supervised |

Closure preconditions recorded on `bd-ib-o35rcx`: an independent
adversarial review of the design record (launched 2026-07-23, Codex;
findings will be dispositioned on the design record or the item) AND
S3's journaled evidence.

## 2. Groomed queue — per-item acceptance criteria and routing

Ordered by the synthesis priority (failure-bucket size), not by rank.

### 2.1 `bd-ib-nga9` — refuse workflow-editing items pre-dispatch (31% bucket)

Routing: **factory-safe**. Spec-backed: Scenario 48 is RATIFIED and its
general mechanism is already implemented — the admission valve refuses
any item with non-null `factory_safety`
(`test_loop_refuses_factory_unsafe_item_before_launch`). The residual
is exactly Scenario 48's second and third Gherkin scenarios.

Acceptance criteria:

1. A `ready` item whose scope edits a file under `.github/workflows/`
   is refused at the admission valve even when its `factory_safety`
   field was never manually set: not admitted, no sandbox launched,
   refusal names the attended-host-session route, terminal verdict with
   no interactive prompt, item stays `ready` (not `blocked`)
   (Scenario 48, second scenario, verbatim semantics).
2. The detection is keyed on the `.github/workflows/` path prefix
   SPECIFICALLY: an item editing only `.github/actions/**` (composite
   actions) is admitted (Scenario 48, third scenario).
3. A cite-only false positive (an item that MENTIONS a workflow file
   without editing it) has a documented override route via the existing
   valve surfaces (implementer's choice of mechanism; the refusal
   message names it).
4. `tests/heading-coverage.json`'s Scenario 48 entry graduates from
   `TODO` to the binding test if the classifier accepts the path (the
   entry's own recorded intent).
5. Red-Green-Replay; paired tests; `just check` green.

### 2.2 `bd-ib-lgv` — declare + enforce the no-workflow-edits boundary in-run (31% bucket, defense-in-depth)

Routing: **factory-safe**. Complementary to nga9: nga9 gates on the
item's DECLARED scope at admission; lgv gates on the ACTUAL branch diff
in-run, catching an agent that drifts into workflow edits mid-run.

Acceptance criteria (from the item body, confirmed still-valid):

1. The Dispatcher's goal-file builder states the standing constraint
   verbatim: factory branches never create/update files under
   `.github/workflows/`; a legitimately-needed workflow change is
   restored to master's content, the rest published, and the dropped
   unified diff reported for maintainer-side landing.
2. An early mechanical guard (janitor stage or earlier) fails fast when
   `git diff origin/master...HEAD` touches `.github/workflows/`, with
   the carve-out hint — instead of discovering the boundary at push.
3. Ride-along: the groom prose gains the corollary that grooming splits
   workflow-file wiring into an explicitly maintainer-side step.
4. Red-Green-Replay for the Python legs; paired tests; `just check`
   green.

### 2.3 `bd-ib-qq7f` — push leg races master churn: rebase before publish

Routing: **factory-safe** (prompt/config change, possibly no product
Python — then a `chore` commit; live evidence rides the next
dispatches).

Acceptance criteria:

1. The pr stage fetches and rebases onto CURRENT `origin/master`
   immediately before the push/PR leg.
2. On the exact remote-rejection signature (`refusing to allow a GitHub
   App to create or update workflow … without workflows permission`),
   exactly ONE auto-retry after a fresh fetch+rebase.
3. A simulated stale-base push (or scripted equivalent) demonstrates
   the rebase path; existing dispatch tests stay green.
4. The rejection signature no longer reaches needs-human for the
   stale-base cause (journal evidence on the item from the first
   affected live dispatch).

### 2.4 `bd-ib-pums` — staging preflight: refuse a non-origin-reachable base (adopt into epic, §3)

Routing: **factory-safe** — scoped to the Dispatcher-side preflight
(the item's suggested directions (a)+(c) at the Dispatcher seam).
The engine's silent snapshot fallback itself is fork territory and out
of scope here.

Acceptance criteria:

1. Before launching a run, the Dispatcher verifies the source
   checkout's HEAD is an ancestor of an origin ref; when it is not, the
   dispatch is refused BEFORE any sandbox work, loudly naming the
   unpushed commits and the hook-refusal outcome.
2. The refusal is a distinct journaled terminal outcome (no interactive
   prompt, no stranded `active` item).
3. Red-Green-Replay; paired tests; `just check` green.

### 2.5 `bd-ib-sd8o` — concurrent-dispatch safety (slice into a/b/c)

Too big for one dispatch; propose THREE slices per its own deliverable
structure (filed on approval, children of `bd-ib-sd8o`'s epic context):

- **sd8o-c interim admission-time mutex** — **factory-safe**, first.
  Acceptance: (1) with one dispatch RUNNING, a second is refused at
  admission naming the running run id and the guard; (2) the guard
  releases on terminal state with no leaked lock after a crashed
  dispatch (liveness-checked, per the janitor-lock TOCTOU lineage);
  (3) PARKED (human_input_required) runs do NOT hold the mutex;
  (4) recorded as interim — `bd-ib-sd8o` is not done until (b) lands.
  This mechanizes today's manual cross-track serialization protocol.
- **sd8o-a diagnose the contended resource** — **supervised** (live
  host experiments with concurrent sandboxes). Acceptance as written on
  the item (controlled reproduction or bounded-search null result;
  mechanism-level evidence naming the resource; clean teardown).
- **sd8o-b the real fix** — routing decided AFTER (a); blocked on (a).
  The item body's acceptance stands, including retiring the manual
  serialization doctrine and re-scoping `.ai/dispatcher-drain-operations.md`.

### 2.6 `bd-ib-18r` — `blocked` as a first-class dispatch outcome (40% mechanism)

Routing: **factory-safe**, **verify-first** (filed 2026-07-04; the
Dispatcher has since gained the watchdog, `stalled-no-progress`, and
journal machinery — part of this may already exist).

Acceptance criteria:

1. VERIFY-FIRST: demonstrate whether the current `dispatch`/`loop`
   still conflates a parked (`human_input_required`) run with `failed`.
   If fully fixed, close with the evidence; else narrow to the residual.
2. A parked run yields a DISTINCT `blocked` outcome (never `failed`)
   journaled with the run id and the `fabro attach <run-id>` reattach
   command.
3. The parked state is written to the ledger item per the lifecycle
   (blocked/needs-human surfacing, not silence).
4. Exit-code semantics per the documented contract (non-green, but the
   outcome record says `blocked`).
5. Red-Green-Replay; paired tests.

### 2.7 `bd-ib-6vu` — parked-run resume credential re-projection: verify-first

Routing: **supervised verification now; re-slice only if a residual
remains.** The pinned fork build carries PR #568 (credential refresh)
and `workflow.toml` now requests App-token permissions so fabro OWNS a
mintable token source and re-projects a fresh `GITHUB_TOKEN` at each
node spawn ("fabro-token-refresh part 1", merged via PR #429 of
`bd-ib-2nq`). That plausibly fixes exactly this item.

Acceptance criteria:

1. Verify on the pinned host fabro (0.254.0 factory-integration):
   does a run resumed via `fabro attach` after >1h parked receive a
   fresh token at its next publish attempt? Evidence: the fork's
   turn-entry re-mint code path plus one live or simulated
   confirmation.
2. If fixed: reconcile the Dispatcher docstring with the actual re-mint
   mechanics and close with journaled evidence.
3. If not fixed: file the narrowed implementation slice (a
   dispatcher-mediated resume entry point that re-projects credentials
   — factory-safe) and route the fabro-seam variant to the fork track.

### 2.8 `bd-ib-4sy` — in-sandbox PR-node token TTL: verify-first

Routing: **supervised verification now; likely closeable.** Same
mechanism as 2.7: the `[run.integrations.github.permissions]` block
exists precisely to make fabro re-project a fresh `GITHUB_TOKEN` into
every node's ACP launch env, replacing the static launch-time
projection this item describes.

Acceptance criteria:

1. Evidence that a >60-minute run's pr node receives a fresh token
   (recent run transcript/events, or one deliberate long-run probe).
2. If confirmed: close 4sy with the evidence journaled; split the
   still-open secondary hardening (preserve committed work on
   publish-stage failure — rescue ref or bundle export instead of
   teardown) into its own follow-up item, which `bd-ib-pums`'s manual
   `fabro dump` rescue precedent motivates.
3. If not confirmed: the item body's fix directions stand; re-groom.

### 2.9 Cited for status only (not in this cut's promotion set)

- `bd-ib-2nq` — part 1 merged (PR #429); parts 2+3 are outward-facing
  fork/host rollout: **hand**, tracked in ledger `bd-ib-2nq.4`.
- `bd-ib-6ka` — `blocked` `infra-external`; untouched by this cut.

## 3. Epic-coverage verification (the four 2026-07-23 dispatch-failure classes)

Requested check: `bd-ib-qq7f` (push-race) and `bd-ib-sd8o`
(concurrency) are tracked in the epic — CONFIRMED, both are in the
epic's cited list and groomed above. The other two:

- **`bd-ib-pums`** (silent snapshot-base fallback → disjoint-history
  publish → misleading workflows-scope rejection): tracked NOWHERE —
  no epic cites it; it is only laterally cross-referenced from its
  sibling filings. It is squarely this epic's subject matter (a
  publish-stage work-product loss class). RECOMMEND: adopt into
  `bd-ib-cvgjop`'s tracked list and groom per §2.4.
- **`bd-ib-w2ah`** (work-item tenant repo ≠ implementation repo;
  execution-mirror convention is the working remedy): tracked NOWHERE.
  It is a dispatch-failure class, but its remedy is a maintainer
  DECISION first — build native cross-repo staging, or codify the
  proven execution-mirror convention as the documented answer.
  RECOMMEND: adopt into the epic's tracked list as a cited class, and
  put the decision to the maintainer (flag §4.4). My recommendation:
  codify the convention (a documentation chore; the convention is
  proven end-to-end, and native cross-repo staging is real engine work
  the failure data does not currently justify).

## 4. Maintainer-facing flags (explicit)

1. **`disposition_adapter` default model** (o35rcx S2): the design
   record defaults the new disposition node to the UN-pinned
   implementer-class Claude adapter, not the Opus-pinned review
   adapter. One-line knob to change; flagged as a policy choice.
2. **S1 is a spec-change-tier revise** (Scenario 20 amendment): the
   revise valve is the maintainer's; the factory cannot proceed to S2
   until it ratifies.
3. **Adversarial-review disposition**: the independent review of the
   design record may return findings; their disposition (and any design
   change) comes back through the supervisor before S2 dispatches.
4. **`bd-ib-w2ah` decision**: native cross-repo staging vs codifying
   the execution-mirror convention (recommendation: codify, §3).
5. **Epic adoption edits**: adding `bd-ib-pums` and `bd-ib-w2ah` to
   `bd-ib-cvgjop`'s tracked list is a ledger description edit executed
   on approval of this cut.
6. **`bd-ib-4sy`/`bd-ib-6vu` may close on evidence** rather than be
   implemented — approving this cut approves closing them if the §2.7/
   §2.8 verification confirms the fix, with evidence journaled.

## 5. Promotion set + drain order (EXECUTED ONLY ON APPROVAL)

On approval, in this order:

1. Set non-null `factory_safety` (host-only routing) on: `bd-ib-t5u62i`
   (S1), `bd-ib-p3sjiy` (S3), and the new sd8o-a slice — so no drain
   can ever pick them.
2. File the sd8o slices per §2.5 (c: factory-safe; a: supervised;
   `bd-ib-sd8o` remains the anchor for b).
3. Adopt `bd-ib-pums` + `bd-ib-w2ah` into the epic's tracked list
   (description edit).
4. Promote to `ready` (rank order = drain order):
   `bd-ib-nga9` → `bd-ib-lgv` → `bd-ib-qq7f` → `bd-ib-pums` →
   sd8o-c → `bd-ib-18r`. (`bd-ib-fe574e`/S2 joins the drain
   automatically once S1 ratifies — its dependency edge is the gate.)
5. Run the supervised verify-first legs (§2.7, §2.8) from the host
   session in parallel with the drain — they cost minutes and may
   close two items.
6. Drain strictly sequentially (`--budget 1 --parallel 1`) under the
   cross-track serialization protocol (claim/release in the
   fleet-pin-propagation supervisor status.log) until sd8o-c lands and
   is blessed as the mechanized replacement.

## 6. Artifacts and repo-change plan

New files this session (untracked, in the primary checkout — same
posture as the pending `wip-cap-zero-dispatch-off.md` proposal):

- `plan/factory-success-rate-remediation/research/review-fix-split-design.md`
- `plan/factory-success-rate-remediation/grooming-cut-2026-07-23.md`
  (this file)

On approval both go to `master` via the standard worktree → PR → merge
path (`chore(plan): …`). Ledger mutations already made under the
pre-authorization: the three o35rcx slices filed; `bd-ib-o35rcx` and
`bd-ib-cvgjop` descriptions updated with the decision, design-record
pointer, and child citations.

## 7. Execution addendum (2026-07-23, post-review)

Supervisor verdict on this cut: **APPROVED WITH AMENDMENTS**. Flag
dispositions: flag 1 DECIDED (keep the un-pinned implementer-class
`disposition_adapter` default); flag 2 RE-ROUTED (S1 is NOT
maintainer-blocked — the split decision was the substantive one; S1
proceeds autonomously as propose-change → independent adversarial
Fable review → on NO-BLOCKERS drive the revise accept citing the
2026-07-23 maintainer directive; S1 stays host-only); flag 4 DECIDED
(codify the execution-mirror convention for `bd-ib-w2ah` as a
documentation chore under the epic; native cross-repo staging stays
unbuilt); flags 5–6 approved as written. AMENDMENT (relocate-never-
drop): `bd-ib-pums`' root defect — the ENGINE-side silent
snapshot-base fallback — gets a tracked fork-track item
cross-referenced from `bd-ib-pums`, not an "out of scope" note.

The independent adversarial review of the design record returned
**SOUND-WITH-CHANGES** (2 blocking, 4 advisory, 4 cleared); all ten
findings are dispositioned in the design record's §"Adversarial
review disposition" (blocking #4 → both `max_visits` backstops raised
to 10 with the cap-override coupling documented; blocking #5 → the
durability claim downgraded and hardened with round-distinct
`finding_dispositions_r<N>` context keys). Per the supervisor's
sequencing: S1 (`bd-ib-t5u62i`) and S2 (`bd-ib-fe574e`) WAIT until
the supervisor reviews those dispositions; every other branch of this
cut executes now.
