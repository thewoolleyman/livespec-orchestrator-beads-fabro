# livespec dark-factory orchestrator image (Beads/Dolt + Fabro, Docker-in-Docker)

Step 1 of the W7 orchestrator-convergence epic (`livespec-impl-beads-8bc`). This
directory builds the **production orchestrator container**: a privileged image
running an *inner* Docker daemon (Docker-in-Docker) on which Fabro spawns its
sandboxes, fully decoupled from the host daemon. It carries the dispatcher's
host-level runtime (`fabro`, `bd`, `dolt`, `gh`, `mise`, `uv`, `git`, Python) and a
supervisor entrypoint that brings up dockerd + a headless fabro server, then
hands off to the dispatcher.

The recipe is derived from the step-0 DinD spike
(`../research/w7-orchestrator-convergence/dind-spike.md`) — read it for the
constraint rationale. The image is **secret-free by construction**; every
credential is injected at `docker run` time.

## Contents

| File | Purpose |
|---|---|
| `Dockerfile` | `ubuntu:24.04` base (glibc 2.39 — the fabro v0.254.0 hard floor) + inner `docker.io` + content-pinned `bd` v1.0.5 / `dolt` v2.1.4 + `uv` + `gh` + `mise` + the COPYed pinned `fabro` binary; `VOLUME /var/lib/docker`; `EXPOSE 32276`. |
| `orchestrator-entrypoint.sh` | Supervisor: start dockerd → wait for socket → provision headless fabro (gh auth + `fabro install --non-interactive` + bind `0.0.0.0:32276`) → exec the dispatcher (or a passed command). |
| `build-and-verify.sh` | Stages the fabro binary, builds the image, runs the privileged container with an ext4-backed volume + injected secrets, and runs tier-1 verification. |
| `tier2-dispatch-proof.sh` | Runs the W7 Tier-2 proof: one explicit shadow dispatch from inside the container against a tiny ready item, with redacted logs and inner-daemon evidence. |
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

See `research/w7-orchestrator-convergence/tier2-dispatch-proof.md` for the
evidence checklist and Codex/runtime classification.

When `TIER2_USE_HOST_NETWORK=1` (the default for that helper), the helper runs
Fabro on `32281` unless `FABRO_PORT` is explicitly set. This avoids colliding
with a maintainer's normal host Fabro server on `32276`.

## `docker run` invocation (production)

The dispatcher needs the impl-beads checkout mounted and the externals injected.
Always launch under the 1Password wrapper so the secret env values are present
for `docker run -e VAR` to forward (docker reads the value from the wrapper
process's env — it is never written to a file or logged):

```bash
/data/projects/1password-env-wrapper/with-livespec-env.sh -- docker run -d \
  --name livespec-orchestrator \
  --privileged \
  --cgroupns=host \                                  # nested resource-limited Fabro sandboxes on cgroup v2
  -v livespec-orch-varlib:/var/lib/docker \          # ext4-backed inner graph store
  -v /data/projects/livespec-impl-beads:/workspace/livespec-impl-beads \
  -p 127.0.0.1:32276:32276 \                         # web UI / control plane, HOST LOOPBACK ONLY
  --network host \                                   # to reach the EXTERNAL family-tenant Dolt (127.0.0.1:3307)
  -e LIVESPEC_FAMILY_GITHUB_TOKEN \                  # GitHub token (clone/push/PR)
  -e ANTHROPIC_API_KEY_LIVESPEC_E2E \                # fabro LLM provider key
  -e CLAUDE_CODE_OAUTH_TOKEN \                       # model auth the dispatcher projects per-dispatch
  -e BEADS_DOLT_PASSWORD_livespec_impl_beads \       # external tenant Dolt password
  -e BEADS_DOLT_PASSWORD="$BEADS_DOLT_PASSWORD_livespec_impl_beads" \
  -e HONEYCOMB_INGEST_KEY_LIVESPEC \                 # telemetry egress key
  livespec-orchestrator:dev \
  python3 /workspace/livespec-impl-beads/.claude-plugin/scripts/bin/dispatcher.py \
    loop --repo /workspace/livespec-impl-beads --budget 1 --mode shadow --item <id>
```

The checkout mount is intentionally read-write: after Fabro merges a PR, the
dispatcher refreshes that primary checkout and provisions a fresh post-merge
janitor worktree from it.

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
| `LIVESPEC_FAMILY_GITHUB_TOKEN` | GitHub token for clone / push / PR (`token` strategy; the entrypoint `gh auth login`s with it, then exports it as `GH_TOKEN` for the Dispatcher) | entrypoint + dispatcher |
| `GH_TOKEN` | conventional GitHub token name projected by the Dispatcher into the Fabro sandbox env table so the in-sandbox PR node can run `gh pr create`; do not inject it at container launch because `gh auth login --with-token` refuses to store credentials when `GH_TOKEN` is already set | dispatcher / sandbox PR node |
| `ANTHROPIC_API_KEY_LIVESPEC_E2E` | fabro LLM-provider API key (name overridable via `FABRO_LLM_API_KEY_ENV`) | `fabro install` |
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

    For the containerized orchestrator the entrypoint's `fabro install`
    provisions it; retrieve it from the running container the same way, e.g.
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
