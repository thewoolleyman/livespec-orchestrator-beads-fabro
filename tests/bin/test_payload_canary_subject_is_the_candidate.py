"""The candidate canary's SUBJECT must be the candidate, not the running build.

Work-item `bd-ib-mtuqxb`'s fifth assertion requires that the retained execution
path preserves "candidate canary outcomes without moving a running Dispatcher to
another payload", and `SPECIFICATION/scenarios.md` `## Scenario 54 — Host-side
dispatch runs a released payload, never the working tree` states the behaviour
as "it validates the newer payload with a canary on this host" and "a failing
canary keeps the last-known-good payload running and alarms a human".

The canary launches the CANDIDATE's own `scripts/bin/dispatcher.py` by pathname
and the parent's environment is inherited, so the candidate child sees the
parent's `LIVESPEC_RETAINED_PAYLOAD_ROOT` hand-down. `retain_payload` adopts an
inherited payload whenever the selected source equals the holder's recorded
source, and that comparison is a PATH comparison — so once a newer build has
landed at the installation path, the path still matches and the candidate adopts
the RUNNING build's payload. The canary then validates the running build against
itself, and a genuinely broken candidate reports PASS.

Measured against the pre-fix tree on 2026-10-06, through this file's own first
case: install A at release 7.1.0 was retained, the installation was replaced by
candidate B at 9.9.9 with one module `ledger-check` imports removed, and the
exported `self_update_after_release` boundary recorded
`self-update-restart-due` on a candidate exit code of 0 — a restart recommended
onto a build that cannot start. The same argv with the hand-down absent exits 1
with `ModuleNotFoundError: No module named
'livespec_orchestrator_beads_fabro.commands._dispatcher_run_checks'`, raised
from a payload provisioned at B's own release, so the canary could have returned
the other answer and the subject was the whole difference.

The candidate is BROKEN rather than incomplete on purpose: it still passes the
launcher's own completeness grade (asserted below), so this is the candidate
REGRESSION class a canary exists to catch, not an unusable payload the launcher
would refuse on its own.

The fix is at the CALL SITE, not in the launcher's adoption rule. A canary
addresses a DIFFERENT BUILD by construction, so the self-update stage must not
hand its own payload down to it; the launcher's adoption rule must keep working
exactly as it does, because `test_payload_public_cli_routes_after_eviction.py`
pins a helper that runs from its parent's payload AFTER the installation is
evicted, and an adoption rule that re-checked the source tree's content would
refuse that child instead of serving it.

The second case is the CONTROL, and it is what a fix cannot satisfy by failing
every canary: a HEALTHY candidate at the same newer release must still record
`self-update-restart-due` on exit code 0. It passes against both the pre-fix and
the fixed tree, by design.

Both cases also assert that the running Dispatcher did not move: its executing
payload root and its running release are unchanged across the boundary call, so
no canary outcome promotes, re-points or re-imports the artifact in flight.

DECLARED HERMETIC FIXTURE SETUP. Both builds are private copies of this clone's
delivered `.claude-plugin`, re-stamped with synthetic release labels so they are
distinguishable without waiting for a real release; no native plugin install,
update or removal happens and no shared cache is touched. The ledger is the
in-memory fake selected by the scratch `.livespec.jsonc`, so no tenant is
contacted; the notification poster is a recorder that makes no network request;
and the credential value is a placeholder, named only as
`BEADS_DOLT_PASSWORD`.

A real child process is required and no in-process call can stand in: the
question is which tree a SECOND process resolves its code from, and the pytest
process is a source checkout that retains no payload at all.

Listed in `subprocess_spawn_allowlist`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_ROOT = _REPO_ROOT / ".claude-plugin"

_CLI_TIMEOUT_SECONDS = 900.0
_PLACEHOLDER_SECRET = "test-not-a-real-secret"
_FIXTURE_TOPIC = "test-fixture-topic-not-a-real-channel"
_RELEASE_A = "7.1.0"
_RELEASE_B = "9.9.9"

# A module the candidate's `ledger-check` imports on the way up. Removing it
# leaves a candidate that still passes the launcher's completeness grade, so
# only the candidate's OWN code can expose the regression.
_CANARY_IMPORTED_MODULE = Path(
    "scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_run_checks.py"
)
_MISSING_MODULE_NEEDLE = "_dispatcher_run_checks"

_RESTART_DUE = "self-update-restart-due"
_KEPT_LAST_KNOWN_GOOD = "self-update-kept-last-known-good"
_CANARY_FAILED = "self-update-canary-failed"

# The child enters payload A through the real `bootstrap()`, replaces its own
# installation with candidate B, and drives the exported boundary with the REAL
# production runner so the environment merge is production's rather than the
# test's. It records the actual candidate exit code, stdout, stderr and journal.
_CHILD = '''#!/usr/bin/env python3
"""Drive the self-update canary against a candidate installed over this payload's source."""

import json
import os
import shutil
import sys
from pathlib import Path

INSTALL = Path(sys.argv[1])
REPO = Path(sys.argv[2])
SCRATCH = Path(sys.argv[3])
REPORT = Path(sys.argv[4])
CANDIDATE_TREE = Path(os.environ["CANARY_CANDIDATE_TREE"])
BREAK_CANDIDATE = os.environ["CANARY_BREAK_CANDIDATE"] == "yes"
IMPORTED_MODULE = Path(os.environ["CANARY_IMPORTED_MODULE"])

sys.path.insert(0, str(INSTALL / "scripts" / "bin"))
from _bootstrap import bootstrap

bootstrap(required=("BEADS_DOLT_PASSWORD",))

import _payload_grading

from livespec_orchestrator_beads_fabro.commands import _dispatcher_paths as paths
from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update as update
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner


class RecordingJournal:
    def __init__(self):
        self.records = []

    def append(self, *, record):
        self.records.append(dict(record))


class RecordingRunner:
    """Delegates to the REAL production runner; records what it was asked and got."""

    def __init__(self):
        self.inner = ShellCommandRunner()
        self.calls = []

    def run(self, *, argv, cwd, timeout_seconds, env=None, stdin=None):
        result = self.inner.run(
            argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env, stdin=stdin
        )
        self.calls.append(
            {
                "argv": list(argv),
                "env_overlay": None if env is None else dict(env),
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        return result


class RecordingPoster:
    def __init__(self):
        self.posts = []

    def post(self, *, url, body, title, timeout_seconds):
        self.posts.append({"title": title, "body": body})
        return True


report = {
    "executing_payload_root_before": str(paths.executing_payload_root()),
    "running_release_before": update.running_release_version(),
}

# Replace this payload's own installation with the candidate build.
shutil.rmtree(INSTALL)
shutil.copytree(CANDIDATE_TREE, INSTALL, ignore=shutil.ignore_patterns("__pycache__"))
if BREAK_CANDIDATE:
    (INSTALL / IMPORTED_MODULE).unlink()

report["candidate_passes_launcher_completeness_grade"] = (
    _payload_grading.missing_payload_paths(root=INSTALL) == ()
)
report["plugin_root"] = str(paths.plugin_root())

candidate = update.candidate_dispatcher_bin()
report["candidate_bin"] = str(candidate)

journal = RecordingJournal()
runner = RecordingRunner()
poster = RecordingPoster()
update.self_update_after_release(
    work_item_id="canary-subject-regression",
    candidate_bin=str(candidate),
    scratch_root=str(SCRATCH),
    repo=REPO,
    journal=journal,
    runner=runner,
    poster=poster,
)

report["journal_records"] = journal.records
report["runner_calls"] = runner.calls
report["notification_posts"] = poster.posts
report["executing_payload_root_after"] = str(paths.executing_payload_root())
report["running_release_after"] = update.running_release_version()

REPORT.write_text(json.dumps(report, indent=2) + "\\n", encoding="utf-8")
'''


def _stamp(*, tree: Path, label: str) -> None:
    """Give a fixture build a distinguishable release label."""
    manifest = tree / "plugin.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["version"] = label
    _ = manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _build(*, root: Path, label: str) -> Path:
    _ = shutil.copytree(_PLUGIN_ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    _stamp(tree=root, label=label)
    return root


def _fake_ledger_scratch(*, root: Path) -> Path:
    """A throwaway project root whose ledger is the in-memory fake.

    The canary runs `ledger-check --project-root <scratch>`, which loads store
    configuration, so a scratch with no `.livespec.jsonc` refuses at SETUP with
    a missing connection prefix. That refusal is indistinguishable at the exit
    code from the candidate regression this file measures, so the scratch
    declares a fake connection and a healthy candidate genuinely reaches exit 0.
    """
    root.mkdir(parents=True)
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "canary-fixture",
                        "prefix": "bd-cf",
                        "fake": True,
                    }
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def _run_child(*, tmp_path: Path, break_candidate: bool) -> dict[str, object]:
    """Retain payload A, install the candidate over it, drive the boundary."""
    install_root = _build(root=tmp_path / "install", label=_RELEASE_A)
    candidate_tree = _build(root=tmp_path / "candidate", label=_RELEASE_B)
    child = tmp_path / "canary_child.py"
    _ = child.write_text(_CHILD, encoding="utf-8")
    repo = _fake_ledger_scratch(root=tmp_path / "repo")
    scratch = _fake_ledger_scratch(root=tmp_path / "scratch")
    private_tmp = tmp_path / "tmp"
    private_tmp.mkdir()
    report_path = tmp_path / "report.json"

    scrubbed = (
        "PYTHONPATH",
        "COVERAGE_PROCESS_START",
        "LIVESPEC_RETAINED_PAYLOAD_ROOT",
        "LIVESPEC_INSTALLED_PLUGIN_ROOT",
        "LIVESPEC_BEADS_FAKE",
        "LIVESPEC_CREDENTIAL_REEXEC",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in scrubbed and not key.startswith("COV_CORE_")
    }
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    env["BEADS_DOLT_PASSWORD"] = _PLACEHOLDER_SECRET
    env["TMPDIR"] = str(private_tmp)
    env["CLAUDE_NTFY_DISPATCHER_TOPIC"] = _FIXTURE_TOPIC
    env["CANARY_CANDIDATE_TREE"] = str(candidate_tree)
    env["CANARY_BREAK_CANDIDATE"] = "yes" if break_candidate else "no"
    env["CANARY_IMPORTED_MODULE"] = _CANARY_IMPORTED_MODULE.as_posix()

    completed = subprocess.run(
        [
            sys.executable,
            str(child),
            str(install_root),
            str(repo),
            str(scratch),
            str(report_path),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        check=False,
        timeout=_CLI_TIMEOUT_SECONDS,
    )

    assert (
        completed.returncode == 0
    ), f"the canary driver child failed:\n{completed.stdout}\n{completed.stderr}"
    record: dict[str, object] = json.loads(report_path.read_text(encoding="utf-8"))
    assert record["candidate_passes_launcher_completeness_grade"] is True, (
        "the candidate does not pass the launcher's own completeness grade, so "
        "this fixture measures an unusable payload the launcher would refuse "
        f"rather than a candidate regression: {record}"
    )
    assert record["plugin_root"] == str(
        install_root
    ), f"the candidate root is no longer the INSTALLED tree: {record}"
    return record


def _stages(*, record: dict[str, object]) -> list[str]:
    records = record["journal_records"]
    assert isinstance(records, list)
    return [str(entry["stage"]) for entry in records]


def _canary_call(*, record: dict[str, object]) -> dict[str, object]:
    calls = record["runner_calls"]
    assert isinstance(calls, list)
    assert len(calls) == 1, f"expected exactly one canary subprocess: {record}"
    first: dict[str, object] = calls[0]
    return first


def _assert_running_dispatcher_did_not_move(*, record: dict[str, object]) -> None:
    assert (
        record["executing_payload_root_after"] == record["executing_payload_root_before"]
    ), f"the canary moved the running Dispatcher's executing payload: {record}"
    assert (
        record["running_release_after"] == record["running_release_before"]
    ), f"the canary changed the running Dispatcher's release in flight: {record}"


def test_a_broken_candidate_fails_the_canary_and_keeps_the_last_known_good(
    tmp_path: Path,
) -> None:
    """A candidate that cannot start must not be recommended for a restart."""
    record = _run_child(tmp_path=tmp_path, break_candidate=True)
    call = _canary_call(record=record)

    assert call["exit_code"] != 0, (
        "the canary ran a BROKEN candidate and it exited 0, so the subject of "
        "the canary was not the candidate's own payload — the running build was "
        f"validated against itself: {record}"
    )
    stderr = str(call["stderr"])
    assert _MISSING_MODULE_NEEDLE in stderr, (
        "the candidate failed for some reason other than its own removed "
        f"module, so this case is not measuring the candidate regression: {record}"
    )
    stages = _stages(record=record)
    assert (
        _KEPT_LAST_KNOWN_GOOD in stages
    ), f"a failing canary must keep the last-known-good payload running: {record}"
    assert (
        _RESTART_DUE not in stages
    ), f"a failing canary must not record a restart as due: {record}"
    posts = record["notification_posts"]
    assert isinstance(posts, list)
    assert posts, f"a failing canary must alarm a human: {record}"
    assert _CANARY_FAILED in str(
        posts[0]["body"]
    ), f"the alarm does not carry the failed-canary outcome class: {record}"
    _assert_running_dispatcher_did_not_move(record=record)


def test_a_healthy_candidate_at_the_newer_release_still_passes_the_canary(
    tmp_path: Path,
) -> None:
    """The control: a fix must not be satisfiable by failing every canary."""
    record = _run_child(tmp_path=tmp_path, break_candidate=False)
    call = _canary_call(record=record)

    assert call["exit_code"] == 0, (
        "a healthy candidate's own self-check failed, so the canary can no "
        f"longer validate a good newer build: {record}"
    )
    stages = _stages(record=record)
    assert _RESTART_DUE in stages, f"a passing canary must record the restart as due: {record}"
    assert (
        _KEPT_LAST_KNOWN_GOOD not in stages
    ), f"a passing canary must not report the candidate as rejected: {record}"
    _assert_running_dispatcher_did_not_move(record=record)
