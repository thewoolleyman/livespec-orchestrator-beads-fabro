# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
"""Evidence readers for host-capture-payload.py: each refuses when its evidence is missing."""

import json
import os
import re
import subprocess
from pathlib import Path

# Host configuration: the one place this script names a host value.
ORCH = Path(
    os.environ.get("FLEET_LAUNCH_ORCH_REPO", "/data/projects/livespec-orchestrator-beads-fabro")
)
OUT = Path(os.environ.get("FLEET_LAUNCH_STATE_DIR", str(ORCH / "tmp/petri-canary")))
GATE_RUNS = ORCH / "tmp/gate-runs"
PETRI_CLIENT = os.environ.get(
    "FLEET_LAUNCH_FABRO",
    "/home/ubuntu/.local/state/fabro-currency/carrier-petri-v0.382-adeefec4c/fabro",
)
REGISTRY = Path(os.environ.get("FLEET_LAUNCH_REGISTRY", "/etc/livespec/fabro-factories.json"))
PLUGIN_REGISTRY = Path(
    os.environ.get(
        "FLEET_LAUNCH_PLUGIN_REGISTRY", str(Path.home() / ".claude/plugins/installed_plugins.json")
    )
)
PLUGIN_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
BD = os.environ.get("FLEET_LAUNCH_BD", "/usr/local/bin/bd")
JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"

REFUSED = 2
MIN_ARGS = 6
HEAD_ARG = 6
OBSERVED_BY_ARG = 7
JOURNAL_KEYS = (
    "at",
    "stage",
    "dispatch_id",
    "dispatch_factory",
    "dispatch_factory_server",
    "fabro_run_id",
    "invoker",
)

__all__: list[str] = [
    "BD",
    "HEAD_ARG",
    "JOURNAL",
    "MIN_ARGS",
    "OBSERVED_BY_ARG",
    "OUT",
    "REFUSED",
    "REGISTRY",
    "RefusedError",
    "first_host_captured_assertion",
    "installed_build",
    "journal_rows",
    "launcher_log",
    "release_containment",
    "resolve_server",
    "sh",
]


class RefusedError(Exception):
    """A required piece of evidence is missing; nothing may be written."""


def sh(*, argv: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False).stdout.strip()


def resolve_server(*, repo: Path) -> tuple[str, str, str]:
    """Return (default factory, its registry server, the fabro client that reads it)."""
    found = re.search(
        r'"default_factory"\s*:\s*"([a-z0-9-]+)"', (repo / ".livespec.jsonc").read_text()
    )
    if not found:
        msg = "no dispatcher.default_factory in .livespec.jsonc"
        raise RefusedError(msg)
    default = found.group(1)
    registry = json.loads(REGISTRY.read_text())
    if default not in registry:
        msg = f"default factory {default} does not resolve in the registry"
        raise RefusedError(msg)
    return default, registry[default]["server"], PETRI_CLIENT


def release_containment(
    *, repo: Path, slug: str, merge: str, head_arg: str
) -> tuple[str, str, str]:
    """Return (release tag or "none", the exercised commit, a one-line containment account)."""
    sh(argv=["git", "fetch", "-q", "--tags", "origin"], cwd=repo)
    tags = [
        t
        for t in sh(
            argv=["git", "tag", "--contains", merge, "--sort=creatordate"], cwd=repo
        ).split()
        if t.startswith("v")
    ]
    if tags:
        tag = tags[0]
        remote = sh(argv=["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], cwd=repo)
        if not remote:
            msg = f"tag {tag} is not on the forge remote"
            raise RefusedError(msg)
        commit = sh(argv=["git", "rev-parse", f"{tag}^{{commit}}"], cwd=repo)
        return (
            tag,
            commit,
            f"first release tag: {tag} -> {commit}; on origin: {remote.split()[0][:12]}",
        )
    # No release applies (none is cut for a config-only change): name the default-branch commit the
    # dispatch exercised, which the pass checks for the same ancestry.
    if not head_arg:
        msg = (
            f"no release tag of {slug} contains merge {merge}; "
            "pass the exercised master head as argv[6]"
        )
        raise RefusedError(msg)
    commit = sh(argv=["git", "rev-parse", f"{head_arg}^{{commit}}"], cwd=repo)
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", merge, commit], cwd=repo, check=False
    )
    if ancestry.returncode != 0:
        msg = f"exercised head {commit} does not contain merge {merge}"
        raise RefusedError(msg)
    if not sh(argv=["git", "branch", "-r", "--contains", commit], cwd=repo).count("origin/master"):
        msg = f"exercised head {commit} is not on origin/master"
        raise RefusedError(msg)
    return (
        "none",
        commit,
        "no release tag contains it (none cut for this change); "
        f"exercised origin/master commit {commit}; "
        f"merge-base --is-ancestor {merge[:12]} {commit[:12]}: exit 0",
    )


def journal_rows(*, repo: Path, dispatched: str, server: str) -> list[dict[str, object]]:
    rows = []
    for line in (repo / JOURNAL).read_text().splitlines():
        if dispatched not in line:
            continue
        rec = json.loads(line)
        if rec.get("stage") in ("dispatch-id", "dispatch-run-stamp") and "dispatch_factory" in rec:
            rows.append({k: rec.get(k) for k in JOURNAL_KEYS if k in rec})
    rows = rows[-2:]
    if not rows or rows[-1].get("dispatch_factory_server") != server:
        msg = f"no dispatch-run-stamp row for {dispatched} naming {server}"
        raise RefusedError(msg)
    return rows


def launcher_log(*, dispatched: str) -> str:
    gate = os.environ.get("LAUNCHER_LOG") or sh(
        argv=[
            "bash",
            "-c",
            f"grep -l 'impl:{dispatched}\\|dispatch {dispatched} \\|LISTED.*{dispatched}' "
            f"{GATE_RUNS}/*/output.log | xargs -r grep -l 'CAPTURE_NULL:' | tail -1",
        ]
    )
    if not gate:
        return ""
    return sh(
        argv=[
            "bash",
            "-c",
            "grep -E 'CAPTURE_NULL:|LAUNCH target=|CAPTURE argv|CAPTURE env|"
            f"Permission denied|LISTED' {gate} | cut -c1-240",
        ]
    )


def installed_build(*, repo: Path) -> str:
    installed = json.loads(PLUGIN_REGISTRY.read_text())
    return next(
        e["version"] for e in installed["plugins"][PLUGIN_KEY] if e.get("projectPath") == str(repo)
    )


def first_host_captured_assertion(*, repo: Path, item: str) -> str:
    desc = json.loads(sh(argv=[BD, "show", item, "--json"], cwd=repo))[0]["description"]
    section = desc[desc.index("### Host-captured") :]
    return next(line[2:].strip() for line in section.splitlines() if line.startswith("- "))
