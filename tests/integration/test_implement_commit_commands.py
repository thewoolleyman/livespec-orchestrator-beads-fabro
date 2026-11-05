"""Real-repository coverage for the implement stage's command commits.

The workflow graph invokes these scripts in a sandbox clone.  These tests use
ordinary temporary repositories instead, so checkpoint folding, index shaping,
commit hooks, and the append-only handoff are all observed at the git boundary.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (
    _mechanical_commit_refusal_policy,
)

_ROOT = Path(__file__).parents[2]
_RED = _ROOT / "dev-tooling" / "commit-red.sh"
_GREEN = _ROOT / "dev-tooling" / "commit-green.sh"
_REENTRY_POLICY = _ROOT / "dev-tooling" / "commit-reentry-policy.sh"
_REENTRY_ADMISSION = _ROOT / "dev-tooling" / "commit-reentry-admission.sh"


def _run(*, repo: Path, argv: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run one git or command-script invocation in the temporary repository."""
    return subprocess.run(argv, cwd=repo, check=check, capture_output=True, text=True)


def _git(*, repo: Path, argv: list[str]) -> str:
    """Run git successfully and return its stripped standard output."""
    return _run(repo=repo, argv=["git", *argv]).stdout.strip()


def _initialize_repository(*, tmp_path: Path) -> Path:
    """Make a real repository with an ordinary baseline commit and identity."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _run(repo=repo, argv=["git", "init", "--quiet"])
    _run(repo=repo, argv=["git", "config", "user.name", "Test Author"])
    _run(repo=repo, argv=["git", "config", "user.email", "author@example.invalid"])
    _ = (repo / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "implementation.py"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "chore: baseline"])
    return repo


def _checkpoint(*, repo: Path, name: str) -> None:
    """Commit the current tree in the shape the engine leaves between nodes."""
    _git(
        repo=repo,
        argv=[
            "commit",
            "--all",
            "--quiet",
            "-m",
            f"fabro(run): {name}",
            "-m",
            "Fabro-Run: run",
        ],
    )


def _handoff(*, repo: Path, text: str) -> Path:
    """Write the local, never-committed handoff file the command consumes."""
    path = repo / _git(repo=repo, argv=["rev-parse", "--git-path", "livespec-implement-handoff.md"])
    _ = path.write_text(text, encoding="utf-8")
    return path


def test_commit_red_folds_checkpoints_stages_only_the_named_red_test_and_runs_hooks(
    tmp_path: Path,
) -> None:
    """The Red command lands directly on the base with only the named test staged."""
    assert _RED.is_file()
    repo = _initialize_repository(tmp_path=tmp_path)
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert False\n", encoding="utf-8")
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red")
    handoff = _handoff(repo=repo, text="## red\nRed test file: tests/test_feature.py\n")
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text("#!/bin/sh\nprintf 'hook ran\\n' >> hook.log\n", encoding="utf-8")
    hook.chmod(0o755)

    completed = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert (
        _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"])
        == "tests/test_feature.py"
    )
    assert (repo / "hook.log").read_text(encoding="utf-8") == "hook ran\n"
    assert "## commit_red" in handoff.read_text(encoding="utf-8")
    assert "Exit status: 0" in handoff.read_text(encoding="utf-8")


def test_commit_green_folds_checkpoints_and_amends_the_unpaired_red_with_hooks(
    tmp_path: Path,
) -> None:
    """The Green command folds the engine checkpoint back onto its Red commit."""
    assert _GREEN.is_file()
    repo = _initialize_repository(tmp_path=tmp_path)
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert True\n", encoding="utf-8")
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red")
    _handoff(repo=repo, text="## red\nRed test file: tests/test_feature.py\n")
    hook = repo / ".git" / "hooks" / "commit-msg"
    _ = hook.write_text(
        "#!/bin/sh\ngit interpret-trailers --in-place --trailer "
        "'TDD-Red-Test-File-Checksum: red' \"$1\"\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    assert _run(repo=repo, argv=["bash", str(_RED)], check=False).returncode == 0
    _checkpoint(repo=repo, name="green")
    _ = hook.write_text(
        "#!/bin/sh\ngit interpret-trailers --in-place --trailer "
        "'TDD-Green-Verified-At: green' \"$1\"\n",
        encoding="utf-8",
    )

    completed = _run(repo=repo, argv=["bash", str(_GREEN)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["rev-parse", "HEAD^"]) == base
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "implementation.py\ntests/test_feature.py"
    )
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"])
    assert "TDD-Red-Test-File-Checksum: red" in message
    assert "TDD-Green-Verified-At: green" in message


def test_refused_commands_append_failed_targets_and_the_recorded_output_tail(
    tmp_path: Path,
) -> None:
    """Both commands preserve a hook refusal in the local append-only handoff."""
    repo = _initialize_repository(tmp_path=tmp_path)
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert True\n", encoding="utf-8")
    _ = (repo / "implementation.py").write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red")
    handoff = _handoff(repo=repo, text="## red\nRed test file: tests/test_feature.py\n")
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\nprintf 'Failed targets (1):\\n  - check-example\\n'\n"
        'i=1; while [ "$i" -le 100 ]; do printf \'hook line %s\\n\' "$i"; '
        "i=$((i + 1)); done\nexit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    red = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert red.returncode == 1
    red_handoff = handoff.read_text(encoding="utf-8")
    assert "## commit_red" in red_handoff
    assert "Exit status: 1" in red_handoff
    assert "  - check-example" in red_handoff
    assert "hook line 100" in red_handoff
    assert "hook line 20" not in red_handoff

    hook.unlink()
    assert _run(repo=repo, argv=["bash", str(_RED)], check=False).returncode == 0
    _checkpoint(repo=repo, name="green")
    _ = hook.write_text(
        "#!/bin/sh\nprintf 'Failed targets (1):\\n  - check-green\\n'; exit 1\n", encoding="utf-8"
    )
    hook.chmod(0o755)

    green = _run(repo=repo, argv=["bash", str(_GREEN)], check=False)

    assert green.returncode == 1
    green_handoff = handoff.read_text(encoding="utf-8")
    assert "## commit_green" in green_handoff
    assert "  - check-green" in green_handoff


def test_commit_red_refuses_when_the_latest_red_section_names_no_test_file(tmp_path: Path) -> None:
    """A stale earlier Red test must not let the next Red command make a commit."""
    repo = _initialize_repository(tmp_path=tmp_path)
    before = _git(repo=repo, argv=["rev-parse", "HEAD"])
    handoff = _handoff(
        repo=repo,
        text=(
            "## red\nRed test file: tests/test_old.py\n\n"
            "## green\nThe old test was wrong.\n\n"
            "## red\nNo test was written this visit.\n"
        ),
    )

    completed = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert completed.returncode != 0
    assert _git(repo=repo, argv=["rev-parse", "HEAD"]) == before
    recorded = handoff.read_text(encoding="utf-8")
    assert "Cause: latest red section names no test file" in recorded


def test_commit_red_accepts_test_file_label_in_the_latest_red_section(tmp_path: Path) -> None:
    """The Red prompt's `Test file:` spelling names the test commit_red stages."""
    repo = _initialize_repository(tmp_path=tmp_path)
    test_file = repo / "tests" / "test_feature.py"
    test_file.parent.mkdir()
    _ = test_file.write_text("def test_feature() -> None:\n    assert False\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "tests/test_feature.py"])
    _checkpoint(repo=repo, name="red")
    _handoff(repo=repo, text="## red\nTest file: tests/test_feature.py\n")

    completed = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert completed.returncode == 0, completed.stderr
    assert _git(repo=repo, argv=["show", "--format=", "--name-only", "HEAD"]) == (
        "tests/test_feature.py"
    )


def test_declared_mechanical_refusals_use_their_budget_before_the_ordinary_reentry(
    tmp_path: Path,
) -> None:
    """The two target-only refusals preserve Red's ordinary re-entry for later."""
    repo = _initialize_repository(tmp_path=tmp_path)
    handoff = _handoff(repo=repo, text="## commit_red\n\nExit status: 1\n")
    output = repo / "hook-output"
    _ = output.write_text("Failed targets (1):\n  - check-lint\n", encoding="utf-8")

    for remaining in (1, 0):
        recorded = _run(
            repo=repo,
            argv=[
                "bash",
                str(_REENTRY_POLICY),
                "red",
                "check-lint,check-format",
                "2",
                str(output),
                str(handoff),
                "1",
            ],
            check=False,
        )
        assert recorded.returncode == 0, recorded.stderr
        admitted = _run(repo=repo, argv=["bash", str(_REENTRY_ADMISSION), "red"], check=False)
        assert admitted.returncode == 0, admitted.stderr
        assert f"Mechanical re-entries remaining: {remaining}" in handoff.read_text(
            encoding="utf-8"
        )

    # The next target-only refusal uses the still-unspent ordinary re-entry.
    recorded = _run(
        repo=repo,
        argv=[
            "bash",
            str(_REENTRY_POLICY),
            "red",
            "check-lint,check-format",
            "2",
            str(output),
            str(handoff),
            "1",
        ],
        check=False,
    )
    assert recorded.returncode == 0, recorded.stderr
    assert "Refusal classification: ordinary" in handoff.read_text(encoding="utf-8")
    assert (
        _run(repo=repo, argv=["bash", str(_REENTRY_ADMISSION), "red"], check=False).returncode == 0
    )

    exhausted = _run(
        repo=repo,
        argv=[
            "bash",
            str(_REENTRY_POLICY),
            "red",
            "check-lint,check-format",
            "2",
            str(output),
            str(handoff),
            "1",
        ],
        check=False,
    )
    assert exhausted.returncode == 0
    refused = _run(repo=repo, argv=["bash", str(_REENTRY_ADMISSION), "red"], check=False)
    assert refused.returncode != 0
    assert "mechanical re-entries exhausted (2 of 2)" in refused.stderr
    assert "ordinary re-entry exhausted (1 of 1)" in refused.stderr


def test_unlisted_or_unnamed_hook_targets_spend_only_the_ordinary_reentry(
    tmp_path: Path,
) -> None:
    """A target outside the declaration, including no target, cannot spend mechanical budget."""
    for name, output_text in (
        ("outside", "Failed targets (1):\n  - check-types\n"),
        ("unnamed", "hook failed before its target summary\n"),
    ):
        case = tmp_path / name
        case.mkdir()
        repo = _initialize_repository(tmp_path=case)
        handoff = _handoff(repo=repo, text="## commit_green\n\nExit status: 1\n")
        output = repo / "hook-output"
        _ = output.write_text(output_text, encoding="utf-8")

        recorded = _run(
            repo=repo,
            argv=[
                "bash",
                str(_REENTRY_POLICY),
                "green",
                "check-lint,check-format",
                "2",
                str(output),
                str(handoff),
                "1",
            ],
            check=False,
        )

        assert recorded.returncode == 0, recorded.stderr
        assert (
            _run(repo=repo, argv=["bash", str(_REENTRY_ADMISSION), "green"], check=False).returncode
            == 0
        )
        assert "Refusal classification: ordinary" in handoff.read_text(encoding="utf-8")
        assert not (repo / ".git" / "livespec-commit-green-mechanical-reentries").exists()


def test_malformed_mechanical_commit_refusal_policy_is_disabled() -> None:
    """Only a list of non-empty targets and a non-negative integer enables it."""
    malformed_targets = (
        '{"livespec-orchestrator-beads-fabro": '
        '{"dispatcher": {"implement": '
        '{"mechanical_targets": "check-lint", "mechanical_reentries": 2}}}}'
    )
    malformed_budget = (
        '{"livespec-orchestrator-beads-fabro": '
        '{"dispatcher": {"implement": '
        '{"mechanical_targets": ["check-lint"], "mechanical_reentries": -1}}}}'
    )

    assert _mechanical_commit_refusal_policy(config_text=malformed_targets) == ((), 0)
    assert _mechanical_commit_refusal_policy(config_text=malformed_budget) == ((), 0)


def test_commit_red_refuses_naming_every_changed_product_path_after_the_fold(
    tmp_path: Path,
) -> None:
    """A red turn's product writes, tracked or new, are refused and left uncommitted."""
    repo = _initialize_repository(tmp_path=tmp_path)
    _ = (repo / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = [\n    "src/pkg",  # comment\n]\n',
        encoding="utf-8",
    )
    (repo / "src" / "pkg").mkdir(parents=True)
    _ = (repo / "src" / "pkg" / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "--all"])
    _git(repo=repo, argv=["commit", "--quiet", "-m", "chore: product layout"])
    base = _git(repo=repo, argv=["rev-parse", "HEAD"])
    (repo / "tests").mkdir()
    _ = (repo / "tests" / "test_feature.py").write_text(
        "def test_feature() -> None:\n    assert False\n", encoding="utf-8"
    )
    _ = (repo / "src" / "pkg" / "existing.py").write_text("VALUE = 2\n", encoding="utf-8")
    _checkpoint(repo=repo, name="red")
    _ = (repo / "src" / "pkg" / "created.py").write_text("NEW = 1\n", encoding="utf-8")
    _ = (repo / "implementation.py").write_text("VALUE = 3\n", encoding="utf-8")
    handoff = _handoff(repo=repo, text="## red\nRed test file: tests/test_feature.py\n")

    completed = _run(repo=repo, argv=["bash", str(_RED)], check=False)

    assert completed.returncode == 3
    assert _git(repo=repo, argv=["rev-parse", "HEAD"]) == base
    recorded = handoff.read_text(encoding="utf-8")
    assert "## commit_red" in recorded
    assert "Exit status: 3" in recorded
    assert "src/pkg/existing.py" in recorded
    assert "src/pkg/created.py" in recorded
    assert "tests/test_feature.py" not in recorded.split("## commit_red")[1]
    assert "implementation.py" not in recorded.split("## commit_red")[1]
