# Triaging an ACP turn failed stage

Moved word for word from `AGENTS.md` §"Triaging an `ACP turn failed` stage" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

## Triaging an `ACP turn failed` stage — the cause is not in `status.json`

**`ACP turn failed` is the one string in the export that carries no
information, and the stage's own `status.json` carries nothing else.** It is
the label the engine puts on every ACP turn failure whatever the real fault
was — a shell call the harness moved to a background task, an adapter that
exited before the protocol handshake, a turn that hit its ceiling, a provider
spend ceiling. Four conditions with four different remedies, one label.

A triager who opens the failed stage's export first sees exactly four keys.
Measured on `stages/010-pr@1/status.json` of run
`01M44F9E56XCEWZNMVJX4M14Z6`: `outcome: failed`, `notes: null`,
`failure_reason: "ACP turn failed"`, `timestamp` — **and nothing else**. There
is no cause, no category, and no indication that a cause exists elsewhere, so
the file reads like a complete account of a failure whose remedy it cannot
name.

**The cause string lives in the `stage.failed` events of `events.jsonl`**, and
is mirrored in `run.json` under
`checkpoints[].checkpoint.node_outcomes.<node>.failure.causes` plus
`loop_failure_signatures` (which reads `pr|deterministic|acp turn failed` —
itself the generic label again, so the signature is not a substitute for the
chain). Read it with:

```bash
~/.fabro/bin/fabro dump <run> --server <factory> -o <export-dir>
python3 - <<'PY' <export-dir>/events.jsonl
import json, sys
for line in open(sys.argv[1], encoding="utf-8"):
    event = json.loads(line)
    if event.get("type", "").endswith("stage.failed"):
        print(json.dumps(event, indent=2))
PY
```

**Take the LAST element of the cause chain, never the first.** Measured
2026-08-22 over every failure block in the 53 failed runs on hp: all 17 blocks
carry exactly two causes, `causes[0]` is the literal constant `ACP protocol
error` in 17 of 17, and `causes[-1]` holds the real message every time. The
outer element identifies the transport and names no fault, so reading
`causes[0]` reports every one of the four conditions above as a bare protocol
error. `_fabro_port_records._root_cause` already does this correctly; the
exposure is to a human reading a dump by hand.

**Where a tool call's output lives depends on the engine — a Petri-era dump
DOES carry it.** On the pinned pre-Petri engine, the `agent.tool.completed`
events carry each tool call's title, `status`, `elapsed_ms` and `is_error` but
NOT the tool's output text, so on that engine every duration in a triage
write-up has to be an `elapsed_ms` and never a reading of output. A Petri-era
`fabro dump` export is different: its `events.jsonl` records each ACP tool
call's terminal `status` and its `rawOutput` under
`item.record.body.ev.custom.event.update`. The shape of `rawOutput` depends on
the adapter. A `codex-acp` turn records an object with `exit_code` and
`formatted_output`. A `claude-acp` turn records the output as a plain string
with no separate exit code. Measured 2026-10-25 on petri: run
`01M5QNH88NHN68ST28Y80CZJ48` (bd-ib-8zyan, Codex implement) carries 129
`{exit_code, formatted_output}` records, and among them is the Green amend's
full hook output with `exit_code` 1 and the three pyright errors that failed
`check-types`. Run `01M5RDS52FQ1NX5W8QB6W3E3R4` (bd-ib-eqiw4f, ended at a
`claude-acp` `dod_gate`) carries 23 string records.

**So classify an implement ending — hook killed, gate failed, agent stopped —
from the commit tool call's recorded `exit_code` and output, never from the
agent's own closing message.** On bd-ib-8zyan the agent's closing line said the
hook "terminated without moving HEAD" while the recorded commit call held
`exit_code` 1 and the failing gate's errors; a triager who trusted the account
misclassified the run, and the coordinator caught it from the dump.

And `fabro inspect --json` is NOT the dump: it returns a one-element list whose
record carries only a single top-level `checkpoint` (no `checkpoints` array),
so the historical per-node cursor a dump shows is absent there. Use `inspect`
for the terminal state and `dump` for the causal history.

**A backgrounded-tool cause is not a question anybody asked.** Its wording is
`ACP tool call <id> (<the command>) continued in background as task <task>;
Fabro terminated the turn ...`, the graph routes the run to `needs_human`, and
the item rests at `blocked / needs-human` — which looks exactly like an agent
asking for a decision. It is not: no agent asked anything and no answer is
owed. The Dispatcher now classifies this and says so on the dispatch detail,
the dispatcher stderr, the dispatch journal and a durable
`livespec-needs-human-cause` ledger comment on the item; that comment is the
only one of the four that outlives the run record, so read it first when
triaging after the run has been pruned or reaped. Full measurement: epic
`bd-ib-ctagnf`, opening research note "Failure analysis and mechanism
candidates", section "What the stage export does and does not carry".
