# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""no_fleet_toolchain_literals — no fleet premise is hardcoded outside the fleet-defaults module.

`SPECIFICATION/constraints.md`, the fleet-toolchain-literal-ban clause, requires
that a fleet-toolchain literal -- this fleet's tool runner, a fleet recipe name,
its hook manager, its shared dev-tooling package, its step timer, or a bare
default-branch name used as a ref -- appear in the dispatcher package and the
workflow payload ONLY inside the single fleet-defaults module the
`RepoIntegrationContract` schema designates, so a new hardcoded premise cannot be
reintroduced by a later change.

WHY A GATE RATHER THAN THE SCHEMA ALONE. Every one of these literals used to sit
at its point of use, and each was a silent assumption imposed on an adopter that
carries none of this fleet's tooling. Gathering them into the fleet-defaults
module fixed the instances that existed; nothing stopped the NEXT one. A defaults
module is only load-bearing if putting a fleet literal anywhere else fails a
build.

This module owns the SCOPE and the POLICY; the sibling matcher module owns what
counts as a literal in the first place.

THERE IS NO ALLOW-LIST OF ANY KIND. Neither the package nor the payload has one.
The payload's went first, with the typed-workflow-inputs carrier (C5-payload),
which converted every fleet premise the payload and prompt files carried into an
`inputs.<name>` projection of the resolved integration contract. The package's
followed, with the retire-measured-exemptions carrier (C7): its six
`MEASURED_EXEMPTIONS` entries were always a CONVERSION FOLLOW-UP rather than a
judgement that the sites were correct, and each site now reads its value through
the resolved integration contract or from the fleet-defaults module. A fleet
literal anywhere outside that one module is a finding, wherever it appears.

That the list retired itself is what the design bought. Every entry carried a
stale-entry control -- the moment a site converted, its entry stopped matching
and this check FAILED until the entry was removed -- so the deletions were
mechanical rather than remembered, and the list could not outlive its reason by
being quietly ignored. The control is gone with the list it guarded; what
replaces it is that there is nothing left to be stale.

EVERY REGISTERED VARIANT IS SCANNED, NOT ONLY THE BUNDLE. `contracts.md`
section "Self-contained plugin dispatch", clause "A registered variant is the
reserved workflow's peer, not its exception", names this gate and requires it to
read the bundle AND every directory this repository registers under its own
`dispatcher.workflows`. `_checked_workflow_payloads` owns that enumeration for
both payload gates; every finding and control failure is prefixed with the
directory it came from, so a literal reintroduced in a variant is as actionable
as one in the bundle.

POSITIVE CONTROLS, because this check reports an ABSENCE for a living. A broken
pattern or a mis-scoped glob would make it permanently green while printing
exactly what a clean repo prints, so `main` refuses to report a clean scan unless
all of them hold: the package DISCOVERY control asserts the package walk reached
the modules that carry the literals; a payload DISCOVERY control PER CHECKED
DIRECTORY asserts each walk reached a file, so a registered directory whose scan
yields nothing FAILS rather than reporting clean -- a repository-wide control
would be satisfied by the bundle alone and would then certify a variant it never
read; a COMPLETENESS control per directory reports an unreadable or half-written
registered directory by name rather than skipping it; the DESIGNATION control
asserts the one module the scan skips is the one the schema actually designates,
so the skip cannot drift onto a module the contract never named; and the MATCHER
control asserts the checked-in fixture still produces findings through the same
parse/match path.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
for _path in (_SCRIPT_DIR, _SCRIPTS, _SCRIPTS / "_vendor"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script (per
# the `no_write_direct` ban on direct `sys.stderr.write`). It is not vendored in
# this repo's own tree, so it is imported from the installed shared dev-tooling
# package's vendored copy, whose path is added to `sys.path` below.
#
# The matcher beside it is a sibling PRIVATE module in this same directory. This
# file's own directory is on `sys.path` above, so the sibling import resolves
# both under `python <path>` and under the importlib-by-path load the paired
# test uses.
import livespec_dev_tooling  # noqa: E402
from _checked_workflow_payloads import (  # noqa: E402  — sibling private import
    CheckedPayload,
    checked_payloads,
    incompleteness,
)
from _fleet_toolchain_literals_matcher import (  # noqa: E402  — sibling private import
    Finding,
    source_findings,
    text_findings,
)

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
# APPEND, never insert at the front: since livespec-dev-tooling v1.90.0 that
# `_vendor` also carries a PARTIAL `livespec_runtime` (the github_budget
# modules only, no `work_items`), and putting it ahead of this repo's own
# `_vendor` shadowed the full copy every plugin module imports, so every
# check in this directory died on `No module named
# 'livespec_runtime.work_items'` (livespec-dev-tooling-8o8e.24 is the
# two-copies class). Appending keeps `structlog` resolvable while this
# repo's full vendored runtime keeps precedence.
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402

__all__: list[str] = [
    "DISCOVERY_ANCHORS",
    "FLEET_DEFAULTS_MODULE",
    "SCHEMA_MODULE",
    "all_findings",
    "control_failures",
    "main",
    "package_findings",
    "payload_findings",
    "payload_paths",
]

# The single fleet-defaults module. Package-relative, and asserted below to be
# the module the schema designates rather than merely a module named here.
FLEET_DEFAULTS_MODULE = "commands/_dispatcher_integration_defaults.py"
SCHEMA_MODULE = "commands/_dispatcher_integration_schema.py"

# Package-relative paths the walk MUST reach: the two contract modules, plus the
# argv builder that carried the largest measured residue before C7 converted it.
# A walk that misses one is mis-scoped, and its clean report means nothing.
DISCOVERY_ANCHORS: tuple[str, ...] = (
    "commands/_dispatcher_fabro_argv.py",
    FLEET_DEFAULTS_MODULE,
    SCHEMA_MODULE,
)

_PACKAGE_RELPATH = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro"
_FIXTURE_RELPATH = "dev-tooling/checks/fixtures/fleet_toolchain_literal_control.py.txt"
_PAYLOAD_SUFFIXES = frozenset({".fabro", ".md", ".toml"})
_FINDING_MESSAGE = "fleet-toolchain literal outside the fleet-defaults module"
_BYTECODE_DIRNAME = "__pycache__"


def _walked_files(*, root: Path) -> list[Path]:
    """Every file under `root`, tolerating that tree changing underneath the walk.

    BOTH trees this gate reads are LIVE, so both can change while being walked.
    `os.walk` rather than `Path.rglob` because pathlib lists a directory and then
    opens it, and lets a `FileNotFoundError` from that open escape: a
    `__pycache__` a concurrent pytest worker removed between the two steps took
    this whole check down and turned master CI red on a pure version bump, which
    closed the green-master preflight and so blocked every factory dispatch here.
    `os.walk` ignores a `scandir` error by default, so a vanished subtree is
    dropped rather than fatal. This is the walk `spec_id_presence_discipline`
    adopted for the same race; both of this gate's walks share this one helper so
    they cannot come to differ about it.

    `__pycache__` is pruned from the descent as well as tolerated: it can hold
    neither a scanned module nor a payload file, and it is the directory that
    actually races here.
    """
    paths: list[Path] = []
    for parent, dirnames, filenames in os.walk(root):
        dirnames[:] = [dirname for dirname in dirnames if dirname != _BYTECODE_DIRNAME]
        paths.extend(Path(parent) / name for name in filenames)
    return paths


def _module_paths(*, package: Path) -> list[Path]:
    return sorted(path for path in _walked_files(root=package) if path.suffix == ".py")


def _payload_files(*, payload: CheckedPayload) -> list[Path]:
    """Every payload and prompt file in ONE checked workflow directory.

    A directory that is not there walks to nothing rather than raising; the
    completeness and discovery controls are what turn that nothing into a
    finding naming the directory.
    """
    return sorted(
        path for path in _walked_files(root=payload.directory) if path.suffix in _PAYLOAD_SUFFIXES
    )


def payload_paths(*, repo_root: Path) -> list[Path]:
    """Every payload and prompt file the scan walks, across every checked directory."""
    return [
        path
        for payload in checked_payloads(repo_root=repo_root)
        for path in _payload_files(payload=payload)
    ]


def package_findings(*, repo_root: Path) -> list[Finding]:
    """Every literal in the dispatcher package outside the fleet-defaults module."""
    package = repo_root / _PACKAGE_RELPATH
    findings: list[Finding] = []
    for path in _module_paths(package=package):
        relpath = path.relative_to(package).as_posix()
        if relpath == FLEET_DEFAULTS_MODULE:
            continue
        findings.extend(source_findings(source=path.read_text(encoding="utf-8"), relpath=relpath))
    return findings


def payload_findings(*, repo_root: Path) -> list[Finding]:
    """Every literal in every checked workflow directory; nothing excuses one there."""
    findings: list[Finding] = []
    for payload in checked_payloads(repo_root=repo_root):
        for path in _payload_files(payload=payload):
            findings.extend(
                text_findings(
                    text=path.read_text(encoding="utf-8"),
                    relpath=f"{payload.where}/{path.relative_to(payload.directory).as_posix()}",
                )
            )
    return findings


def all_findings(*, repo_root: Path) -> list[Finding]:
    """Every literal the scan found, package and payload alike; nothing excuses one."""
    return package_findings(repo_root=repo_root) + payload_findings(repo_root=repo_root)


def _designates_defaults(*, source: str) -> bool:
    module_name = Path(FLEET_DEFAULTS_MODULE).stem
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.endswith(module_name)
        for node in ast.walk(ast.parse(source))
    )


def control_failures(*, repo_root: Path) -> list[str]:
    """Why a clean scan of `repo_root` would not be trustworthy, if it would not."""
    failures: list[str] = []
    package = repo_root / _PACKAGE_RELPATH
    discovered = {path.relative_to(package).as_posix() for path in _module_paths(package=package)}
    failures.extend(
        f"discovery control: the walk of {package} did not reach {anchor}"
        for anchor in DISCOVERY_ANCHORS
        if anchor not in discovered
    )
    for payload in checked_payloads(repo_root=repo_root):
        failures.extend(incompleteness(payload=payload))
        if not _payload_files(payload=payload):
            failures.append(f"discovery control: the walk of {payload.where} reached no file")
    # The one skipped module is only legitimate while the schema still designates
    # it; without this control the skip could silently drift onto a module the
    # contract never named.
    schema = package / SCHEMA_MODULE
    if not schema.is_file() or not _designates_defaults(source=schema.read_text(encoding="utf-8")):
        failures.append(
            f"designation control: {SCHEMA_MODULE} does not import {FLEET_DEFAULTS_MODULE}"
        )
    fixture = repo_root / _FIXTURE_RELPATH
    if not fixture.is_file():
        failures.append(f"matcher control: the positive-control fixture is missing at {fixture}")
        return failures
    if not source_findings(source=fixture.read_text(encoding="utf-8"), relpath=fixture.name):
        failures.append(f"matcher control: no fleet-toolchain literal was found in {fixture}")
    return failures


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("no_fleet_toolchain_literals")
    repo_root = Path.cwd()
    failures = control_failures(repo_root=repo_root)
    for failure in failures:
        log.error(
            "positive control failed; this scan cannot report a trustworthy absence",
            detail=failure,
        )
    findings = all_findings(repo_root=repo_root)
    for finding in findings:
        log.error(
            _FINDING_MESSAGE,
            path=finding.relpath,
            line=finding.lineno,
            token=finding.token,
            literal=finding.literal,
        )
    return 1 if failures or findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
