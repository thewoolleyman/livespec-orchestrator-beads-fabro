"""No-network ACP agent fixture for the Enemy Unit Tests.

A copy of plan fabro-currency research fixture 004-fake-acp-agent.py, carried
INSIDE the suite so the tier 1 ACP-launch test keeps working after that plan is
archived. It speaks only enough ACP (initialize, session/new, session/prompt)
to answer one prompt, refuse it with a provider-cap error, or exit once. It
never invokes a model or a provider API. The sandbox runs it from the cloned
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


def emit(*, value):
    sys.stdout.write(value + "\n")
    sys.stdout.flush()


def record_prompt(*, mode, record):
    """Append this prompt attempt to `record` and return the entry just written.

    Kept apart from `agent` because recording what the agent SAW is a different
    concern from deciding what to do about it: the `env-probe` verdict stays
    beside the exit code in `agent`, while the observation lands here with the
    attempt counter it belongs to.
    """
    attempt = len(record.read_text().splitlines()) + 1 if record.exists() else 1
    entry = {"mode": mode, "attempt": attempt}
    if mode == ENV_PROBE_MODE:
        entry["observed"] = os.environ.get(ENV_PROBE_NAME)
    with record.open("a") as stream:
        stream.write(json.dumps(entry) + "\n")
    return entry


def agent(*, mode, record_path):
    """Speak only enough ACP to answer a prompt, fail it, exit once, or judge env."""
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
            entry = record_prompt(mode=mode, record=record)
            if mode == ENV_PROBE_MODE and entry["observed"] != ENV_PROBE_VALUE:
                return 4
            if mode == "exit-once" and entry["attempt"] == 1:
                return 3
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
                                    "content": {"type": "text", "text": "fixture success"},
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
