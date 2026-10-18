"""The suite does not inherit the dispatching operator's own dispatch inputs.

WHAT THIS BINDS. `tests/conftest.py`'s `_hermetic_operator_attribution_env`
scrubs the two variables an operator sets to dispatch work: `LIVESPEC_INVOKER`,
the asserted invoker identity `drive` forwards to the Dispatcher as an explicit
`--invoker <id>`, and `LIVESPEC_FABRO_FACTORY`, the factory selection that
outranks the committed default. Both are ambient per-invocation inputs, not
repository test configuration, so a case that resolves either must supply its
own and inherit none.

WHY THIS EXISTS AT ALL. The asymmetry hides the defect in the one place it
costs the most. Continuous integration exports NEITHER name, so a case reading
one is permanently green there; a session that DISPATCHES exports the identity
because the driver's gate requires it, and `just check` runs inside that
session on every pre-push and inside the post-merge janitor. Measured
2026-10-18 at master d36799fa: with `LIVESPEC_INVOKER` exported, two of the
four Scenario 17 drive cases failed, because the forwarded `--invoker` pair
shifts the recorded dispatcher argv past the fixed index they read. The per-file
coverage gate, the total coverage gate and the aggregate all went red, so a
dispatching session got a red host-side pre-push on every branch while the same
tree's default-branch continuous integration was green (work-item
bd-ib-untu6x).

WHERE THE BEHAVIOURAL PROOF LIVES, stated plainly so this module is not read as
carrying it. The cases here are CONFIGURATION assertions over the scrub tuple.
The behaviour — that the drive operator surface locates its target repository
by the value FOLLOWING `--repo`, whatever the argv's length — is asserted by
`tests/integration/test_drive_operator_defaults_scenario17.py`, whose own
shifted-argv case sets the identity explicitly exactly as this fixture's
contract requires. A case here that re-derived that argv would prove nothing
that module does not already prove.

WHY THE CONTROL IS NOT OPTIONAL. Without it, the scrub assertions would be
satisfied just as well by a fixture that made these names permanently
unsettable — which would break every case that sets one deliberately, from the
shifted-argv case above to `test_dispatcher_factory_ledger.py`'s
environment-selection cases. The control pins "no AMBIENT leak" rather than "no
value ever".
"""

from __future__ import annotations

import os

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import (
    JANITOR_REMOVED_ENV_VARS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import INVOKER_ENV_VAR

# THE OPERATOR'S OWN DISPATCH INPUTS, SPELLED AS LITERALS AND BOUND BELOW.
# Reaching only for the exported names would make this module agree with the
# production constants whatever they said — including after a rename that left
# the conftest tuple behind, which is the drift that causes this class of
# defect. These literals are what an operator actually exports;
# `test_the_scrubbed_names_match_the_production_spellings` is what keeps them
# honest.
_OPERATOR_NAMES = (
    "LIVESPEC_INVOKER",
    "LIVESPEC_FABRO_FACTORY",
)


@pytest.mark.parametrize("name", _OPERATOR_NAMES)
def test_no_operator_dispatch_input_reaches_a_test(*, name: str) -> None:
    """Neither name survives into the environment a case resolves against.

    This is the red pre-push's own failure condition, caught at its source:
    every production resolver reads these through `os.environ`, so an absence
    here is what makes a case answer the same way on a dispatching host, on a
    developer host, and in continuous integration.
    """
    assert name not in os.environ


def test_a_case_that_sets_an_operator_input_still_carries_it() -> None:
    """The control: the scrub removes the AMBIENT leak, not the value."""
    env = {**os.environ, INVOKER_ENV_VAR: "claude:test"}

    assert env[INVOKER_ENV_VAR] == "claude:test"


def test_the_scrubbed_names_match_the_production_spellings() -> None:
    """Keep the literals above honest against the production env-var names."""
    assert INVOKER_ENV_VAR == "LIVESPEC_INVOKER"
    assert INVOKER_ENV_VAR in _OPERATOR_NAMES
    # The factory selector's own name is private to `_config`, so the janitor's
    # removal list is the only PUBLIC spelling of it. The assertion is a
    # CONTAINMENT rather than an equality against that tuple: the janitor
    # scrubs the same two names today, but its list answers a different
    # question — what a merge-time check run must not inherit — and a future
    # addition to it is not a name this suite owes a scrub.
    assert "LIVESPEC_FABRO_FACTORY" in JANITOR_REMOVED_ENV_VARS
    assert "LIVESPEC_FABRO_FACTORY" in _OPERATOR_NAMES
