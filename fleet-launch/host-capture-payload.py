#!/usr/bin/env python3
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
"""Build a host_recorded Proof-of-Done payload from a registry-resolved capture dispatch.

The expected server is RESOLVED from the repository's committed
dispatcher.default_factory through the host factory registry, never hard-wired.

Usage: host-capture-payload.py <repo-path> <acceptance-item> <pr-number>
       <dispatched-item> <out.json> [<exercised-master-head>] [<observed-by-session>]

Run it UNDER the tenant's credential wrapper. It prints the payload path, and exits
non-zero, writing nothing, when any piece of evidence is missing, so a capture that
did not happen can never be published.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _capture_evidence import (
    HEAD_ARG,
    JOURNAL,
    MIN_ARGS,
    OBSERVED_BY_ARG,
    OUT,
    REFUSED,
    REGISTRY,
    RefusedError,
    first_host_captured_assertion,
    installed_build,
    journal_rows,
    launcher_log,
    release_containment,
    resolve_server,
    sh,
)

__all__: list[str] = ["build_payload", "dispatch_texts", "main", "read_capture"]


def dispatch_texts(*, dispatched: str, build: str, observed_by: str) -> tuple[str, str]:
    """Return (the proof's dispatch line, the replay step that dispatch maps to)."""
    if observed_by:
        return (
            f"$ observe-capture {dispatched}   # read-only /proc observer of {observed_by}'s "
            f"own dispatch (no factory pin); launched nothing, build {build}",
            f"Observe, read-only, the session {observed_by}'s own dispatch of a ready item of "
            f"this repository ({dispatched}), whose launcher sets no LIVESPEC_FABRO_FACTORY and "
            f"passes no --factory, on the registered orchestrator build {build}: record the argv "
            "of the fabro run process it spawned and whether LIVESPEC_FABRO_FACTORY is present in "
            "the environment of that process and each readable ancestor.",
        )
    return (
        f"$ env -u LIVESPEC_FABRO_FACTORY drive.py --action impl:{dispatched}   "
        f"# CAPTURE_NULL=1, no --factory, build {build}",
        f"Dispatch a ready item of this repository ({dispatched}) through drive.py --action "
        f"impl:{dispatched} on the registered orchestrator build {build}, with "
        "LIVESPEC_FABRO_FACTORY unset and no --factory flag (launcher CAPTURE_NULL=1), and "
        "record the argv of the fabro run process it spawned.",
    )


def read_capture(*, dispatched: str, default: str, server: str, fabro: str) -> tuple[str, str, str]:
    """Return (the captured argv line, the launcher log excerpt, the factory board rows)."""
    argv_file = OUT / f"{dispatched}-r267.capture-argv"
    if not argv_file.exists():
        msg = f"no capture argv file {argv_file}"
        raise RefusedError(msg)
    argv_line = argv_file.read_text().strip()
    if f"--server {server}" not in argv_line:
        msg = f"captured argv does not name the {default} server {server}"
        raise RefusedError(msg)
    log = launcher_log(dispatched=dispatched)
    if "CAPTURE argv OK" not in log:
        msg = f"no launcher log with 'CAPTURE argv OK' for {dispatched}"
        raise RefusedError(msg)
    ps = sh(
        argv=[
            "bash",
            "-c",
            f"{fabro} ps -a --server {server} | grep -F 'Work-item: {dispatched}' | head -3",
        ]
    )
    if not ps:
        msg = f"{dispatched} has no run listed on {server}"
        raise RefusedError(msg)
    return argv_line, log, ps


def build_payload(*, argv: list[str]) -> Path:
    repo, item, pr, dispatched, out = Path(argv[1]), argv[2], argv[3], argv[4], Path(argv[5])
    head_arg = argv[HEAD_ARG] if len(argv) > HEAD_ARG else ""
    observed_by = argv[OBSERVED_BY_ARG] if len(argv) > OBSERVED_BY_ARG else ""
    default, server, fabro = resolve_server(repo=repo)
    slug = sh(
        argv=["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=repo
    )
    merge = sh(
        argv=[
            "gh",
            "pr",
            "view",
            pr,
            "--repo",
            slug,
            "--json",
            "mergeCommit",
            "--jq",
            ".mergeCommit.oid",
        ]
    )
    if not merge:
        msg = f"PR {pr} has no merge commit"
        raise RefusedError(msg)
    tag, tag_commit, containment = release_containment(
        repo=repo, slug=slug, merge=merge, head_arg=head_arg
    )
    argv_line, log, ps = read_capture(
        dispatched=dispatched, default=default, server=server, fabro=fabro
    )
    rows = journal_rows(repo=repo, dispatched=dispatched, server=server)
    cfg = sh(
        argv=[
            "bash",
            "-c",
            'grep -nE \'"default_factory"|"registry": true|"legacy"|"petri"\' '
            ".livespec.jsonc | head -8",
        ],
        cwd=repo,
    )
    build = installed_build(repo=repo)
    dispatch_line, dispatch_step = dispatch_texts(
        dispatched=dispatched, build=build, observed_by=observed_by
    )
    exercised = f"release {tag}" if tag != "none" else f"origin/master commit {tag_commit}"
    proof = "\n".join(
        [
            f"$ gh pr view {pr} --repo {slug} --json mergeCommit   # merge {merge}",
            f"$ git tag --contains {merge}   # {containment}",
            f"$ grep -nE 'default_factory|registry|legacy|petri' .livespec.jsonc   # {repo.name}",
            cfg,
            f"$ cat {REGISTRY}   # control node",
            REGISTRY.read_text().strip(),
            dispatch_line,
            log,
            f"$ cat {dispatched}-r267.capture-argv",
            argv_line,
            f"$ grep {dispatched} {repo.name}/{JOURNAL}   # factory resolution rows",
            *[json.dumps(r) for r in rows],
            f"$ fabro ps -a --server {server} | grep {dispatched}",
            ps,
        ]
    )
    steps = [
        f"On the control node, confirm {slug} PR {pr}'s merge {merge} is contained in the "
        f"exercised build ({exercised}), and read the committed .livespec.jsonc factory table "
        f"and the rendered registry {REGISTRY}.",
        dispatch_step,
        "Read that dispatch's factory-resolution journal rows, then read the created run on the "
        f"server the registry maps the committed default factory {default} to ({server}) with "
        "fabro ps -a.",
    ]
    payload = {
        "build": {"release_tag": tag, "installed_build": build, "commit": tag_commit},
        "assertions": [
            {
                "text": first_host_captured_assertion(repo=repo, item=item),
                "steps": steps,
                "proof": proof,
            }
        ],
    }
    out.write_text(json.dumps(payload, indent=2))
    return out


def main(*, argv: list[str]) -> int:
    if len(argv) < MIN_ARGS:
        print(__doc__, file=sys.stderr)
        return REFUSED
    try:
        print(build_payload(argv=argv))
    except RefusedError as refusal:
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return REFUSED
    return 0


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv))
