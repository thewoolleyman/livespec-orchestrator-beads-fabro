"""Public CLI contract for the scheduled-workflow breakage pass."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher


def test_dispatcher_help_advertises_the_breakage_pass_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Scenario 313 requires a host-invokable Dispatcher breakage pass."""
    with pytest.raises(SystemExit) as exit_status:
        dispatcher.main(argv=["--help"])

    assert exit_status.value.code == 0
    assert "breakage-pass" in capsys.readouterr().out
