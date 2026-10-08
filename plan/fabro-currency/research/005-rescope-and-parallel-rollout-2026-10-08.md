# Re-scope and parallel rollout, 2026-10-08

The maintainer resumed plan `fabro-currency` on 2026-10-08 and ruled: get the
upgrade to the latest published Fabro done as soon as possible, keep only the
factory functionality the fleet uses today, and defer everything else. This note
records the measurements behind that ruling, the plan's Definition of Done
authored from it (the epic predates the Definition-of-Done requirement), the
rollout and rollback design, and the Enemy Unit Test safety net. The ledger
scope event of the same date carries the carrier map and the deferrals.

## Measured state, 2026-10-08

| Fact | Measurement |
| --- | --- |
| hp serving engine | `fabro 0.254.0 (8869e88 2026-10-01)`, unit active, 402G free, load 1 to 3 on 16 cores, 25G available |
| vps | `fabro-server` unit inactive and disabled; retired factory, absent from `.livespec.jsonc` |
| Newest published upstream release | `v0.378.0-nightly.0`, published 2026-10-06T10:48:35Z |
| Newest stable | still `v0.254.0` (2026-06-04) |
| Ratified end of the 0.254 transition | 2026-11-14T00:00:00Z (`SPECIFICATION/constraints.md` section "Fabro runtime constraints") |
| Upstream issue 553 | CLOSED by upstream 2026-10-06T19:06:42Z, "no longer applicable": the Petri migration removed the legacy ACP implementation and deleted the test module (`af38d689`) |
| Upstream PR 688 (spend limit) | OPEN, untouched since 2026-07-30; NOT among the 28 commits the serving carrier carries |
| Upstream PR 576 (OTLP export) | OPEN, untouched since 2026-08-02 |
| Petri ACP error conversion | identical at the Petri revisions pinned by `v0.371.0-nightly.0` (`98144f1`) and `v0.378.0-nightly.0` (`e46845b`): every non-cancel ACP error maps to `retry_requested` |
| Fallback chain in live dispatches | zero occurrences of `fallback_chain` in `fabro inspect --json` of the latest hp run (`01M06TFP1JGG`, 12 `acp.command` nodes); no `acp_nodes` override in `.livespec.jsonc` |
| Readiness-timeout carry | `FABRO_SERVER_START_READY_TIMEOUT_SECS` is not set on the hp unit; the default is in use |
| OTLP on hp | the server unit exports its own spans (`otel.conf` drop-in); worker forwarding is a fork carry; `bd-ib-z13s` records that `run_turn` spans never land on this build anyway |
| Dispatcher spend handling | `commands/_fabro_port_records.py` rewrites provider usage and spend ceilings to `deterministic` and records provider-exhaustion holds, matching the Codex and Anthropic phrasings; the Fabro-side fix would not catch the Codex form |

## Why the spend-limit item was a blocker, and why it no longer is

`bd-ib-m637al` blocked P3 structurally, not technically: the 2026-09-30
direction required every open upstream pull request to be dispositioned before
migrating, and the graph encoded that as `bd-ib-4jzql3` depending on all three
P1 children. The 2026-10-01 rider then forbade writes to non-owned repositories,
which made P1 unfinishable and deadlocked everything downstream; the 2026-10-02
session went looking for a Petri-side fix and asked for a `thewoolleyman/petri`
fork. The serving factory never carried PR 688, the Dispatcher already handles
provider ceilings on its own side, and the only thing the engine fix would save
is one extra prompt attempt per cap hit. The item is deferred, PR 688 is left
open and untouched, and no Petri fork is created.

## Deferred, with the reason each is not current functionality

- **Spend-limit classification** (`bd-ib-m637al`, PR 688): see above.
- **OTLP export and `run_turn` telemetry** (`bd-ib-lic3n3`, `bd-ib-wo4m6o`,
  PR 576): observability, not function; the Dispatcher's own spans do not pass
  through the engine; `run_turn` spans already never land.
- **Cross-candidate ACP fallback chain and in-protocol model selection**
  (`bd-ib-r5cnjd`, S4 and S5 of plan `bd-ib-jxvgq5`): no live dispatch renders
  the attribute and nothing configures it.
- **Configurable daemon readiness timeout** (`bd-ib-ik7sbn`): unused on hp.
- **Issue 553** (`bd-ib-g7qlmo`): closed by upstream; satisfied without action.

## What the migration must preserve

The ImplementWorkItem graph (templated `acp.command` becomes literal
`acp.config`; the three review-cap edge conditions lose their `inputs.*` tokens;
the needs-human script's run-id input; the loop caps that read
`context.internal.node_visit_count`), the Dispatcher's port of `validate`,
`inspect`, `events` and the terminal conclusion, the credential channel (forced,
because Petri stores workflow versions immutably on the server), Docker resource
limits, codex-acp compatibility, cancellation, and the human gate. Those are
`bd-ib-4jzql3` (P3) and the three factory-eligible P4 children `bd-ib-hti4zf`,
`bd-ib-4ipmub` and `bd-ib-227cbw`.

## Rollout and rollback: a parallel instance on hp

hp already runs instance-parameterised units (the fleet instance on 32276 and a
disabled `mi-homelab` instance on 32277, each with its own home, storage,
settings and port), and tailscale serve already fronts both ports. The
Dispatcher routes per factory name through `dispatcher.factories`, `--factory`,
`LIVESPEC_FABRO_FACTORY` and the item's `dispatch_factory` metadata, records the
factory per item so reconcile addresses the right server, and pins a named
workflow variant per item through `dispatch_workflow`.

1. Stand up `hp-candidate` on port 32278 with its own home, storage, settings,
   auth, secrets and a copy of the fleet GitHub App credential, running the
   exact newest published tag plus only the carries still required. Production
   is untouched.
2. Run the Enemy Unit Test comparison pinned versus candidate; extend the suite
   to one test per preserved behaviour.
3. Route hand-picked low-risk items to the candidate with the Petri graph
   pinned until a Claude item, a Codex item, a needs-human exit and a cancel
   have each behaved.
4. Cut over with one committed change, `dispatcher.default_factory` from `hp`
   to `hp-candidate`. In-flight production runs finish on the legacy server.
   Rollback is reverting that pull request.
5. Soak for a week, then stop the legacy unit and keep its binary and storage
   read-only. The `mi-homelab` instance shares the legacy binary path and gets
   its own decision at that point.

There is no in-place upgrade and therefore no one-way SQLite migration of
production storage. vps is out of scope: it is retired and CPU-starved.

Three Dispatcher gaps make the parallel run possible: the engine client binary
is a single global setting rather than per factory (`bd-ib-qytzf4`); the port
must parse both engines' output during the overlap (`bd-ib-227cbw`); and the
Petri graph must be a registered workflow variant (`bd-ib-hti4zf`).

## The Enemy Unit Test safety net

The suite under `fabro-enemy-unit-tests/` is green and already written against
the `FabroPort` facade: tier 0 (six tests, real Fabro calls, no run), tier 1
(four tests launching real runs on a minimal graph), parameterised over a client
binary and a server URL through `FABRO_EUT_*` overrides, with
`just fabro-enemy-compare` rendering a pinned-versus-candidate delta. It has
fired once already: `bd-ib-i3zhgk` ran it against `0.348.0-nightly.0` on
2026-09-07 and caught the templated `acp.command` break (fabro 474).

Two gaps are now plan children. Coverage is thin, so P3 adds one test per
preserved behaviour. And fourteen Dispatcher modules reach Fabro outside the
facade, so `bd-ib-sbg3ze` routes every engine call through it and adds a
structural check; only then does "the comparison is green on both engines"
equal "the Dispatcher works on both engines". One limit stays: the workflow
graph is the engine's input language and cannot sit behind a port; its enemy
test is "the rendered graph validates on the target engine".

## Ledger changes recorded on 2026-10-08

Definition of Done authored onto `bd-ib-6tcjfx`; scope event with carrier map;
`bd-ib-qytzf4` and `bd-ib-sbg3ze` filed and ready; `bd-ib-4jzql3`,
`bd-ib-iud52v` and `bd-ib-sxcnj7` re-scoped; `bd-ib-g7qlmo` closed as
satisfied; `bd-ib-m637al`, `bd-ib-lic3n3`, `bd-ib-wo4m6o`, `bd-ib-r5cnjd` and
`bd-ib-ik7sbn` closed as deferred; P3 no longer depends on P1, and the release
bundle no longer depends on the deferred P5 children.

## The maintainer's statement of what done means

just get the upgrade done so we are on latest fabro, and defer what we can and don't absolutely need for current factory functionality - don't worry about spend, or unimpleemented features, only current functioanlity we are using.

## Definition of Done assertions derived from that statement

- `fabro --version` on the serving hp factory reports a build whose upstream base is an exact published fabro-sh/fabro release tag inside the ratified 30-calendar-day currency window, and that integration commit is reachable from origin/factory-integration.
- On the upgraded hp factory, one Claude-adapter ImplementWorkItem dispatch and one Codex-adapter ImplementWorkItem dispatch each run through the implement, janitor, review and pr stages and each produces a merged pull request.
- A dispatch that reaches the needs-human exit on the upgraded factory terminates its run, and the Dispatcher routes the work-item to blocked on the ledger.
- A dispatch on the upgraded factory can be cancelled, and the Dispatcher reports that run's terminal status as cancelled rather than as an implementation failure.
- `fabro inspect` and `fabro dump` of a run on the upgraded factory contain no resolved credential value.
- The orchestrator image bakes the same binary digest as the serving hp binary, and the runbook orchestrator-image/README.md names the pinned tag and the carried patch set.
- The legacy 0.254 instance on hp is stopped after the post-cutover soak, before 2026-11-14T00:00:00Z, with its binary and storage directory retained read-only beside the serving build.
