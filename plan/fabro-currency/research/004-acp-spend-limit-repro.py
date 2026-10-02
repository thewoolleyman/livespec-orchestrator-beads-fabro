"""Bounded, no-provider-call reproducer for Fabro v0.371.0-nightly.0.

Run: python3 004-acp-spend-limit-repro.py /absolute/path/to/fabro
Exit 0 means the recorded defect was reproduced, NOT that the candidate passed.
Only a new temporary directory and its private Unix-socket server are mutated.
"""

import hashlib
import json
import os
import secrets
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

__all__: list[str] = []

BINARY_SHA256 = "bd6366c6b1ce687c92944c48c005f042fc7cdd3e298d51ce5d849788fe478447"
MODES = ("success", "exit-once", "monthly-cap", "usage-cap")
RUN_ARG_COUNT = 2


def emit(*, value):
    sys.stdout.write(value + "\n")
    sys.stdout.flush()


def require(*, condition, evidence):
    if not condition:
        raise AssertionError(evidence)


def qualified_binary(*, binary):
    binary = Path(binary).resolve(strict=True)
    with binary.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != BINARY_SHA256:
        message = "Refusing an unqualified binary: SHA256 differs from the exact candidate"
        raise SystemExit(message)
    return binary


def write_settings(*, root):
    settings = root / "settings.toml"
    settings.write_text("""_version = 1
[server.auth]
methods = ["dev-token"]
[server.web]
enabled = false
[run.clone]
enabled = false
[run.run_branch]
enabled = false
push = false
[run.environment]
id = "local"
[cli.updates]
check = false
""")
    return settings


def cli_for(*, binary, root, env):
    def cli(*args, check=True):
        # The executable was hash-verified; argv is fixed or derived from fresh fixture paths.
        return subprocess.run(  # noqa: S603
            [str(binary), *args, "--no-upgrade-check"],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
            check=check,
        )

    return cli


def wait_for_server(*, server, root):
    deadline = time.monotonic() + 15
    while not (root / "probe.sock").exists():
        if server.poll() is not None or time.monotonic() > deadline:
            message = f"Private server did not start; inspect {root / 'server.log'}"
            raise RuntimeError(message)
        time.sleep(0.1)


def selected_evidence(*, events):
    evidence = []
    for event in events:
        item = event.get("item", {})
        body = item.get("record", {}).get("body", {})
        kind = body.get("event")
        probe_finished = (
            kind == "step.finished"
            and item.get("subject", {}).get("node", {}).get("name") == "probe"
        )
        if probe_finished or kind in ("invocation.finished", "run.finished"):
            evidence.append(body)
    return evidence


def run_case(*, cli, root, mode):
    case = root / mode
    target = case / "target"
    target.mkdir(parents=True)
    attempts = case / "attempts.jsonl"
    graph = case / "workflow.fabro"
    command = shlex.join(
        [
            "/usr/bin/python3",
            str(Path(__file__).with_name("004-fake-acp-agent.py").resolve()),
            mode,
            str(attempts),
        ]
    )
    graph.write_text(f"""digraph CurrencyAcpProbe {{
  graph [goal="Local fixture only", backend="acp", acp.command={json.dumps(command)}]
  start [shape=Mdiamond]
  probe [prompt="Local fixture", max_retries=1, goal_gate=true]
  exit [shape=Msquare]
  start -> probe -> exit
}}
""")
    result = cli(
        "run",
        str(graph),
        "--server",
        str(root / "probe.sock"),
        "--environment",
        "local",
        "--target-from",
        str(target),
        "--auto-approve",
        "--json",
        check=False,
    )
    (case / "events.jsonl").write_text(result.stdout)
    (case / "stderr.txt").write_text(result.stderr)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    if events:
        inspection = cli(
            "inspect", events[0]["run_id"], "--server", str(root / "probe.sock"), "--json"
        )
        (case / "inspect.json").write_text(inspection.stdout)
    return {
        "mode": mode,
        "exit_code": result.returncode,
        "run_id": events[0]["run_id"] if events else None,
        "prompt_attempts": len(attempts.read_text().splitlines()) if attempts.exists() else 0,
        "evidence": selected_evidence(events=events),
    }


def verify_case(*, summary):
    mode, evidence = summary["mode"], summary["evidence"]
    cap = mode in ("monthly-cap", "usage-cap")
    require(
        condition=summary["prompt_attempts"] == (1 if mode == "success" else 2), evidence=summary
    )
    steps = [row for row in evidence if row["event"] == "step.finished"]
    require(condition=len(steps) == summary["prompt_attempts"], evidence=summary)
    failed = steps if cap else steps[:-1]
    require(
        condition=all(
            row["outcome"]["status"]["failure"]["class"] == "retry_requested" for row in failed
        ),
        evidence=summary,
    )
    if not cap:
        require(condition=steps[-1]["outcome"]["status"] == "success", evidence=summary)
    terminal = [row for row in evidence if row["event"] == "run.finished"]
    require(condition=len(terminal) == 1, evidence=summary)
    require(condition=terminal[0]["status"] == ("failed" if cap else "success"), evidence=summary)
    require(condition=summary["exit_code"] == (1 if cap else 0), evidence=summary)


def run_cases(*, cli, root, token):
    cli("auth", "login", "--server", str(root / "probe.sock"), "--dev-token", token)
    # This tag requires a ready provider even for ACP-only graphs. Only a
    # fake value is stored in this server's private vault; ACP never uses it.
    cli("secret", "set", "OPENAI_API_KEY", "local-fixture-invalid-key")
    summaries = []
    for mode in MODES:
        summary = run_case(cli=cli, root=root, mode=mode)
        summaries.append(summary)
        (root / "results.json").write_text(json.dumps(summaries, indent=2) + "\n")
        emit(value=json.dumps(summary))
        verify_case(summary=summary)
    emit(value="REPRODUCED: both cap errors retried; this is NOT a qualification pass.")


def reproduce(*, binary):
    binary = qualified_binary(binary=binary)
    root = Path(tempfile.mkdtemp(prefix="fabro-currency-acp-"))
    emit(value=f"Evidence directory: {root}")
    # Do not inherit provider credentials, credential wrappers, or factory targets.
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ["HOME"], "FABRO_HOME": str(root / "home")}
    socket = root / "probe.sock"
    env["FABRO_SERVER"] = str(socket)
    # Fresh synthetic credentials, used only by this private fixture instance.
    token = "fabro_dev_" + secrets.token_hex(32)
    server_env = dict(env)
    server_env["SESSION_SECRET"] = secrets.token_hex(32)
    server_env["FABRO_DEV_TOKEN"] = token
    settings = write_settings(root=root)
    with (root / "server.log").open("w") as log:
        # The executable was hash-verified; every writable path is in our new temp directory.
        server = subprocess.Popen(  # noqa: S603
            [
                str(binary),
                "server",
                "start",
                "--foreground",
                "--no-web",
                "--config",
                str(settings),
                "--storage-dir",
                str(root / "storage"),
                "--bind",
                str(socket),
                "--max-concurrent-runs",
                "1",
            ],
            env=server_env,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
        )
        try:
            wait_for_server(server=server, root=root)
            run_cases(cli=cli_for(binary=binary, root=root, env=env), root=root, token=token)
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            # Evidence is deliberately retained; no broad cleanup or shared state.


def main():
    if len(sys.argv) != RUN_ARG_COUNT:
        raise SystemExit(__doc__)
    reproduce(binary=sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
