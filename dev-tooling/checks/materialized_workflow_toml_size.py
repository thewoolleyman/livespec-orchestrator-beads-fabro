# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""materialized_workflow_toml_size — every dispatch package file stays under the engine's caps.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"The materialized workflow.toml stays inside the engine's size limit", and
Scenario 279. Fabro refuses a workflow file over 524,288 bytes. It also caps the
package at 2 MiB and 512 files, and it refuses at `fabro-run`, after the
Dispatcher has claimed the item. After v0.312.3 the livespec-dev-tooling dispatch
`workflow.toml` measured 524,343 bytes, and that repository stopped dispatching
(bd-ib-p5e32s). This check renders each package the way a dispatch does
(`_workflow_package_measure`) and fails when a file passes 471,859 bytes, the
package passes 1,887,436 bytes (both 90 percent of the cap), or the package holds
more than 460 files. Each refusal names the size, the threshold and the limit.
Every measured size is printed, so growth shows before it fails.

TWO SCOPES.

- With no argument the check measures THIS repository's reserved workflow and
  every variant it registers. It reads nothing outside the checkout, so it also
  runs in the delegated cluster gate, whose pod carries no sibling clones.
- With `--fleet [clones-root]` it measures every member of the `fleet` array in
  livespec's `.livespec-fleet-manifest.jsonc`. That is the list the overlay
  already clones into every sandbox. Each member is rendered from its
  `origin/master` tree, extracted with `git archive` after a best-effort
  fetch. The working tree is never read, because a dirty or stale checkout would
  give a false green. THIS repository is the exception: it is measured from this
  checkout, because the build under test is what is being judged. The root is the
  argument, else `LIVESPEC_SIBLING_CLONES_ROOT` (a sandbox), else the directory
  that holds the primary checkout. A member with no clone FAILS, naming it.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
for _path in (_SCRIPT_DIR, _SCRIPTS, _SCRIPTS / "_vendor"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script; it
# is imported from the installed shared dev-tooling package's vendored copy,
# APPENDED so its partial `livespec_runtime` cannot shadow this repo's own.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402
from _workflow_package_measure import (  # noqa: E402
    RESERVED_RELPATH,
    Measurement,
    measure_repository,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import (  # noqa: E402
    parse_fleet_members,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (  # noqa: E402
    SIBLING_CLONES_ROOT_ENV_VAR,
)

__all__: list[str] = ["FILE_THRESHOLD_BYTES", "PACKAGE_THRESHOLD_BYTES", "clones_root", "main"]

FILE_LIMIT_BYTES = 524_288
FILE_THRESHOLD_BYTES = FILE_LIMIT_BYTES * 9 // 10
PACKAGE_LIMIT_BYTES = 2 * 1024 * 1024
PACKAGE_THRESHOLD_BYTES = PACKAGE_LIMIT_BYTES * 9 // 10
FILE_COUNT_LIMIT = 512
FILE_COUNT_THRESHOLD = FILE_COUNT_LIMIT * 9 // 10
_MANIFEST = Path("livespec") / ".livespec-fleet-manifest.jsonc"
_BUNDLED = _REPO_ROOT / ".claude-plugin" / RESERVED_RELPATH
_PROSE = _REPO_ROOT / "SPECIFICATION" / "contracts.md"
# THIS repository's own scope has no manifest to read, so it renders a sibling set
# of the fleet's current size, with names as long as its longest member's.
_SELF_SCOPE_SIBLINGS = tuple(f"livespec-representative-member-{n:02d}" for n in range(10))
# The paths a member's dispatch reads from its own tree.
_MEMBER_PATHS = (".livespec.jsonc", ".fabro", "SPECIFICATION")
_GITHUB_APP_ENV = {"GITHUB_APP_ID": "1234567", "GITHUB_PRIVATE_KEY": "k" * 50}


def _own_name() -> str:
    manifest = _REPO_ROOT / ".claude-plugin" / "plugin.json"
    return str(json.loads(manifest.read_text(encoding="utf-8"))["name"])


def _measure(
    *, repository: Path, name: str, siblings: tuple[str, ...], owner: str
) -> list[Measurement]:
    return measure_repository(
        repository=repository,
        name=name,
        siblings=siblings,
        owner=owner,
        bundled=_BUNDLED,
        prose=_PROSE,
    )


def _git(*, clone: Path, argv: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(clone), *argv], capture_output=True, check=False)


def _committed_tree(*, clone: Path, into: Path) -> Path | None:
    """`clone`'s `origin/master` tree, the paths a dispatch reads, extracted under `into`."""
    _ = _git(clone=clone, argv=["fetch", "--quiet", "origin", "master"])
    listed = _git(clone=clone, argv=["ls-tree", "--name-only", "origin/master"])
    present = [path for path in _MEMBER_PATHS if path in listed.stdout.decode().split()]
    if listed.returncode != 0 or ".livespec.jsonc" not in present:
        return None
    archive = _git(clone=clone, argv=["archive", "--format=tar", "origin/master", *present])
    tree = into / clone.name
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as members:
        members.extractall(tree)  # noqa: S202 -- our own fleet member's committed tree
    return tree


def clones_root(*, arguments: list[str], repo_root: Path = _REPO_ROOT) -> Path:
    """The argument, else the sandbox's clone root, else the directory holding the primary."""
    if arguments:
        return Path(arguments[0])
    declared = os.environ.get(SIBLING_CLONES_ROOT_ENV_VAR, "").strip()
    if declared:
        return Path(declared)
    dotgit = repo_root / ".git"
    gitdir = (
        Path(dotgit.read_text(encoding="utf-8").split("gitdir:", 1)[1].strip())
        if dotgit.is_file()
        else None
    )
    primary = repo_root if gitdir is None else gitdir.parent.parent.parent
    return primary.parent


def _fleet(*, clones_root: Path, into: Path) -> tuple[list[Measurement], list[str]]:
    manifest = clones_root / _MANIFEST
    if not manifest.is_file():
        return [], [f"fleet manifest {manifest} is missing, so no member was measured"]
    members = parse_fleet_members(manifest_text=manifest.read_text(encoding="utf-8"))
    if members is None:
        return [], [f"fleet manifest {manifest} does not parse into an owner and members"]
    measurements: list[Measurement] = []
    findings: list[str] = []
    for name in members.repos:
        tree = (
            _REPO_ROOT
            if name == _own_name()
            else _committed_tree(clone=clones_root / name, into=into)
        )
        if tree is None:
            missing = f"no committed .livespec.jsonc on origin/master under {clones_root}"
            findings.append(f"fleet member {name}: no clone with {missing}")
            continue
        measurements.extend(
            _measure(repository=tree, name=name, siblings=members.repos, owner=members.owner)
        )
    return measurements, findings


def _verdicts(*, measurements: list[Measurement]) -> list[str]:
    """The finding each over-threshold file, package or unrenderable run config earns."""
    file_bound = (
        f"over the {FILE_THRESHOLD_BYTES}-byte threshold"
        f" (90 percent of the engine's {FILE_LIMIT_BYTES}-byte limit)"
    )
    package_bound = (
        f"over the {PACKAGE_THRESHOLD_BYTES}-byte threshold (90 percent of {PACKAGE_LIMIT_BYTES})"
    )
    count_bound = f"over {FILE_COUNT_THRESHOLD} (90 percent of the engine's {FILE_COUNT_LIMIT})"
    findings = [
        f"{m.repository} {m.workflow} ({m.case}): {m.file} did not render"
        if m.size is None
        else f"{m.repository} {m.workflow} ({m.case}): {m.file} is {m.size} bytes, {file_bound}"
        for m in measurements
        if m.size is None or m.size > FILE_THRESHOLD_BYTES
    ]
    packages: dict[tuple[str, str, str], list[int]] = {}
    for m in measurements:
        packages.setdefault((m.repository, m.workflow, m.case), []).append(m.size or 0)
    for (repository, workflow, case), sizes in packages.items():
        where = f"{repository} {workflow} ({case})"
        if sum(sizes) > PACKAGE_THRESHOLD_BYTES:
            findings.append(f"{where}: the package is {sum(sizes)} bytes, {package_bound}")
        if len(sizes) > FILE_COUNT_THRESHOLD:
            findings.append(f"{where}: the package holds {len(sizes)} files, {count_bound}")
    return findings


def main(
    *, argv: list[str] | None = None, measure: Callable[..., list[Measurement]] = _measure
) -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("materialized_workflow_toml_size")
    arguments = sys.argv[1:] if argv is None else argv
    # The gh-refresh steps render only when the GitHub App inputs are present,
    # as they are on every factory host; a stand-in keeps them in the render.
    for key, value in _GITHUB_APP_ENV.items():
        _ = os.environ.setdefault(key, value)
    with tempfile.TemporaryDirectory(prefix="workflow-package-size-") as scratch:
        if arguments[:1] == ["--fleet"]:
            measurements, findings = _fleet(
                clones_root=clones_root(arguments=arguments[1:]), into=Path(scratch)
            )
        else:
            own = measure(
                repository=_REPO_ROOT,
                name=_own_name(),
                siblings=_SELF_SCOPE_SIBLINGS,
                owner="thewoolleyman",
            )
            measurements, findings = own, []
    for m in measurements:
        log.info(
            "workflow package file measured",
            repository=m.repository,
            workflow=m.workflow,
            case=m.case,
            file=m.file,
            size=m.size,
            threshold=FILE_THRESHOLD_BYTES,
            limit=FILE_LIMIT_BYTES,
        )
    findings = findings + _verdicts(measurements=measurements)
    for finding in findings:
        log.error(
            "workflow package size refusal",
            finding=finding,
            threshold=FILE_THRESHOLD_BYTES,
            limit=FILE_LIMIT_BYTES,
        )
    return 1 if findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
