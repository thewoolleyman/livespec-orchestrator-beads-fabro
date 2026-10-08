# hp-candidate instance and first Enemy Unit Test measurements, 2026-10-08

P3 of plan `fabro-currency` (`bd-ib-4jzql3`), first session. The candidate
instance exists beside production on hp, the pinned Enemy Unit Test suite ran
against both, and the deltas below name the owning P4 child for each failure.
Production on port 32276 was not touched at any point; both units were `active`
at the end of the session, host load 0.15 on 16 cores.

## The hp-candidate instance

| Property | Value |
| --- | --- |
| Unit | `fabro-server-candidate.service` (hand-installed, enabled, active) |
| Binary | `/home/cwoolley/.fabro-candidate/bin/fabro`, `fabro 0.378.0-nightly.0 (64b9d88 2026-10-06)` |
| Binary SHA-256 | `864df2d94c96d7625a867e21e289e36bd7d1bbd6108f0b8aeb58ce5d1572788e` |
| Release asset SHA-256 | `457828ee7648ee0b1b88c866efd26cf682479d1aab78cd330b67a7ee7ba34342` (`fabro-x86_64-unknown-linux-gnu.tar.gz`, tag `v0.378.0-nightly.0`, published 2026-10-06T10:48:35Z, newest at 2026-10-08T08:5xZ) |
| Home, storage, settings | `/home/cwoolley/.fabro-candidate/{storage,settings.toml,environments}`; `HOME` set to that directory in the unit |
| Bind, console | `127.0.0.1:32278`, `https://hp-xubuntu.perch-rudd.ts.net:32278` via `tailscale serve` |
| Auth | `dev-token`; `server.env` (mode 600) holds a fresh `SESSION_SECRET` and a fresh `FABRO_DEV_TOKEN` |
| GitHub App | the fleet App `3668528`; the fleet vault file was copied and the server imported it into its SQLite vault at first start |
| Sandbox | Docker, `buildpack-deps:noble`, cpu 2, memory 4GB (the fleet `environments/*.toml` copied verbatim) |
| Scheduler | `max_concurrent_runs = 3` |
| Storage engine | `sqlite` (`storage/db/fabro.sqlite3`); the legacy build used SlateDB objects |
| Doctor | Configuration ok, version parity ok, GitHub App configured, Docker reachable, LLM providers none (correct under the OAuth-only posture) |

Three things learned standing it up, each a refusal with no hint until the
next one:

1. `server.auth.methods = ["dev-token"]` requires BOTH `SESSION_SECRET` and
   `FABRO_DEV_TOKEN` in the environment at start. The server does not generate a
   dev token.
2. The dev token has a fixed format: the literal prefix `fabro_dev_` followed by
   64 lowercase hex characters (74 bytes). Any other value is refused as
   "invalid format" (`fabro_util::dev_token::validate_dev_token_format`).
3. The legacy plain-JSON vault (`storage/vaults/default/secrets.json`) is still
   imported on first start, but the server log names a removal deadline of
   2026-10-11 for that import path. A later tag will not read the legacy file;
   secrets must then be set through `fabro secret set`.

The CLI side: `fabro auth login --server <url> --dev-token <token>` records the
entry in `~/.fabro/auth.json` with the same `{kind, logged_in_at, token}` shape
the 0.254 client writes, so the new client can share the production auth file
(backed up first to `~/.local/state/fabro-currency/auth.json.pre-candidate-2026-10-08.bak`).
The new client honours `FABRO_SERVER` and per-subcommand `--server` exactly as
the old one does. The client binary on vps is at
`~/.local/state/fabro-currency/v0.378.0-nightly.0/fabro` (same digest).

The Ansible role that owns both existing hp instances
(`livespec-dev-tooling`, `ansible/roles/fabro_server`) hardcodes one shared
binary path, `<host_home>/.fabro/bin/fabro`, for every instance, so the
candidate cannot be expressed in it today. `just ansible-drift` will report the
hand-installed unit until the role grows a per-instance binary override; that
lockstep change belongs to `bd-ib-sxcnj7`.

## Enemy Unit Tests, pinned versus candidate

Pinned leg: `~/.fabro/bin/fabro` (0.254.0, 8869e88) against
`https://hp-xubuntu.perch-rudd.ts.net:32276`. Candidate leg: the 0.378 client
against `:32278`. Tier 1 was run against the candidate first so that a
completed run existed for the tier 0 inspect tests.

| Test | Pinned | Candidate | Owner |
| --- | --- | --- | --- |
| tier0 `version_reports_client_and_server_independently` | FAIL | FAIL | harness: `FabroPort.version` never passes `--server`, so both legs query the dead local `127.0.0.1:32276`; fix in `bd-ib-sbg3ze` |
| tier0 `validate_accepts_livespec_workflow_templated_acp_command` | pass | FAIL | `bd-ib-hti4zf`: three `attractor.condition.syntax` errors at lines 784, 786, 787 (the review-cap conditions carry `inputs.*` tokens). The templated `acp.command` attribute itself raised NO diagnostic on 0.378; whether the runtime still de-templates it (fabro 474) is a tier 1 question, not a validate question |
| tier0 `ps_records_carry_reader_field_set` | pass | pass | |
| tier0 `server_flag_is_per_subcommand` | pass | pass | |
| tier0 `inspect_and_events_completed_run_field_sets` | pass | FAIL | `bd-ib-227cbw`: Petri event payload shape (below) |
| tier0 watchdog `inspect_record_still_lacks_updated_at` | pass | pass | |
| tier1 `preflight_accepts_the_tier1_minimal_run_configuration` | not run | pass | |
| tier1 `completed_run_maps_to_green_terminal_path_and_emits_liveness_events` | not run | FAIL | run SUCCEEDED and the terminal mapping was green; the assertion that failed is the liveness timestamp: Petri events carry `recorded_at` (integer milliseconds), not `timestamp`/`ts`/`at`. `bd-ib-227cbw` |
| tier1 `failed_run_maps_to_failed_terminal_path_and_structured_failure_block` | not run | FAIL | the failing fixture (a node with no outgoing edge) is refused at run creation: `attractor.exit_unreachable: the exit node is not reachable from the start node`. Petri validates exit reachability; the fixture needs a Petri-valid failing graph, and the production graph's `abandon`-style terminals need the same check (P3 enemy test) |
| tier1 `force_remove_in_flight_run_removes_it_from_ps` | not run | pass | |

## Payload shapes measured on the candidate

- `ps --json` record keys: `goal, labels, parent_id, repo_origin_url, run_id,
  source_directory, start_time, status, total_usd_micros, wall_time_ms,
  workflow_graph_name, workflow_name, workflow_slug`.
- `inspect --json` top-level keys: `checkpoint, conclusion, parent_id, run_id,
  run_spec, sandbox, stages, start_record, status`; `status` is
  `{kind: succeeded, reason: completed}`; `conclusion` keys: `diff,
  final_git_commit_sha, stages, status, timestamp, timing, total_retries`.
  No `causes`, no `signature`, as assessment 003 predicted.
- `events --json` is a stream of `{run_id, stream_seq, kind, id, recorded_at,
  item: {seq, recorded_at, record: {kind: "run.created", ...}}}` envelopes; the
  first record inlines the whole run spec, including the resolved environment
  (`provider: docker`, image, resources cpu 2 / memory 4GB).
- Sandbox containers are named `petri-<run-id>-l0` and stop on terminal
  (`Exited (143)`), beside the legacy `fabro-run-<run-id>` containers.
- `validate --json` on the production graph: `valid: false`, 3 errors (the
  conditions above), 7 warnings (`ignored.workflow_toml.run.*` for checkpoint,
  integrations, meta_branch, pull_request, run_branch; an ignored
  `environments.livespec-ci.resources`; `info.budget.default`).

## What P3 still owes

One enemy test per preserved behaviour, run on both servers: node-visit loop
caps, Docker resource propagation (the run spec above shows resources reach the
spec; the container limits are the thing to assert), the accepted `acp.config`
shape, script token quoting, a codex-acp session start, the needs-human exit
routing the item to blocked, cancellation's terminal status, and
inspect/dump carrying no credential value. Then the comparison artifact and the
go-or-no-go naming the exact tag.
