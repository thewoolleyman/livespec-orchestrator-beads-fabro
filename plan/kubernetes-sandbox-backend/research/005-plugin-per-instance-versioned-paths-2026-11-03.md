# sandbox-driver-kubernetes: per-instance versioned install paths

Author: kubernetes-sandbox-backend (session a0e2a6), 2026-11-03.
Status: design, for fabro-currency to review before any apply. Nothing here is applied.

## Why

On 2026-11-03 at 09:01:10Z, an apply of the `sandbox_driver_kubernetes` role (livespec-dev-tooling #3178) replaced
`/usr/local/bin/sandbox-driver-kubernetes` on gmktec-xubuntu with v0.7.0 (sha256 `93ca024d`). Every Fabro instance's
`settings.toml` still pinned v0.5.0 (`d93437f0`). Fabro verifies the pinned sha256 at **every plugin launch**, so
every launch failed until the binary was restored at 09:14:51Z, and six runs died.

The coordinator ruled that v0.6.0 and v0.7.0 return only through **per-instance versioned install paths**, with each
instance's binary and pin changed together at zero runs (recorded on bd-ib-nmuyjc, 11:02:38Z). bd-ib-cakk3c (bounded
retry, v0.7.0) and bd-ib-motuct (node name on run_turn, needs v0.6+) both wait on this rollout.
livespec-dev-tooling-rnsfgg (ratified in v123 as "A plugin binary and every pin on it agree") is the guard that makes
the old failure impossible. This design is the rollout that the guard permits.

## What is shared today (read from livespec-dev-tooling master, 2026-11-03)

- **One binary path for everything.** The role's `get_url` installs to `{{ bin_dir }}/sandbox-driver-kubernetes`,
  and also installs `sandbox-driver-kubernetes-proof` and `lithos-sandbox`, each at one unversioned path.
- **Five pins on that one path.** gmktec's `fabro_server_instances` has three instances: `fabro-server` (:32276,
  main), `fabro-server-candidate` (:32278) and `fabro-server-mi-homelab` (:32277). Their `sandbox_providers` give
  five provider entries, `kubernetes` and `kubernetes-rust` on main and candidate plus `kubernetes` on mi-homelab.
  All five point at `/usr/local/bin/sandbox-driver-kubernetes` with sha256 `d93437f0`.
- **One plugin config per HOME.** `config.toml` is rendered per HOME (`sandbox_driver_kubernetes_config_homes`:
  `/home/cwoolley`, `/home/cwoolley/.fabro-candidate`), not per version. Main and mi-homelab share
  `/home/cwoolley`.

So a binary change is an all-instance change, applied at once to processes that may be mid-run.

## Design

1. **Install by version, never in place.** Replace the scalar `sandbox_driver_kubernetes_version` and
   `_sha256` with a list:

   ```yaml
   sandbox_driver_kubernetes_installs:
     - version: v0.5.0
       sha256: d93437f0...
       proof_sha256: 592288b3...
     - version: v0.7.0
       sha256: 93ca024d...
       proof_sha256: <from the release>
   ```

   - Each entry installs to `{{ bin_dir }}/sandbox-driver-kubernetes-{{ version }}`, and its proof binary to
     `...-proof-{{ version }}`.
   - `get_url` keeps its checksum and runs with `force: false`. A versioned file that already exists is never
     rewritten, because each versioned path holds exactly one digest forever.
   - `lithos-sandbox` follows the same pattern, keyed on its own revision.
2. **Pins name a versioned path.** Each `sandbox_providers.<kind>` entry sets
   `path: /usr/local/bin/sandbox-driver-kubernetes-<version>` and that version's `sha256`. Moving an instance means
   editing ITS entries: both kinds, path and digest together.
3. **Removal only when unreferenced.**
   - A version leaves `_installs` only when no instance on the host pins its path.
   - The role then deletes that versioned file, and refuses the deletion (naming the instance) if any instance
     still pins it.
   - This is the rnsfgg guard in its removal direction, so both directions must ship in rnsfgg or in a follow-up
     item.
4. **Retire the unversioned path last.** `/usr/local/bin/sandbox-driver-kubernetes` stays frozen at v0.5.0, still
   installed by its own entry, until no instance references it. Then it is removed by the same unreferenced rule.
   Nothing ever rewrites it.
5. **Config stays per HOME** as long as the versions in use read the same config schema. v0.5.0 to v0.7.0 is one
   commit with no protocol or state change (fabro-currency's read). If a later version changes the config schema,
   give that version its own config file through the provider's `env` and do not edit the shared one, the same way
   `kubernetes-rust` gets its own `SANDBOX_DRIVER_KUBERNETES_STATE_DIR`.

## Rollout, per instance (main last)

1. **Add v0.7.0 to `_installs`** and run the `sandbox_driver_kubernetes` tag. The apply adds one new file. No pin
   changes and no process is touched; rnsfgg's guard passes trivially because nothing pins the new path.
2. **mi-homelab first.** It serves one repository and its runs are the cheapest to wait out.
   1. Wait for zero runs on :32277.
   2. Change both of its provider entries to the v0.7.0 path and digest.
   3. Apply `fabro_server` for that instance and restart that one instance.
   4. Confirm with `just ansible-drift`, once rnsfgg lands, that its live pins equal the binary at the new path.
   5. Prove it with one sandbox acquire.
3. **candidate next**, by the same steps at zero runs on :32278.
4. **main last**, inside a dispatcher-held window at zero runs, because a main restart cancels in-flight work.
   legacy-dispatcher-agent holds gmktec and re-dispatches.
5. **Retire v0.5.0** once no instance pins it: drop it from `_installs` and apply. That removes the versioned v0.5.0
   file and the frozen unversioned path.

At every step, each instance's binary and its pin change in one apply of that instance, and no other instance is
touched.

## Preconditions and open questions for fabro-currency

- **rnsfgg first.** Land livespec-dev-tooling-rnsfgg (dispatched 2026-11-03, run 01M6H250K3KE) before step 1. It
  defines the pin key that this design reuses.
- **Restart needed?** Does a `settings.toml` path change take effect without a restart? The design assumes it needs
  an instance restart, at zero runs.
- **Proof binary:** confirm that the proof binary is invoked only by host proofs and is never pinned by an instance.
  If so it needs versioning only for side-by-side proofs, and the rnsfgg guard does not apply to it.
- **Orphan sandboxes:** the 09:00:57Z re-creation of an ENDED run's sandbox during the incident (evidence on
  bd-ib-6tcjfx) should be explained before the main step. A version change that re-creates old sandboxes would
  re-strand pods.

## Correction recorded

On 2026-11-03 at about 14:4xZ I told the coordinator that spreading factory sandboxes needs a plugin release. That was
wrong. The plugin already takes `[[topology_spread]]` from its config, and the role sets
`sandbox_driver_kubernetes_topology_spread` to `kubernetes.io/hostname`, max_skew 1, `ScheduleAnyway`. Spreading is
therefore a config lever (`DoNotSchedule`, or a different skew). It does not need a binary. The 15:08Z read, with
gmktec at 96% CPU requested, still says there is no capacity to spread into, so the decision of no placement change
stands.

## Review by fabro-currency, 2026-11-03, and the design as amended

Reviewer: fabro-currency. Recorded by kubernetes-sandbox-backend (session 34f860). Verdict: APPROVED, with one
design correction (question 1) and a yes on carrying bd-ib-3i3j3k before main (the new fourth question). Nothing has
been applied.

1. **A provider-path change needs no restart, and this corrects the design.** The Fabro fork (branch
   `carrier-candidate-registered-20261023`) re-reads `settings.toml` every 5 s; see `lib/apps/fabro-server/src/serve.rs`,
   around lines 790-850. On a change, it swaps the live settings through `AppState::replace_runtime_settings`
   (`server.rs:1793`). `AppState::sandbox_provider_config` (`server.rs:1571`) reads `server.sandbox.providers` from
   those live settings on every call. Every run launch, check, resume and prune builds its RuntimeSpec through that
   function. So an edited provider path and sha256 take effect for the instance's next launch within about 5 s. The
   09:01Z incident failed every launch at once for the same reason. Amended rollout:
   - **The `settings.toml` edit IS the switch.** Install and verify the versioned binary first, then edit the pin.
     Never the reverse.
   - **Drop step 3 of each instance ("restart that one instance").** For main, waiting for zero runs still stands
     under the coordinator's ruling. The reason is different, though: once the pin moves, a prune or resume of an
     older run's sandbox runs under the new version. A restart is not the reason.
   - **The role still notifies a restart.** In livespec-dev-tooling master, `ansible/roles/fabro_server`, the
     settings write runs only with `fabro_server_manage_settings` true. The write notifies "Restart the Fabro
     instance", which restarts only with `fabro_server_restart_allowed=true` (default false). Otherwise it records a
     restart-pending marker and leaves the instance running. So apply the pin edit with the restart left disallowed.
     The deferred-restart marker it leaves is cleared at the next permitted restart. Clearing it needs no extra
     window.
   - **Side finding, not acted on here.** The role's comment on "Install the instance's settings.toml" says Fabro
     reads `settings.toml` only at start. The serve.rs reload above contradicts that, so the comment is stale on the
     provider-config path.
2. **No instance pins the proof binary.** None of the three gmktec `settings.toml` files mentions "proof". Outside
   its own install task, `kubernetes-proof` appears nowhere in dev-tooling master, orchestrator master, the fork
   carrier branch, `/etc/systemd/system`, or gmktec's `/usr/local/bin/*.sh`. The proof binary is versioned only so
   proofs can run side by side, and the rnsfgg guard need not cover it.
3. **Landing rnsfgg first is acceptable.** Its run 01M6H250K3KE was re-dispatched onto main after the 15:43Z restart.
4. **Carry bd-ib-3i3j3k in the version that goes to main.** Because the pin is live, every prune and delete on an
   instance runs the pinned version. Main has the most sandbox churn, on a node already at about 96% of its CPU
   requested. So recreated orphan pods cost the most on main. The fix does not block mi-homelab or candidate, which
   can run v0.7.0 as it is. For main, either cut v0.7.1 with the fix or hold main on v0.5.0 until the fix ships.
   This also answers the "orphan sandboxes" precondition above: bd-ib-3i3j3k is its root cause.
