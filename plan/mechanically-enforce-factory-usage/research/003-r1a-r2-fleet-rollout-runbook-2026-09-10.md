# R1a/R2 fleet-rollout runbook — factory-provenance commit gate (2026-09-10)

Drafted at the maintainer's request ("draft runbook, then pause") after Wave 2
shepherding closed. This note plans the warn→fail rollout of the hermetic
factory-provenance commit gate across the fleet and stops short of any action
that mutates the shared hook body. Every `file:line` was verified on the live
repos on 2026-09-10. It does NOT authorize the rollout — the maintainer owns
the go/no-go at the pause recorded on epic `bd-ib-btr5do`.

The work items this sequences:
- **R1a** `livespec-dev-tooling-pxsr7w` — the dev-tooling hook refuse branch
  (the body change). `status: backlog`, zero comments, `dependent_count: 1`.
- **R2** `livespec-dev-tooling-xzxrm5` — the warn→fail rollout + fleet installer
  re-run coordination. `status: backlog`, zero comments, typed `blocks` edge:
  pxsr7w blocks xzxrm5 (so R1a lands first).

Precondition already met: **R1b `bd-ib-dosmpm` landed** (PR #2408, closed green)
— the Dispatcher now injects `git config livespec.factoryRunId <dispatch_id>`
into every sandbox (`commands/_dispatcher_factory_provenance.py` on master). So
the marker the hook reads is present fleet-wide before the hook begins reading
it.

## The blast-radius mechanism, stated precisely

The fear in the handoff ("landing pxsr7w reddens EVERY fleet primary") is real
but is NOT a simultaneous fleet break. Three verified facts reshape it:

1. **The check is strict byte-identity against a wheel-carried constant.**
   `livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py`
   imports `install_commit_refuse_hooks.CANONICAL_HOOK_BODY` (`:117`) and fails
   when any of `.git/hooks/{pre-commit,pre-push,commit-msg}` differs by a byte
   (`_HOOK_NAMES` at `:225`; missing / non-executable / byte-different all fail
   equally, `contracts.md:204`). Changing the constant therefore makes a
   primary's installed hooks non-identical **to the constant that primary is
   now running**.

2. **Consumers adopt the constant only on a per-repo pin bump — pickup is NOT
   automatic.** Each consumer pins `livespec-dev-tooling` to a git **tag** in
   `[tool.uv.sources]` (orchestrator `pyproject.toml:67` → `v1.70.0`; livespec
   `:73` → `v1.69.4`; overseer `:60` → `v1.64.1`; console `:49` → `v1.83.6`;
   driver-claude `:39` → `v1.69.4`). `livespec_dev_tooling` is NOT vendored
   (`.vendor.jsonc` carries only `returns`/`structlog`/`typing_extensions`/
   `livespec_runtime`/`livespec_spec_clauses`), so there is no second on-disk
   body. A consumer sees the new body only after it (a) bumps the tag,
   (b) `uv sync --all-groups` re-resolves `uv.lock`, and (c) re-runs the
   installer. A repo still on its old pin keeps old constant + old hooks and
   **passes**.

3. **CI is self-consistent; the red surface is the DEVELOPER/SESSION PRIMARY
   CHECKOUT.** A fresh CI checkout installs hooks from the same wheel it then
   checks against, so CI on a pin-bumped branch is green as long as bootstrap
   runs first. The window that actually reddens is a long-lived primary checkout
   (a dev box, a running session) whose wheel was upgraded by a pin bump +
   `uv sync` but whose `.git/hooks/` was not re-installed. `.git/hooks/` is
   untracked, so the re-install is a LOCAL action per primary, never a committed
   diff.

**Consequence:** the rollout is sequenceable repo-by-repo. The "lockstep" the
handoff wanted is really one rule — *pair every dev-tooling pin bump that crosses
the body-changing release with an installer re-run on that primary, before the
next commit there.* The one way to turn this into a fleet-wide break is an
automated pin-bump that advances many repos past the release without re-running
their installers; see "Open decisions" #4.

## Fleet-primary set (who is subject)

Roster: `livespec/.livespec-fleet-manifest.jsonc` — `fleet` (10) + `adopters`.
Empirically byte-identical canonical body installed (sha256 `1ebaebfe2271…`,
verified locally): **livespec, livespec-dev-tooling, livespec-driver-claude,
livespec-orchestrator-beads-fabro, livespec-overseer,
livespec-console-beads-fabro** — the six that redden the moment they adopt the
new release.

Same manifest class but NOT verifiable from this host (verify on their own
hosts before flipping): **livespec-driver-codex, livespec-driver-pi,
livespec-orchestrator-git-jsonl, livespec-runtime**.

NOT subject (substantiated): **openbrain** (lefttook stub, no commit-refuse
module in its vendored partial tree) and **homelab** (a distinct adopter-local
bash hook, not the wheel-carried canonical string). Neither is byte-identity
bound to the constant — do not re-install on them.

## The precedent to mirror: the bd-guard warn→fail playbook

R2's own description names "the bd-guard rollout." The authoritative artifact is
`bd-guard/README.md` + `bd-guard/bd-guard.sh`:
- **Host-wide mode file, env→file→default(warn) precedence** — `bd-guard.sh:109-126`.
  Mode file `/usr/local/etc/livespec-bd-guard.mode` (override
  `LIVESPEC_BD_GUARD_MODE_FILE`), env `LIVESPEC_BD_GUARD_MODE`; any non-`fail`
  value resolves to warn, so a misconfig can never brick the tool. Load-bearing:
  `with-livespec-env.sh` scrubs the environment, so an exported env var never
  reaches real callers — **the file is the switch that takes effect**
  (`README.md:233-254`; flip = `echo fail | sudo tee <mode-file>`, `:244`).
- **Warn-phase OTLP census** — one span per invocation, default-on + fail-open,
  `service.name=bd-guard`, emitter `bd-guard/bd-guard-emit.py`, endpoint
  `LIVESPEC_BD_GUARD_OTLP_ENDPOINT` default `http://127.0.0.1:4319/v1/traces`.
  A would-block context is observable as a span carrying the guard decision.
- **Throwaway proof harness** — `bd-guard/test/run-*-candidate-tests.sh` +
  `preflight-probe.sh` (recipe `just check-bd-guard-candidate`): `mktemp`
  throwaway repos with temp `HOME`/`XDG_CONFIG_HOME`, never a real tenant, prove
  warn/fail end-to-end before any host flip.
- **"In force" verification, not exit status** —
  `livespec-driver-claude/dev-tooling/bin/verify_guard_rollout.py` reads the
  install RECORD and replays a committed regression corpus through the body the
  install path actually carries ("merged to master is not in force"). Mirror
  this to confirm each primary re-installed.

## Rollout sequence (warn-first, fail-last)

**Phase 0 — land R1a (pxsr7w) in dev-tooling, warn-default.**
Deliverable per pxsr7w's acceptance criteria: a new refuse branch in
`CANONICAL_HOOK_BODY` that (1) reads `git config livespec.factoryRunId` for a
commit staging product `.py` (scope = `config.derive_source_prefixes`),
(2) fires in worktrees, not only at the primary (today's hook only refuses when
`git_dir == common_dir`), (3) honors a host-wide mode file defaulting to **warn**
(emit a record, do not refuse), (4) exempts a non-empty `Factory-Override:
<reason>` trailer as an audited exception, (5) writes a `Factory-Run-Id` trailer
when the marker is present. AND-ed in front of the untouched Red-Green-Replay
delegation. Ships with hermetic hook tests. Dispatch through the factory like
every other child (this plan is subject to its own rule). On merge, cut the
dev-tooling release tag and re-run `just install-commit-refuse-hooks` on
dev-tooling's own primary (the only repo whose pin is implicitly the source).

**Phase 1 — warn-phase census, fleet-wide.**
Bump each of the six local primaries' dev-tooling pin to the Phase-0 release,
`uv sync`, and **re-run the installer on that primary in the same step**. With
the mode file at its `warn` default, commits are never refused; the gate emits
an OTLP census span for every commit it WOULD block. Let this run across normal
fleet activity. Read the census in Honeycomb and classify every would-block
context: each must be either (a) a genuine hand-crank that SHOULD route through
the factory (the behavior we want to stop), or (b) a legitimate host commit that
needs a `Factory-Override: <reason>` — if (b) is common, the scope or the
override ergonomics need revisiting before any flip.

**Phase 2 — throwaway proof in fail-mode.**
Before flipping any real host, prove fail-mode end-to-end on a `mktemp` throwaway
repo (mirror `check-bd-guard-candidate`): a commit carrying both
`livespec.sandboxExempt=true` and `livespec.factoryRunId=<id>` (the factory
sandbox shape) passes; a host commit missing provenance is refused; a
`Factory-Override: <reason>` commit passes and is recorded. Never touch a real
tenant or `/usr/local` in this phase.

**Phase 3 — flip to fail, once the census is clean.**
`echo fail | sudo tee /usr/local/etc/livespec-factory-gate.mode` (name TBD, see
Open decisions #1). Confirm each of the six local primaries is "in force" via the
record-replay verifier pattern, NOT exit status. Then verify the four
non-local fleet members on their own hosts (driver-codex, driver-pi,
orchestrator-git-jsonl, runtime) are re-installed before relying on the flip
there. Leave openbrain/homelab alone.

## Installer re-run recipe (the per-primary fix)

`just install-commit-refuse-hooks` → `uv run python -m
livespec_dev_tooling.install_commit_refuse_hooks` (dev-tooling `justfile:134-135`):
idempotent, worktree-safe (resolves `git rev-parse --git-common-dir`), writes all
three hooks armed. `just bootstrap` also re-syncs them (it runs
`livespec_dev_tooling.fleet.local_reconcile`, whose obligation rows include the
commit-refuse hooks — `justfile:122-123`, `contracts.md:541`). Full per-consumer
sequence: bump tag in `[tool.uv.sources]` → `uv sync --all-groups` →
`just install-commit-refuse-hooks` (or `just bootstrap`).

## Open decisions for the maintainer (at the pause)

1. **Mode-file path + env-var names.** Proposed, mirroring bd-guard:
   `/usr/local/etc/livespec-factory-gate.mode`, `LIVESPEC_FACTORY_GATE_MODE`,
   `LIVESPEC_FACTORY_GATE_MODE_FILE`; default warn; any non-`fail` → warn. Confirm
   the names (they become a host-mutation surface under `sudo`).
2. **Census exit criteria.** Fixed warn-phase duration vs. a would-block-volume
   threshold vs. "clean for N days across the six primaries" — pick the bar that
   ends warn phase.
3. **Factory-Override audit.** Is the OTLP span sufficient provenance for an
   override, or does an override also need a ledger/record trail?
4. **Automated pin-bump interaction.** Does the release-dispatch / bump-pin shim
   machinery (`contracts.md` §"Shared code sync — livespec-dev-tooling") advance
   consumer pins automatically? If so, the body-changing release must either be
   held from auto-bump until Phase 1 is deliberately driven, or the auto-bump
   must carry the installer re-run — otherwise #4 is the one path to a
   simultaneous fleet break. This is the single highest-risk coupling; resolve it
   before Phase 1.
5. **Remote fleet members.** Who re-installs on the hosts carrying
   driver-codex, driver-pi, orchestrator-git-jsonl, runtime, and when, relative
   to the flip.

## Scope boundary

This is R2's plan, not its implementation. No mode file is created, no pin is
bumped, no installer is re-run, and pxsr7w is NOT dispatched by authoring this
note. The plan stays live with `next_action: human` until the maintainer
authorizes Phase 0.
