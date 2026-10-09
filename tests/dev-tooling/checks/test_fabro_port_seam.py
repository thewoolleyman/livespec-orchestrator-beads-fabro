"""Tests for the guard that keeps the Fabro facade the single engine seam.

The guard reports an ABSENCE, so this module carries the controls that make a
clean scan mean something:

- a DISCOVERY control over the package walk, so a mis-scoped file list fails
  rather than certifying a tree it never read;
- a MATCHER control over a checked-in fixture carrying all three violation
  forms, so a broken sub-matcher cannot masquerade as a clean repo;
- an AIM control, which is the one this guard needs most. Its whole output is
  "nothing outside the facade family reaches the engine", and the cheapest way
  to earn that sentence falsely is to widen the exempt family until it covers
  the Dispatcher. So the family is asserted to be where the seam ACTUALLY
  lives — scanned unexempted it must yield every form — and a real Dispatcher
  module is asserted NOT to be exempt;
- two NEGATIVE controls that re-inline the direct invocations this repository
  carried on `origin/master` before the conversion, each PROVING its own
  mutation landed by reading the file back off disk before the check's verdict
  is treated as evidence of anything.

The negative controls are not invented shapes. Measured against
`origin/master` on 2026-10-09, those exact three modules produced exactly four
findings — a `binary-argv` in each preserve-by-reference module, and a
`transport-call` plus a `server-api-path` in the capability reader — which is
what the mutations below restore.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "fabro_port_seam.py"
_PACKAGE_RELPATH = (".claude-plugin", "scripts", "livespec_orchestrator_beads_fabro")
_JUSTFILE = _REPO_ROOT / "justfile"
_SLUG = "check-fabro-port-seam"

# A module that is unambiguously the Dispatcher rather than the facade. The aim
# control asserts it is NOT exempt: a family prefix widened to `_` would hide
# every private module's violations while printing a perfectly clean scan.
_NON_FAMILY_ANCHOR = "commands/_dispatcher_engine.py"

# The routed form each converted call site carries, and the direct form it
# carried on `origin/master`. Every pair is a literal re-inline, not a
# paraphrase, so a mutation that matched nothing leaves the file byte-identical
# and is caught by the read-back rather than passing as a clean scan.
_ROUTED_DUMP = """        dumped = port.dump(
            run_id=run_id,
            output_dir=output_dir,
            timeout_seconds=_DUMP_TIMEOUT_SECONDS,
        ).command"""
_INLINED_DUMP = """        dumped = command_runner.run(
            argv=[fabro_bin, "dump", run_id, "--server", server_url, "-o", str(output_dir)],
            cwd=repo,
            timeout_seconds=_DUMP_TIMEOUT_SECONDS,
        )"""
_ROUTED_SYSTEM_INFO = """    result = FabroHttpPort(
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        transport=transport,
    ).system_info(timeout_seconds=_TIMEOUT_SECONDS)"""
_INLINED_SYSTEM_INFO = """    result = fabro_http_request(
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        transport=transport,
        method="GET",
        path="/api/v1/system/info",
        payload=None,
        timeout_seconds=_TIMEOUT_SECONDS,
    )"""


def _load_check() -> ModuleType:
    # Asserted BEFORE the load, so a repository where the guard does not yet
    # exist fails on this assertion rather than on an import error that would
    # prove only unimportability.
    assert _CHECK_PATH.is_file()
    spec = importlib.util.spec_from_file_location("fabro_port_seam_under_test", _CHECK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="check")
def _check_fixture() -> ModuleType:
    return _load_check()


def _seed_package(*, repo_root: Path, relpaths: tuple[str, ...]) -> Path:
    """Copy real package modules into a throwaway repo root, preserving layout."""
    source_package = _REPO_ROOT.joinpath(*_PACKAGE_RELPATH)
    target_package = repo_root.joinpath(*_PACKAGE_RELPATH)
    for relpath in relpaths:
        target = target_package / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy2(source_package / relpath, target)
    return target_package


def _seed_fixture(*, repo_root: Path, check: ModuleType) -> Path:
    source = check.fixture_path(repo_root=_REPO_ROOT)
    target = check.fixture_path(repo_root=repo_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy2(source, target)
    return target


def _reinline(*, path: Path, routed: str, inlined: str) -> None:
    """Replace a routed call site with its direct form, proving the edit landed."""
    before = path.read_text(encoding="utf-8")
    _ = path.write_text(before.replace(routed, inlined), encoding="utf-8")
    after = path.read_text(encoding="utf-8")
    assert after != before
    assert routed not in after
    assert after.count(inlined) == 1


# ---------------------------------------------------------------------------
# The package as it stands, and the wiring that makes the guard binding.
# ---------------------------------------------------------------------------


def test_the_check_is_installed_where_the_justfile_target_invokes_it() -> None:
    assert _CHECK_PATH.is_file()


def test_the_guard_runs_under_the_check_aggregate() -> None:
    # The obligation is a check "under `just check`", so the wiring IS part of
    # it: a guard present on disk and absent from the aggregate never refuses
    # anything.
    justfile = _JUSTFILE.read_text(encoding="utf-8")
    targets = re.search(r"(?ms)^    targets=\((?P<body>.*?)^    \)", justfile)

    assert targets is not None
    assert _SLUG in targets.group("body").split()
    assert re.search(rf"(?m)^{re.escape(_SLUG)}:$", justfile) is not None


def test_no_module_outside_the_facade_family_reaches_the_engine(check: ModuleType) -> None:
    assert check.package_findings(repo_root=_REPO_ROOT) == []


def test_controls_hold_against_the_real_repo(check: ModuleType) -> None:
    assert check.control_failures(repo_root=_REPO_ROOT) == []


def test_main_passes_against_the_real_repo(
    check: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(_REPO_ROOT)

    assert check.main() == 0


# ---------------------------------------------------------------------------
# AIM — the exemption covers the seam, and nothing more.
# ---------------------------------------------------------------------------


def test_the_exempt_family_is_where_the_engine_seam_actually_lives(check: ModuleType) -> None:
    # Scanned WITHOUT the exemption the family must yield every form. If it
    # yielded none, the guard would be exempting modules that no longer hold
    # the seam while the real invocations sat somewhere it does scan.
    findings = check.family_findings(repo_root=_REPO_ROOT)

    assert {finding.form for finding in findings} == set(check.FORMS)
    assert {finding.relpath for finding in findings} <= set(check.DISCOVERY_ANCHORS)


def test_a_dispatcher_module_is_not_exempt(check: ModuleType) -> None:
    # The widened-prefix evasion: `FAMILY_PREFIX = "_"` would exempt every
    # private module and report a spotless package.
    root = check.package_dir(repo_root=_REPO_ROOT)
    scanned = {
        path.relative_to(root).as_posix()
        for path in check.module_paths(root=root)
        if not check.is_family_module(path=path)
    }

    assert _NON_FAMILY_ANCHOR in scanned
    assert not check.is_family_module(path=root / _NON_FAMILY_ANCHOR)


def test_discovery_anchors_are_reached_by_the_package_walk(check: ModuleType) -> None:
    root = check.package_dir(repo_root=_REPO_ROOT)
    walked = {path.relative_to(root).as_posix() for path in check.module_paths(root=root)}

    assert set(check.DISCOVERY_ANCHORS) <= walked


def test_discovery_control_fails_when_the_walk_misses_an_anchor(
    check: ModuleType,
    tmp_path: Path,
) -> None:
    _ = _seed_package(repo_root=tmp_path, relpaths=(check.DISCOVERY_ANCHORS[0],))
    _ = _seed_fixture(repo_root=tmp_path, check=check)

    failures = check.control_failures(repo_root=tmp_path)

    assert [failure for failure in failures if check.DISCOVERY_ANCHORS[-1] in failure]
    assert not [failure for failure in failures if "matcher" in failure]


# ---------------------------------------------------------------------------
# POSITIVE CONTROL — the fixture the guard is required to find.
# ---------------------------------------------------------------------------


def test_positive_control_fixture_carries_every_violation_form(check: ModuleType) -> None:
    fixture = check.fixture_path(repo_root=_REPO_ROOT)
    persisted = fixture.read_text(encoding="utf-8")

    # Read back off disk and asserted by CONTENT: the fixture must carry real
    # invocations, not merely name the binary or the transport.
    assert "fabro_bin, " in persisted
    assert "fabro_http_request(" in persisted
    assert "/api/v1/" in persisted
    findings = check.path_findings(paths=[fixture], root=fixture.parent)
    assert {finding.form for finding in findings} == set(check.FORMS)


def test_matcher_control_fails_the_build_when_the_fixture_reports_no_hit(
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _seed_package(repo_root=tmp_path, relpaths=check.DISCOVERY_ANCHORS)
    blinded = check.fixture_path(repo_root=tmp_path)
    blinded.parent.mkdir(parents=True, exist_ok=True)
    _ = blinded.write_text(
        '"""Prose naming fabro_bin and /api/v1 and invoking nothing."""\n', "utf-8"
    )
    monkeypatch.chdir(tmp_path)

    # The blinded fixture still NAMES both tokens, so a name-only instrument
    # would be satisfied by it; the guard must not be.
    assert "fabro_bin" in blinded.read_text(encoding="utf-8")
    assert [
        failure for failure in check.control_failures(repo_root=tmp_path) if "matcher" in failure
    ]
    assert check.main() == 1


def test_matcher_control_fails_the_build_when_the_fixture_is_missing(
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = _seed_package(repo_root=tmp_path, relpaths=check.DISCOVERY_ANCHORS)
    monkeypatch.chdir(tmp_path)

    assert not check.fixture_path(repo_root=tmp_path).exists()
    assert check.main() == 1


# ---------------------------------------------------------------------------
# NEGATIVE CONTROLS — the direct invocations master carried, re-inlined.
# ---------------------------------------------------------------------------


def test_a_reinlined_fabro_dump_argv_is_caught(
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _seed_package(repo_root=tmp_path, relpaths=check.DISCOVERY_ANCHORS)
    _ = _seed_fixture(repo_root=tmp_path, check=check)
    target = "commands/_dispatcher_preserve_reference.py"

    _reinline(path=package / target, routed=_ROUTED_DUMP, inlined=_INLINED_DUMP)

    findings = check.package_findings(repo_root=tmp_path)
    assert [(finding.relpath, finding.form) for finding in findings] == [
        (target, check.FORM_BINARY_ARGV)
    ]
    assert check.control_failures(repo_root=tmp_path) == []
    monkeypatch.chdir(tmp_path)
    assert check.main() == 1


def test_a_reinlined_transport_request_and_api_path_are_both_caught(
    check: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _seed_package(repo_root=tmp_path, relpaths=check.DISCOVERY_ANCHORS)
    _ = _seed_fixture(repo_root=tmp_path, check=check)
    target = "commands/_acp_factory_capabilities.py"

    _reinline(path=package / target, routed=_ROUTED_SYSTEM_INFO, inlined=_INLINED_SYSTEM_INFO)

    findings = check.package_findings(repo_root=tmp_path)
    assert sorted({(finding.relpath, finding.form) for finding in findings}) == [
        (target, check.FORM_SERVER_API_PATH),
        (target, check.FORM_TRANSPORT_CALL),
    ]
    monkeypatch.chdir(tmp_path)
    assert check.main() == 1


def test_the_unmutated_seed_of_the_same_call_sites_is_clean(
    check: ModuleType,
    tmp_path: Path,
) -> None:
    # The negative controls' own control: the identical seed, unmutated, must
    # pass — otherwise neither finding above says anything about the edit.
    package = _seed_package(repo_root=tmp_path, relpaths=check.DISCOVERY_ANCHORS)
    _ = _seed_fixture(repo_root=tmp_path, check=check)

    assert _ROUTED_DUMP in (package / "commands" / "_dispatcher_preserve_reference.py").read_text(
        encoding="utf-8"
    )
    assert check.package_findings(repo_root=tmp_path) == []


# ---------------------------------------------------------------------------
# Matcher behaviour.
# ---------------------------------------------------------------------------


def test_matcher_recognises_every_invocation_form(check: ModuleType) -> None:
    source = "\n".join(
        [
            "def probe(*, args, runner, transport, target, plan):",
            "    runner.run(argv=[args.fabro_bin, 'ps'], cwd=None, timeout_seconds=1.0)",
            "    runner.run(argv=[fabro_bin, 'rm'], cwd=None, timeout_seconds=1.0)",
            "    runner.run(argv=[str(plan.fabro_bin), 'ps'], cwd=None, timeout_seconds=1.0)",
            "    runner.run(argv=['fabro', 'version'], cwd=None, timeout_seconds=1.0)",
            "    runner.run(argv=(args.fabro_bin, 'events'), cwd=None, timeout_seconds=1.0)",
            "    fabro_http_request(target=target, transport=transport, method='GET',"
            " path='/runs', payload=None, timeout_seconds=1.0)",
            "    transport.send(method='GET', url='https://f/x', headers={}, body=None,"
            " timeout_seconds=1.0)",
            "    return '/api/v1/runs'",
            "",
        ]
    )

    findings = check.source_findings(source=source, relpath="probe.py")

    # The two wrapped entries above are IMPLICITLY CONCATENATED, so each is one
    # line of the generated source rather than two; the expected numbers are the
    # generated file's, not this module's.
    assert [(finding.lineno, finding.form) for finding in findings] == [
        (2, check.FORM_BINARY_ARGV),
        (3, check.FORM_BINARY_ARGV),
        (4, check.FORM_BINARY_ARGV),
        (5, check.FORM_BINARY_ARGV),
        (6, check.FORM_BINARY_ARGV),
        (7, check.FORM_TRANSPORT_CALL),
        (8, check.FORM_TRANSPORT_CALL),
        (9, check.FORM_SERVER_API_PATH),
    ]


def test_matcher_ignores_reads_that_are_not_invocations(check: ModuleType) -> None:
    source = "\n".join(
        [
            '"""Prose naming fabro_bin, fabro_http_request and /api/v1 is invisible."""',
            "def probe(*, args, plan, runner, queue, port):",
            "    # A comment showing argv=[fabro_bin, 'ps'] is invisible too.",
            "    plan_bin = resolve_fabro_bin(cwd=args.repo)",
            "    built = FabroPort(fabro_bin=plan_bin, target=None, runner=runner, cwd=None)",
            "    passed = make_plan(fabro_bin=plan.fabro_bin)",
            "    listed = [plan.repo, plan.fabro_bin]",
            "    queue.send(payload={'fabro_bin': plan_bin})",
            "    runner.run(argv=['git', 'status'], cwd=None, timeout_seconds=1.0)",
            "    route = '/runs/42/questions'",
            "    return [built, passed, listed, route, port.ps(timeout_seconds=1.0)]",
            "",
        ]
    )

    assert check.source_findings(source=source, relpath="probe.py") == []
