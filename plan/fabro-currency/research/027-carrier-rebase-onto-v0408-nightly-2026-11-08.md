# 027 — the carrier rebased onto v0.408.0-nightly.0 (2026-11-08)

Written by `claude:fabro-currency` (session `eaa81d`), a resume of plan epic `bd-ib-6tcjfx`, on
2026-11-08. It records the hand-build of work-item `bd-ib-qx45e6` up to its candidate pin, and
the decisions made on the way. All times are UTC. Gate, build and decision records with run ids
are also on the item's ledger comments.

## The stack

- **Base:** upstream `fabro-sh/fabro` `v0.408.0-nightly.0` (`08ef6b429`, published
  2026-11-05T10:49:59Z). The forge confirmed it as the newest release.
- **Fabro fork branch** `carrier-v0.408.0-nightly.0-20261108`, tip `85071c828`. It holds:
  - the 36 commits of `carrier-candidate-registered-20261023` (`bbe693847`), rebased onto the
    tag with three trivial conflicts;
  - fork PR #36's authored `run_prepare` tests (`a73519096` and `afa0f3cd2`, as `95ef0a8d2`
    and `62754c360`);
  - four fixes the new base needed (next section).
- **Petri fork branch** `fabro-integration-f30a12df-20261108`, tip `ac0b9fb3`: the seven fork
  carries on the `f30a12df` that v0.408 locks. `496e3d171` re-points the carrier's `[patch]`
  at it and changes only the fifteen `petri-*` lock entries.
- **Not in the stack:** the `bd-ib-6tcjfx.1` rider (fail-closed `fabro inspect`). No fix
  commit exists yet, and the coordinator ruled it droppable.

## What the new base broke, and the fixes

1. **rustfmt (`703596e5d`).** The rebase's import-conflict resolutions in `fabro-config`
   (`lib.rs` and `resolve/run.rs`) left lists that the pinned `nightly-2026-04-14` rewraps.
2. **E0432 in `fabro-petri/src/prepare.rs` (`cd0b77338`).**
   - The cause: Petri `a04dae73` ("Remove run.prepare authoring in favor of workflow
     commands") is inside `f30a12df`. It removed `[run.prepare]` and the
     `PREPARE_NODE_PREFIX` export that the re-prepare-on-reacquire carry (`bd-ib-ljw2xg`)
     imported.
   - The fix: the prefix `"run_prepare_"` is now Fabro's own constant. A migrated workflow
     authors its setup under exactly those names (`bd-ib-dpsiwz`), and that item's Definition
     of Done now pins the names for this reason.
   - The tests: the five older resume tests built `[[run.prepare.steps]]`, which the frontend
     now refuses. Their fixture authors nodes instead, and no assertion line changed.
3. **The fabro-server it harness (`85071c828`, test-only).**
   - The failures: Fork gates run 2 failed `dry_run_serve_starts_and_runs_workflow` and
     `cancel_at_human_gate_persists_cancelled_terminal_event`, both "within 5s".
   - The cause: every poll in the harness was bounded by wall clock, through a 5 s
     `time::timeout` or `POLL_ATTEMPTS` (500 × 10 ms). Under the maintainer's 2026-11-03
     ruling that is a test defect.
   - The fix: those polls now wait for the state itself, with no deadline.
   - Left as they were, and tracked: `wait_for_run_status_with_timeout` (Docker tests only),
     the 2 s frame read in `sse.rs`, `FRAME_TIMEOUT` in `petri_stream.rs`, and the 5 s HTTP
     clients in `petri_store.rs`.

## The reachability question, and how it was settled

Carry `bd-ib-6vhgqg` (`2d04300fb` and `4a445c25d`) adds a `run_records::projection` read to
`spawn_scheduler` before every `execute_run`, and both failing tests go through that path. So
the carrier's diff could reach them, and under the same ruling a reachable failure blocks the
merge.

The coordinator first asked for five solo iterations at the tag and at the tip, and for a 120 s
bound. Both contradict the ruling: "a rerun pass is not evidence", "never spend runs comparing a
flaky test across commits", and "longer deadlines are not fixes". It withdrew both.

The evidence instead was Fork gates run 3 itself. With deadline-free waits, a pass means the
behaviour happened. A real regression would have shown as a hang, which nextest's `ci` profile
names in a SLOW line after 30 s.

Result: 4434/4434 passed and zero SLOW lines, so both tests finished in under 30 s. No
per-test durations exist, because the job runs `--status-level slow` and uploads no JUnit.

## Gates and build

| Fork gates run | Head | Format | Clippy | Test |
| --- | --- | --- | --- | --- |
| 42449259657 | `496e3d171` | red | red (E0432) | red (E0432) |
| 42453480164 | `cd0b77338` | green | green | red, 2 timing failures, then cancelled at 3374/4434 |
| 42457891271 | `85071c828` | green | green | green, 4434/4434 |

The one carrier-build is run `42461605229` on fabro-k3s:

- `fabro --version` prints `fabro 0.408.0-nightly.0 (85071c8 2026-11-08)`;
- SHA256 `e5c98af4bd1db97253cb7a51bef0a61f3a37e0d05341183a07bcdaeeb5d04d04`, with
  `SHA256SUMS` and `BUILD_INFO` verified;
- it is staged on vps at `/home/ubuntu/.local/state/fabro-web-prod/v0408-85071c828/`.

## Rollout order (coordinator sequencing ruling, 2026-11-08)

v0.408 refuses `[run.prepare]`, so a canary on the candidate means nothing until
`bd-ib-dpsiwz`'s migrated workflow exists.

1. `bd-ib-dpsiwz` lands and releases. Its workflow must also run on petri's current
   `bbe693847`, which its Definition of Done now asserts.
2. The release rolls to the gmktec launch clone only.
3. livespec-dev-tooling PR #3775 merges and applies. It moves `fabro-server-candidate`
   (:32278) alone to `85071c828`, and is held as a draft under the dev-tooling merge hold.
4. One fresh candidate dispatch whose rendered graph contains a `run_prepare_<N>` node. That is
   the shared canary event.
5. One item on petri, then petri and mi-homelab move.

The repo's merge automation arms auto-merge on push. Only a draft holds a pull request against
that.

## factory-integration is the legacy line

Both `bd-ib-qx45e6` and the plan's own Definition of Done assertion 1 require the serving
commit to be reachable from `origin/factory-integration`. Measured on 2026-11-08:

- FI's tip is `8b82e99bb`. Its merge base with the new carrier is `5c90ad2e0`
  (0.389.0-nightly.0).
- `git cherry` finds 36 FI commits with no equivalent in the carrier. They include the legacy
  ACP Wave A/B/C fixes, `fallback_chain` and the 0.254-line OTLP carries.
- FI's `8869e88` is the legacy 0.254 client that the dev host's PATH and its fabro-server units
  run.

The coordinator ruled option (a) at 11:31Z, on conditions:

1. Only after `bd-ib-qx45e6` closes.
2. Archive first: push `legacy/factory-integration-0254` at `8b82e99bb` and verify it.
3. Merge the carrier into FI with the carrier's tree, as a merge commit, never a force-push.
4. Repoint every legacy rebuild path to the archive in the same change.
5. Watch the fork-gates run that the merge fires.

The fleet-scope survey for condition 4 found:

- nothing that builds from FI by name;
- the vps units pin the staged binary `v0254-8869e88/fabro`;
- two prose references describe FI as the legacy build source. They are the
  `fabro_server` role's missing-binary `fail_msg` in livespec-dev-tooling and the header
  comment of `dev-tooling/install-ci-fabro.sh` here. Both get repointed to the archive ref in
  the merge's change;
- `fork-gates.yml` triggers on FI pushes in both lineages, so the merge fires one gates run.

## Side findings, routed elsewhere

- **Flattened catch-up commit, routed to publish-draft-green-work-loss.** A resume of a stale
  branch produced a `fix_commit_settle` checkpoint (`2f6b29844`, one parent, 666 files) that
  flattened four days of master. That failed `bd-ib-n4kj4y`'s janitor.
- **No release-to-fresh valve, routed to factory-run-work-preservation.** Routing seeds from
  the first `needs-human/<run>` ref it finds, and reads fresh only when preserved work is
  confirmed absent. `bd-ib-n4kj4y` reached a fresh route only after both of its `needs-human`
  refs were archived under `preserve/bd-ib-n4kj4y-*`. That was the coordinator's 4th recorded
  exception to moving refs by hand.
- **The jpiesc host leg.** A run relayed as seeded journaled `route=resume`, so it could carry
  no proof. Check the journal's own `recovery-route` record before taking a host capture.
