# livespec dark-factory orchestrator image (Beads/Dolt + Fabro, Docker-in-Docker)

Step 1 of the W7 orchestrator-convergence epic (`livespec-impl-beads-8bc`). This
directory builds the **production orchestrator container**: a privileged image
running an *inner* Docker daemon (Docker-in-Docker) on which Fabro spawns its
sandboxes, fully decoupled from the host daemon. It carries the dispatcher's
host-level runtime (`fabro`, `bd`, `dolt`, `gh`, `mise`, `uv`, `git`, Python,
and `libatomic1` for Pyright's Node runtime) and a
supervisor entrypoint that brings up dockerd + a headless fabro server, then
hands off to the dispatcher.

The recipe is derived from the step-0 DinD spike
(`../archive/research/w7-orchestrator-convergence/dind-spike.md`) — read it for the
constraint rationale. The image is **secret-free by construction**; every
credential is injected at `docker run` time.

## Contents

| File | Purpose |
|---|---|
| `Dockerfile` | `ubuntu:24.04` base (glibc 2.39 — the fabro v0.254.0 hard floor) + inner `docker.io` + content-pinned `bd` v1.0.5 / `dolt` v2.1.4 + `uv` + `gh` + `mise` + `libatomic1` + the COPYed pinned `fabro` binary; `VOLUME /var/lib/docker`; `EXPOSE 32276`. |
| `orchestrator-entrypoint.sh` | Supervisor: start dockerd → wait for socket → provision headless fabro (gh auth with a minted App token + hand-written settings with the native GitHub App integration + dev-token server credentials, listening on `0.0.0.0:32276`) → exec the dispatcher (or a passed command). |
| `build-and-verify.sh` | Stages the fabro binary, builds the image, runs the privileged container with an ext4-backed volume + injected secrets, and runs tier-1 verification. |
| `tier2-dispatch-proof.sh` | Runs the W7 Tier-2 proof: one explicit shadow dispatch from inside the container against a tiny ready item, with redacted logs and inner-daemon evidence. **Bind-mounts the host impl-beads checkout** — it is a proof runner, not the real-work substrate. |
| `real-work-dispatch.sh` | The W7 step-5 **real-work substrate**: dispatches one ready work-item with **no host checkout bind-mount**. It fresh-`git clone`s impl-beads (dispatcher code + the `.fabro/workflows` graph) *and* the dispatch target *inside* the container, `uv sync`s the dispatcher clone, regenerates the gitignored `.beads/metadata.json` (server-stable `project_id`), and points `dispatcher.py loop --repo` at the in-container target clone. The only host coupling is the `-e` secret set. |
| `fabro` | The pinned fabro binary, fetched at build time from `~/.fabro/bin/fabro`. **Gitignored — never committed** (111MB blob; the version is pinned in the Dockerfile's `FABRO_VERSION` for documentation). |

## Hard constraints (proven by the spike + this build)

- **Base must be `ubuntu:24.04` (glibc ≥ 2.39).** fabro v0.254.0 links
  `GLIBC_2.39`; `debian:12` (glibc 2.36) silently passes the dockerd checks then
  fails the moment fabro is invoked, and Alpine/musl won't run it at all.
- **`--privileged` is required.** The inner dockerd needs cgroup/device/mount
  capabilities to run nested. There is no unprivileged-DinD path in scope.
- **`/var/lib/docker` must be on a non-overlay (ext4) filesystem.** A privileged
  container's rootfs is itself an overlay mount; if the inner graph store lives
  there, the inner daemon silently degrades `overlay2` → `vfs` (slow, no
  hardlinks). Back `/var/lib/docker` with an ext4 docker volume or bind. The
  `VOLUME /var/lib/docker` declaration is load-bearing.
- **DinD, not DooD.** No host docker socket is mounted; the only socket in the
  container is the inner dockerd's, so Fabro targets the inner daemon by
  construction and never reaches the host daemon.

## Build + verify

Run on the host as `ubuntu` (Docker access) **under the 1Password env wrapper**
so the injected secrets are present:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/build-and-verify.sh
```

This stages the fabro binary, builds `livespec-orchestrator:dev`, runs a
privileged container with an ext4-backed `/var/lib/docker` volume + the
host-loopback web-UI port, and asserts: inner storage driver is overlay-based
(not vfs), `fabro version`/`fabro doctor` run with the server reachable + GitHub
configured, the web UI answers on the published port, and an ephemeral
in-container Dolt + `bd` round-trip succeeds. All probe output is redacted /
status-only; no secret is printed. The container + volume + staged binary are
cleaned up on exit.

## Tier-2 dispatch proof

After Tier 1 is green, `tier2-dispatch-proof.sh` runs the next W7 proof: one
explicit `dispatcher.py loop --mode shadow --item <id>` invocation from inside
the container. It uses the same entrypoint path as production, proves the inner
Docker daemon is the only daemon available to Fabro, captures a redacted
dispatcher journal tail, and leaves automatic item closure disabled with
`--no-close-on-merge`.

Preflight:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --preflight
```

Run against a deliberately tiny ready item:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/tier2-dispatch-proof.sh --run --item <tiny-ready-item>
```

See `archive/research/w7-orchestrator-convergence/tier2-dispatch-proof.md` for the
evidence checklist and Codex/runtime classification.

When `TIER2_USE_HOST_NETWORK=1` (the default for that helper), the helper runs
Fabro on `32281` unless `FABRO_PORT` is explicitly set. This avoids colliding
with a maintainer's normal host Fabro server on `32276`.

## e2e-repo reaper (orphaned `livespec-e2e-*` cleanup)

`reap-e2e-repos.sh` is the W7 mechanical fail-safe that sweeps orphaned
throwaway GitHub repos (`livespec-e2e-*`) left behind by dark-factory
acceptance runs in the disposable `livespec-e2e` org. It is **org- and
name-scoped by construction**, **age-gated** so an in-progress run's repo is
never reaped, and its deletes **retry with backoff** for the GitHub
create-on-disk race (`HTTP 403 … done being created on disk`) and treat an
already-gone repo as success. It reads `LIVESPEC_E2E_GITHUB_TOKEN` by byte
count only and never prints a secret.

Preview (deletes nothing):

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/reap-e2e-repos.sh --dry-run
```

Real reap (default 120-minute age gate; `--force-all` deletes regardless of
age):

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  bash orchestrator-image/reap-e2e-repos.sh
```

**Run it only at boundaries — session-start, post-confirmed-merge, deliberate
teardown, or as a scheduled sweep — never mid-dispatch.** See
`archive/research/w7-orchestrator-convergence/e2e-repo-reaper.md` for the full safety
model and validation evidence.

## Real-work substrate (production)

For routine cross-repo work the Dispatcher runs on the **real-work substrate**:
it mounts **no host checkout**. Every git working tree the Dispatcher needs is
fresh-`git clone`d from GitHub *inside* the container, so the only host coupling
is the explicit `-e` secret set. Use the `real-work-dispatch.sh` helper (wired
as `just w7-real-work-dispatch`), which clones impl-beads (the dispatcher code +
the `.fabro/workflows/implement-work-item/` graph) and the dispatch target,
`uv sync`s the dispatcher clone, regenerates the gitignored
`.beads/metadata.json` in the target clone (the `project_id` is server-stable,
so the regenerated value is identical), and dispatches one ready item:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- \
  just w7-real-work-dispatch -- --target-repo <repo-name> --item <id> --run
```

Under the hood the helper runs the container with **no `-v <host-checkout>`
bind-mount**, only the substrate volume + the injected secrets, then clones
fresh and points the Dispatcher at the clones:

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- docker run -d \
  --name livespec-orchestrator \
  --privileged \
  --cgroupns=host \                                  # nested resource-limited Fabro sandboxes on cgroup v2
  -v livespec-orch-varlib:/var/lib/docker \          # ext4-backed inner graph store (NOT host checkout state)
  -p 127.0.0.1:32276:32276 \                         # web UI / control plane, HOST LOOPBACK ONLY
  --network host \                                   # to reach the EXTERNAL family-tenant Dolt (127.0.0.1:3307)
  -e GITHUB_APP_ID \                                 # GitHub App id (token mint; clone/push/PR)
  -e GITHUB_PRIVATE_KEY \                            # GitHub App private key PEM (token mint)
  -e ANTHROPIC_API_KEY_LIVESPEC_E2E \                # fabro LLM provider key
  -e CLAUDE_CODE_OAUTH_TOKEN \                       # model auth the dispatcher projects per-dispatch
  -e BEADS_DOLT_PASSWORD_<target-tenant> \           # external tenant Dolt password (tenant DB == target repo)
  -e BEADS_DOLT_PASSWORD="$BEADS_DOLT_PASSWORD_<target-tenant>" \
  -e HONEYCOMB_INGEST_KEY_LIVESPEC \                 # telemetry egress key
  livespec-orchestrator:dev \
  sleep infinity
# then, INSIDE the container (the helper does this for you):
#   git clone https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git /workspace/livespec-orchestrator-beads-fabro
#   (cd /workspace/livespec-orchestrator-beads-fabro && uv sync --all-groups)
#   git clone https://github.com/<org>/<target>.git /workspace/dispatch-target
#   regenerate /workspace/dispatch-target/.beads/metadata.json  (bd init --server --external)
#   python3 /workspace/livespec-orchestrator-beads-fabro/.claude-plugin/scripts/bin/dispatcher.py \
#     loop --repo /workspace/dispatch-target --budget 1 --mode autonomous --item <id>
```

There is **no read-write host checkout to refresh**: the Dispatcher's post-merge
primary refresh and the post-merge janitor worktree both operate on the
in-container *target clone* (`/workspace/dispatch-target`), which lives under
`/workspace` — not `/tmp` — so the janitor worktree at
`<target-clone>/worktrees/janitor-<id>` is measured by coverage (the family
pyproject's `[tool.coverage.run]` omit excludes `/tmp/*`). The clone origins are
**token-free URLs**; the container's `gh auth setup-git` supplies the credential
out of band, so no token-bearing URL is ever printed or stored.

> The legacy **bind-mount** invocation (`-v /data/projects/livespec-orchestrator-beads-fabro:
> /workspace/livespec-orchestrator-beads-fabro` + `--repo` pointed at it) survives only in the
> Tier-2 *proof* runner (`tier2-dispatch-proof.sh`). It is a proof harness, not
> the production substrate; real work runs on the fresh-clone path above.

> **`--network host` vs `-p`.** If you use `--network host` (to reach the
> external family-tenant Dolt on `127.0.0.1:3307`), the `-p` publish is ignored
> and the fabro web UI is reachable directly on the host's `127.0.0.1:32276`
> (the entrypoint binds `0.0.0.0:32276` inside the container; under host
> networking that is the host's all-interfaces bind — restrict with a firewall
> or prefer a bridge network + explicit route to the Dolt server if you do not
> want the UI on non-loopback interfaces). For a pure-bridge run, drop
> `--network host` and publish only `-p 127.0.0.1:32276:32276`.

### Injectable externals (all runtime-injected; none baked into the image)

| Env var | Purpose | Used by |
|---|---|---|
| `GITHUB_APP_ID` + `GITHUB_PRIVATE_KEY` | the GitHub App credential (livespec-pr-bot for the fleet; adopters bring their own App), injected by the dispatch TARGET's credential_wrapper on the host and forwarded in. The SOLE GitHub credential source — there is NO fleet-PAT fallback (fail-closed per the github-app-auth design). The entrypoint mints an installation token to `gh auth login` the container (which also authenticates the in-container fresh clones via the `gh` git credential helper; clone origin URLs stay token-free); the Dispatcher's caching provider re-mints before EVERY subprocess so the ~76-minute merge-poll and any >1-hour operation survive token expiry | entrypoint + dispatcher + in-container clones |
| `GITHUB_APP_INSTALLATION_ID` / `GITHUB_API_URL` | optional: pin the App installation (multi-install Apps) / override the API root (GitHub Enterprise) | entrypoint + dispatcher |
| `GH_TOKEN` | conventional GitHub token name the Dispatcher populates with freshly minted installation tokens — refreshed per subprocess in its own env and projected into the Fabro sandbox env table so the in-sandbox PR node can run `gh pr create`; never injected at container launch (`gh auth login --with-token` refuses to store credentials when `GH_TOKEN` is already set, and a launch-time value would expire mid-run) | dispatcher / sandbox PR node |
| `ANTHROPIC_API_KEY_LIVESPEC_E2E` | fabro LLM-provider API key (name overridable via `FABRO_LLM_API_KEY_ENV`; exported as `ANTHROPIC_API_KEY` into the fabro server's env) | fabro server |
| `CLAUDE_CODE_OAUTH_TOKEN` | model auth the dispatcher projects into each sandbox per-dispatch (run-scoped overlay) | dispatcher |
| `BEADS_DOLT_PASSWORD_<tenant>` | external family-tenant Dolt password (tenant DB == repo name) | dispatcher / `bd` |
| `BEADS_DOLT_PASSWORD` | generic password name consumed by `bd`; set from the tenant-scoped variable at `docker run` time | `bd` |
| `HONEYCOMB_INGEST_KEY_LIVESPEC` | OTel/Honeycomb telemetry egress key | dispatcher |
| `FABRO_PORT` | control-plane / web-UI port (default `32276`) | entrypoint |
| `FABRO_SKIP_LLM` | set non-empty to provision GitHub only (no LLM) | entrypoint |
| `ORCHESTRATOR_SKIP_FABRO` | set non-empty to bring up dockerd only (skip fabro provisioning) | entrypoint |

The **external** family-tenant ledger (the production beads/Dolt store) is *not*
run inside the container — it is reached as an endpoint (`127.0.0.1:3307`, per
the repo's committed `.beads/config.yaml`). The image also ships `dolt` for an
*ephemeral / scratch* in-container ledger (the spike's Goal-5 pattern), which is
a separate, optional substrate used by tier-1 verification — not the family
tenant.

## Observing the dark factory (Fabro web UI)

Fabro serves a web UI from its server on the control-plane port (default
`32276`). It lets a human watch runs, attach to a parked human-gate
(`fabro attach <run-id>`), and inspect the orchestrator's activity from a
browser.

- **URL / port.** `http://127.0.0.1:32276` (the `[server.web]` URL; port set by
  `[server.listen] address`). The entrypoint binds `0.0.0.0:32276` *inside the
  container* so a published port is reachable, and `EXPOSE 32276` documents it.
- **Auth (dev-token).** The control plane is protected by fabro's `dev-token`
  auth. The token is a **secret** — anyone holding it controls the orchestrator
  (GitHub + model creds, dispatch power) — so transfer it over a private channel
  only and never commit it or paste it into a shared log.
  - **Where the token lives / how to retrieve it.** It is stored in fabro's CLI
    auth state at `~/.fabro/auth.json`, under `servers["<server-url>"].token`
    (with sibling keys `kind` = `dev-token` and `logged_in_at`). On the host:

    ```bash
    jq -r '.servers["http://127.0.0.1:32276"].token' ~/.fabro/auth.json
    ```

    For the containerized orchestrator the entrypoint's hand-provisioning
    generates it; retrieve it from the running container the same way, e.g.
    `docker exec <name> jq -r '.servers["http://127.0.0.1:32276"].token' /root/.fabro/auth.json`
    (the server side also persists it under `~/.fabro/storage/`). Note:
    `fabro server start` prints `Auth: dev-token` but does **not** print the
    token value.
  - **Logging a browser in.** `fabro auth login --no-browser` prints an
    `http://127.0.0.1:32276/auth/cli/start?…` PKCE URL to open in a browser. Its
    redirect target is a localhost callback, so it completes cleanly when the
    browser and the server share a host (local use); for a pure SSH-tunnel setup,
    authenticate the UI with the dev-token value retrieved above.
- **Remote access = SSH tunnel, NOT a 0.0.0.0 host bind.** The host publish is
  loopback-only (`-p 127.0.0.1:32276:32276`) by default, so the control plane is
  **not** network-exposed. To view it from your laptop, tunnel over SSH:

  ```bash
  ssh -L 32276:127.0.0.1:32276 <orchestrator-host>
  # then open http://127.0.0.1:32276 in your local browser
  ```

- **Security posture (read this).** The fabro web UI is a **credential-bearing
  control plane**: the server it fronts holds the GitHub token and the model
  API key, and can launch sandboxed runs that clone/push/PR against the family
  repos. Exposing it on a non-loopback interface would hand anyone who can reach
  the port (subject only to dev-token auth) control of those credentials and the
  ability to dispatch work. **Bind the host port to loopback only** (the default
  here) and reach it via SSH tunnel; never `-p 0.0.0.0:32276:32276` on a
  reachable host.

## Secret hygiene

- The image contains **no secret** — no token, key, or password is baked into
  the Dockerfile, the entrypoint, or any committed file. Every credential is
  injected at `docker run` via `-e VAR` (docker forwards the value from the
  invoking process's env; under the 1Password wrapper that value never lands in
  a file or a log).
- Tokens flow into tools via **stdin / env only**; the entrypoint never `echo`es
  a secret and never prints `git remote -v`, env, or token-bearing URLs.
- The staged `fabro` binary is gitignored and never committed.
