# 016 — Candidate as permanent mirror, and the staged rollout (2026-11-02)

Written by `claude:fabro-currency` (session 51a84501) on 2026-11-02. It records the
maintainer's attended ruling of 2026-11-02T19:22:32Z. The full text is the plan epic
`bd-ib-6tcjfx` scope event of that timestamp; the hp read-back is the scope event of
19:23:49Z. Facts marked UNVERIFIED were not checked by this note's author.

## What the ruling replaces

It supersedes legacy-coordinator-agent's R301 combined cancel-and-restart window for
gmktec main `fabro-server` `:32276`, and R301's ruling that the candidate and
mi-homelab stay on `9f6c38fab`. To protect throughput, no live run on main is
cancelled.

## The six steps

1. **Retire hp for the record.** livespec-dev-tooling stopped and disabled hp's
   legacy 0.254 server on 2026-11-02 (hp host_vars commit `c40dc35e`). Read-only check
   at 19:23:49Z: `fabro-server.service` inactive and disabled, no fabro process, the
   0.254 binary (117,340,832 bytes) kept at `r-xr-xr-x`, and `~/.fabro` (4.0G) kept
   at `dr-xr-xr-x`. tailscaled still listens on hp `:32276` (a leftover
   `tailscale serve` entry pointing at the dead backend), left to dev-tooling's hp
   retirement owner. No code is deleted.
2. **Build the current carrier with no rebase** and no fork cleanup: the
   `carrier-candidate-registered-20261023` tip (per-run GitHub App selection, the node
   name on `run_turn` spans, and the sandbox connection-failure category fix once fork
   PR #15 merges).
3. **Deploy it to `fabro-server-candidate` `:32278` and `fabro-server-mi-homelab`
   `:32277`**, both measured at 0 runs around 19:2xZ, on the current shared Kubernetes
   plugin. Run one ordinary test job on the candidate.
4. **The candidate becomes a permanent mirror of main** (same environments, vault, App
   and cap) and hot fallback. It is owned by this seat as its dogfood factory; this
   seat routes its own work there and sets its cap. The coordinator and dispatcher
   are told.
5. **Route fleet work to the candidate and let main drain naturally.** At zero runs,
   restart main onto the same build plus sandbox-driver-kubernetes v0.7.0 (once
   livespec-dev-tooling #3178 merges, else v0.6.0), then flip traffic back. Move the
   candidate and mi-homelab to that plugin while each is idle.
6. **Rebase onto the newest `fabro-sh/fabro` nightly** and drop the carries upstream
   now covers. Dogfood on the candidate, then move main, the candidate and mi-homelab
   together. This meets the plan's 30-day release-tag assertion.

Each pin change targets one instance and lands only when that instance is empty, so no
apply stages a binary under a running server (the 2026-11-02 outage in note 015).

## Constraints

- **One shared plugin binary.** sandbox-driver-kubernetes is one
  `/usr/local/bin/sandbox-driver-kubernetes` whose sha256 every instance pins and
  verifies at start. It moves only while every instance that would run on it is empty.
- **Counting rule (gmktec-factory-placement).** main and the candidate share gmktec, so
  their runs count against one shared fleet total of at most fleet-cap 16. The
  candidate's sub-cap file is owned by fabro-currency. UNVERIFIED: the 16 and the
  sub-cap file's location were relayed, not read.

## Fork-carry inventory and upstream status (checked with `gh`, 2026-11-02)

- **Upstream base.** The carrier sits on upstream `main` `9d9cbe9f4`, four commits past
  `v0.393.0-nightly.1` (`e28675a1d`): the merges of #1062 (internal-deps bump) and
  #1065 (skipped-stage display). It is not an exact tag, so it fails the currency
  rule regardless of age.
- **Carrier.** `carrier-candidate-registered-20261023` carries 11 commits over
  `9d9cbe9f4`, tip `84fb903b8` (10 through `613add19c`, plus `84fb903b8` for
  `bd-ib-motuct`). Fork PR #15 (`bd-ib-6r3yax`, sandbox transport failure as
  `transient_infra`) is open against it.
- **Upstream Fabro PRs.** #1048 (configured sandbox plugins through Petri's registered
  providers) is an open draft that depends on lithoscomputer/petri#122 and #131. #576
  (opt-in OTLP export) has been open since 2026-07-14; the promised rewrite as an OTLP
  logs exporter is UNVERIFIED. #568 and #552 are merged; #688 closed 2026-10-10.
- **Petri.** lithoscomputer/petri#122 closed 2026-10-28, "in favor of the sandbox-driver
  redesign" (swerner). Our #131 is open with no reviews. The review-routing brace fix
  is not offered upstream (UNVERIFIED).
- **Likely drop.** `v0.403.0-nightly.0`'s `Cargo.toml` depends on
  `lithoscomputer/sandbox-driver` and names plugins "through sandbox-driver-protocol".
  That probably lets step 6 drop the plugin-provider carry (`63d513863`, `6dc0242f2`)
  and most of the Petri fork. UNVERIFIED: no build or behavior check has been done
  against that tag.
