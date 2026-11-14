"""Tests for the affected-tests gate's selection and coverage verdict.

The gate widens a changed product module's tests beyond its mirror-paired test file
to every test module that imports it directly or through another imported module.
These cases build a throwaway repository whose import graph has each shape the scan
must follow, and a fake `uv` that records what the gate asks pytest and coverage to
do, so the verdict is read from the arguments rather than from a nested run.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "_affected_tests_selection.py"
_NPROCS = _REPO_ROOT / "dev-tooling" / "just-test-nprocs.sh"

_PKG = ".claude-plugin/scripts/pkg"
_WORKFLOW = ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    f'source_tree_prefixes = ["{_PKG}/"]\n'
    "[[tool.livespec_dev_tooling.mirror_pairings]]\n"
    f'source_tree = "{_PKG}"\n'
    'test_tree = "tests/pkg"\n'
    "[[tool.livespec_dev_tooling.mirror_pairings]]\n"
    'source_tree = "dev-tooling/checks"\n'
    'test_tree = "tests/dev-tooling/checks"\n'
)
_BASE: dict[str, str] = {
    "pyproject.toml": _PYPROJECT,
    f"{_PKG}/__init__.py": "",
    f"{_PKG}/a.py": "VALUE = 1\n",
    f"{_PKG}/b.py": "from . import a\n",
    f"{_PKG}/c.py": "from .a import VALUE\n",
    f"{_PKG}/orphan.py": "ORPHAN = 1\n",
    f"{_PKG}/json.py": "SHADOW = 1\n",
    f"{_PKG}/sub/__init__.py": "from .. import a\n",
    f"{_PKG}/sub/deep.py": "from ..c import VALUE\n",
    "dev-tooling/checks/script.py": "SCRIPT = 1\n",
    "tests/pkg/test_a.py": "def test_a() -> None: ...\n",
    "tests/pkg/test_a_edges.py": "def test_a_edges() -> None: ...\n",
    "tests/pkg/test_atlas.py": "def test_atlas() -> None: ...\n",
    "tests/pkg/test_b.py": "import pkg.b\n",
    "tests/pkg/test_deep.py": "from pkg.sub.deep import VALUE\n",
    "tests/pkg/test_direct.py": "import pkg.a\n",
    "tests/pkg/test_unrelated.py": "import json\n",
    "tests/dev-tooling/checks/test_loader.py": 'PATH = "dev-tooling/checks/script.py"\n',
    "tests/helper_reads_graph.py": f'GRAPH = "{_WORKFLOW}"\n',
    "tests/test_reads_graph.py": "import helper_reads_graph\n",
    "tests/test_names_graph.py": 'NAME = "workflow.fabro"\n',
}


def _load() -> ModuleType:
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    spec = importlib.util.spec_from_file_location(
        "affected_tests_selection_under_test", _MODULE_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(*, root: Path, arguments: list[str]) -> None:
    done = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr


def _repo(*, root: Path, files: dict[str, str] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for relative, text in (_BASE if files is None else files).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(text, encoding="utf-8")
    _git(root=root, arguments=["init", "--quiet", "-b", "master"])
    return root


def test_a_module_selects_its_mirror_test_and_every_direct_or_transitive_importer(
    *, tmp_path: Path
) -> None:
    """The mirror test, its sibling, the direct importers and the importers of importers."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=[f"{_PKG}/a.py"])

    assert outcome.measured == (f"{_PKG}/a.py",)
    assert list(outcome.tests) == [
        "tests/pkg/test_a.py",
        "tests/pkg/test_a_edges.py",
        "tests/pkg/test_b.py",
        "tests/pkg/test_deep.py",
        "tests/pkg/test_direct.py",
    ]


def test_a_stem_shared_with_another_modules_test_is_not_a_sibling(*, tmp_path: Path) -> None:
    """`test_atlas.py` is not a sibling of `test_a.py`: the stem match needs its underscore."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=[f"{_PKG}/a.py"])

    assert "tests/pkg/test_atlas.py" not in list(outcome.tests)
    assert "tests/pkg/test_unrelated.py" not in list(outcome.tests)


def test_a_script_a_test_names_by_path_is_reached_through_the_string(*, tmp_path: Path) -> None:
    """A test that loads a script by its path never imports it, and is still selected."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=["dev-tooling/checks/script.py"])

    assert list(outcome.tests) == ["tests/dev-tooling/checks/test_loader.py"]
    assert outcome.measured == ()


def test_a_changed_test_runs_even_when_it_imports_nothing(*, tmp_path: Path) -> None:
    """A changed test module is itself affected."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=["tests/pkg/test_unrelated.py"])

    assert list(outcome.tests) == ["tests/pkg/test_unrelated.py"]


def test_a_conftest_that_reaches_the_module_selects_the_tests_requesting_its_fixtures(
    *, tmp_path: Path
) -> None:
    """A test reaches the module through a fixture it requests by argument or by name."""
    module = _load()
    conftest = (
        "import functools\n"
        "import pytest\n"
        "from pytest import fixture\n"
        "from pkg import orphan\n"
        "@pytest.fixture\n"
        "def widget() -> None: ...\n"
        "@pytest.fixture(autouse=True)\n"
        "async def gadget() -> None: ...\n"
        "@fixture\n"
        "def named() -> None: ...\n"
        "@functools.cache\n"
        "def helper() -> None: ...\n"
    )
    files = {
        **_BASE,
        "tests/pkg/conftest.py": conftest,
        "tests/pkg/test_wants_widget.py": "def test_it(widget) -> None: ...\n",
        "tests/pkg/test_wants_named.py": 'import pytest\n@pytest.mark.usefixtures("named")\ndef test_it() -> None: ...\n',
        "tests/pkg/test_wants_helper.py": "def test_it(helper) -> None: ...\n",
        "tests/elsewhere/test_wants_widget.py": "def test_it(widget) -> None: ...\n",
    }
    root = _repo(root=tmp_path / "repo", files=files)

    outcome = module.select(root=root, changed=[f"{_PKG}/orphan.py"])

    assert list(outcome.tests) == [
        "tests/pkg/test_wants_named.py",
        "tests/pkg/test_wants_widget.py",
    ]


def test_a_changed_module_no_test_reaches_cannot_be_scoped(*, tmp_path: Path) -> None:
    """A module with no mirror test and no importer test is a change the gate cannot scope."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=[f"{_PKG}/orphan.py"])

    assert outcome.reason == f"no test module imports or names {_PKG}/orphan.py"


@pytest.mark.parametrize("path", ["pyproject.toml", "justfile", "dev-tooling/just-check.sh"])
def test_a_shared_configuration_change_cannot_be_scoped(*, tmp_path: Path, path: str) -> None:
    """A file the whole suite reads cannot be mapped to a subset of tests."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=[f"{_PKG}/a.py", path])

    assert outcome.reason == f"{path} is shared configuration read by the whole suite"


def test_a_bare_import_of_a_standard_library_name_does_not_reach_a_module_named_like_it(
    *, tmp_path: Path
) -> None:
    """`import json` in a test is the standard library, not the package's own `json.py`."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=[f"{_PKG}/json.py"])

    assert outcome.reason == f"no test module imports or names {_PKG}/json.py"


def test_a_python_file_under_dev_tooling_is_not_shared_configuration(*, tmp_path: Path) -> None:
    """Only dev-tooling's non-Python files are shared; a `.py` there is scoped by its tests."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=["dev-tooling/checks/script.py"])

    assert list(outcome.tests) == ["tests/dev-tooling/checks/test_loader.py"]


def test_a_change_with_no_python_and_no_graph_selects_no_test(*, tmp_path: Path) -> None:
    """A documentation-only change names no module, so the gate has nothing to scope."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=["README.md"])

    assert outcome.reason == "the change selects no test module"


def test_a_file_that_does_not_parse_cannot_be_scoped(*, tmp_path: Path) -> None:
    """The scan cannot say what an unparseable module imports, so it hands over to the aggregate."""
    module = _load()
    root = _repo(root=tmp_path / "repo", files={**_BASE, "tests/pkg/test_broken.py": "def (:\n"})

    outcome = module.select(root=root, changed=[f"{_PKG}/a.py"])

    assert outcome.reason == "tests/pkg/test_broken.py cannot be parsed (SyntaxError)"


def test_a_repository_git_cannot_list_cannot_be_scoped(*, tmp_path: Path) -> None:
    """A directory that is not a git repository has no file list."""
    module = _load()
    root = tmp_path / "plain"
    root.mkdir()

    outcome = module.select(root=root, changed=[f"{_PKG}/a.py"])

    assert outcome.reason == "the repository's files could not be listed"
    assert module.changed_paths(root=root) is None


def test_a_workflow_change_selects_the_tests_that_read_the_graph(*, tmp_path: Path) -> None:
    """Tests that name the graph, and tests that import a module naming it, are selected."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=[_WORKFLOW])

    assert list(outcome.tests) == ["tests/test_names_graph.py", "tests/test_reads_graph.py"]
    assert outcome.measured == ()


def test_a_workflow_change_beside_a_module_change_selects_both_sets(*, tmp_path: Path) -> None:
    """The graph's tests run together with the tests the `.py` change selects."""
    module = _load()
    root = _repo(root=tmp_path / "repo")

    outcome = module.select(root=root, changed=[_WORKFLOW, f"{_PKG}/a.py"])

    assert "tests/test_names_graph.py" in list(outcome.tests)
    assert "tests/pkg/test_a.py" in list(outcome.tests)
    assert outcome.measured == (f"{_PKG}/a.py",)


def test_a_workflow_change_no_test_reads_cannot_be_scoped(*, tmp_path: Path) -> None:
    """When no test module names the graph the gate cannot say which tests read it."""
    module = _load()
    files = {k: v for k, v in _BASE.items() if "graph" not in k}
    root = _repo(root=tmp_path / "repo", files=files)

    outcome = module.select(root=root, changed=[_WORKFLOW])

    assert outcome.reason == "no test module reads workflow.fabro"


def test_the_changed_paths_are_the_branch_diff_and_the_staged_additions(*, tmp_path: Path) -> None:
    """A committed change and a staged change are both changed; a staged deletion is not."""
    module = _load()
    root = _repo(root=tmp_path / "repo")
    _git(root=root, arguments=["add", "."])
    _git(
        root=root,
        arguments=["-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "base"],
    )
    _git(root=root, arguments=["update-ref", "refs/remotes/origin/master", "HEAD"])
    _ = (root / f"{_PKG}/a.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(root=root, arguments=["add", "."])
    _git(
        root=root,
        arguments=["-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "branch"],
    )
    _ = (root / f"{_PKG}/b.py").write_text("from . import a\nVALUE = 3\n", encoding="utf-8")
    _git(root=root, arguments=["add", f"{_PKG}/b.py"])
    _git(root=root, arguments=["rm", "-q", f"{_PKG}/c.py"])

    assert module.changed_paths(root=root) == [f"{_PKG}/a.py", f"{_PKG}/b.py"]


def _fake_uv(*, directory: Path) -> Path:
    """A `uv` that records its arguments and the environment pytest would measure under."""
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "uv.log"
    program = directory / "uv"
    _ = program.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{log}'\n"
        f"printf 'COVERAGE_FILE=%s COV_CORE=%s\\n' \"${{COVERAGE_FILE:-}}\" \"${{COV_CORE_SOURCE:-}}\" >> '{log}'\n"
        'case "$*" in *"coverage report"*) exit "${FAKE_COVERAGE_STATUS:-0}" ;; esac\n'
        'exit "${FAKE_PYTEST_STATUS:-0}"\n',
        encoding="utf-8",
    )
    _ = program.chmod(program.stat().st_mode | stat.S_IXUSR)
    return log


def _committed_repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    root = _repo(root=tmp_path / "repo")
    (root / "dev-tooling").mkdir(exist_ok=True)
    _ = shutil.copy(_NPROCS, root / "dev-tooling" / "just-test-nprocs.sh")
    _git(root=root, arguments=["add", "."])
    _git(
        root=root,
        arguments=["-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "base"],
    )
    _git(root=root, arguments=["update-ref", "refs/remotes/origin/master", "HEAD"])
    log = _fake_uv(directory=tmp_path / "bin")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("COV_CORE_SOURCE", "leaked")
    monkeypatch.chdir(root)
    return root, log


def _stage(*, root: Path, path: str, text: str) -> None:
    _ = (root / path).write_text(text, encoding="utf-8")
    _git(root=root, arguments=["add", path])


def test_the_gate_runs_the_selected_tests_then_holds_the_changed_module_to_full_coverage(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pytest runs every selected test under an isolated data file; coverage names the lines."""
    module = _load()
    root, log = _committed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(root=root, path=f"{_PKG}/a.py", text="VALUE = 2\n")

    status = module.main()

    pytest_line, env_line, report_line, _ = log.read_text(encoding="utf-8").splitlines()
    assert status == 0
    assert pytest_line.startswith("run pytest -n ")
    assert pytest_line.endswith(
        "--cov-fail-under=0 tests/pkg/test_a.py tests/pkg/test_a_edges.py tests/pkg/test_b.py"
        " tests/pkg/test_deep.py tests/pkg/test_direct.py"
    )
    assert "COV_CORE=leaked" not in env_line
    assert "COVERAGE_FILE=/" in env_line
    assert f"--include={_PKG}/a.py" in report_line
    assert "--fail-under=100" in report_line
    assert "--show-missing" in report_line


@pytest.mark.parametrize(("pytest_status", "coverage_status"), [(1, 0), (0, 2)])
def test_a_failing_test_or_an_uncovered_line_refuses_the_commit(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pytest_status: int, coverage_status: int
) -> None:
    """The gate's verdict is the worse of the test run and the per-file coverage report."""
    module = _load()
    root, _ = _committed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(root=root, path=f"{_PKG}/a.py", text="VALUE = 2\n")
    monkeypatch.setenv("FAKE_PYTEST_STATUS", str(pytest_status))
    monkeypatch.setenv("FAKE_COVERAGE_STATUS", str(coverage_status))

    assert module.main() == max(pytest_status, coverage_status)


def test_a_workflow_only_change_runs_its_tests_without_a_coverage_report(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No product module changed, so nothing is measured."""
    module = _load()
    root, log = _committed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    workflow = root / _WORKFLOW
    workflow.parent.mkdir(parents=True)
    _stage(root=root, path=_WORKFLOW, text="digraph {}\n")

    status = module.main()

    assert status == 0
    assert "coverage report" not in log.read_text(encoding="utf-8")
    assert "tests/test_names_graph.py" in log.read_text(encoding="utf-8")


def test_a_change_the_gate_cannot_scope_exits_75_without_running_anything(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The commit hook reads 75 as 'run the full check aggregate instead'."""
    module = _load()
    root, log = _committed_repo(tmp_path=tmp_path, monkeypatch=monkeypatch)
    _stage(root=root, path="pyproject.toml", text=_PYPROJECT + "# edited\n")

    assert module.main() == module.EXIT_CANNOT_SCOPE == 75
    assert not log.exists()


def test_a_diff_git_cannot_take_exits_75(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no `origin/master` the changed set is unknown, which is not the same as empty."""
    module = _load()
    root = _repo(root=tmp_path / "bare")
    monkeypatch.chdir(root)

    assert module.main() == 75
