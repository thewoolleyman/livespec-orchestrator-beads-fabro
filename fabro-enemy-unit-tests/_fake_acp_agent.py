"""No-network ACP agent fixture for the Enemy Unit Tests.

A copy of plan fabro-currency research fixture 004-fake-acp-agent.py, carried
INSIDE the suite so the tier 1 ACP-launch test keeps working after that plan is
archived. It speaks only enough ACP (initialize, session/new, session/prompt)
to answer one prompt, refuse it with a provider-cap error, or exit once. It
never invokes a model or a provider API. The sandbox runs it from the cloned
repository, so this file must exist on the commit the run observes.
"""

import json
import sys
from pathlib import Path

__all__: list[str] = []


def emit(*, value):
    sys.stdout.write(value + "\n")
    sys.stdout.flush()


def agent(*, mode, record_path):
    """Speak only enough ACP to answer a prompt, fail it, or exit once."""
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
            attempt = len(record.read_text().splitlines()) + 1 if record.exists() else 1
            with record.open("a") as stream:
                stream.write(json.dumps({"mode": mode, "attempt": attempt}) + "\n")
            if mode == "exit-once" and attempt == 1:
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
