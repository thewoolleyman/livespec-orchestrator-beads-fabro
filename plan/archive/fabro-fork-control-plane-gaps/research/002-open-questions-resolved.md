# 002 — Open questions (a) to (d) resolved by reading the pinned fork; .6 narrows and .1's fork half is confirmed

Follow-up to research note 001 for plan thread `fabro-fork-control-plane-gaps`
(epic `bd-ib-bb41`), 2026-09-06, same session, same instruments (`git show`
and `git grep` on `origin/factory-integration` at `56a14c871`; the pinned
crate source from the local cargo registry; `docker info` on both factory
hosts). Labels **measured** / **inferred** as in 001.

## (a) Script nodes cannot see the run id today — .1's fork half is real

- **Measured.** Script nodes are executed by
  `lib/crates/fabro-workflow/src/handler/command.rs`; their environment is
  `services.env_for_stage()` (:105), which is
  `EngineServices::env_for_stage` in `services.rs:251` and resolves ONLY the
  workflow-declared base env plus the GitHub token. No `FABRO_*` key is
  inserted anywhere in `fabro-workflow/src` outside tests, and the context key
  module carries no run-id key.
- **Inferred fix.** Insert `FABRO_RUN_ID`, `FABRO_WORKFLOW` and
  `FABRO_NODE_ID` into the command handler's env at `command.rs:105`, the
  same trio the hook executor inserts at `fabro-hooks/src/executor.rs:165`.
  The handler already holds `node.id`; the run id is available from the
  emitter (`event/emitter.rs:36` carries `run_id`).
- The orchestrator half (drop the `unknown-run` placeholder at
  `workflow.fabro:283`, fail loudly with no id) is unchanged from 001 and is
  the one factory-safe piece of this plan.

## (b) `init: Some(true)` needs no image change — .2 is a one-field fix

- **Measured.** `docker info --format '{{.InitBinary}}'` reports
  `docker-init` on vps (Docker 28.2.2) and on hp (Docker 29.1.3, binary at
  `/usr/bin/docker-init`). Both factory daemons carry tini.
- So the bollard `HostConfig { init: Some(true), .. }` route in
  `fabro-sandbox/src/docker.rs::host_config` (:1120) is sufficient; the
  sandbox image is untouched and `sleep infinity` stays as the command.

## (c) The pinned ACP crate has no user-input request — .6 narrows to `request_permission`

- **Measured.** The fork pins `agent-client-protocol 0.11.1` (`Cargo.lock`).
  Its agent-to-client request surface is the whole of
  `src/schema/agent_to_client/requests.rs`; a case-insensitive grep of the
  crate source for `user_input`, `elicit` and `RequestUserInput` returns zero
  files. The only question-shaped request an agent can send the client at
  this version is `request_permission`.
- **Consequence.** .6's "and user-input" clause has no protocol carrier on the
  0.254 base. Record it as a deferral (see the scope event) tied to the crate
  bump that rides `bd-ib-6qu`; do not fake it. The permission bridge alone
  still delivers what the console's b3 consumer needs, because every parked
  question today is a permission question.

## (d) The question runtime already exists; .6 is plumbing, not a new API

- **Measured.** `fabro-workflow/src/interview_runtime.rs` implements
  `AgentQuestionRuntime::ask_questions(tool_call_id, questions, cancel_token)`
  (:199) for `WorkflowAgentQuestionRuntime`: it emits `InterviewStarted` per
  question, blocks the run through `RunInterviewBlocker`, and resolves on an
  answer arriving through the server's `accepted_questions` path
  (`fabro-server/src/server.rs:2913`). The API-agent handler constructs one at
  `handler/agent.rs:260`. The ACP handler (`handler/llm/acp.rs`) constructs
  none, and `fabro-acp/src/session.rs:205` answers `request_permission`
  inline with `select_permission_outcome` (:313).
- **Inferred shape for .6.** Give the ACP session an optional
  `Arc<dyn AgentQuestionRuntime>`; under a park-and-ask policy, map the
  permission request's options onto one `AgentQuestion` and call
  `ask_questions`, translating the answer back to a `RequestPermissionOutcome`;
  under the default policy keep `select_permission_outcome`. Timeout falls
  through the existing interview timeout, which is the `needs_human` path the
  child's criterion 4 asks for. The `human` node handler is the reference for
  how an interviewer blocks and resumes a run.

## What this changes in 001's proposal

- Wave A is confirmed as four small fork changes (.2, .5, .3 tail-and-timestamp,
  .1 fork half) plus the runbook table; one rebuild and re-pin.
- Wave B: .4 stays as described; .6 is smaller than 001 assumed (plumbing to an
  existing runtime) but its user-input clause is deferred.
- Nothing here needs a maintainer decision; the remaining calls are which host
  builds each wave and the order within Wave B, both self-decidable.
