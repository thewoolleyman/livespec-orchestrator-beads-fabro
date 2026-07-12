"""Regression coverage for Phase-1 fleet-check mechanical burndown."""

import json
from collections.abc import Callable
from pathlib import Path

from livespec_dev_tooling.checks import (
    all_declared,
    keyword_only_args,
    main_guard,
    no_inheritance,
    no_lloc_soft_warnings,
    no_write_direct,
    private_calls,
    wrapper_shape,
)

__all__: list[str] = []


def test_phase1_mechanical_checks_have_no_newly_covered_warnings(capsys) -> None:
    checks: tuple[Callable[[], int], ...] = (
        keyword_only_args.main,
        all_declared.main,
        private_calls.main,
        no_write_direct.main,
        no_inheritance.main,
        main_guard.main,
        no_lloc_soft_warnings.main,
    )

    for check in checks:
        assert check() == 0

    captured = capsys.readouterr()
    assert '"newly_covered": true' not in captured.out
    unexpected_newly_covered = [
        event
        for line in captured.err.splitlines()
        if line.startswith("{")
        for event in [json.loads(line)]
        if event.get("newly_covered") is True
        and event.get("file")
        != ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_run_commands.py"
    ]
    assert unexpected_newly_covered == []


def test_check_wrapper_shape_uses_strict_shared_gate(monkeypatch) -> None:
    """The check-wrapper-shape gate must invoke the strict SHARED
    livespec_dev_tooling wrapper_shape module — never a locally-forked,
    weakened copy — and every bin/*.py wrapper must conform to it (no
    __all__; canonical launcher shape).

    Guards the B1 gate-fork regression (see
    plan/fleet-check-coverage/research/wrapper-shape-conflict.md in the
    livespec hub): a factory slice resolved an all_declared x
    wrapper_shape conflict by FORKING the shared check into
    dev-tooling/checks/wrapper-shape-compat.sh, rewiring the justfile to
    it, and adding __all__ to the wrappers to clear all_declared. The
    upstream fix (dev-tooling v0.35.3) instead exempts bin wrappers from
    all_declared, so the wrappers keep the strict wrapper_shape (no
    __all__) and the shared gate stays canonical.
    """
    repo_root = Path(__file__).resolve().parent.parent

    # No local fork of the shared check may exist.
    assert not (repo_root / "dev-tooling" / "checks" / "wrapper-shape-compat.sh").exists()

    # The justfile recipe must invoke the shared pinned module, not a fork.
    justfile = (repo_root / "justfile").read_text()
    assert "python -m livespec_dev_tooling.checks.wrapper_shape" in justfile
    assert "wrapper-shape-compat.sh" not in justfile

    # Every bin/*.py wrapper conforms to the strict shared check (exit 0).
    monkeypatch.chdir(repo_root)
    assert wrapper_shape.main() == 0
