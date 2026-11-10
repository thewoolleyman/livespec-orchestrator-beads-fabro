"""Tests for the `materialized_workflow_toml_size` check (Scenario 279, bd-ib-p5e32s).

The check renders every file of the Dispatcher's dispatch package through the
Dispatcher's own functions. It fails above 90 percent of Fabro's 524,288-byte
per-file cap, above 90 percent of its 2 MiB package cap, or above 90 percent of
its 512-file cap. The verdict cases inject measurements of exact sizes, because
the scenario names exact sizes. Every other case renders for real, so no test here
pins what a real render measures, except the worst-case subject case: a fixture
sized from the largest live subject must render under the threshold.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "materialized_workflow_toml_size.py"
_OWN_NAME = json.loads((_REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["name"]
_GIT_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "materialized_workflow_toml_size_under_test", _CHECK_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_CHECK = _load_check()
_MEASURE = sys.modules["_workflow_package_measure"]


@pytest.fixture(autouse=True)
def github_app_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Present on every factory host; set here so the check's default never leaks."""
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")


def _events(*, stderr: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stderr.splitlines() if line.startswith("{")]


def _sized(*, sizes: list[int | None]) -> Callable[..., list[Any]]:
    def measure(**_: object) -> list[Any]:
        return [
            _MEASURE.Measurement(
                repository="fixture",
                workflow="implement-work-item",
                case="representative",
                file=f"file-{index}",
                size=size,
            )
            for index, size in enumerate(sizes)
        ]

    return measure


def test_the_representative_item_carries_a_goal_of_exactly_the_contract_size() -> None:
    item = _MEASURE.representative_item()

    assert len(item.description.encode("utf-8")) == _MEASURE.GOAL_BYTES == 20_480
    assert item.description.startswith("## Definition of Done\n")


def test_this_repository_renders_every_package_file_under_the_threshold(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = _CHECK.main(argv=[])

    events = _events(stderr=capsys.readouterr().err)
    measured = [e for e in events if e["event"] == "workflow package file measured"]
    assert status == 0, [e for e in events if e["level"] == "error"]
    assert {(e["case"], e["file"]) for e in measured} >= {
        ("representative", "workflow.toml"),
        ("worst-case", "workflow.toml"),
        ("worst-case", "workflow.fabro"),
    }


def test_the_worst_case_subject_is_larger_than_the_largest_measured_live_subject() -> None:
    """The fixture's size is the margin: the largest live block measured was 120,466 bytes."""
    assert _MEASURE.WORST_CASE_SUBJECT_BYTES > 120_466


def test_a_file_over_the_threshold_fails_naming_size_threshold_and_limit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = _CHECK.main(argv=[], measure=_sized(sizes=[471_860]))

    stderr = capsys.readouterr().err
    assert status == 1
    assert "471860 bytes" in stderr
    assert "471859" in stderr
    assert "524288" in stderr


def test_a_file_at_or_under_the_threshold_passes_and_prints_its_size(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = _CHECK.main(argv=[], measure=_sized(sizes=[463_547]))

    events = _events(stderr=capsys.readouterr().err)
    assert status == 0
    assert [event["size"] for event in events] == [463_547]


def test_a_package_over_its_threshold_fails_even_when_every_file_fits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    status = _CHECK.main(argv=[], measure=_sized(sizes=[400_000] * 5))

    stderr = capsys.readouterr().err
    assert status == 1
    assert "the package is 2000000 bytes" in stderr
    assert "1887436" in stderr


def test_a_package_with_too_many_files_fails(capsys: pytest.CaptureFixture[str]) -> None:
    status = _CHECK.main(argv=[], measure=_sized(sizes=[1] * 461))

    assert status == 1
    assert "the package holds 461 files" in capsys.readouterr().err


def test_a_run_config_that_does_not_render_fails(capsys: pytest.CaptureFixture[str]) -> None:
    status = _CHECK.main(argv=[], measure=_sized(sizes=[None]))

    assert status == 1
    assert "did not render" in capsys.readouterr().err


def _git(*, cwd: Path, argv: list[str]) -> None:
    _ = subprocess.run(["git", *argv], cwd=cwd, env=_GIT_ENV, check=True, capture_output=True)


def _fleet(*, root: Path, members: list[str]) -> Path:
    manifest = root / "livespec" / ".livespec-fleet-manifest.jsonc"
    manifest.parent.mkdir(parents=True)
    entries = [{"repo": name, "class": "library"} for name in members]
    _ = manifest.write_text(
        "// fixture manifest\n" + json.dumps({"owner": "fixture-owner", "fleet": entries}),
        encoding="utf-8",
    )
    return root


def _member(*, root: Path, name: str, files: dict[str, str]) -> None:
    """A clone whose `origin/master` carries `files`, and whose working tree does not."""
    repository = root / name
    repository.mkdir()
    _git(cwd=repository, argv=["init", "-q"])
    for relative, text in files.items():
        path = repository / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(text, encoding="utf-8")
    _git(cwd=repository, argv=["add", "-A"])
    _git(cwd=repository, argv=["commit", "-q", "--allow-empty", "-m", "fixture"])
    _git(cwd=repository, argv=["update-ref", "refs/remotes/origin/master", "HEAD"])
    _git(cwd=repository, argv=["rm", "-q", "-r", "--cached", "--ignore-unmatch", "."])
    _ = (repository / ".livespec.jsonc").write_text("not the committed config", encoding="utf-8")


def test_the_fleet_scope_renders_every_member_from_its_committed_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _fleet(root=tmp_path, members=[_OWN_NAME, "fixture-member"])
    _member(root=root, name="fixture-member", files={".livespec.jsonc": "{}\n"})

    status = _CHECK.main(argv=["--fleet", str(root)])

    events = _events(stderr=capsys.readouterr().err)
    assert status == 0, [e for e in events if e["level"] == "error"]
    assert {event["repository"] for event in events} == {_OWN_NAME, "fixture-member"}


def test_a_fleet_member_with_no_clone_fails_naming_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _fleet(root=tmp_path, members=["absent-member", "uncommitted-member"])
    _member(root=root, name="uncommitted-member", files={"README.md": "no config\n"})

    status = _CHECK.main(argv=["--fleet", str(root)])

    stderr = capsys.readouterr().err
    assert status == 1
    assert "fleet member absent-member: no clone" in stderr
    assert "fleet member uncommitted-member: no clone" in stderr


def test_a_member_whose_own_run_config_does_not_render_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _fleet(root=tmp_path, members=["fixture-member"])
    own = ".fabro/workflows/implement-work-item"
    _member(
        root=root,
        name="fixture-member",
        files={
            ".livespec.jsonc": "{}\n",
            f"{own}/workflow.toml": "[run]\n",
            f"{own}/workflow.fabro": "digraph g {}\n",
        },
    )

    status = _CHECK.main(argv=["--fleet", str(root)])

    assert status == 1
    assert "fixture-member implement-work-item (representative): workflow.toml did not render" in (
        capsys.readouterr().err
    )


def test_a_missing_manifest_fails_rather_than_measuring_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["materialized_workflow_toml_size.py", "--fleet"])
    monkeypatch.setenv("LIVESPEC_SIBLING_CLONES_ROOT", str(tmp_path))

    status = _CHECK.main()

    assert status == 1
    assert "is missing, so no member was measured" in capsys.readouterr().err


def test_a_malformed_manifest_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = tmp_path / "livespec" / ".livespec-fleet-manifest.jsonc"
    manifest.parent.mkdir(parents=True)
    _ = manifest.write_text('{"owner": "fixture-owner"}', encoding="utf-8")

    status = _CHECK.main(argv=["--fleet", str(tmp_path)])

    assert status == 1
    assert "does not parse" in capsys.readouterr().err


def test_with_no_root_given_the_clones_sit_beside_the_primary_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LIVESPEC_SIBLING_CLONES_ROOT", raising=False)
    primary = tmp_path / "projects" / "repo"
    (primary / ".git" / "worktrees" / "wt").mkdir(parents=True)
    worktree = tmp_path / "worktrees" / "wt"
    worktree.mkdir(parents=True)
    _ = (worktree / ".git").write_text(f"gitdir: {primary}/.git/worktrees/wt\n", encoding="utf-8")

    from_worktree = _CHECK.clones_root(arguments=[], repo_root=worktree)
    from_primary = _CHECK.clones_root(arguments=[], repo_root=primary)

    assert from_worktree == from_primary == tmp_path / "projects"
