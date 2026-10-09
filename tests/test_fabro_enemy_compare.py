"""Tests for the Fabro Enemy Unit Test comparison harness."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

__all__: list[str] = []


def test_comparison_harness_writes_per_assertion_delta(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)
    calls: list[tuple[str, str, list[str], Path]] = []

    def fake_run(
        *, args: list[str], env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        junit_path = _junit_path(args=args)
        calls.append((env["FABRO_EUT_BIN"], env["FABRO_EUT_SERVER"], args, junit_path))
        if len(calls) == 1:
            _write_junit(
                path=junit_path,
                cases={
                    "test_tier0_fabro.py::test_version": "passed",
                    "test_tier0_fabro.py::test_validate": "failed",
                },
            )
            return subprocess.CompletedProcess(args=args, returncode=1)
        _write_junit(
            path=junit_path,
            cases={
                "test_tier0_fabro.py::test_version": "passed",
                "test_tier0_fabro.py::test_validate": "passed",
                "test_tier0_fabro.py::test_new_candidate_case": "failed",
            },
        )
        return subprocess.CompletedProcess(args=args, returncode=1)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)
    artifact_path = tmp_path / "comparison.md"

    exit_code = compare.main(
        argv=[
            "--pinned-bin",
            "/opt/fabro-pinned",
            "--pinned-server",
            "http://127.0.0.1:32276",
            "--candidate-bin",
            "/opt/fabro-candidate",
            "--candidate-server",
            "http://127.0.0.1:32286",
            "--artifact",
            str(artifact_path),
        ]
    )

    assert exit_code == 1
    assert [(call[0], call[1]) for call in calls] == [
        ("/opt/fabro-pinned", "http://127.0.0.1:32276"),
        ("/opt/fabro-candidate", "http://127.0.0.1:32286"),
    ]
    test_args = [arg for arg in calls[0][2] if arg.startswith("fabro-enemy-unit-tests/")]
    # A CLOSED list, kept closed on purpose: the harness globs the tier 0
    # modules, so a new one must be seen here rather than silently joining or
    # silently missing the comparison the pinned-versus-candidate verdict rests
    # on. Adding a tier 0 module means updating this line.
    assert test_args == [
        "fabro-enemy-unit-tests/test_tier0_fabro.py",
        "fabro-enemy-unit-tests/test_tier0_fabro_port_surface.py",
        "fabro-enemy-unit-tests/test_tier0_watchdog_gap.py",
    ]
    artifact = artifact_path.read_text()
    assert "| Assertion | Pinned | Candidate | Delta |" in artifact
    assert "| `test_tier0_fabro.py::test_validate` | failed | passed | improved |" in artifact
    assert (
        "| `test_tier0_fabro.py::test_new_candidate_case` | missing | failed | candidate-only |"
        in artifact
    )
    assert "## Delta" in artifact
    assert "- Regressions: 0" in artifact
    assert "- Improvements: 1" in artifact
    assert "- Candidate-only assertions: 1" in artifact


def test_comparison_harness_reports_empty_delta_for_pinned_vs_pinned(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)

    def fake_run(
        *, args: list[str], env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert env["FABRO_EUT_BIN"] == "fabro"
        assert env["FABRO_EUT_SERVER"] == "http://127.0.0.1:32276"
        _write_junit(
            path=_junit_path(args=args),
            cases={
                "test_tier0_fabro.py::test_version": "passed",
                "test_tier0_fabro.py::test_validate": "passed",
            },
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)
    artifact_path = tmp_path / "comparison.md"

    exit_code = compare.main(argv=["--artifact", str(artifact_path)])

    assert exit_code == 0
    artifact = artifact_path.read_text()
    assert "| `test_tier0_fabro.py::test_version` | passed | passed | unchanged |" in artifact
    assert "- Regressions: 0" in artifact
    assert "- Improvements: 0" in artifact
    assert "- Pinned-only assertions: 0" in artifact
    assert "- Candidate-only assertions: 0" in artifact


def test_comparison_harness_leaves_unset_expected_values_absent(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)
    expected_keys = [
        "FABRO_EUT_EXPECTED_CLIENT_VERSION",
        "FABRO_EUT_EXPECTED_CLIENT_COMMIT",
        "FABRO_EUT_EXPECTED_CLIENT_DATE",
        "FABRO_EUT_EXPECTED_SERVER_VERSION",
        "FABRO_EUT_EXPECTED_SERVER_COMMIT",
        "FABRO_EUT_EXPECTED_SERVER_DATE",
    ]
    for key in expected_keys:
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.replace("FABRO_EUT_", "FABRO_EUT_PINNED_", 1), raising=False)
        monkeypatch.delenv(key.replace("FABRO_EUT_", "FABRO_EUT_CANDIDATE_", 1), raising=False)

    def fake_run(
        *, args: list[str], env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert all(key not in env for key in expected_keys)
        _write_junit(
            path=_junit_path(args=args), cases={"test_tier0_fabro.py::test_version": "passed"}
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)

    assert compare.main(argv=["--artifact", str(tmp_path / "comparison.md")]) == 0


def test_comparison_harness_maps_target_specific_expected_values(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)
    monkeypatch.setenv("FABRO_EUT_PINNED_EXPECTED_CLIENT_VERSION", "0.254.0")
    monkeypatch.setenv("FABRO_EUT_CANDIDATE_EXPECTED_CLIENT_VERSION", "0.255.0")
    seen_versions: list[str] = []

    def fake_run(
        *, args: list[str], env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        seen_versions.append(env["FABRO_EUT_EXPECTED_CLIENT_VERSION"])
        _write_junit(
            path=_junit_path(args=args),
            cases={"test_tier0_fabro.py::test_version": "passed"},
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)

    assert compare.main(argv=["--artifact", str(tmp_path / "comparison.md")]) == 0
    assert seen_versions == ["0.254.0", "0.255.0"]


def test_comparison_harness_fails_clearly_when_tier0_tests_are_absent(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)
    monkeypatch.setattr(compare, "_TEST_ROOT", tmp_path)

    with pytest.raises(FileNotFoundError) as error:
        compare.main(argv=["--artifact", str(tmp_path / "comparison.md")])

    assert (
        str(error.value) == f"no Fabro Enemy Unit Test files matched {tmp_path / 'test_tier0_*.py'}"
    )


def test_comparison_harness_exits_non_zero_when_candidate_skips_a_passing_assertion(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """A skip on one target is a delta, so it must move the exit code.

    Both pytest legs exit 0 here -- pytest counts a skip as a success -- so this
    is the exact case the old exit code could not see.
    """
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)
    calls: list[Path] = []

    def fake_run(
        *, args: list[str], env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert env["FABRO_EUT_BIN"] != ""
        calls.append(_junit_path(args=args))
        candidate_status = "skipped" if len(calls) == 2 else "passed"
        _write_junit(
            path=calls[-1],
            cases={
                "test_tier0_fabro.py::test_version": "passed",
                "test_tier0_fabro.py::test_watchdog_gap": candidate_status,
            },
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)
    artifact_path = tmp_path / "comparison.md"

    exit_code = compare.main(argv=["--artifact", str(artifact_path)])

    assert exit_code == 1
    artifact = artifact_path.read_text()
    assert (
        "| `test_tier0_fabro.py::test_watchdog_gap` | passed | skipped | skip-delta |" in artifact
    )
    assert "- Skip deltas: 1" in artifact
    assert "- Regressions: 0" in artifact
    assert "- Total deltas: 1" in artifact


def test_comparison_harness_exits_non_zero_for_a_pinned_only_assertion(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """An assertion present only on the pinned side is a delta with both legs green."""
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)
    calls: list[Path] = []

    def fake_run(
        *, args: list[str], env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert env["FABRO_EUT_SERVER"] != ""
        calls.append(_junit_path(args=args))
        cases = {"test_tier0_fabro.py::test_version": "passed"}
        if len(calls) == 1:
            cases["test_tier0_fabro.py::test_pinned_only_case"] = "passed"
        _write_junit(path=calls[-1], cases=cases)
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)
    artifact_path = tmp_path / "comparison.md"

    exit_code = compare.main(argv=["--artifact", str(artifact_path)])

    assert exit_code == 1
    artifact = artifact_path.read_text()
    assert (
        "| `test_tier0_fabro.py::test_pinned_only_case` | passed | missing | pinned-only |"
        in artifact
    )
    assert "- Pinned-only assertions: 1" in artifact
    assert "- Total deltas: 1" in artifact


def test_comparison_harness_exits_zero_for_an_identical_pass_set_on_both_targets(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Control: the exit code is not simply stuck at non-zero once deltas are consulted."""
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)

    def fake_run(
        *, args: list[str], env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert env["FABRO_EUT_BIN"] != ""
        _write_junit(
            path=_junit_path(args=args),
            cases={
                "test_tier0_fabro.py::test_version": "passed",
                "test_tier0_fabro.py::test_watchdog_gap": "skipped",
            },
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)
    artifact_path = tmp_path / "comparison.md"

    exit_code = compare.main(argv=["--artifact", str(artifact_path)])

    assert exit_code == 0
    artifact = artifact_path.read_text()
    assert (
        "| `test_tier0_fabro.py::test_watchdog_gap` | skipped | skipped | unchanged |" in artifact
    )
    assert "- Skip deltas: 0" in artifact
    assert "- Total deltas: 0" in artifact


def test_comparison_harness_exits_non_zero_for_a_genuinely_failing_testcase(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Control: a real regression still fails, and is counted as a regression, not a skip."""
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)
    calls: list[Path] = []

    def fake_run(
        *, args: list[str], env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert env["FABRO_EUT_BIN"] != ""
        calls.append(_junit_path(args=args))
        candidate_status = "failed" if len(calls) == 2 else "passed"
        _write_junit(
            path=calls[-1],
            cases={"test_tier0_fabro.py::test_version": candidate_status},
        )
        return subprocess.CompletedProcess(args=args, returncode=1 if len(calls) == 2 else 0)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)
    artifact_path = tmp_path / "comparison.md"

    exit_code = compare.main(argv=["--artifact", str(artifact_path)])

    assert exit_code == 1
    artifact = artifact_path.read_text()
    assert "| `test_tier0_fabro.py::test_version` | passed | failed | regressed |" in artifact
    assert "- Regressions: 1" in artifact
    assert "- Skip deltas: 0" in artifact
    assert "- Total deltas: 1" in artifact


def test_comparison_harness_writes_a_git_ignored_artifact_when_no_artifact_flag_is_given(
    *,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """The DEFAULT `--artifact` is the path `just fabro-enemy-compare` actually writes.

    Every other case in this file passes an explicit `--artifact` under `tmp_path`,
    so the default was this module's one uncovered path -- which is how it shipped
    pointing at a path inside the repo that `.gitignore` did not cover, leaving the
    working tree dirty after the sanctioned entry point ran. The two halves are
    pinned in ONE case deliberately: asserting only that a default exists would not
    catch a default that is not ignored, and asserting only that
    `fabro-enemy-unit-tests/comparison.md` is ignored would not catch a default that
    moved off it. `git check-ignore` is the behaviour test -- a grep of `.gitignore`
    for the literal would still pass if a later negation pattern un-ignored it.
    """
    module_path = Path("fabro-enemy-unit-tests/compare.py")

    assert module_path.is_file()
    compare = _load_compare_module(module_path=module_path)
    default_artifact = Path("fabro-enemy-unit-tests/comparison.md")
    ignored = subprocess.run(
        args=["git", "check-ignore", "--quiet", str(default_artifact)],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
    )

    assert ignored.returncode == 0, f"{default_artifact} is not git-ignored"

    (tmp_path / default_artifact.parent).mkdir()
    (tmp_path / default_artifact.parent / "test_tier0_fabro.py").write_text("")
    monkeypatch.chdir(tmp_path)

    def fake_run(
        *, args: list[str], env: dict[str, str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert env["FABRO_EUT_BIN"] == "fabro"
        _write_junit(
            path=_junit_path(args=args),
            cases={"test_tier0_fabro.py::test_version": "passed"},
        )
        return subprocess.CompletedProcess(args=args, returncode=0)

    monkeypatch.setattr(compare.subprocess, "run", fake_run)

    exit_code = compare.main(argv=[])

    assert exit_code == 0
    artifact = (tmp_path / default_artifact).read_text()
    assert "# Fabro Enemy Unit Test Comparison" in artifact
    assert "| `test_tier0_fabro.py::test_version` | passed | passed | unchanged |" in artifact
    assert "- Total deltas: 0" in artifact


def _load_compare_module(*, module_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("fabro_enemy_compare", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _junit_path(*, args: list[str]) -> Path:
    return Path(
        next(arg.removeprefix("--junitxml=") for arg in args if arg.startswith("--junitxml="))
    )


def _write_junit(*, path: Path, cases: dict[str, str]) -> None:
    testcase_xml = "\n".join(
        _testcase_xml(assertion_id=key, status=value) for key, value in cases.items()
    )
    path.write_text(f'<testsuite tests="{len(cases)}">\n{testcase_xml}\n</testsuite>\n')


def _testcase_xml(*, assertion_id: str, status: str) -> str:
    if status == "passed":
        return f'  <testcase classname="{assertion_id}" name="" />'
    if status == "skipped":
        return f'  <testcase classname="{assertion_id}" name=""><skipped /></testcase>'
    return f'  <testcase classname="{assertion_id}" name=""><failure /></testcase>'
