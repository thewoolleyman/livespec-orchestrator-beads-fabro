## The maintainer's statement of what done means

Relayed by the dispatching session (Claude Code session b1e14094-853e-412d-aa8b-c2adb51d7461, plan definition-and-proof-of-done) on 2026-10-08, as the maintainer's ask: "a standalone plan to fix a factory fault: the implement-work-item workflow's pr stage dies with the generic label 'ACP turn failed' after review and replay have already approved, leaving a merged-ready item blocked as a false 'needs-human' gate." The maintainer's own words were not available to the opening sub-agent; this is the relay's wording, recorded verbatim.

## Definition of Done assertions derived from that statement

- A dispatch whose publish branch must be rebased onto a default branch that moved after publish_draft reaches a ready pull request with auto-merge armed, or deliberately unarmed under the item's merge hold, without any agent turn in the publish leg, on a factory whose sandbox pre-push aggregate takes longer than the agent harness's default foreground timeout.
- A run that ends because the harness moved an agent stage's tool call to the background reports, on the drive result, in the dispatch journal and on the item's ledger record, the failing stage, the backgrounded command and a transport-fault classification at that stage, and does not describe the item as waiting on a human answer.
- In every agent stage of implement-work-item that runs on the Claude adapter, a foreground shell call that exceeds its timeout is reported to the agent as a timed-out call it can retry with a raised timeout in the same turn, rather than moved to a background task that ends the turn.

# The pr stage dies on a backgrounded push: failure analysis and mechanism candidates (2026-10-08)

Status of this note: the opening research note of plan
`pr-stage-backgrounded-push-fault`. It records what was measured on two
exported runs, tests the mechanism the dispatching session handed over and
corrects it where the evidence disagrees, surveys prior art in this ledger,
and lays out candidate mechanisms with their costs and a recommended order. It
decides nothing that binds an implementer; the scoping event and the child
work-items come later.

The Definition of Done assertions above this heading are SESSION-DERIVED. The
plan was opened by a sub-agent on the maintainer's instruction with no
maintainer present to confirm them, so they are a proposal to be confirmed,
not a ruling.

All times are UTC. "The harness" means the Claude Code runtime that the
`@agentclientprotocol/claude-agent-acp` adapter embeds and that every Claude
ACP stage of `implement-work-item` runs inside. "The engine" means the Fabro
build on the factory (`factory-integration` fork, `8869e88` on `hp` as of
2026-10-01). "The hook" means this repository's pre-push hook as installed in
the sandbox by the prepare chain (lefthook `pre-push` running
`dev-tooling/just-check-pre-push.sh`, then the ledger-conformance leg).
"The aggregate" means `just check`, the full enforcement suite the hook runs
when its green token misses.

## 1. The fault in one paragraph

After the `review` and `proof_verify` stages have approved an implementation,
the `pr` stage — an agent turn whose only job is to rebase, push, mark the
draft pull request ready and arm auto-merge — dies twice with the generic
label `ACP turn failed`. The structured cause on every attempt is the engine's
own `BackgroundedTool` fault: a shell call the agent made was moved to a
background task by the harness, and the engine (by the design of
`bd-ib-bindom`) terminated the turn rather than let the agent continue beside
a detached process. The run then routes to the `needs_human` terminal, the
dispatcher records the item as `blocked / needs-human`, and the operator is
sent looking for a question nobody asked. In both measured runs the only work
lost was marking an already-reviewed pull request ready, and recovery cost a
full re-implementation.

## 2. What was measured

Two runs, both on factory `hp`, both with the Claude adapter on every ACP
node (`npx -y @agentclientprotocol/claude-agent-acp`, `provider_used.json`
`mode: acp`). Both dumps were read with `fabro dump <run> --server
https://hp-xubuntu.perch-rudd.ts.net:32276`; the `events.jsonl` sequence
numbers below are from those exports.

### 2.1 bd-ib-qm4luz, run 01M44F9E56XCEWZNMVJX4M14Z6 (2026-10-04)

| seq | time | event |
|---|---|---|
| 271-274 | 22:32:28 | `janitor` script `mise exec -- just check`: exit 0 in 192,816 ms on HEAD `05079eac` |
| 280-283 | 22:35:41 | `publish_draft` script push: exit 0 in 6,561 ms; hook printed `green token check: matched - skipping full aggregate` for tree `53c0068b`; pull request 2581 opened as draft on `feat/bd-ib-qm4luz` at head `05079eac` |
| 289-481 | 22:35:49-22:53:00 | `proof_capture`, `review`, `proof_verify` all succeeded; captured and verified records posted on 2581 at 22:45:59 and 22:52:44 |
| 487 | 22:53:01 | `pr` stage, attempt 1 of 2 (agent) |
| 496-497 | 22:53:16 | `git fetch origin master --quiet && git rebase origin/master`: completed, 1,665 ms (HEAD moves off `05079eac`) |
| 500-501 | 22:53:21-22:57:37 | `git push -u origin HEAD:refs/heads/feat/bd-ib-qm4luz 2>&1`: **status failed, 256,153 ms** |
| 502 | 22:57:40 | `git push -u origin HEAD:refs/heads/feat/bd-ib-qm4luz 2>&1 \| tail -100` started |
| 503-504 | 22:59:42 | session deactivated; `stage.failed`: `ACP turn failed`, cause `ACP tool call toolu_01528c... (git push ... \| tail -100) continued in background as task b9hp9md1u; Fabro terminated the turn before the agent could start conflicting work`, category `deterministic`, wall 401,031 ms, `will_retry: true` |
| 506 | 22:59:46 | `pr` attempt 2 of 2 |
| 519-520 | 23:00:04-23:04:05 | same push: **status failed, 241,424 ms** |
| 521-523 | 23:04:07-23:06:09 | same push with `\| tail -100`: backgrounded after about 122 s; `stage.failed` with the same cause string, wall 383,472 ms, `will_retry: false` |
| 524 | 23:06:09 | edge `pr -> needs_human` (`condition failed`) |
| 530-532 | 23:06:10-23:10:26 | `needs_human` script: push of `refs/heads/needs-human/01M44F9E56XCEWZNMVJX4M14Z6` **succeeded in 255,839 ms** (`LIVESPEC_NEEDS_HUMAN_PRESERVED`); the node exits 1 by design |
| 539 | 23:10:27 | `run.failed`, reason `workflow_error`: `stage needs_human failed with no outgoing fail edge`; `final_git_commit_sha` `2aaa5085` |

Forge state read 2026-10-08: pull request 2581's only commit is `05079eac`; the
rebased head `2aaa5085` never reached `feat/bd-ib-qm4luz`. It survives only as
`refs/heads/needs-human/01M44F9E56XCEWZNMVJX4M14Z6`. The pull request was later
marked ready by hand and merged at 00:53 on 2026-10-05 as `6b04670a`; the
attribution of its proof records to the item needed `bd-ib-yebrb7`.

### 2.2 bd-ib-555xcd, run 01M4C9GDZ7RYB477YXSMNMJWKH (2026-10-08)

| seq | time | event |
|---|---|---|
| 727-730 | 02:02:33 | `janitor` `mise exec -- just check`: exit 0 in 259,233 ms on HEAD `84e23051` |
| 736-739 | 02:06:53 | `publish_draft` push: exit 0 in 6,321 ms; pull request 2656 opened as draft at head `84e23051` |
| 745-1137 | 02:07:00-02:50:35 | `proof_capture`, `review`, `proof_verify` all succeeded; records posted on 2656 at 02:31:11 and 02:50:03 |
| 1143 | 02:50:36 | `pr` attempt 1 of 2 |
| 1154-1165 | 02:50:49-02:51:06 | `git fetch ... && git rebase origin/master`: **failed** (conflict); `git status`; Read and a failed Edit of `commands/_dispatcher_proof_evidence.py`; `git checkout --theirs .claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_proof_evid...`; `git rebase --continue`: completed |
| 1168-1169 | 02:51:09-02:55:34 | `git push -u origin HEAD:refs/heads/feat/bd-ib-555xcd`: **status failed, 264,935 ms** |
| 1170-1172 | 02:55:35-02:57:37 | `git push ... 2>&1 \| tail -50` started; backgrounded after about 122 s; `stage.failed`, cause names `toolu_01SQwC... (git push ... \| tail -50) continued in background as task biu9vxrdx`, wall 421,197 ms |
| 1174 | 02:57:43 | `pr` attempt 2 of 2 |
| 1183-1184 | 02:57:56 | rebase: completed in 3,543 ms (HEAD already rebased by attempt 1) |
| 1187-1188 | 02:58:02-03:02:47 | `git push ... 2>&1`: **status failed, 285,311 ms** |
| 1189-1190 | 03:02:48-03:07:06 | `timeout 600 bash -c 'git push -u origin HEAD:refs/heads/feat/bd-ib-555xcd 2>&1' \| tail -100`: **completed, 257,390 ms** (the pipe to `tail` masks the push's exit code) |
| 1191-1194 | 03:07:08-03:07:11 | `git diff --name-only origin/master..HEAD`; `cd /repo && mise exec -- just check-coverage 2>&1 \| head -100`: failed in 1,635 ms (wrong path) |
| 1195-1197 | 03:07:12-03:09:14 | `mise exec -- just check-coverage 2>&1 \| tail -200`: backgrounded after about 122 s; `stage.failed`, cause names `toolu_012TV8... (mise exec -- just check-coverage 2>&1 \| tail -200) continued in background as task bai98447y`, wall 691,549 ms, `will_retry: false` |
| 1198 | 03:09:14 | edge `pr -> needs_human` |
| 1204-1206 | 03:09:15-03:13:31 | `needs_human` script push of the preserved ref: **failed after 256,205 ms** (`LIVESPEC_NEEDS_HUMAN_PUSH_FAILED: tree not pushed; rely on the preserve-by-reference dump pointer`) |
| 1213 | 03:13:33 | `run.failed`, `workflow_error`, `final_git_commit_sha` `6362a904`; run `status.kind` `failed` |

Forge state read 2026-10-08: pull request 2656's commits end at `84e23051`;
the rebased head `6362a904` never reached the branch. The item's ledger
comments record a hand publish at 03:16 that was withdrawn at 03:16:51 because
2656 conflicted with master in `commands/_dispatcher_proof_evidence.py` (18
commits had landed behind it), and a re-dispatch on the normal path at 03:17.

### 2.3 What the stage export does and does not carry

`stages/010-pr@1/status.json` carries exactly four keys — `outcome: failed`,
`notes: null`, `failure_reason: "ACP turn failed"`, `timestamp` — and nothing
else. The cause string lives ONLY in the `stage.failed` events of
`events.jsonl` (and, mirrored, in `run.json` under
`checkpoints[].checkpoint.node_outcomes.pr.failure.causes` and
`loop_failure_signatures`, which reads `pr|deterministic|acp turn failed`).
The `agent.tool.completed` events carry each tool call's title, `status`,
`elapsed_ms` and `is_error`, but NOT the tool's output text: what the first
push printed is not in the export at all. Every duration in section 2 is
therefore an `elapsed_ms` from the events, never a reading of output.

## 3. The mechanism, tested

The dispatching session handed over this account: the `publish_draft` push is
fast because the hook's green token matches; by the `pr` stage the branch has
been rebased, the tree differs, and the hook runs the full aggregate (8-10
minutes) inside the sandbox; the agent's shell tool cannot hold a foreground
call that long, the harness moves it to a background task, and the engine
treats that as fatal. The account is right about the shape and wrong about two
load-bearing details. Each claim below is marked with what supports it.

### 3.1 The green token is keyed on the HEAD tree hash, so any rebase misses it

`livespec_dev_tooling/green_token.py` writes a token holding `git rev-parse
HEAD^{tree}` at the end of a successful full aggregate (the janitor's `just
check` writes it in the sandbox) and `check` exits 0 only when the current
HEAD tree hash equals the token's and the worktree is clean. A rebase onto a
master that moved produces a new tree hash even when the branch's own diff is
byte-identical, so every post-rebase push runs the aggregate. Measured: the
`publish_draft` push took 6.3-6.6 s with `green token check: matched` in its
output; every post-rebase push took 241-285 s. (Read from the module source
and the `publish_draft` output blob in `run.json`.)

### 3.2 The hook costs about four to five minutes in the sandbox, not eight to ten

Four agent pushes and two `needs_human` script pushes ran the hook to
completion: 256, 241, 265, 285, 256 and 256 seconds. The janitor's bare `just
check` on the same sandboxes took 193 and 259 seconds. The 8-10 minute figure
is the host-side pre-push suite; in the sandbox it is 4-5 minutes. This
matters because 4-5 minutes is still more than TWICE the harness's default
foreground budget (section 3.4), so the correction changes no conclusion, but
a child that budgets a script step from the 8-10 minute figure would
over-provision.

### 3.3 The first push of every attempt ran to completion and FAILED; only the retry was backgrounded

This is the correction that matters. In all four `pr` attempts the agent's
first push returned after 241-285 s with `status: failed, is_error: true` —
it was not backgrounded. The backgrounded call was always the SECOND long
call of the attempt: three times a re-run of the same push piped through
`tail`, once a `just check-coverage` piped through `tail`. The harness
backgrounded each of those after about 122 s (section 3.4), which is the
default foreground budget, while the first pushes ran well past it, so the
agent had raised the timeout on the first push and not on the retry.

Why the first push failed differs between the two runs, and the export does
not carry the push output, so both readings are inferences from surrounding
evidence:

- **qm4luz: non-fast-forward against the run's own draft.** The branch was
  at `05079eac` (the `publish_draft` push); after the rebase HEAD was
  `2aaa5085`, not a descendant. The `needs_human` push of a NEW ref from the
  same tree passed the hook and succeeded in 255 s, so the hook was green on
  that tree; the only thing that distinguishes the agent's push is that its
  target ref already existed at a diverged tip. This is exactly the collision
  `bd-ib-e3xm` recorded and the `pr.md` prompt's lease-retry arm was written
  for. Git starts the pre-push hook BEFORE it skips rejected refs (the hook
  process is spawned, then the ref loop skips `REJECT_NONFASTFORWARD` rows
  when writing its stdin), and this repository's hook runs the aggregate
  regardless of what arrives on stdin, so the sandbox spent 4 minutes running
  the full suite for a push git had already decided to reject. Then the agent
  re-ran the push with `| tail -100` — the natural move when a 4-minute hook
  has pushed the one line that matters past the tool's output cap — and the
  re-run died at the default budget.
- **555xcd: a red hook on the rebased, conflict-resolved tree.** The rebase
  conflicted in `commands/_dispatcher_proof_evidence.py` and the agent
  resolved it with `git checkout --theirs` plus `git rebase --continue`. The
  `needs_human` push of a NEW ref from that tree then FAILED after 256 s, so
  the hook was red on it (a non-fast-forward cannot explain a new ref). The
  agent's own next move after its second push was `just check-coverage`,
  which is what a coverage finding in the hook output would provoke. The
  hand publish of pull request 2656 at 03:16 was withdrawn minutes later
  because the branch conflicted with master, which is the same tree state
  seen from the forge.

So the account's "the push takes too long to hold in the foreground" is
true of the RETRY and not of the first push, and the fault needs a first
push that fails for the retry to exist. Two different first-push failures
(a rejected ref, a red aggregate) produced the identical turn fault.

### 3.4 What the harness does at the timeout, and why the engine then kills the turn

Read from the Claude Code 2.1.292 bundle on this host and the project's
changelog (`anthropics/claude-code`, `CHANGELOG.md`):

- The Bash tool's default foreground timeout is 120,000 ms
  (`BASH_DEFAULT_TIMEOUT_MS`), and a model-supplied `timeout` is capped at
  600,000 ms (`BASH_MAX_TIMEOUT_MS`).
- Since 2.0.19 ("Auto-background long-running bash commands instead of
  killing them") a foreground command that reaches its timeout is moved to a
  background task when auto-backgrounding is permitted. The tool result then
  reads `Command running in background with ID: <id>. Output is being written
  to: <path>.` — the plain wording — and since 2.1.210 the timeout case reads
  `Command did not complete within its <n>s timeout and was moved to the
  background (ID: <id>). Output is being written to: <path>.` instead.
- Auto-backgrounding is permitted unless `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`
  is set (added 2.1.4: "disable all background task functionality including
  auto-backgrounding"), the session was started with `--bare` (2.1.286: "a
  shell command that reaches its timeout now stops instead of moving to the
  background"), or the command's first word is on a small deny list. In the
  bundle this is `hd()` returning
  `backgroundTasksDisabled || CLAUDE_CODE_DISABLE_BACKGROUND_TASKS || gr()`,
  and the Bash tool computes `canAutoBackground = !hd() && <first-word check>`
  and arms `onTimeout -> background` only when it is true.

On the engine side, `lib/crates/fabro-acp/src/session.rs` (fork
`factory-integration`, from `4b8cc85e0` "contain backgrounded ACP commands
before retry (bd-ib-bindom)", 2026-09-12) inspects every completed
`tool_call_update` and, when the `raw_output` text starts with the plain
wording above, raises `AcpError::BackgroundedTool`, which the node reports as
`ACP turn failed` with the cause string the tables in section 2 show. The
design is deliberate and correct: `bd-ib-bindom` measured the adapter
translating a background handoff into `status=completed`, after which the
worker launched the same commit AGAIN beside the detached one. Letting the
turn continue is the worse outcome.

So the fault is a collision of three behaviours that are each correct on
their own: the hook takes 4-5 minutes per push; the harness turns a 2-minute
foreground timeout into a background handoff; the engine turns a background
handoff into a fatal turn fault. The prompt (`pr.md`, "Ending the turn — leave
nothing running in the background", landed by `bd-ib-5qlr`) already tells the
agent to raise a long call's timeout instead of backgrounding it, and the
agent did so on the first push and not on the retry. Prompt compliance is not
a mechanism; a design in which a correct agent cannot trip this needs no
prompt.

### 3.5 How the fault reaches the ledger as "needs-human"

`commands/_dispatcher_fabro_terminal.py`:

- `_blocked_outcome` handles a run whose `status_kind` is `blocked` or
  `human_input_required`, and since `bd-ib-bg2zz5` (2026-08-27) renders an
  ENGINE-ESCALATED run — a checkpoint whose `next_node_id` is `needs_human`
  with a non-empty `loop_failure_signatures` — as an escalation naming the
  signature, not as a gate.
- But since plan `ledger-is-the-only-gate` (v093) the `needs_human` node is a
  TERMINAL script that exits 1, so the run ends with `status.kind: failed`
  (`stage needs_human failed with no outgoing fail edge`), never `blocked`.
  That path goes through `_failed_outcome`, which first tries
  `_needs_human_terminal_outcome`: it matches the `LIVESPEC_NEEDS_HUMAN`
  sentinel and returns `status: blocked, stage: fabro-run` with a detail that
  reads `run <id> terminated at the needs_human node (needs-human); the tree
  was preserved on refs/heads/needs-human/<id> ...; answer with
  resolve-blocked:<item>:ready`. It passes NO `fabro_failure_cause`,
  `fabro_failure_category` or `fabro_failure_signature` — the fields the
  sibling `failed` outcome a few lines below does pass — and names neither the
  stage that failed nor why.

Net effect: the `bg2zz5` fix is unreachable for every run that ends at the
`needs_human` terminal, which since v093 is every needs-human ending. The
item is marked `blocked / needs-human`, the dispatch journal and `drive`
result say "terminated at the needs_human node", and the one line a triager
needs — `pr|deterministic|acp turn failed` plus the `BackgroundedTool`
cause — is only in the run export. The same wording covers an agent that
ended with the prompt's needs-human protocol (a decision IS needed) and an
engine fault (no decision exists), which is the mislabel `bg2zz5` fixed for
the `blocked` status and this plan must fix for the terminal.

### 3.6 The triage trap, stated once

Read `events.jsonl` (`stage.failed` → `properties.failure.causes`), or
`run.json` → the latest checkpoint's `loop_failure_signatures` and
`node_outcomes.<node>.failure.causes`. Never the stage `status.json` alone:
it says `ACP turn failed` for a backgrounded tool call, a timed-out turn, an
adapter that could not start, and a provider spend limit alike
(`bd-ib-g56f`, `bd-ib-9ek4`, `bd-ib-qulf`, this plan). And do not expect the
export to carry what a tool call PRINTED: it carries the call's title,
status and elapsed time only.

## 4. This is not the Codex adapter quoting defect

`bd-ib-qulf` (closed 2026-08-27) recorded release 0.82.0's Codex adapter
failing under the same `ACP turn failed` stage label. Its signature is
different in every discriminating field: cause `ACP process exited before
protocol completed: termination=exited, exit_code=1`; adapter stderr carrying
a `SyntaxError: Expected property name or '}' in JSON at position 1` from
`codex-acp/dist/index.js`; adapter `@agentclientprotocol/codex-acp` with a
`CODEX_CONFIG` env whose quotes `shlex::split` had stripped; the failure
BEFORE the protocol handshake, so no tool call ever ran. Both runs here used
`npx -y @agentclientprotocol/claude-agent-acp`, completed dozens of tool calls
in the stage, and carry the explicit `BackgroundedTool` cause. The two share
a label and nothing else. Any triage note or classifier that keys on the
label will conflate them; key on the cause.

## 5. Prior art in this ledger, and what each settled

Scope searched: all 1,189 items of this tenant (`bd list --status all
--limit 0 --json`, 2026-10-08), title, description, notes, acceptance and
design fields, for the strings `ACP turn failed`, `continued in background`,
`run_in_background`/`backgrounded`, `non-fast-forward`/`force-with-lease`,
`pre-push`/`green token`, `human gate`/`needs-human`, and `pr stage`; plus
the named ids. No item describes this fault; a draft filing script for it
exists in the dispatching session's scratch directory and was never run.

- **bd-ib-bindom** (closed 2026-09-12, repo `thewoolleyman/fabro`): the
  engine-side containment this fault is the designed output of. It ruled that
  a backgrounded ACP command ends the turn and that the engine confirms
  process exit before any retry. This plan must not weaken that; it must stop
  the backgrounding from being reached.
- **bd-ib-e3xm** (closed 2026-08-26): the post-publish rebase collides with
  the run's own prior push. Ruled that force-pushing an unknown branch is not
  a fix and that reconciling against the run's OWN prior push, whose
  provenance is known, is; delivered the `pr.md` lease-retry arm. The qm4luz
  first push is this collision; the lease arm was never reached because the
  diagnostic re-push died first. Its first suggested direction — "do not push
  before the rebase, or do not rebase after pushing" — is still open.
- **bd-ib-xw34** (closed 2026-09-06): a run that re-pushes after a rebase and
  is rejected non-fast-forward against its own head reported `failed` with
  `pr_number: null`; ruled the dispatcher must recognise an already-published
  head. Adjacent: there the first push had landed; here it never does.
- **bd-ib-gapagf** (ready, 2026-10-04): the `pr` worker reasoned from stale
  tracking refs, attempted a stale lease, then bare `-f` and `--no-verify`
  despite prohibitions, and under-reported it. Evidence that the publish leg
  is where an agent turn is most dangerous and least valuable; mechanism (1)
  below discharges its "make normal publication decisions use authoritative
  remote observations" ask by construction, and its guard-coverage ask
  becomes moot for a leg with no agent.
- **bd-ib-cvge** (backlog, 2026-09-06): a conflicted rebase at the `pr` stage
  pushed master's workflow-file edits as branch content and the App push was
  refused; `needs_human` preservation failed the same way. Same stage, same
  "rebase at the publish leg" root; its candidate (b) (preserve with workflow
  files reset) is independent of this plan, its candidate (a) is absorbed by
  a script-step rebase that asserts the per-commit workflow diff is empty.
- **bd-ib-ckocwc** (ready, 2026-09-12): measured on two runs the same day
  that a minutes-long gate CANNOT run inside an ACP agent turn
  (`check-mutants` at 44 m, a tool install at 40 m, both ending with the
  identical `continued in background` cause) and ruled "the gate runs as a
  script node with its own timeout — never as an instruction to an agent
  turn", shaped as a repo-declared merge-gate script node between
  janitor/review and `pr`. Mechanism (1) is the same principle applied to
  the publish leg, and its post-rebase aggregate re-run is the same node
  shape; the two should be one node or adjacent nodes, not two designs.
- **bd-ib-bg2zz5** (closed 2026-08-27): the engine-escalated run rendered as
  a human gate; fixed for the `blocked` status. Section 3.5 shows the fix is
  unreachable for the v093 terminal. Its own ruling — "this is a presentation
  defect over accurate state; do not fix the classification" — carries
  over: the `blocked / needs-human` ledger status stays, the rendering and
  the carried fields change.
- **bd-ib-b5dg.1 / bd-ib-5qlr** (closed 2026-09-08 / 2026-10-01): the
  opposite failure of the same primitive — background pollers kept a green
  turn OPEN until the node ceiling. Delivered the "leave nothing running in
  the background" prompt block every ACP prompt now carries. Together with
  `bindom` they bracket the design space: a background task either holds the
  turn open past its ceiling or ends it at once; neither is a turn an agent
  can finish.
- **bd-ib-g56f** and **bd-ib-9ek4** (closed): two earlier `ACP turn failed`
  families (spend limit; Codex compaction 404), both ruled that the cause
  must be surfaced verbatim in the dispatcher envelope and that a permanent
  condition must not be retried as transient. This fault's category is
  already `deterministic` (one engine retry, then park), so retry policy is
  not the issue; cause surfacing at the terminal is.
- **bd-ib-fngpwg** (ready, 2026-10-07, plan `definition-and-proof-of-done`):
  resume a terminated run at its unfinished stage from the published pull
  request. It makes THIS fault cheap to recover from and does not prevent
  it; qm4luz is one of its three measured cases. This plan does not touch it.
- **bd-ib-yebrb7** (closed 2026-10-05): attribution of proof records across
  dispatches and the stale-branch reclaim at re-dispatch; the recovery both
  measured runs used. Not changed here.
- **bd-ib-qulf** (closed): the Codex quoting defect, section 4.
- **bd-ib-rnlks6** (closed): a blocked run holding its scheduler slot. Since
  v093 the `needs_human` terminal ends the run, so no slot is held here.

## 6. Candidate mechanisms, with costs

### (1) Make the publish leg a script node — RECOMMENDED FIRST

Replace the `pr` agent node with a script node (or a short chain of them),
exactly as `publish_draft` already is: fetch; if `origin/<default>` is an
ancestor of HEAD, no rebase and the push is a fast-forward whose hook finds
the janitor's green token; otherwise record `old=$(git rev-parse HEAD)`,
rebase, run the aggregate ONCE as a script step with its own timeout (which
re-validates the rebased tree — today nothing does, the janitor validated the
PRE-rebase tree — and writes the green token so the push's hook is a no-op),
then push with `--force-with-lease=refs/heads/feat/<item>:$old` because the
run itself wrote `$old` and the remote tip is checked against it by git (the
lease is the proof of provenance `bd-ib-e3xm` demanded, with no agent
judgement in the loop); then `gh pr edit`, `gh pr ready`, and `gh pr merge
--<mode> --auto` or nothing under a merge hold, each failing closed with a
named sentinel like the existing script nodes. A conflicted rebase fails
closed to `needs_human` with the conflict listing in the stage log — the
agent's `--theirs` resolution of a product-code conflict in 555xcd is not a
behaviour to preserve.

What moves to the Dispatcher: the pull request title and body, which the
agent authored "from the work-item". The Dispatcher already renders the
goal preamble and `LIVESPEC_PUBLISH_BRANCH` into the run; it can render a
title and a body file (title from the item, body from the Definition of Done
and the item id, ending with the required attribution line) the same way.
Cost: one workflow graph change (keep an unconditional outgoing edge on every
touched node — `bd-ib-kwat` is the precedent for a graph `fabro validate`
rejects), one dispatcher rendering change, the `pr.md` prompt retired, the
`pr_adapter` input retired or left unused, tests for the new script node's
sentinels, and `verify_pr` unchanged. It removes the agent turn, the 4-minute
hook run on a doomed push, the non-fast-forward ambiguity, and the
conflicted-rebase hazard of `bd-ib-cvge` in one move. It is the only
candidate that removes the fault rather than one of its triggers.

Coordinate with `bd-ib-ckocwc`: its merge-gate node and this aggregate
re-run are one node shape and should land as one design.

### (2) Skip the aggregate in the sandbox on a rebased tree — REJECTED

The hook already states that CI is authoritative when it skips on a token
match, so extending the skip to "any sandbox push" is a one-line change. It
is rejected: the repository's rules forbid weakening a gate, `bd-ib-ckocwc`
rules in the opposite direction (the run should fail on its own gates, not at
merge-poll), and the rebased tree is precisely the tree nobody has checked —
555xcd's hook was RED on it. The acceptable form of this idea is mechanism
(1)'s single explicit aggregate run after the rebase, which writes the token
honestly.

### (3) Carry the failing stage and cause through the needs_human terminal — RECOMMENDED SECOND

In `_needs_human_terminal_outcome`, pass `fabro_failure_cause`,
`fabro_failure_category` and `fabro_failure_signature` exactly as
`_failed_outcome` does, and split the detail: when the latest checkpoint's
`loop_failure_signatures` names a stage other than `needs_human` (here
`pr|deterministic|acp turn failed`) render "run <id> failed at stage <pr>
after a non-retryable fault: <cause>; the graph routed it to the needs_human
terminal; no agent asked anything" and name the `BackgroundedTool` /
`TimedOut` / `ProcessExited` families as transport faults at that stage;
when the only signature is the terminal's own, keep today's wording, which
is right for an agent that ended with the needs-human protocol. The ledger
status stays `blocked / needs-human` per `bg2zz5`'s ruling; the `drive`
result, the journal and the ledger comment carry the stage and cause. Cost:
one function, two tests, one `needs-attention` line. It also closes the
`bg2zz5` regression for every v093 terminal ending, not only this cause.

### (4) A mandatory stage-level check that the last tool call completed — ALREADY EXISTS

This is what `bd-ib-bindom` built: the engine inspects every completed tool
call and ends the turn when one was backgrounded. Nothing to add at the
stage level. What is worth adding is below.

### (5) Disable auto-backgrounding in every Claude ACP stage — RECOMMENDED THIRD, defence in depth

Set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in the environment the
Dispatcher renders for Claude ACP nodes (`commands/_acp_node_adapters.py`
renders the adapter env; the engine passes workflow env to the agent process
at launch, per the `github_token_refresh_limited` notice). With it set, a
foreground call that reaches its timeout is KILLED and reported to the agent
as a timed-out call, which the agent can retry with a raised `timeout` inside
the same turn, and `run_in_background` — which every prompt already
forbids — is refused outright. It does not fix the 4-minute-versus-2-minute
mismatch and does not save a run whose work needs more than the 600 s cap in
one call (that is `bd-ib-ckocwc`'s territory); it converts a fatal turn fault
into a recoverable tool error for the implement, fix, proof and review stages
that remain agent turns after (1). Cost: one env line and a probe run proving
the adapter honours it (the adapter spawns the SDK's bundled runtime with the
inherited environment; verify, do not assume). Risk: none identified; a
`--bare` session already behaves this way by design.

### (6) Widen the engine's background detection — fork-side, host-routed

`claude_background_task_id` matches only the plain wording. Since 2.1.210 the
timeout case has its own wording, and the adapter (0.87.0, 2026-10-07,
pinning SDK 0.3.287 which bundles runtime 2.1.287) now also exposes the task
id structurally. On a harness that emits the new wording the engine would
report the backgrounded call as `completed` — the exact false completion
`bindom` was built to refuse — and the worker would proceed beside a
detached push. Both measured runs matched the plain wording, so the runtime
the sandbox resolved on those dates is to be ESTABLISHED by a probe (`npx
-y` resolves the adapter unpinned at each sandbox start), not assumed from
the registry's current version. Either way the parser is fragile: match both
wordings, or read the structured id. Repo `thewoolleyman/fabro`, branch
`factory-integration`, through the host-routed door in
`.ai/fabro-fork-hand-build.md`. Not a prerequisite for (1), (3) or (5).

### (7) Record the triage trap — documentation

An `AGENTS.md` entry under the Fabro section: `status.json` says only `ACP
turn failed`; the cause is in `events.jsonl` and the checkpoint's
`loop_failure_signatures`; the export carries no tool output; the needs-human
label on the ledger does not mean a question was asked. Small, and it is what
a triager reads first.

### Recommended order and why

(1) removes the fault. (3) makes the next fault of any cause legible at the
ledger without an export. (5) protects the stages that stay agent turns. (6)
is a fork item on its own clock and must not block the three above. (7) rides
with (3). (2) is rejected; (4) exists.

## 7. Definition of Done, derivation

The session-derived assertions at the head of this note map to: the first to
mechanism (1) (and its aggregate re-run), the second to mechanism (3), the
third to mechanism (5). Each is `host_captured`: the first needs a factory
dispatch of an item whose master moved after `publish_draft`, on a factory
whose sandbox hook takes longer than 120 s; the second needs a run that ends
on a transport fault and a read of the `drive` result and the ledger record;
the third needs a probe run whose agent deliberately exceeds a call's timeout
and reads a timeout error rather than a background handoff. None can be
`factory_captured` from inside the run that exhibits the behaviour.

## 8. Open questions for the scoping session

1. Whether (1) lands as one script node or a chain (`pr_refresh`,
   `pr_gate`, `pr_publish`), and whether `bd-ib-ckocwc`'s merge-gate node is
   the same node. One design, one graph change.
2. Where the pull request title and body are rendered: Dispatcher-side file
   in the run bundle, or a workflow input. The attribution line is fixed
   text either way.
3. Whether the rebase in the publish leg should move EARLIER — before
   `publish_draft`, so the draft and the proof records already sit on a fresh
   base and the publish-leg rebase is usually a no-op (`bd-ib-e3xm`'s first
   suggested direction). The proof records name the head they were captured
   on; a rebase after capture changes the head, which `bd-ib-fngpwg`'s resume
   refusal keys on. This interaction needs a ruling before (1) is cut.
4. Whether `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` is honoured through the
   adapter, established by a probe before (5) is filed as a behaviour.
5. Which runtime version the sandbox actually resolved on 2026-10-04 and
   2026-10-08, for (6); a probe that prints the adapter's and runtime's
   versions from inside a sandbox settles it.

## 9. Boundary

Owned here: the publish leg's design, the terminal's rendering and carried
fields, the agent-stage background policy, the engine parser's wording
dependency (as a routed fork item), and the triage note. Not owned here:
resuming a terminated run from its pull request (`bd-ib-fngpwg`, plan
`definition-and-proof-of-done`); the repo-declared merge-gate suite's
CONTENT (`bd-ib-ckocwc`, coordinated on node shape only); the needs_human
preservation push's own failure modes (`bd-ib-cvge` candidate (b)); the
`pr` worker's stale-ref reasoning (`bd-ib-gapagf`, mooted by (1) if (1)
lands, otherwise its own item).
