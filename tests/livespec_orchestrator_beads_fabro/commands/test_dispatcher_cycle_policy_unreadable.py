"""An unreadable config refuses rather than reading as "no ceiling adopted".

Beside `test_dispatcher_cycle_policy_refusal`, which covers an INVALID declared
value, this file covers the arm where the configuration file itself cannot be
read. The two must not collapse: an unparseable `.livespec.jsonc` says nothing
about which ceilings a repository adopted, so reporting it as no adoption would
let a dispatch proceed past a gate nobody could resolve.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    runtime_ceiling_policy_refusal,
)


def test_an_unparseable_config_refuses_naming_the_resolution_failure(tmp_path: Path) -> None:
    (tmp_path / ".livespec.jsonc").write_text("{ not valid jsonc", encoding="utf-8")

    refusal = runtime_ceiling_policy_refusal(repo=tmp_path)

    assert refusal is not None
    assert "cannot resolve the adopted per-cycle runtime ceilings" in refusal
