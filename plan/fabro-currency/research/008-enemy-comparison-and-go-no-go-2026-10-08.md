# Enemy Unit Test comparison and P3 go-or-no-go, 2026-10-08

P3 of plan `fabro-currency` (`bd-ib-4jzql3`): the comparison artifact. Pinned
leg: `~/.fabro/bin/fabro` `0.254.0 (8869e88 2026-10-01)` against
`https://hp-xubuntu.perch-rudd.ts.net:32276` (production). Candidate leg:
`~/.local/state/fabro-currency/v0.378.0-nightly.0/fabro`
`0.378.0-nightly.0 (64b9d88 2026-10-06)` against `:32278` (the `hp-candidate`
instance of research note 006). Both legs ran from the orchestrator primary
checkout at a pushed `master` tip; the suite is the one merged by the
`fabro-currency-enemy-matrix` pull request, which added
`test_tier1_preserved_behaviours.py`, `test_tier1_acp_launch.py`, the in-suite
fake ACP agent, a Petri-valid failing fixture and the `recorded_at` liveness
field.

## The table

| Test | Pinned 0.254 | Candidate 0.378 | Reading |
| --- | --- | --- | --- |
| tier0 `version_reports_client_and_server_independently` | FAIL | FAIL | harness: `FabroPort.version` never passes `--server` (`bd-ib-sbg3ze`) |
| tier0 `validate_accepts_livespec_workflow_templated_acp_command` | pass | FAIL | three `attractor.condition.syntax` errors from `inputs.*` tokens in edge conditions (`bd-ib-hti4zf`) |
| tier0 `ps_records_carry_reader_field_set` | pass | pass | |
| tier0 `server_flag_is_per_subcommand` | pass | pass | |
| tier0 `inspect_and_events_completed_run_field_sets` | pass | FAIL | Petri payload shapes (`bd-ib-227cbw`) |
| tier0 watchdog `inspect_record_still_lacks_updated_at` | pass | pass | |
| tier1 `preflight_accepts_the_tier1_minimal_run_configuration` | pass | pass | |
| tier1 `completed_run_maps_to_green_terminal_path_and_emits_liveness_events` | pass | pass | after the `recorded_at` harness fix |
| tier1 `failed_run_maps_to_failed_terminal_path_and_structured_failure_block` | pass | pass | after the goal-gate fixture |
| tier1 `force_remove_in_flight_run_removes_it_from_ps` | pass | pass | cancellation route |
| tier1 `docker_resource_limits_reach_the_sandbox` | pass | FAIL | limits dropped on the Petri Docker path (`bd-ib-otyq6l`) |
| tier1 `outcome_conditions_route_a_bounded_self_loop` | pass | pass | |
| tier1 `node_visit_count_condition_exits_a_fixed_loop` | pass | FAIL | the key is not populated on Petri (`bd-ib-hti4zf`) |
| tier1 `max_visits_caps_a_self_loop_as_a_failed_run` | pass | pass | the loop cap that survives |
| tier1 `needs_human_marker_is_readable_from_the_failed_run` | FAIL | pass | pinned never surfaces script stderr in inspect; the Dispatcher reads it elsewhere today (`bd-ib-227cbw` moves the read) |
| tier1 `script_quoting_is_verbatim_shell` | pass | pass | |
| tier1 `acp_agent_launches_from_acp_config_json` | FAIL | pass | the 0.254 parser rejects the JSON attribute (`failed to parse acp.config as JSON`); the Petri-era engine launches it |
| tier1 `acp_agent_launches_from_literal_acp_command` | pass | pass | a literal `acp.command` with a leading `KEY=value` and `backend="acp"` launches on BOTH engines |

## The ACP result that decides the graph port

`backend="acp"` plus a literal `acp.command` launches an ACP agent on both the
pinned 0.254 engine and the 0.378 candidate, while the `acp.config` JSON form
launches only on the candidate and a templated `acp.command` launches only on
pinned. So the engine-agnostic rendering for every agent node is a literal
`acp.command` string carrying the adapter command with its `KEY=value`
environment prefix, which is what the Dispatcher already resolves per node
today; only the template indirection has to go. With the three edge
conditions rewritten (research note 007) that leaves one `ImplementWorkItem`
graph that validates and runs on both factories during the overlap, which is
what the parallel rollout of research note 005 needs.

## Go or no-go

NO-GO for a production re-pin to `v0.378.0-nightly.0` today, and GO for P4
design freeze against that tag. The three candidate failures that matter are
each owned: the graph port (`bd-ib-hti4zf`: literal `acp.config` or
`acp.command`, `backend="acp"`, no `inputs.*` tokens in conditions, loop caps
re-expressed with `max_visits` plus outcome/preferred_label routing), the
port rebase (`bd-ib-227cbw`: Petri payload shapes, the needs-human marker in
`conclusion.failure.detail.message`), and the Docker resource forwarding
(`bd-ib-otyq6l`, upstream first). Everything else the factory relies on
behaves the same on both engines. The placeholder provider secret the
candidate carries is a cutover decision for `bd-ib-sxcnj7` and
`bd-ib-4ipmub`. Codex-acp against a real credential and the no-credential
inspect/dump assertion are deferred to the P4 and P6 canary dispatches, where
the real adapters and the native secrets channel exist.

The exact tag to design against is `v0.378.0-nightly.0` (`64b9d88`,
published 2026-10-06T10:48:35Z). It will be out of the ratified 30-day window
on 2026-11-05 if nothing newer is adopted; `bd-ib-sxcnj7` re-evaluates
currency before building the bundle, as the constraint requires.
