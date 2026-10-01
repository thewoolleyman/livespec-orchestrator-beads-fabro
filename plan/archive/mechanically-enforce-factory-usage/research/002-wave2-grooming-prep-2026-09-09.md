# Wave 2 grooming-prep — verified anchors (2026-09-09)

Input to the maintainer-owned groom of the four backlog carriers (R1, R2, R4,
R5). Every `file:line` below was read from the live repos on 2026-09-09; this
note grounds the eventual slice cuts in real anchors rather than the opening
research's high-level design. It does NOT make the cut — that is the maintainer's
at groom time. Notation: `factoryRunId` = the git-config provenance marker U+27E6
run-id U+27E7 the Dispatcher would inject.

## R1 — hermetic factory-provenance commit gate (`livespec-dev-tooling-pxsr7w`)

Verified anchors (dev-tooling unless noted):
- Canonical commit-refuse hook body + the marker-read pattern:
  `livespec_dev_tooling/install_commit_refuse_hooks.py` ~130-168. The hook already
  reads a declared git-config marker: `sandbox_exempt="$(git config --get
  livespec.sandboxExempt || true)"`, and skips its refuse branch when the marker
  is `true`. `livespec.factoryRunId` follows the identical read pattern.
- Red-Green-Replay product-`.py` scope (the gate reuses this exact vocabulary):
  `livespec_dev_tooling/checks/red_green_replay.py` — `derive_source_prefixes`
  + `is_vendored_path` + `_classify_staged` (imports ~117, scope helper ~161-186).
- Marker injection home (orchestrator): `.claude-plugin/.fabro/workflows/
  implement-work-item/workflow.toml:298` `sandbox_exempt_marker =
  "livespec.sandboxExempt"`, set by a `[[run.prepare.steps]]` block (~422). The
  `factoryRunId` injection is a sibling prepare step here.
- Confirmed genuinely unbuilt: `grep -rl factoryRunId` across dev-tooling and the
  orchestrator scripts returned NOTHING on 2026-09-09.

**Load-bearing design insight the opening research did NOT spell out.** Today's
canonical hook refuses ONLY at the primary checkout — its condition is
`[ "$git_dir" = "$common_dir" ] && [ "$sandbox_exempt" != "true" ]`. A commit in a
HOST WORKTREE passes the hook today. But a host worktree is exactly where the
hand-crank incident happened. So R1's gate is NOT a tweak to the existing
primary-refuse branch; it is a NEW refuse branch that must also fire IN WORKTREES,
gated on the absence of `livespec.factoryRunId`. In a factory sandbox both
`sandboxExempt=true` and `factoryRunId=<id>` are set, so factory commits pass; on a
host worktree neither is set, so staged product `.py` is refused unless a
`Factory-Override` trailer with a reason is present. Groom must keep R1's branch
AND-ed in front of the untouched Red-Green-Replay delegation.

Candidate slices (maintainer owns the cut): (1) Dispatcher injects
`git config livespec.factoryRunId` in the sandbox prepare step; (2) hook refuse
branch reading the marker over the RGR product-`.py` scope, worktree-inclusive;
(3) `Factory-Run-Id` trailer write on a marked commit; (4) `Factory-Override:
<reason>` audited exception + telemetry; (5) hermetic hook tests.

## R2 — warn->fail rollout (`livespec-dev-tooling-xzxrm5`, depends_on pxsr7w)

Playbook is the bd-guard rollout: host-wide mode file, warn-phase OTLP census of
every context the gate WOULD block, sandbox runs fail-mode first via a throwaway
proof dispatch, then flip. No new code anchors beyond R1's hook. Genuinely gated
on R1 landing first (the typed depends_on is set).

## R4 — set-factory-safety valve (`bd-ib-jhn2jw`) — NEEDS A SPEC CLAUSE FIRST

- The `factory_safety` FIELD already shipped (`bd-ib-fv6wse`, closed) and is
  referenced throughout `SPECIFICATION/contracts.md` (367, 2412-2432): an
  INTRINSIC capture-time host-only axis, orthogonal to `admission_policy`.
- The VALVE does not exist: `grep set-factory-safety SPECIFICATION/contracts.md`
  returned nothing on 2026-09-09. The per-lane operator-verb vocabulary lives at
  contracts.md §"Per-state operator verb vocabulary" (2452) / "Per-lane valid
  operator verb sets" (2473-2480); `set-factory-safety` must be ADDED there by a
  spec clause before the impl. This confirms R4's two-phase shape: (1) spec via
  `/livespec:propose-change` + `/livespec:revise`, then (2) the valve impl.
- Impl anchor: `drive.py` config-action path — `is_config_action` /
  `run_config_action` (drive.py:140-141), where `set-admission` / `set-acceptance`
  live; `set-factory-safety:<id>:<reason>` is a new config action beside them.

## R5 — realize driver-dispatch:<id> (`bd-ib-y4mb`) — IMPL-ONLY, no spec work

Correction to the opening research's Wave-2 framing: R5 needs NO propose-change.
`driver-dispatch:<id>` is ALREADY fully specified:
- `SPECIFICATION/contracts.md:2567` `#### driver-dispatch:<id>` (semantics), and
  :2479 lists it as a valid `ready`-lane verb "host-only-refused items only", with
  the design constraint at :2580 ("driver-dispatch to any ready item WOULD require
  a claim mechanism" — so it is scoped to `factory_safety`-non-null host-only
  items, NOT any ready item).
- Impl anchor: `drive.py` action parsing — `_IMPL_PREFIX` (:59),
  `_RESOLVE_BLOCKED_PREFIX` (:60), routed in `run_action` (:125-151). Add a
  `driver-dispatch:` prefix branch: journaled actor + driver-session reference,
  `ready -> active`, scoped to host-only items.
- `bd-ib-y4mb` (adopted as this epic's child) already carries the maintainer's
  2026-07-28 ruling: BUILD the verb, do not delete the spec surface.

## Cross-carrier notes

- R1/R2 land in the `livespec-dev-tooling` tenant; R4/R5 in this tenant; all
  cross-tenant association is PROSE, never a typed cross-tenant depends_on
  (force-factory convention).
- Sequencing unchanged: Wave 2 = R1 -> R2, plus R4 (spec then impl) and R5 (impl)
  and R7 (blocked on driver-claude setup, see the ledger timeline). Wave 3 = R6
  (ladder C) + the R1 fail-mode flip after a clean warn census.
