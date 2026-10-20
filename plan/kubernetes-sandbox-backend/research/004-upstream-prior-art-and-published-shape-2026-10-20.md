# 004 — Upstream prior art, and the shape we published (2026-10-20)

Author: claude:kubernetes-sandbox-backend (plan session), under coordinator
ruling R263. That ruling quotes the maintainer: "get the fabro/petri issue and
prs published, after we update and rebase and get our fork in order". This note
records why what was published differs from the draft in research note 003
section 4, and the measurements that decided it. Where the two notes differ,
this one wins.

## The finding

A prior-art check against both forges, made before rebasing, found that the
upstream maintainers were already building most of our Petri change:

| Upstream record | State on 2026-10-20 | What it covers |
| --- | --- | --- |
| lithoscomputer/petri issue #114 | open | "Support registered external sandbox providers throughout the standard runtime" |
| lithoscomputer/petri PR #119 | merged | "Route each scope and lease to its provider kind" (prefactor) |
| lithoscomputer/petri PR #122 | open since 2026-10-13, head `a42b194`, no reviews | the feature PR for #114 |
| fabro-sh/fabro issue #937 | open, no comments before ours | "Enable configured sandbox plugins for workflow execution through Petri" |

PR #122 adds `ProviderRegistrations::register_plugin(PluginConfig, SandboxSpec)`,
`SandboxBackend::Registered(ProviderKind)`, and a Fabro frontend that accepts
any valid provider kind. Three of its decisions bear on us:

- **Sizing.** It builds every process scope from the registration's static
  template, and it refuses `resources` and `image` under a registered kind
  (`unsupported.workflow_toml.environments.custom`). A run therefore cannot
  size its own sandbox, and per-run pod requests and limits are this plan's
  assertion 2.
- **Environment.** A registered plugin takes no `inherit_env`; its
  environment must be complete.
- **Host address.** A registered plugin has no host address, which matters
  only for GitHub-action runners and services. #122 refuses both on a
  registered kind, so ordinary process scopes do not need one.

None of this repository's plan records or ledger items mentioned PR #122
before this note. Our port of 2026-10-19 (fork PR thewoolleyman/petri#1) was
built on #119's per-kind registry but not on #122. Publishing the draft in
note 003 section 4 as written would have competed with the Petri maintainers'
own in-flight design.

Two more measurements: upstream Petri `main` (`12dd5a6`) and PR #122 both
forward no resources to Docker; only Daytona is sized. Upstream Fabro `main`
(`7a876b544`) pins Petri `50809f9`. PR #122 is based on `857a171`, an ancestor
of that pin, and it merges cleanly onto Petri `main`.

## What was published instead

| Artifact | Branch and commits | Content |
| --- | --- | --- |
| Issue lithoscomputer/petri#130 | none | the one new gap: a run cannot size its sandbox on a registered provider |
| PR lithoscomputer/petri#131 | thewoolleyman/petri `plugin-resources-on-registered` = `f342550`, based on #122's branch `registered-sandbox-providers` | `SandboxOptions.resources` replaces the template's fields one by one, and a field left out keeps the template's. The Fabro frontend lowers `resources` (not `image`) under a registered kind |
| Draft PR fabro-sh/fabro#1048 | thewoolleyman/fabro `plugin-registered-providers` = `3022c9922` (feature) + `2398da5b7` (temporary Cargo pin) on upstream `main` | for #937. Each enabled `[server.sandbox.providers.<kind>]` gains `process_spec` and is registered through `register_plugin`. `inherit_env` names are resolved into the complete `env`. An unbundled kind maps to `Registered`. The environment's resources are forwarded. A run or prune on a kind that does not register is refused with the reason |
| Comments | petri PR #122, fabro issue #937 | cross-links |

Deliberately left out:

- **Docker resources.** They change behaviour for existing Docker users, so
  they are raised as a question in #130 and #131.
- **Our old `host_address` provider key.** See the host-address point above.
- **A new fabro-sh/fabro issue.** It would duplicate #937.

The temporary pin points at thewoolleyman/petri `fabro-integration-registered`
= `71d5244` (Petri `main` + #122 + #131). The draft stays a draft until #122
and #131 land.

## Gates, as run on vps

| Leg | Command | Result |
| --- | --- | --- |
| Petri format | `cargo +nightly-2026-04-14 fmt --check --all` | clean |
| Petri lint | `cargo +1.97.1 clippy --locked --all-targets --all-features -- -D warnings` over the three touched crates | clean (the default nightly ICEs in untouched `petri-steps`; 1.97.1 is Petri CI's pin) |
| Petri tests | nextest over five crates, with the built plugins | 472 of 478 passed, including both new tests |
| Fabro format and lint | `nightly-2026-04-14` fmt and clippy `-D warnings` over five crates | clean |
| Fabro tests | nextest over `fabro-petri`, `fabro-config` and `fabro-types` | 789 of 793 passed, including all six new tests |
| Fabro server and CLI | nextest filtered to sandbox, provider, plugin and worker | 301 of 301 passed |
| Fabro lockfile | `cargo check --locked` against the git pin | passes |

The failures, each checked against a control:

- **Petri, 3 Docker service tests.** They fail identically on #122
  unmodified: this host's Docker networking.
- **Petri, 3 `external_provider_cli` tests.** They look for the fixture two
  directories above the test executable, and this host's nightly Cargo puts
  test executables under `target/debug/build/<pkg>/<hash>/out/`. The change
  does not touch them.
- **Fabro, 4 timeouts at 20 s under load.**
  - `a_docker_run_commits_inside_the_container_and_publishes_every_checkpoint`
    passes serially in 17.1 s, against 14.1 s on unmodified `main`.
  - `a_shallow_run_pushes_each_checkpoint_and_its_fork_fetches_from_the_origin`
    passes serially in 7.8 s, against 8.9 s on `main`.
  - Both large-output blob tests time out on unmodified `main` too.

A trap measured on the way: two Fabro worktrees sharing one `CARGO_TARGET_DIR`
produce the same artifact identity for a workspace crate. Freshness is judged
by mtime, so building the baseline worktree silently replaced this branch's
artifacts, and the next build reported a missing field that the source plainly
had. The remedy is to touch the changed files, or give each worktree its own
target directory.

## What follows, and what does not change

- The running carrier (`carrier-0389` / `factory-integration` `5b5abec3`,
  served by gmktec) still carries the 2026-10-19 port. Moving the carrier to
  #122 + #131 is a separate GitOps rollout: a next-carrier candidate built
  from upstream `main` + these topics + the six OTLP carries. Nothing was
  redeployed here.
- The factory's provider configuration will need `process_spec` for the
  `kubernetes` kind when that carrier lands. Draft livespec-dev-tooling PR
  #2663 predates this and must be revised to match.
- `bd-ib-jadfxx`'s Definition of Done names "an issue in fabro-sh/fabro". The
  issue landed in lithoscomputer/petri for the reasons above; the record of
  that divergence is on the item, for the maintainer's attestation.
