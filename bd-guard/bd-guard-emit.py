#!/usr/bin/env python3
"""Fire-and-forget OTLP/HTTP emitter for the bd-guard wrapper. Fail-open:
any error is swallowed and the process exits 0 so telemetry can never affect
bd. Invoked detached by bd-guard.sh; reads span fields from BDG_* env."""

import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

__all__: list[str] = ["main"]


def _s(*, v):
    return {"stringValue": str(v)}


def _b(*, v):
    return {"boolValue": bool(v)}


def _i(*, v):
    try:
        return {"intValue": str(int(v))}
    except (TypeError, ValueError):
        return {"intValue": "0"}


def _read_int(*, name):
    # Read a BDG_* env var as an int, fail-open to 0 (missing / unparseable).
    try:
        return int(os.environ.get(name) or 0)
    except (TypeError, ValueError):
        return 0


def main():
    ep = os.environ.get("LIVESPEC_BD_GUARD_OTLP_ENDPOINT", "http://127.0.0.1:4319/v1/traces")
    argv = os.environ.get("BDG_ARGV", "")
    # derive subcommand = first non-flag token
    sub = ""
    for tok in argv.split():
        if not tok.startswith("-"):
            sub = tok
            break
    start_ns = _read_int(name="BDG_START_NS")
    end_ns = _read_int(name="BDG_END_NS")
    if not end_ns:
        end_ns = time.time_ns()
    if not start_ns:
        start_ns = end_ns
    exit_code = _read_int(name="BDG_EXIT")
    cwd = os.environ.get("BDG_CWD", "")
    repo = Path(cwd).name if cwd else ""
    attrs = [
        {"key": "bd.subcommand", "value": _s(v=sub)},
        {"key": "bd.argv", "value": _s(v=argv)},
        {"key": "guard.warned", "value": _b(v=os.environ.get("BDG_WARNED") == "1")},
        {"key": "guard.op", "value": _s(v=os.environ.get("BDG_OP", ""))},
        {"key": "guard.mode", "value": _s(v=os.environ.get("BDG_MODE", "warn"))},
        {"key": "exit_code", "value": _i(v=exit_code)},
        {"key": "duration_ms", "value": _i(v=max(0, (end_ns - start_ns)) // 1_000_000)},
        {"key": "bd.caller.ppid", "value": _i(v=os.environ.get("BDG_PPID") or 0)},
        {"key": "bd.caller.comm", "value": _s(v=os.environ.get("BDG_COMM", ""))},
        {"key": "bd.caller.cmd", "value": _s(v=os.environ.get("BDG_CALLER_CMD", ""))},
        {"key": "bd.cwd", "value": _s(v=cwd)},
        {"key": "bd.repo", "value": _s(v=repo)},
    ]
    payload = {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": _s(v="bd-guard")}]},
                "scopeSpans": [
                    {
                        "scope": {"name": "bd-guard"},
                        "spans": [
                            {
                                "traceId": secrets.token_hex(16),
                                "spanId": secrets.token_hex(8),
                                "name": "bd.invoke",
                                "kind": 1,
                                "startTimeUnixNano": str(start_ns),
                                "endTimeUnixNano": str(end_ns),
                                "attributes": attrs,
                                "status": {"code": 2 if exit_code != 0 else 1},
                            }
                        ],
                    }
                ],
            }
        ]
    }
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    # S310: both Request and urlopen below target our own FIXED local OTLP
    # collector over a constant http:// endpoint (LIVESPEC_BD_GUARD_OTLP_ENDPOINT,
    # default 127.0.0.1:4319), not attacker-controlled input. Fail-open: any
    # error is suppressed and never affects bd.
    req = urllib.request.Request(ep, data=data, headers=headers)  # noqa: S310
    try:
        urllib.request.urlopen(req, timeout=2).read()  # noqa: S310
    except (OSError, TimeoutError, urllib.error.URLError):
        return


if __name__ == "__main__":
    main()
    sys.exit(0)
