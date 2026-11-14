# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""_affected_tests_selection — the tests, and the coverage verdict, of the affected-tests gate.

`SPECIFICATION/contracts.md`, the clause "An implement, fix or review_fix turn's
commits run the affected-tests gate", has a commit made inside one of those turns
run `just check-changed` in place of the full check aggregate. This module is what
`check-changed` runs. It answers two questions: WHICH test modules a change
affects, and WHETHER every product module the change touched is fully covered by
them.

WHY THE SELECTION IS WIDER THAN THE MIRROR TEST. The first landing of this gate
measured each changed module only from its mirror-paired test file, at 100%. A
module whose lines are executed by OTHER tests read as uncovered, so every
in-turn commit on it was refused for coverage the full aggregate passes, and the
fleet stopped. The selection per changed product module is now its mirror-paired
test and that test's `test_<name>_*.py` siblings, plus EVERY test module that
imports it directly or through another imported module, found by a static scan of
the import graph. Coverage is then judged per changed module over that whole set.
Over-selection only runs more tests, so the scan errs wide: an import is matched
by every dotted-name suffix, and a module that a test names in a string literal (a
path, a file name, a dotted name) counts as imported, which is how a test loads a
script it cannot import. The scan itself is the sibling private module
`_affected_tests_scan`; this module owns what a change selects and the verdict.

A CHANGE TO THE WORKFLOW GRAPH SELECTS THE TESTS THAT READ IT. A `workflow.fabro`
edit changes no `.py`, yet it broke integration tests in three of the five
measured runs. Its affected tests are every test module that names `workflow.fabro`
in a string literal, or imports a module that does, closed over the same import
graph.

WHAT THE SCAN CANNOT RESOLVE EXITS 75. A file that does not parse, a changed `.py`
that no test module reaches, a changed shared configuration file, and a diff that
could not be taken are all changes whose affected tests this module cannot
determine. It then exits `EXIT_CANNOT_SCOPE`, and the commit hook runs the full
check aggregate instead. A refusal is reserved for a change the selected tests
really leave uncovered or failing. The residual risk is coverage that reaches a
module through no import path and no string naming it.

This gate is INNER-LOOP ONLY. The janitor stage still runs the full aggregate once
per run before publication.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import livespec_dev_tooling

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
# APPENDED, never inserted at the front, for the reason the sibling checks give: the
# shared package's `_vendor` carries a PARTIAL `livespec_runtime` that must not
# shadow this repository's full copy.
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

# The scan beside it is a sibling PRIVATE module in this same directory. This file's own
# directory is put on `sys.path`, so the sibling import resolves both under `python
# <path>` and under the importlib-by-path load the paired test uses.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import structlog  # noqa: E402
import tomli  # noqa: E402
from _affected_tests_scan import (  # noqa: E402  — sibling private import
    git_lines,
    is_test,
    scan_repository,
    tests_reaching,
)

__all__: list[str] = [
    "EXIT_CANNOT_SCOPE",
    "Selection",
    "Unscoped",
    "changed_paths",
    "main",
    "select",
]

EXIT_CANNOT_SCOPE = 75
WORKFLOW_FILE_NAME = "workflow.fabro"
# A change to one of these cannot be mapped to the tests it affects: each is read
# by the whole suite or by the gate itself.
SHARED_CONFIGURATION = frozenset(
    {"pyproject.toml", "uv.lock", "justfile", "lefthook.yml", ".mise.toml"}
)
SHARED_CONFIGURATION_PREFIX = "dev-tooling/"
_COVERAGE_FLOOR = "100"


@dataclass(frozen=True, kw_only=True)
class Selection:
    """The product modules to measure and the test modules to run, repo-relative."""

    measured: tuple[str, ...]
    tests: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class Unscoped:
    """A change whose affected tests this module cannot determine."""

    reason: str


def changed_paths(*, root: Path) -> list[str] | None:
    """The branch's changed paths plus the staged ones, or None when git cannot say."""
    branch = git_lines(root=root, arguments=["diff", "--name-only", "origin/master...HEAD"])
    staged = git_lines(root=root, arguments=["diff", "--cached", "--name-only", "--diff-filter=AM"])
    if branch is None or staged is None:
        return None
    return sorted({*branch, *staged})


def _mirror_tests(*, root: Path, path: str, pairings: list[dict[str, str]]) -> set[str]:
    """The mirror-paired test of `path` and its `test_<name>_*.py` siblings that exist."""
    found: set[str] = set()
    for pairing in pairings:
        source_tree = pairing["source_tree"].rstrip("/") + "/"
        if path.startswith(source_tree):
            relative = Path(path.removeprefix(source_tree))
            stem = relative.stem.removeprefix("_")
            directory = root / pairing["test_tree"] / relative.parent
            for pattern in (f"test_{stem}.py", f"test_{stem}_*.py"):
                found.update(c.relative_to(root).as_posix() for c in directory.glob(pattern))
    return found


def _is_shared(*, path: str) -> bool:
    return path in SHARED_CONFIGURATION or (
        path.startswith(SHARED_CONFIGURATION_PREFIX) and not path.endswith(".py")
    )


def select(*, root: Path, changed: list[str]) -> Selection | Unscoped:
    """The tests and the product modules measured for `changed`, or why it cannot be scoped."""
    shared = [path for path in changed if _is_shared(path=path)]
    if shared:
        return Unscoped(reason=f"{shared[0]} is shared configuration read by the whole suite")
    scan = scan_repository(root=root)
    if isinstance(scan, str):
        return Unscoped(reason=scan)
    layout: dict[str, Any] = tomli.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "tool"
    ]["livespec_dev_tooling"]
    seeds = {path for path in changed if path in scan.graph}
    tests = {path for path in seeds if is_test(path=path)}
    for path in sorted(seeds):
        reached = tests_reaching(seeds={path}, scan=scan) | _mirror_tests(
            root=root, path=path, pairings=layout["mirror_pairings"]
        )
        if not reached:
            return Unscoped(reason=f"no test module imports or names {path}")
        tests |= reached
    if any(Path(path).name == WORKFLOW_FILE_NAME for path in changed):
        reading = tests_reaching(seeds=scan.named.get(WORKFLOW_FILE_NAME, set()), scan=scan)
        if not reading:
            return Unscoped(reason=f"no test module reads {WORKFLOW_FILE_NAME}")
        tests |= reading
    if not tests:
        return Unscoped(reason="the change selects no test module")
    prefixes = tuple(layout["source_tree_prefixes"])
    return Selection(
        measured=tuple(sorted(p for p in seeds if p.startswith(prefixes))),
        tests=tuple(sorted(tests)),
    )


def _run_gate(*, root: Path, selection: Selection) -> int:
    """Run the selected tests under coverage, then hold each measured module to 100%."""
    data_dir = tempfile.mkdtemp(prefix="livespec-affected-tests-")
    data_file = str(Path(data_dir) / "coverage.dat")
    env = {k: v for k, v in os.environ.items() if not k.startswith("COV_CORE_")}
    env["COVERAGE_FILE"] = data_file
    workers = subprocess.run(
        ["bash", "dev-tooling/just-test-nprocs.sh"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    measuring = ["--cov", "--cov-branch", "--cov-config=pyproject.toml", "--cov-report="]
    pytest_status = subprocess.run(
        ["uv", "run", "pytest", "-n", workers, *measuring, "--cov-fail-under=0", *selection.tests],
        cwd=root,
        env=env,
        check=False,
    ).returncode
    report = [
        "uv",
        "run",
        "coverage",
        "report",
        "--rcfile=pyproject.toml",
        f"--data-file={data_file}",
        f"--include={','.join(selection.measured)}",
        f"--fail-under={_COVERAGE_FLOOR}",
        "--show-missing",
    ]
    coverage_status = (
        subprocess.run(report, cwd=root, check=False).returncode if selection.measured else 0
    )
    shutil.rmtree(data_dir, ignore_errors=True)
    return max(pytest_status, coverage_status)


def main() -> int:
    """Exit 0 when the affected tests pass and cover the change, 75 when it cannot be scoped."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("affected_tests_selection")
    root = Path.cwd()
    changed = changed_paths(root=root)
    outcome = (
        Unscoped(reason="the changed-file diff could not be taken")
        if changed is None
        else select(root=root, changed=changed)
    )
    if isinstance(outcome, Unscoped):
        log.warning("affected-tests gate cannot scope this change", reason=outcome.reason)
        return EXIT_CANNOT_SCOPE
    log.info(
        "affected-tests gate selected its tests",
        tests=len(outcome.tests),
        measured=list(outcome.measured),
    )
    return _run_gate(root=root, selection=outcome)


if __name__ == "__main__":
    raise SystemExit(main())
