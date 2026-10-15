"""No-network ACP agent fixture for the Enemy Unit Tests.

A copy of plan fabro-currency research fixture 004-fake-acp-agent.py, carried
INSIDE the suite so the tier 1 ACP-launch test keeps working after that plan is
archived. It speaks only enough ACP (initialize, session/new, session/prompt)
to answer one prompt, answer it at length, refuse it with a provider-cap error,
exit once, or judge what it was handed. It never invokes a model or a provider
API. The sandbox runs it from the cloned
repository, so this file must exist on the commit the run observes.

THE `env-probe` MODE IS AN ORACLE, NOT A REPORTER (`bd-ib-4gkfaa`). A DOT
attribute carries a double quote and a backslash in escaped form, and `fabro
validate` accepts that graph on both engines -- but validity says nothing about
the bytes the engine finally hands the agent, which is the only question the
escape rewrite turns on. So this mode RECORDS the environment assignment it
observed and then JUDGES it: an observation that differs from the unescaped
intent exits non-zero, which fails the run. That makes the run's terminal
status the assertion, because the test cannot read a record file written
inside the sandbox.

THE `prompt-bound` MODE IS AN ORACLE FOR THE SAME REASON (`bd-ib-7zxqyl`). The
engine carries a PREAMBLE describing the stages behind a node into that node's
prompt, and nothing the host can read reports how large the carried prompt
finally was -- the record file this agent writes lives in the sandbox. So this
mode measures the prompt it was handed and JUDGES it against
`PROMPT_BOUND_BYTES`, and `bulk-response` beside it is the stage whose very
large answer is what an unbounded carry would put there.
"""

import json
import os
import sys
from pathlib import Path

__all__: list[str] = []

# The environment assignment the escaped-command EUT probes, and the EXACT
# unescaped bytes the agent must observe. `ENV_PROBE_VALUE` is a RAW string, so
# `a\\b` is a, backslash, backslash, b -- the JSON-escaped backslash a real
# `CODEX_CONFIG` prefix carries, alongside the double quotes that used to make
# the whole command a refusal.
#
# Both sides of the round trip read these THREE names rather than their own
# copies: the test builds the adapter command from them and this agent judges
# against them. A second literal could drift, and the round trip would then
# pass on bytes neither side intended -- a green that proves nothing.
ENV_PROBE_MODE = "env-probe"
ENV_PROBE_NAME = "EUT_ACP_CONFIG"
ENV_PROBE_VALUE = r'{"approval_policy":"never","path":"a\\b"}'

# The two modes of the carried-preamble probe, and the ONE declaration of the
# two sizes both sides of it measure against -- the same single-declaration rule
# the `env-probe` triple above is written for.
#
# THE STATED BOUND IS `PROMPT_BOUND_BYTES`: the total UTF-8 bytes of text an
# agent node may be handed. 65536 is chosen against two measurements. The real
# `disposition` node bounds its carry with `fidelity="summary:medium"`, which
# targets about 1500 tokens -- roughly 6000 bytes -- so the bound leaves a
# tenfold margin over the preamble the real graph declares and cannot fail on
# ordinary variation in it. And it is about three percent of the 200000-token
# window that refused that node's prompt on hp-candidate run
# 01M4XNM4BBMYFPQDA6X5JCBDYM, so a prompt under it cannot be the unbounded
# carry this bound exists to catch.
#
# `BULK_RESPONSE_BYTES` is sixteen times the bound, so a carry of even a small
# fraction of the first node's answer breaks it. The probe asserts that
# relation before it launches: a bulk answer smaller than the bound would make
# the probe pass whatever the engine carried.
BULK_RESPONSE_MODE = "bulk-response"
BULK_RESPONSE_BYTES = 1048576
PROMPT_BOUND_MODE = "prompt-bound"
PROMPT_BOUND_BYTES = 65536

# ASCII filler for the bulk answer. A repeated SENTENCE rather than a repeated
# character, so neither the engine nor a transport can shrink the answer by
# collapsing a run of one byte and leave the probe measuring something smaller
# than the stage actually produced.
_BULK_SENTENCE = "The Petri-era preamble carries a prior stage's response forward. "


def emit(*, value):
    sys.stdout.write(value + "\n")
    sys.stdout.flush()


def bulk_response_text():
    """Return exactly `BULK_RESPONSE_BYTES` of ASCII filler."""
    repeats = BULK_RESPONSE_BYTES // len(_BULK_SENTENCE) + 1
    return (_BULK_SENTENCE * repeats)[:BULK_RESPONSE_BYTES]


def prompt_text_bytes(*, params):
    """Total UTF-8 bytes of every `text` field inside one `session/prompt` params.

    The whole structure is walked rather than one block layout indexed, because
    the carried preamble is the engine's to shape: it may arrive as its own
    content block, appended to the node's own prompt block, or nested inside
    either. A measurement keyed on one of those shapes reports zero for the
    other two, which is an instrument that cannot return the hit it was pointed
    at -- and it would report that zero as a prompt comfortably under the bound.
    """
    total = 0
    pending = [params]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "text" and isinstance(nested, str):
                    total += len(nested.encode("utf-8"))
                else:
                    pending.append(nested)
        elif isinstance(value, list):
            pending.extend(value)
    return total


def record_prompt(*, mode, record, params):
    """Append this prompt attempt to `record` and return the entry just written.

    Kept apart from `agent` because recording what the agent SAW is a different
    concern from deciding what to do about it: the deciding lives in
    `prompt_verdict` below, while the observation lands here with the attempt
    counter it belongs to.
    """
    attempt = len(record.read_text().splitlines()) + 1 if record.exists() else 1
    entry = {"mode": mode, "attempt": attempt}
    if mode == ENV_PROBE_MODE:
        entry["observed"] = os.environ.get(ENV_PROBE_NAME)
    if mode == PROMPT_BOUND_MODE:
        entry["observed"] = prompt_text_bytes(params=params)
    with record.open("a") as stream:
        stream.write(json.dumps(entry) + "\n")
    return entry


def prompt_verdict(*, mode, entry):
    """The exit code this prompt attempt must end the agent with, or None.

    All three judgements live together because they are ONE concern -- what the
    agent was handed is not acceptable, so the run must fail -- while `agent`
    owns the protocol. Splitting them would leave half of one concern beside
    the protocol loop and half beside the observation.

    The `prompt-bound` arm writes a stderr line as well as returning its code:
    the code is what fails the run, and the line is what makes the failure
    diagnosable from the stage export, which carries adapter stderr and cannot
    reach the record file.
    """
    if mode == ENV_PROBE_MODE and entry["observed"] != ENV_PROBE_VALUE:
        return 4
    if mode == PROMPT_BOUND_MODE and entry["observed"] > PROMPT_BOUND_BYTES:
        sys.stderr.write(
            f"EUT_PROMPT_BOUND_EXCEEDED: received {entry['observed']} bytes of prompt "
            f"text against a bound of {PROMPT_BOUND_BYTES}\n"
        )
        return 5
    if mode == "exit-once" and entry["attempt"] == 1:
        return 3
    return None


def response_text(*, mode):
    """The agent message text this mode answers a prompt with."""
    if mode == BULK_RESPONSE_MODE:
        return bulk_response_text()
    return "fixture success"


def agent(*, mode, record_path):
    """Speak only enough ACP to answer a prompt, fail it, exit once, or judge it."""
    record = Path(record_path)
    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        response = {"jsonrpc": "2.0", "id": message["id"]}
        method = message.get("method")
        if method == "initialize":
            response["result"] = {"protocolVersion": 1, "agentCapabilities": {}}
        elif method == "session/new":
            response["result"] = {"sessionId": "enemy-probe"}
        elif method == "session/prompt":
            entry = record_prompt(mode=mode, record=record, params=message.get("params"))
            verdict = prompt_verdict(mode=mode, entry=entry)
            if verdict is not None:
                return verdict
            if mode in ("monthly-cap", "usage-cap"):
                text = (
                    "You've hit your org's monthly spend limit · ask your admin "
                    "to raise it at claude.ai/settings/usage"
                    if mode == "monthly-cap"
                    else "You've hit your limit · resets Jul 31, 5am (UTC)"
                )
                response["error"] = {
                    "code": -32603,
                    "message": text,
                    "data": {"errorKind": "rate_limit"},
                }
            else:
                emit(
                    value=json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "method": "session/update",
                            "params": {
                                "sessionId": "enemy-probe",
                                "update": {
                                    "sessionUpdate": "agent_message_chunk",
                                    "content": {
                                        "type": "text",
                                        "text": response_text(mode=mode),
                                    },
                                },
                            },
                        }
                    )
                )
                response["result"] = {"stopReason": "end_turn"}
        else:
            response["result"] = {}
        emit(value=json.dumps(response))
    return 0


def main():
    mode, record_path = sys.argv[1:]
    return agent(mode=mode, record_path=record_path)


if __name__ == "__main__":
    raise SystemExit(main())
