"""Regression coverage for Phase-1 fleet-check mechanical burndown."""

from collections.abc import Callable

from livespec_dev_tooling.checks import all_declared, keyword_only_args, private_calls

__all__: list[str] = []


def test_phase1_mechanical_checks_have_no_newly_covered_warnings(capsys) -> None:
    checks: tuple[Callable[[], int], ...] = (
        keyword_only_args.main,
        all_declared.main,
        private_calls.main,
    )

    for check in checks:
        assert check() == 0

    captured = capsys.readouterr()
    assert '"newly_covered": true' not in captured.out
    assert '"newly_covered": true' not in captured.err
