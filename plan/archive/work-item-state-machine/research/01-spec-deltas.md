# L1a spec deltas — `SPECIFICATION/contracts.md` (the propose-change payload)

This is the **drafted propose-change payload**, human-readable. The
machine payload for `/livespec:propose-change` is
`02-propose-change-findings.json`. The `revise` gate ratifies it
(AUTO-RATIFY — design LOCKED). Authority for every value below: the
cross-repo design of record (`02-design.md` §2/§3/§4/§5/§6;
`03-decision-log.md` decisions 7/9/10/22/26/28/32/33/34/35/36/39/40/44).

Targets: `SPECIFICATION/contracts.md` (the wire/realization contract),
`SPECIFICATION/scenarios.md` (the load-bearing-behavior Gherkin per
authoring discipline (i)), and `tests/heading-coverage.json` (the
H2-registry co-edit for the one new H2).

---

## Delta 1 — rewrite the `status` / field homes in `## Work-item beads-issue mapping`

The section's logical-field → beads-home map is rewritten for the
deterministic lifecycle (decisions 36/39):

- **`status`** — the seven livespec states map to beads as **5 custom
  statuses + 2 built-in reuses** (decision 36, verified against the
  pinned beads v1.0.5):

  | livespec state | beads | kind | category |
  |---|---|---|---|
  | `backlog` | `backlog` | custom | unspecified |
  | `pending-approval` | `pending-approval` | custom | unspecified |
  | `ready` | `ready` | custom | **active** |
  | `active` | `active` | custom | wip |
  | `acceptance` | `acceptance` | custom | wip |
  | `blocked` | `blocked` | built-in reuse (name matches) | wip |
  | `done` | `closed` | built-in reuse (native closure) | done |

  Only `done`↔`closed` needs an adapter name-mapping — the one place a
  livespec term ≠ its beads term (exactly where decision 2 says backend
  terms live). `ready` is the only `active`-category status, so native
  `bd ready` surfaces exactly the admission-eligible set (defense in
  depth — livespec computes real readiness in Python regardless). The
  legacy enum (`open`/`in_progress`/`blocked`/`closed`/`deferred`) is
  superseded.

- **Custom-status registration (bootstrap, per-tenant).** Each tenant's
  bootstrap MUST register the 5 custom statuses via `bd config set
  status.custom "backlog,pending-approval,ready:active,active:wip,acceptance:wip"`.
  A clean tenant cannot transition into a custom status it has not
  registered.

- **2-step `append_work_item`.** Because `bd create` forces
  `open`/`deferred` (cannot create directly into a custom status), every
  initial-state write is a **2-step** path: `bd create` (lands `open`)
  then `bd update --status <state>` — even a plain `file`, since
  `backlog` is custom. The close path stays the in-place `bd close`
  (mapping livespec `done` → beads `closed`).

- **`rank`** — beads **`metadata.rank`** (a structured value rides the
  metadata JSON column, like `audit`). `rank` is the sole ordering
  authority (decision 39): strictly-required non-null `str`. A legacy
  beads issue whose `metadata` lacks `rank` reads back through the shared
  **bottom-sentinel** (`livespec_runtime.work_items.rank.BOTTOM_SENTINEL`)
  the store adapter substitutes, so it sorts strictly after every real
  key without making the domain type nullable.

- **`priority` REMOVED as a logical field** (decision 39 — two order
  sources = two conflicting truths). Legacy beads issues keep their
  native `priority` harmlessly; new/backfilled records do not depend on
  it. (The native beads `priority` column still exists; the work-item
  mapping simply no longer reads it into the logical record.)

- **`admission_policy`** → beads label `admission:<auto|manual>`;
  **`acceptance_policy`** → beads label `acceptance:<value>`;
  **`blocked_reason`** → beads label `blocked-reason:<value>` (the STORED
  reasons only — `{needs-human, infra-external}`; `dependency` is DERIVED
  and never stored). Absent label ⇒ the field reads back `None` (inherit
  / default — the blessed optional-on-read pattern).

- **`assignee`** stays the beads native `assignee` field (decision 35 —
  reused in place as the claimed-by/owner field; no new `owner` field).
  The Dispatcher sets it on `admit`; it is **REQUIRED once `status ==
  active`** (the `active ⟹ assignee` invariant).

> **Invariants (doctor-checkable; restated for the consumer):**
> `active ⟹ assignee` set; stored `blocked ⟹ blocked_reason ∈
> {needs-human, infra-external}`; reaching `ready` requires transiting
> `pending-approval`; every live (head) issue has a real, non-sentinel
> `rank`. Enforced by this plugin's `doctor` (L1 code), not by the
> mapping prose.

---

## Delta 2 — new H2 `## Dispatcher admission, WIP cap, and post-merge acceptance`

A NEW H2 (heading-coverage co-edit required) documenting the two valves
and the WIP cap (decisions 7/9/10/22/26/33/34). The Dispatcher
(`dispatcher.py` `dispatch`/`loop`) is the **sole enforcer**; the console
only commands + observes.

**Admission valve (`ready → active`).** By the time an item is `ready` it
is already approved (approval ≡ `ready` membership, decision 26). The
valve's remaining conditions:
- **Permission** was settled at the `pending-approval → ready`
  (`approve`) transition: `admission_policy == auto` auto-approves once
  at groom time; `admission_policy == manual` (the default, via inherit)
  waits for a human's explicit `approve`. This `admission_policy` field
  **replaces the `host-only` / `human-gated` text markers** — risky /
  irreversible work is held here, at admission, never by a pre-merge
  acceptance gate (decision 33).
- **Capacity:** a free WIP slot under the per-repo cap
  (`count(active) < wip_cap`).
- **Assignee resolvable:** the Dispatcher sets `assignee` on `admit`
  (decision 35); an item with no resolvable assignee is not admitted.

When a slot frees, the Dispatcher pulls the **highest-`rank`**
admission-eligible `ready` item (eligible = deps-clear ∧ assignee
resolvable), sets `assignee`, and transitions it to `active`.

**Per-repo WIP cap.** Sourced from this repo's `.livespec.jsonc` (a new
config key under the `livespec-orchestrator-beads-fabro` block —
proposed `dispatcher.wip_cap`), default **5** (decision 22). NOT a single
fleet-wide number; total fleet concurrency = the sum of per-repo caps.

**Post-merge acceptance (`acceptance` valve).** `just check` stays the
HARD **pre-merge** floor (the in-sandbox janitor gate). Acceptance
verifies *fit + real behavior* against the **shipped** artifact
(decision 33):
- **`complete` (`active → acceptance`)** — **merge-on-green**: the Fabro
  impl run keeps today's `gh pr merge --rebase --auto`; entering
  `acceptance` means the change is **merged + live + observable**.
- **`accept` (`acceptance → done`)** — a **post-ship confirmation** per
  `acceptance_policy`: `ai-only` (AI confirms autonomously);
  `human-only` (a human accepts from the console); `ai-then-human`
  (**default** — the AI verifies and surfaces, then the item **parks in
  `acceptance`** on the ledger until a human confirms). No "release with
  zero verification" — every acceptance has ≥1 AI pass.
- **`reject` from `acceptance`** carries a corrective side-effect because
  the change is already live: `reject (rework) → active` = **fix-forward**;
  `reject (re-groom) → backlog` = **revert the merged change +
  re-decompose**.

This is the "verify in production" model (observability + reversibility);
there is exactly one merge model (ship-on-green); the risk dial sits at
**admission + reversibility**, not a pre-merge acceptance hold. The
machine-path consent exemption (`### Machine-path exemption — the
Dispatcher`) covers these `admit`/`complete`/`accept` dispositions of
already-filed items; the Dispatcher creates no net-new work-items.

---

## Delta 3 — `### Dispatcher grooming behavior` reconciliation

The existing clause "The Dispatcher MUST refuse to auto-dispatch a
`human-gated` (spec-change) item" is re-expressed: the Dispatcher MUST
refuse to **admit** an item whose effective `admission_policy` is
`manual` until it has been explicitly approved into `ready` — the
`admission_policy` field is the first-class realization of the old
`human-gated` marker. The non-convergence bounce is re-expressed in the
new vocabulary: a non-converging slice **bounces to `backlog`**
(re-decomposition; decision 32's `bounce`), surfaced (escalate-don't-drop),
never infinite-retried. The compose-next clause stands (now ranks by
`rank`).

---

## Delta 4 — `#### list-work-items`: emit flat `lane` + `lane_reason`

`--json` output: each materialized item additionally carries two
**computed flat** keys — **`lane`** (the rendered lane, one of the 7) and
**`lane_reason`** (the rendered reason: `needs-human` / `infra-external`
/ `dependency` / null) — plus the auto-emitted new `WorkItem` fields
(`rank`, `admission_policy`, `acceptance_policy`, `blocked_reason`,
`assignee`, the 7-state `status`). `lane`/`lane_reason` are computed by
the runtime's `lane_of` (consume-don't-recompute, decision 40); the
console reads them directly and retires its `bd ready` re-derivation.

The `--filter` flags track the new lane vocabulary:
- `--filter=ready` — lane == `ready` (stored `ready` AND deps clear).
- `--filter=blocked` — lane == `blocked` (stored `blocked`, OR stored
  `ready` with an open dependency → `blocked:dependency`).
- `--filter=gap-tied` / `freeform` / `closed` / `all` — unchanged.

---

## Delta 5 — `#### next`: rank ordering

The ranking algorithm is re-keyed (decision 39):
1. Identify ready items: lane == `ready` (stored `ready`, `depends_on`
   empty or all-closed).
2. Order by **`rank`** (lexicographic ascending — the sole ordering
   authority), then by `id` as the deterministic tie-break.
3. Apply `--offset` / `--limit`.

The old `Score by priority then gap-tied-ahead-of-freeform then oldest
captured_at` heuristic is retired (decision 12 — `priority` removed). The
`urgency` field is no longer priority-derived (the P0→high mapping is
retired with `priority`); ranked candidates emit `urgency: "medium"` —
the `rank` order is the urgency signal. `action`/`reason`/`work_item_ref`
and the `pagination` block are unchanged.

---

## Delta 6 — `### Open realization choices` → resolved

Both open questions are now resolved by the locked design:
- **`needs-regroom` ledger representation (`:699`)** — RESOLVED: there is
  no separate `needs-regroom` label OR status. `needs-regroom` is a
  **bounce to the `backlog` state** (decision 32 — re-decomposition);
  `defer` is the lighter move back to `pending-approval`. The 7-state
  custom-status encoding (Delta 1) is the ledger representation.
- **groom front-end vs. `capture-work-item` epic-mode** — RESOLVED:
  `groom` is its OWN heavyweight skill (already shipped). 

Rewrite the section to record these resolutions (it stays an H3 — not
tracked by heading-coverage, no registry co-edit for it).

---

## Scenarios (authoring discipline (i)) — `SPECIFICATION/scenarios.md`

Load-bearing behaviors get Gherkin scenarios paired to integration-tier
tests (the existing scenarios.md convention — Dispatcher scenarios are
integration-tier against the `FakeBeadsClient`). New / updated:

1. **NEW `## Scenario: Dispatcher admits the highest-rank ready item up
   to the per-repo WIP cap`** — given N ready items and `wip_cap`, the
   Dispatcher admits in `rank` order until `count(active) == wip_cap`,
   setting `assignee` on each `admit`, and admits no more until a slot
   frees.
2. **NEW `## Scenario: Dispatcher holds a manual-admission item until
   approved`** — an item with effective `admission_policy == manual` is
   NOT admitted until it is approved into `ready`; surfaced, never
   launched. (Replaces the human-gated framing of Scenario 10.)
3. **NEW `## Scenario: complete merges on green into the acceptance
   state`** — `complete` keeps `gh pr merge --rebase --auto` and
   transitions the item to `acceptance` (merged + live), not straight to
   `done`.
4. **NEW `## Scenario: accept confirms post-ship per acceptance_policy`**
   — `ai-then-human` parks the item in `acceptance` until a human
   confirms; `ai-only` accepts autonomously; `reject(rework)` →
   `active` (fix-forward), `reject(re-groom)` → `backlog` (revert).
5. **NEW `## Scenario: list-work-items emits lane and lane_reason`** — a
   stored `ready` item with an open dependency emits `lane: "blocked"`,
   `lane_reason: "dependency"`; a stored `blocked` item emits its stored
   reason; every other state emits `lane: <status>`, `lane_reason: null`.
6. **NEW `## Scenario: next ranks ready items by rank`** — `next` returns
   ready candidates ordered by `rank` then `id`.
7. **NEW `## Scenario: append_work_item registers and lands a custom
   status in two steps`** — a `file` create lands `open` then updates to
   `backlog`; the tenant has the 5 custom statuses registered.
8. **UPDATE Scenario 10/11** — re-express `human-gated` →
   `admission_policy == manual` and `needs-regroom` → bounce-to-`backlog`
   in the scenario text, keeping their bound tests (the test rewrites are
   the implement phase).

Each new scenario gets a `tests/heading-coverage.json` entry (`test:
"TODO"` with a non-empty `reason`) at ratify time; the real integration
test node id is populated when the implement slice binds it.

## heading-coverage co-edit

The shared `heading_coverage` check tracks **only `## ` (H2) headings**.
This change adds exactly **one new H2** (`## Dispatcher admission, WIP
cap, and post-merge acceptance`) to `contracts.md` and **seven new H2**
scenario headings to `scenarios.md` (each `## Scenario: …`). Every one
gets a `tests/heading-coverage.json` row at ratify time (`test: "TODO"`,
non-empty `reason`). All other deltas edit existing H2 sections
(`## Work-item beads-issue mapping`) or H3/H4 subsections
(`#### list-work-items`, `#### next`, `### Dispatcher grooming
behavior`, `### Open realization choices`) — no registry row needed (H2
already registered; H3/H4 not tracked).
