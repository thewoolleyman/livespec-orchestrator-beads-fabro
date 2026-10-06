"""Both public routes read a packaged asset's CONTENT from the retained release.

The sibling `test_payload_public_cli_routes_after_eviction.py` establishes that
the two entry points work-item `bd-ib-mtuqxb` NAMES keep RUNNING after their
installation is evicted. It is deliberately weak about what they then DO: it
accepts any `int` helper exit code and any `failed` envelope, and its own
docstring concedes that "neither public route above reaches a `.fabro/` asset
without starting a factory run". So it cannot distinguish a route that
completed meaningful work from one that merely survived to report a failure.

This file closes that gap with an EXACT outcome on both routes, and it does it
through a surface that reads a packaged asset's CONTENT after the eviction: the
committed `dispatcher.minimum_release` floor. The floor resolves the executing
release by reading `plugin.json` out of the tree the Dispatcher's own modules
were loaded from, compares it against the committed value, and refuses. So one
refusal line is simultaneously evidence of deferred code imports (the floor,
policy-settings and staleness-gate modules are imported well after the
launcher), of a packaged asset CONTENT read (the release STRING, not a path
probe), and of helper subprocess execution (on the drive route the refusal is
produced by a `scripts/bin/dispatcher.py` child).

The installed fixture carries a DISTINGUISHABLE release, `7.1.0`, against a
committed floor of `9.9.9`. `7.1.0` appears nowhere but that installation's
own manifest, and the installation is DELETED before the floor is evaluated,
so the only tree that can still supply the string is the retained payload.

Zero side effects, and they are measured rather than asserted by construction.
The floor refusal lands in `prepare()`, which returns before `load_items`, so
nothing is claimed. `dispatcher.fabro_bin` points at a RECORDER that appends
its argv to a log and the log must not exist, so "no factory run was started"
is observed instead of assumed. The ledger is the in-memory fake, and the item
named does not exist.

Two committed `dispatcher.step_waivers` entries clear the `source-checkout`
and `master-ci` preflights, which sit in `dispatch_preamble` AHEAD of the
floor. The waiver is the repository's own sanctioned escape, named verbatim in
those refusals' remedies; without it a hermetic temporary directory can never
reach `prepare()` at all, and the route would stop at a precondition that has
nothing to do with payload retention. Reaching the floor is the whole point of
the fixture.

WHAT MAKES THIS A GUARD RATHER THAN A TAUTOLOGY, measured 2026-10-06 against
an extract of `refs/recovery/bd-ib-mtuqxb/cycle-10-corrected-red` — the tree
whose floor still resolved the executing release through `plugin_root()`, the
install path the harness owns. Post-eviction that path is gone, so the release
read None and the floor could not be evaluated. That tree emitted:

    WARNING: dispatcher plugin currency could not be determined: the committed
    dispatcher.minimum_release floor '9.9.9' could not be evaluated because
    the executing release is unobservable. Dispatch proceeds.

and it DID proceed — past the floor and into work selection, far enough to
report the item missing from the tenant. So the pre-fix tree let a dispatch
run past a committed floor written to stop it.

Note what that control also shows: the exit code was 3 on BOTH trees, so the
exit code alone discriminates NOTHING here. Only the exact refusal text
separates "refused below the floor" from "could not tell, proceeding" — which
is precisely why this file asserts the string and the release rather than a
status.

NOT a Red, and it must not be read as one. The behaviour it pins was
implemented by this work-item's earlier Red-Green pairs, so it passed the
moment it was written; its value is the control above plus the exactness the
sibling lacks.

The wrapper double RUNS the child and propagates its exit status, which is what
a real `with-<project>-env.sh` does, and it writes the child's output to a file
it then `cat`s to STDOUT. Both of those are load-bearing, for a reason this
docstring ORIGINALLY GOT WRONG.

CORRECTION, measured 2026-10-06. This file first claimed the `exec`-form
double's failure to drive `dispatch` was "fixture mechanics, not product
behaviour … so the shape is not mistaken for a finding". That was false, and
backwards: it IS product behaviour, and it IS a finding. `_bootstrap`'s
credential self-heal runs the wrapper with `capture_output=True` and then, at
lines 276-284, branches:

    if completed.returncode != 0 and not stdout:
        ... write wrapper_launch_failure ...
    elif stderr:
        ... write the child's stderr ...

So a child that REFUSES — non-zero exit, diagnostic on STDERR, empty STDOUT —
takes the first arm, and the `elif` is skipped: its real stderr is DISCARDED,
not supplemented, and the operator is handed "credential_wrapper could not run
in this environment" instead. Measured directly: a dispatch whose floor
refusal read `release 7.1.0 is below the committed … floor 9.9.9` emitted that
wrapper-launch message and the genuine refusal appeared NOWHERE in the output.
The sibling's `exec`-form double works only because `ledger-check` succeeds
and prints to stdout.

That is why this double routes the child's output through stdout: it is a
fixture working AROUND a real product behaviour, which is the opposite of the
fixture artifact the original wording claimed. The behaviour is NOT repaired
here — that is outside this work-item's declared assertions — and it is
recorded as an additive incident in
`plan/dispatcher-cache-lifetime/research/003-red-provenance-cycles-9-to-11-2026-10-06.md`
so the next reader examines it instead of trusting a "not a finding" label.

Real child processes are the only way to ask any of this, so this file is
listed in `pyproject.toml`'s `subprocess_spawn_allowlist` and scrubs the
coverage subprocess hooks exactly as an allowlisted spawn must.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"
_PLUGIN_BLOCK = "livespec-orchestrator-beads-fabro"

_CLI_TIMEOUT_SECONDS = 300.0
_WRAPPER_SEPARATOR = "--"
_MISSING_ITEM = "bd-pb-does-not-exist"
# The fixture installation's release, and a floor above it. `7.1.0` exists
# nowhere but that installation's own `plugin.json`, which is what makes the
# string in the refusal evidence of a CONTENT read from the retained copy.
_INSTALLED_RELEASE = "7.1.0"
_FLOOR = "9.9.9"
_EXIT_PRECONDITION_ERROR = 3

# Injects the secrets the self-heal re-execs to obtain, EVICTS the installation,
# and scrubs the payload hand-down variable exactly as the real wrapper's `sudo`
# stage does — so the child has to reach a usable tree from its own argv. Then
# it RUNS the child and propagates its exit status.
_WRAPPER_DOUBLE = """#!/bin/sh
[ "$1" = "--" ] && shift
printf 'invoked\\n' > "$LIVESPEC_TEST_WRAPPER_MARKER"
if [ -n "$LIVESPEC_TEST_EVICT" ]; then rm -rf "$LIVESPEC_TEST_EVICT"; fi
unset LIVESPEC_RETAINED_PAYLOAD_ROOT
BEADS_DOLT_PASSWORD=test-not-a-real-secret
GITHUB_APP_ID=test-not-a-real-app-id
GITHUB_PRIVATE_KEY=test-not-a-real-key
export BEADS_DOLT_PASSWORD GITHUB_APP_ID GITHUB_PRIVATE_KEY
"$@" > "$LIVESPEC_TEST_CHILD_LOG" 2>&1
status=$?
cat "$LIVESPEC_TEST_CHILD_LOG"
exit $status
"""

# A factory binary that RECORDS rather than runs. Its log must never exist.
_FABRO_RECORDER = """#!/bin/sh
printf '%s\\n' "$@" >> "$LIVESPEC_TEST_FACTORY_LOG"
exit 0
"""


@pytest.fixture(name="install_parent")
def _install_parent() -> Iterator[Path]:
    """A directory for the fixture installation that is OUTSIDE any git worktree.

    Deliberately NOT `tmp_path`. The gate's FIRST question is whether the
    plugin root is a git checkout, because a checkout is exempt from every
    currency question by design — and something in this suite's session
    fixtures leaves a `.git` at the pytest basetemp root, so every path under
    `tmp_path` resolves as a worktree. Measured 2026-10-06: `git -C
    <basetemp>/<test>/install rev-parse --absolute-git-dir` answered
    `<basetemp>/.git`. An intact installation placed there therefore takes the
    checkout exemption, the floor is never evaluated, and the control reads as
    a product failure when it is a fixture artifact.

    This also keeps the EVICTED cases honest. Under `tmp_path` they reached
    the floor partly because the deleted path can no longer answer `rev-parse`
    at all — so the exemption was being dodged by the eviction rather than by
    the installation genuinely not being a checkout. A harness-managed plugin
    cache (`~/.claude/plugins/cache/<build>`) is not inside a worktree, and
    this is that shape.
    """
    parent = Path(tempfile.mkdtemp(prefix="livespec-public-route-exact-"))
    try:
        yield parent
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def _install(*, root: Path) -> Path:
    """The real plugin root, copied aside and re-stamped with a known release."""
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    _ = (root / "plugin.json").write_text(
        json.dumps({"name": _PLUGIN_BLOCK, "version": _INSTALLED_RELEASE}),
        encoding="utf-8",
    )
    return root


def _target_repo(*, root: Path, recorder: Path, wrapper: Path) -> Path:
    (root / ".beads").mkdir(parents=True)
    # The FLAT dotted form `bd` uses, and the one the launcher's server-mode
    # marker matches — a nested mapping does not, which would make the secret
    # optional and the re-exec never happen.
    _ = (root / ".beads" / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    config = {
        _PLUGIN_BLOCK: {
            "connection": {
                "tenant": "probe-tenant",
                "prefix": "bd-pb",
                "database": "probe-tenant",
                "server_user": "probe-tenant",
                "fake": True,
            },
            "dispatcher": {
                "minimum_release": _FLOOR,
                "fabro_bin": str(recorder),
                "step_waivers": [
                    {
                        "step": "source-checkout",
                        "owner": "tests/bin",
                        "reason": "hermetic temporary dispatch target has no origin to prove",
                    },
                    {
                        "step": "master-ci",
                        "owner": "tests/bin",
                        "reason": "hermetic temporary dispatch target has no pipeline to read",
                    },
                ],
            },
        },
        "credential_wrapper": [str(wrapper), _WRAPPER_SEPARATOR],
    }
    _ = (root / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return root


def _script(*, path: Path, body: str) -> Path:
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _not_a_checkout(*, root: Path) -> bool:
    """Whether the gate will see `root` as something OTHER than a git checkout.

    Asserted rather than assumed, because the exemption's failure mode is
    silent: a plugin root the gate reads as a checkout skips the floor
    entirely and the dispatch proceeds with no finding at all. A control that
    could not have observed the refusal is not a control.
    """
    probe = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return probe.returncode != 0


def _run(*, argv_of, tmp_path: Path, install_parent: Path, evict: bool):
    """Run one packaged CLI under the double, optionally evicting its install."""
    install_root = _install(root=install_parent / f"install-{evict}")
    assert _not_a_checkout(root=install_root), (
        f"the fixture installation at {install_root} resolves as a git checkout, so "
        "the gate takes its checkout exemption and the minimum-release floor is "
        "never evaluated — this control cannot observe what it asserts"
    )
    recorder = _script(path=tmp_path / f"fabro-{evict}.sh", body=_FABRO_RECORDER)
    wrapper = _script(path=tmp_path / f"wrapper-{evict}.sh", body=_WRAPPER_DOUBLE)
    repo = _target_repo(root=tmp_path / f"repo-{evict}", recorder=recorder, wrapper=wrapper)
    factory_log = tmp_path / f"factory-{evict}.log"
    marker = tmp_path / f"marker-{evict}"

    scrubbed = ("PYTHONPATH", "COVERAGE_PROCESS_START")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    _ = env.pop("BEADS_DOLT_PASSWORD", None)
    _ = env.pop("LIVESPEC_CREDENTIAL_REEXEC", None)
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["LIVESPEC_BEADS_FAKE"] = "1"
    env["LIVESPEC_TEST_WRAPPER_MARKER"] = str(marker)
    env["LIVESPEC_TEST_EVICT"] = str(install_root) if evict else ""
    env["LIVESPEC_TEST_FACTORY_LOG"] = str(factory_log)
    env["LIVESPEC_TEST_CHILD_LOG"] = str(tmp_path / f"child-{evict}.log")

    completed = subprocess.run(
        [sys.executable, *argv_of(install_root=install_root, repo=repo)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        check=False,
        timeout=_CLI_TIMEOUT_SECONDS,
    )
    return completed, install_root, repo, factory_log, marker


def _expected_refusal() -> str:
    """The floor's refusal, verbatim, naming the JUDGED release and the floor.

    The release half is the load-bearing one: it is read from the retained
    payload, the only tree that still carries it once the installation is
    gone. The INSTALLATION the operator must act on is named in the same
    refusal and is asserted separately by the drive case, because that pair is
    what shows the judged-release / named-install split.
    """
    return (
        f"ERROR: dispatcher plugin release {_INSTALLED_RELEASE} is below the committed "
        f"dispatcher.minimum_release floor {_FLOOR}."
    )


def _drive_argv(*, install_root: Path, repo: Path) -> list[str]:
    return [
        str(install_root / "scripts" / "bin" / "drive.py"),
        "--repo",
        str(repo),
        "--action",
        f"impl:{_MISSING_ITEM}",
        "--invoker",
        "test:public-route-exact",
        "--json",
    ]


def _dispatcher_argv(*, install_root: Path, repo: Path) -> list[str]:
    return [
        str(install_root / "scripts" / "bin" / "dispatcher.py"),
        "dispatch",
        "--repo",
        str(repo),
        "--item",
        _MISSING_ITEM,
        "--invoker",
        "test:public-route-exact",
    ]


def test_the_drive_route_helper_reads_the_retained_releases_manifest_after_eviction(
    tmp_path: Path, install_parent: Path
) -> None:
    """The packaged drive route: helper runs from the payload, exact outcome."""
    completed, install_root, _repo, factory_log, marker = _run(
        argv_of=_drive_argv, tmp_path=tmp_path, install_parent=install_parent, evict=True
    )

    assert marker.exists(), (
        "the credential wrapper was never invoked, so the installation was never "
        f"evicted mid-invocation:\n{completed.stdout}\n{completed.stderr}"
    )
    assert not install_root.exists(), "the wrapper did not actually evict the installation"
    assert completed.stdout.strip(), (
        "the packaged drive route produced no result at all after its installation "
        f"was evicted:\nexit={completed.returncode}\n{completed.stderr}"
    )

    payload = json.loads(completed.stdout)
    helper_argv = payload["dispatcher"]["argv"]
    assert not helper_argv[1].startswith(f"{install_root}{os.sep}"), (
        "the drive route resolved its Dispatcher helper inside the evicted "
        f"installation, so the helper could not have run: {helper_argv}"
    )
    # EXACT, not `isinstance(..., int)`: the helper refused at the floor.
    assert (
        payload["dispatcher"]["exit_code"] == _EXIT_PRECONDITION_ERROR
    ), f"the helper did not refuse at the precondition exit: {payload['dispatcher']}"
    helper_stderr = payload["dispatcher"]["stderr"]
    assert _expected_refusal() in helper_stderr, (
        "the helper did not read the retained release's own manifest content; a "
        "release it could not observe would have produced the non-blocking "
        f"'could not be determined' warning instead:\n{helper_stderr}"
    )
    assert str(install_root) in helper_stderr, (
        "the refusal did not name the INSTALLATION an operator must update, so "
        f"the judged-release / named-install split is not shown:\n{helper_stderr}"
    )
    assert (
        not factory_log.exists()
    ), f"a factory run was started on a refusal: {factory_log.read_text(encoding='utf-8')}"


def test_the_packaged_dispatcher_entry_point_reaches_the_same_exact_outcome(
    tmp_path: Path, install_parent: Path
) -> None:
    """The direct Dispatcher route, refusing on the same asset content read."""
    completed, install_root, _repo, factory_log, marker = _run(
        argv_of=_dispatcher_argv, tmp_path=tmp_path, install_parent=install_parent, evict=True
    )

    assert marker.exists(), "the credential wrapper was never invoked"
    assert not install_root.exists(), "the wrapper did not actually evict the installation"
    assert completed.returncode == _EXIT_PRECONDITION_ERROR, (
        "the packaged Dispatcher entry point did not refuse at the precondition "
        f"exit:\nexit={completed.returncode}\n{completed.stdout}\n{completed.stderr}"
    )
    combined = f"{completed.stdout}\n{completed.stderr}"
    assert _expected_refusal() in combined, (
        "the direct Dispatcher route did not read the retained release's manifest "
        f"content after its installation was evicted:\n{combined}"
    )
    assert not factory_log.exists(), "a factory run was started on a refusal"


def test_an_intact_installation_reaches_the_identical_refusal(
    tmp_path: Path, install_parent: Path
) -> None:
    """The read-only control: eviction did not manufacture the answer.

    Without this, every assertion above is equally consistent with "the floor
    refused because the release came from the retained payload" and with "the
    floor refused for some reason the eviction introduced". The same refusal
    from an INTACT installation settles which.
    """
    completed, install_root, _repo, factory_log, marker = _run(
        argv_of=_dispatcher_argv, tmp_path=tmp_path, install_parent=install_parent, evict=False
    )

    assert marker.exists(), "the credential wrapper was never invoked"
    assert install_root.is_dir(), "the control evicted the installation after all"
    assert (
        completed.returncode == _EXIT_PRECONDITION_ERROR
    ), f"the intact control did not refuse:\n{completed.stdout}\n{completed.stderr}"
    combined = f"{completed.stdout}\n{completed.stderr}"
    assert (
        _expected_refusal() in combined
    ), f"the intact control produced a different refusal:\n{combined}"
    assert not factory_log.exists(), "a factory run was started on a refusal"
