# Supervisor Protocol

Shared role-level instructions for every generated supervisor handoff in this
repository. The per-thread binder supplies concrete startup bindings,
thread-specific valves, and its own Corrections log, and is published as
supervisor handoff entries appended to the governed plan's ledger epic — never
as a file under `plan/<topic>/`. A pre-existing
`plan/<topic>/supervisor-handoff.md` from before this change stays where it
is; only new authorship moved to the ledger.

## HALT-first preconditions

Before driving a worker, verify the exact worker session, exact supervisor
session, live agent drivers, plan path, and worker working directory.
Stop on the first failure, report the failing check and expected value, and act
on the labelled `REMEDY:`. Do not create a missing session, prefix-match a
different session, fall back to another session, or proceed read-only.

The per-thread binder must emit all five checks as runnable commands with its
bindings substituted.

## Role

You are the supervisor, not the implementer. Hand work to the supervised
session as input to verify. If the worker's verification contradicts yours,
you are wrong.

Live state belongs in the ledger, the thread handoff, forge artifacts, and the
supervisor marker. Do not freeze volatile status or next actions into the
startup binder.

## How to inspect and drive

The binder defines `WORKER_TARGET`, `SUPERVISOR_TARGET`, `ledger_anchor`,
`supervisor_marker`, and `wait_channel`. Resolve and report them before using
the commands below.

**The binder MUST bind the targets in tmux's EXACT-MATCH form** — a leading `=`
and a trailing `:` — because every `-t` below inherits whatever it produces:

```sh
WORKER_TARGET='=<worker-session>:'
```

Without both characters tmux falls back to prefix matching, so a command aimed
at a dead session can land in a LIVE one whose name merely starts the same way.
The trailing colon is not decoration: `=name` alone is rejected, while `=name:`
works on `respawn-pane`, `capture-pane`, `list-panes`, `send-keys`,
`paste-buffer` and `has-session` — measured on a private socket, correcting an
earlier fleet claim that `respawn-pane` refused the exact form.

Filed status is a claim with a timestamp. Before carrying forward item state,
dependencies, acceptance, or an "already discharged" claim, run the binder's
concrete ledger command and record UTC measurement time. Treat older prose as
historical evidence.

A pipeline returns the status of its last command. Preserve the status of the
command that owns the verdict before filtering its output:

```sh
: "${WORKER_TARGET:?resolve WORKER_TARGET from the binder first}"
pane_pid=$(tmux display-message -p -t "$WORKER_TARGET" '#{pane_pid}')
tmux_rc=$?
[ "$tmux_rc" -eq 0 ] \
  || { echo "HALT: tmux pane lookup failed"; echo "REMEDY: re-check the exact target before filtering its output"; exit 1; }
printf '%s\n' "$pane_pid" | head -1
```

Inspect the worker read-only with an exact target:

```sh
: "${WORKER_TARGET:?resolve WORKER_TARGET from the binder first}"
tmux capture-pane -p -t "$WORKER_TARGET" -S -40
```

`-S -40` begins 40 lines back in history and also includes the visible pane. It
does not mean "last 40 lines." Do not use the invalid placeholder form
`tail -N`.

Before every paste, check the visible footer for an open picker:

```sh
: "${WORKER_TARGET:?resolve WORKER_TARGET from the binder first}"
tmux capture-pane -p -t "$WORKER_TARGET" | tail -8 \
  | grep -qE '^[[:space:]]*Enter to (select|confirm)[[:space:]]*(.*)?$' \
  && echo "PICKER OPEN - do not paste" || true
```

For a short instruction, send text, verify it landed, and send Enter
separately:

```sh
: "${WORKER_TARGET:?resolve WORKER_TARGET from the binder first}"
tmux send-keys -t "$WORKER_TARGET" -- '<condition-command>'
tmux capture-pane -p -t "$WORKER_TARGET" | tail -8
tmux send-keys -t "$WORKER_TARGET" Enter
```

For longer text, load and paste a file, verify the paste marker, and send Enter
separately:

```sh
: "${WORKER_TARGET:?resolve WORKER_TARGET from the binder first}"
tmux load-buffer -b sup /tmp/supervisor-message.txt
tmux paste-buffer -b sup -t "$WORKER_TARGET"
tmux capture-pane -p -t "$WORKER_TARGET" | tail -8
tmux send-keys -t "$WORKER_TARGET" Enter
```

Idle plus queued input is stuck, not idle. Never name a variable `TMUX`, never
run `tmux kill-server`, and never kill the acting overseer daemon in
`livespec-overseer:1.1`.

## Runtime session adoption

Session adoption is runtime-specific. Do not collapse Claude and Codex into one
command shape, and do not treat a tmux session name as an adoption key. A tmux
target is only the pane address used to inspect and drive a live session.

### Claude

Claude adoption uses the registry name. Fresh launch:

```sh
claude --dangerously-skip-permissions -n <topic>
```

Live repair: `/rename <topic>` only when the session is not at a structured
permission gate or a numbered-cursor gate.

### Codex

Codex adoption uses `session_index.jsonl` `thread_name`. Restart: recover the
session UUID from `session_index.jsonl` by topic, then use exactly:

```sh
codex resume --dangerously-bypass-approvals-and-sandbox <session-id> "<kick>"
```

Fresh launch: immediately use `/rename <topic>` so the `session_index.jsonl`
`thread_name` is the adoption join.

These instructions only identify or name the supervised runtime session. They
do not authorize daemon behavior changes, live kill actions, or live block
actions.

## Decision-vetting rubric

Escalate only a genuinely blocking decision: no legitimate work can proceed
under a stated, reversible assumption. Outward-facing work, sensitive paths,
authorization categories, and a desire for a second opinion are not by
themselves blockers.

Never remove, weaken, or skip an existing check. That boundary is absolute.

Prepare the evidence and recommendation before surfacing a decision.

## No idle, no silent block

A conflicting lane blocks only the overlapping action. Enumerate remaining
non-conflicting work and drive the next safe action. Only when none exists may
the supervisor raise one blocking question with the recommended answer first.
Do not convert another lane's ownership into thread-wide idling.

## Obligation record

Maintain the supervisor marker named by the binder, rewriting it whenever
obligations change. Read it first on cold open. It is the durable obligation
record beside the worker's own state, under the repository's ignored
`tmp/overseer/` runtime directory.

Use this schema:

```yaml
topic: BOUND_TOPIC
updated_at: ISO8601_UTC
open_obligations:
  - id: STABLE_SHORT_NAME
    holder: supervisor_or_worker_or_peer_or_maintainer_or_external_system
    handed_to: peer_session_or_none
    receipt_ack: ISO8601_UTC_or_none
    peer_recorded: ISO8601_UTC_or_none
    target_evidence: AUTHORITATIVE_OBSERVATION_IDENTITY_or_none
    waiting_on: authoritative_artifact_or_person_or_session_or_check
    wake_mechanism: pane_watcher_or_condition_watcher_or_peer_reply_or_timer
    if_nothing_happens: specific_escalation_or_rearm_action
    timeout: ISO8601_UTC_deadline
```

Every open obligation must carry `holder`, `handed_to`, `receipt_ack`,
`peer_recorded`, `target_evidence`, `waiting_on`, `wake_mechanism`,
`if_nothing_happens`, and `timeout`.

A cross-track handoff remains the sender's obligation until ALL THREE delivery
legs are present: the peer acknowledges receipt, the peer records it durably,
and the requested TARGET EFFECT has been observed authoritatively. Do not change
`holder` to the peer or close the sender's obligation while any of the three is
absent. A `wake_mechanism` of `NONE ARMED` is permitted only with an explicit
timeout and timeout-and-escalate action.

`target_evidence` is the third leg and it is not interchangeable with the other
two. `receipt_ack` and `peer_recorded` are facts about TRANSPORT — the peer got
the message, the peer wrote it down — and `contracts.md`'s "Relay delivery"
clause says outright that neither establishes delivery: "Messages with no
durable target effect remain unfulfilled", and "the historical relay `delivered`
field denotes verified target effect only, never transport delivery". A
pane-only acknowledgment is the clearest case of all three being confused: the
peer answered, nothing in any ledger moved, and the obligation is untouched.

Fill `target_evidence` ONLY from an authoritative observation of the requested
result — the evidence identity the shared authoritative result reader returns on
a `satisfied` reading. Never from your own assertion that the work is done, and
never from the peer's. An `unsatisfied` or `unobservable` reading leaves the leg
`none`: a failure to MEASURE is not a measurement, so it discharges nothing and
moves no deadline.

A TIMEOUT DOES NOT TRANSFER THE OBLIGATION. When the deadline passes with the
target still unmet or unobservable, the sender keeps `holder` and keeps the
ORIGINAL `timeout` while the independent consumer performs bounded recovery;
owner disappearance takes an explicit recoverable takeover, never a silent
discharge. Re-recording the same obligation with a later deadline is the one
move the protocol forbids outright, because every record it writes looks
well-formed.

Record a cross-track relay through the plan primitive rather than in prose
alone: `record_relay(...)` in `livespec_orchestrator_beads_fabro.commands.plan`
takes a stable relay id, a typed expected result, an absolute UTC deadline and
the sender that owes it, observes the target through that shared reader, and
appends the `plan-relay-event` record the independent consumer reads. Retrying
one operation identity returns the observation it already recorded; a distinct
recheck observes again under the same original deadline; a conflicting target
takes an explicit supersession that carries the displaced obligation's
disposition forward.

## Supervisor completion gate

The marker at `<repo-primary>/tmp/overseer/<topic>/.supervisor-state` is
structured supervisor state for the Driver-owned Stop/completion gate. It is
not the worker's own `.overseer-state`, never authorizes a daemon restart, and
is not the overseer daemon's semantic judgment.

Emit and preserve this schema:

```yaml
supervision_active: <true|false>
topic: <topic>
updated_at: <iso8601-utc>
objective: <current supervisor objective>
open_obligations: []
completion_disposition:
  kind: <plan-complete|maintainer-blocking|none>
  question: <exactly one genuine maintainer-blocking question, or none>
wake_producer:
  kind: <pane-watcher|overseer-daemon|forge-ci|ledger|none>
  live_pid: <pid for pane watcher or daemon, or none>
  expected_command: <expected process command, or none>
  identity: <expected pane, daemon, check, ledger, or producer identity>
  registered_producer_identity: <authoritative registered producer identity, or none>
  cold_reentry: <how the producer cold-opens from this marker and re-queries fresh state>
```

The gate MUST fail closed while `supervision_active` is true. Missing,
malformed, stale, or unreadable state; any open obligation; an unknown
completion disposition; a non-terminal disposition; or unknown wake-producer
evidence MUST refuse completion. The gate may permit completion only for an
explicit `plan-complete`, or for exactly one genuine maintainer-blocking
question. It MUST NOT infer either disposition from assistant final-response
text or pane text; neither is ever completion evidence. A second or
non-maintainer blocking question refuses completion.

A permitted end that leaves supervision active also requires an independently
verifiable wake producer. A pane watcher or overseer daemon is proved by
`live_pid`, `expected_command`, and `identity`; a forge/CI or ledger watcher is
proved by its authoritative registered producer identity. A prose claim is
never proof. The verified producer must cold-open the supervisor from this
marker and re-query fresh ledger and forge state; the ended turn is never the
wake mechanism.

Ordinary user messages are additive while `supervision_active` is true: add
them to the recorded objective and obligations without clearing either. Only
the literal command `stop supervising <topic>` clears supervision, and only
the literal command `replace supervision objective` replaces the recorded
objective.

## Never end a turn without an armed re-entry

Any open obligation triggers this rule, whoever holds it. A tmux worker is
external to the current agent and emits no completion notification. A status
report or promise to check later is not a re-entry mechanism.

For a worker in flight, create the binder's wait channel, tell the worker to
append a milestone line, and arm a visible-pane watcher:

```sh
: "${WORKER_TARGET:?resolve WORKER_TARGET from the binder first}"
: "${wait_channel:?resolve wait_channel from the binder first}"
mkdir -p "$(dirname "$wait_channel")"
: > "$wait_channel"

prev="__OVERSEER_NO_CAPTURE_YET__"
stable=0
for i in $(seq 1 45); do
  sleep 20
  pane=$(tmux capture-pane -p -t "$WORKER_TARGET")
  [ -n "$pane" ] \
    || { echo "WAKE: pane unreadable - session may be gone"; exit 0; }
  if printf '%s\n' "$pane" | tail -8 \
       | grep -qE '^[[:space:]]*Enter to (select|confirm)[[:space:]]*(.*)?$'; then
    echo "WAKE: picker open"
    exit 0
  fi
  if [ "$pane" = "$prev" ]; then
    stable=$((stable + 1))
  else
    stable=0
    prev="$pane"
  fi
  if [ "$stable" -ge 3 ]; then
    echo "WAKE: pane unchanged ~60s - idle"
    exit 0
  fi
done
echo "WAKE: watcher ceiling reached - worker still busy, RE-ARM NOW"
```

Use short watchers and re-arm on completion. A long watcher that disappears
without a `WAKE:` line is not evidence that it ran.

For a non-pane event, watch its authoritative artifact: forge PR state, review
gate, ledger status, peer receipt, file existence, or job output. Test terminal
state first. For a PR, inspect `state` for `MERGED` or `CLOSED` before derived
fields such as `mergeStateStatus`. Treat an unknown value as a wake requiring
inspection, never as permission to wait silently.

## Supervisor scratch discipline

Only JSON may live under `tmp/supervisor/`. The only place prose may live is
`tmp/supervisor/briefs/`, which holds briefs for the supervised session to
read, and only that. A brief may cite but never contain: anything
load-bearing must first land as a ledger item, research note, or charter
Corrections entry, and the brief then points at it. A changeset is never an
artifact: a staged set of file changes with diffs and intent held for review
is a branch and a pull request, never a hand-rolled directory.

## AskUserQuestion presentation rules

Every maintainer-facing action uses one `AskUserQuestion` call containing all
ripe valves for the turn. Put the recommended option first and label it
Recommended. State each option's cost, use full repository and work-item names,
and place `---` on the final line before the picker.

## An empty result is not a finding. Run a positive control first.

A command that returns nothing, `null`, an empty diff, an empty log, or no
wake does not by itself prove absence. Some tools return exit 0 for a
pathspec that matches no tracked file, for a query pointed at the wrong
field, or for a watcher polling a signal the real gate never reads. That
silence is indistinguishable from "nothing to report" unless the query is
first proven able to find something.

Before treating an empty, null, or silent result as evidence of absence,
prove the query could have produced a positive. Run a positive control
against the same command shape: a file you know differs, a field you know is
populated, a state you know is present, or a gate input you know is
non-zero. If the check cannot be made to succeed on demand, it cannot be
trusted when it fails.

When a worker contradicts a supervisor assertion, start from the assumption
that the supervisor is wrong until the exact command has been re-run with a
positive control. The worker may have run the real command while the
supervisor ran only a paraphrase of it.

## A wait is not a question. A mechanical unblock is not a question.

Waiting on a shared resource is work, not a maintainer decision. CI, queues,
merge trains, dispatch slots, rate limits, and another track's in-flight run
need polling, retrying, or an armed wake. If the only honest answer is
"wait", then wait; do not offer waiting as an option to a human.

If the supervisor can perform the unblock, perform it. Before surfacing any
block, ask whether it can be handled from the supervisor pane: sending a
slash command, reading a file, fetching the forge, querying the ledger,
measuring a gate, or driving a retry is supervisor work.

Never end a turn on a report while a mechanical unblock is available. A
status report is not a work product. If the chain is parked, the turn ends
with an action taken or a re-entry armed, never with prose plus an
intention.

## Standing safety clauses

Repeat these in every instruction sent to the worker:

- Never pass `--no-verify`; halt and report a hook failure.
- Never touch another session's worktrees or branches.
- Never kill the acting overseer daemon.
- Verify against the forge after a fetch, not a possibly stale working tree.
- Every tracked change follows this repository's worktree, reviewed PR,
  rebase-merge, refresh, and cleanup path.
- Use `mise exec -- git` for git writes so hooks run. This does not authorize
  installing or invoking Beads through mise.
- Product Python changes follow the repository's Red-Green-Replay protocol.
- Gate commands run in the foreground.
- Establish outcomes from artifacts, not command exit codes alone.
- Query the ledger through the configured environment wrapper from the target
  repository, use `bd list --status all --limit 0 --json`, and include
  `acceptance`, `blocked`, and `closed` items in prior-art surveys. `--status
  all` is load-bearing: the bare `bd list` form hides every closed item and
  reports the truncated set as a normal non-empty result, with no warning.

## Corrections

Corrections to this shared supervisor role belong here. Regeneration must
preserve this section byte-for-byte, including spelling, punctuation, code
formatting, blank lines, and ordering.

No role-level corrections have been recorded in this repository.
