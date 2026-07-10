"""LIVE Beads/Fabro golden-master pytest binding.

This thin binding is driven by the operator-only
`just acceptance-live-golden-master` flow (see
`orchestrator-image/acceptance-live-golden-master.sh`). After the live run has
created a throwaway repo, let the production container/Fabro factory implement
the greeting from its SPECIFICATION, and merged the generated PR, the shell
clones the MERGED repo and points this binding at that checkout via env:

  LIVESPEC_LIVE_CHECKOUT  absolute path to the merged-repo working tree
  LIVESPEC_LIVE_NAME      the supplied greeting name (default: Ada)

It then exercises the SAME `run_live_acceptance` code path the unit tests cover
and asserts the produced program greets the name exactly. When
`LIVESPEC_LIVE_CHECKOUT` is unset (the default `just acceptance` / CI run) the
test SKIPS — the hermetic golden-master in
`acceptance/test_beads_fabro_golden_master.py` stays the merge gate; this live
binding only fires under the operator-driven shell.
"""

import os
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.acceptance import LiveAcceptanceConfig, run_live_acceptance

__all__: list[str] = ["test_beads_fabro_live_golden_master_greets_the_name"]

_CHECKOUT_ENV = "LIVESPEC_LIVE_CHECKOUT"
_NAME_ENV = "LIVESPEC_LIVE_NAME"


def test_beads_fabro_live_golden_master_greets_the_name() -> None:
    checkout_raw = os.environ.get(_CHECKOUT_ENV)
    if not checkout_raw:
        pytest.skip(f"{_CHECKOUT_ENV} unset; live golden-master runs only under the operator shell")
    name = os.environ.get(_NAME_ENV) or "Ada"
    checkout = Path(checkout_raw)
    assert checkout.is_dir(), f"{_CHECKOUT_ENV}={checkout} is not a directory"

    result = run_live_acceptance(config=LiveAcceptanceConfig(checkout=checkout, name=name))

    assert result.orchestrator_tier == "beads-fabro-live"
    assert result.greeting == f"Hello, {name}!"
    assert result.generated_program.is_file()
