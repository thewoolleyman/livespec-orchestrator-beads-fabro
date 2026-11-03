# 017 — Candidate redeploy, and upstream's sandbox-driver direction (2026-11-02)

Written by `claude:fabro-currency` (session e1c109) on 2026-11-02/03. It continues
note 016. The ledger records are the plan epic `bd-ib-6tcjfx` scope event of
2026-11-02T23:4xZ and its handoff entries. Facts marked UNVERIFIED were not checked
by this note's author.

## Step 3 done: candidate and mi-homelab on 84fb903b8

- livespec-dev-tooling #3183 merged at 23:29:56Z (`f043cca9`). It makes
  `fabro-server-candidate` a permanent mirror of `fabro-server`. It also pins the
  candidate and `fabro-server-mi-homelab` to Fabro `0.393.0-nightly.1` at `84fb903b8`
  (sha256 `d196f2a8…`).
- **The plugin digest is the one installed, not the one in the role default.** gmktec's
  `/usr/local/bin/sandbox-driver-kubernetes` is v0.5.0 (`d93437f0`). master's role
  default is v0.6.0 (`f6a8ec3d`), which was never applied to the host, and #3178
  pins v0.7.0 (`93ca024d`). Every instance verifies the shared binary at start, so
  the restarted pair pins `d93437f0`. Main's committed `f6a8ec3d` therefore differs
  from what it actually runs. That is resolved in main's zero-run window, when the
  plugin moves.
- The apply ran from the primary checkout of livespec-dev-tooling at `f043cca9`:
  `--limit gmktec-xubuntu --tags untagged`, with
  `fabro_server_target_units: [fabro-server-candidate, fabro-server-mi-homelab]` and
  `fabro_server_restart_allowed=true`. It exited with `failed=0` and `changed=14`.
  - Read-back: the candidate became active at 23:46:54Z and mi-homelab at 23:53:08Z.
    Both binaries hash to `d196f2a8…`, and both report
    `fabro 0.393.0-nightly.1 (84fb903 2026-11-02)`.
  - Both boards read 0 runs. Main `:32276` was not restarted (active since 15:04:02Z).
- The candidate's vault needed the homelab App key, which only the homelab AWS chain
  holds: `with-homelab-aws.sh --role homelab-workload hl param run --bind
  MI_HOMELAB_GITHUB_PRIVATE_KEY=/homelab/v1/providers/github/mi-homelab-factory-bot/private-key`.
- **A probe in this session printed most of that key into its own transcript.** The
  probe was `env | cut -d= -f1`. A multi-line value's continuation lines contain no
  `=`, so `cut` prints each one whole. List names with `compgen -e` or
  `env -0 | cut -z -d= -f1` instead. The maintainer ruled no rotation.
- **The candidate is now dispatchable by name.** livespec-dev-tooling registers
  `candidate` in `fabro_factory_registry`, and this repository declares it under
  `dispatcher.factories`. Its cap file is
  `tmp/petri-canary/candidate-cap` = 1.

## Step 6 finding: the rebase keeps every carry

From the rebase-prep investigation of 2026-11-02:

- Target: `v0.403.0-nightly.0` (`9d96890cb`), published 2026-10-31T10:42:37Z. The
  carrier base `9d9cbe9f4` is 62 commits behind it.
- At the tag, `backend()` in `fabro-petri/src/engine.rs` still serves only `local`,
  `docker` and `daytona`. Petri `cfd57a5`, the commit the tag pins, and Petri main
  `25d8bf3` have no `register_plugin`. All 11 carries plus fork PR #15 are still
  needed.
- A trial rebase applied all 11 with trivial conflicts:
  - branch `trial/rebase-v0.403.0-nightly.0` at tip `fe8d3d4c3`, in
    `~/.worktrees/fabro/`;
  - `Cargo.lock` is stale;
  - a matching trial merge of the Petri fork onto `cfd57a5` is staged, uncommitted, in
    `~/.worktrees/petri/trial/registered-on-cfd57a5`.
- UNVERIFIED: whether it compiles (host load was 30 to 37), whether #122's
  registration survives Petri #136's removal of `run.prepare`, and whether upstream
  main has moved since the tag.

## Upstream direction: a bridge, then the shared contract

- lithoscomputer/petri#122 was closed by its maintainer on 2026-10-28, "in favor of
  the sandbox-driver redesign". Provider configuration, discovery and plugin launch
  move into the sandbox-driver library behind one shared API (protocol version 3,
  `docs/next-api.md`). #131 is affected too: sizing a sandbox from the run's
  resources becomes the library's per-field override merge.
- On the maintainer's go-ahead, fabro-sh/fabro#1048 and petri#131 were closed with a
  pointer to the redesign.
- **The new design fits Kubernetes as an ordinary third-party plugin**:
  - a provider entry with `plugin`, `path`, `sha256` and `inherit_env`, plus a
    schema-validated `config`;
  - credentials through `secrets`;
  - environments as spec templates (`source`, `resources`, `network`, `services`);
  - a conformance suite;
  - the spec notes that services are reachable on localhost "in a pod".
- **Path:** keep the fork carries as a bridge, and port sandbox-driver-kubernetes to
  v3 (child `bd-ib-yomgvq` under plan `kubernetes-sandbox-backend`, `bd-ib-nmuyjc`).
  Drop the Fabro plugin-provider carry and the Petri fork at the first rebase after
  Fabro adopts the shared contract. UNVERIFIED: the adoption timeline. Petri #138,
  which prepares Petri for the shared API, is an open draft last touched 10-23.
- The upstream OTLP exporter rewrite (fabro-sh/fabro#576, item `bd-ib-njbg7j`) moved
  to plan `factory-run-correlation-observability` (`bd-ib-qfv9`). It is not a blocker
  here, because the Honeycomb `run_turn` assertion rides our own carries.
