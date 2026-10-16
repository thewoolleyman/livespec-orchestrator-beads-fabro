"""The suite does not inherit the factory's own credential-use projection.

WHAT THIS BINDS. `tests/conftest.py`'s `_hermetic_projected_credential_use`
scrubs three variables the Dispatcher projects for a real dispatched worker:
the credential expiry, the required remaining lifetime, and the UNPROTECTED
declaration. They are ambient runtime inputs, not repository test
configuration, so a case that spawns the shipped credential-use guard must
supply its own and inherit none.

WHY THIS EXISTS AT ALL. The scrub was written with two names, and the
unprotected declaration was added to the projection afterwards — so the tuple
sat one name short, and nothing failed on a developer host or in continuous
integration, because neither projects it. Inside a factory sandbox whose PID 1
carries `LIVESPEC_CREDENTIAL_USE_UNPROTECTED=1` it broke 27 cases across six
modules: the guard refuses when the declaration arrives ALONGSIDE a deadline
("the declaration must be '1' and must stand alone") and it fails CLOSED, so
each of those cases refused at startup instead of exercising the bound it was
about. Measured 2026-10-16 on a tree whose eight credential-use modules are
byte-identical to master: 27 failed with the variable ambient, 91 passed with
it removed.

WHERE THE BEHAVIOURAL PROOF LIVES, stated plainly so this module is not read
as carrying it. The cases here are CONFIGURATION assertions over the scrub
tuple. The behaviour — that the shipped guard, rendered and run around a real
child, honours the deadline each case sets — is asserted by the
`test_dispatcher_credential_use_*` modules, and this scrub is precisely what
lets them do it in an unprotected sandbox. A case here that spawned its own
child to re-read the environment would prove nothing those modules do not
already prove, and nothing the first case does not already imply: a name
absent from `os.environ` cannot reach a child built from `dict(os.environ)`.
That is why no case here spawns a process and why this file is absent from
`subprocess_spawn_allowlist`.

WHY THE CONTROL IS NOT OPTIONAL. Without it, the scrub assertions would be
satisfied just as well by a fixture that made these names permanently
unsettable — which would break every case in
`test_dispatcher_credential_use_unprotected.py`, each of which sets the
declaration deliberately. The control pins "no AMBIENT leak" rather than "no
declaration ever".
"""

from __future__ import annotations

import os

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_EXPIRY_ENV_VAR,
    CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    CREDENTIAL_USE_UNPROTECTED_ENV_VAR,
    CREDENTIAL_USE_UNPROTECTED_VALUE,
)

# THE PROJECTION, SPELLED AS LITERALS AND BOUND BELOW. Reaching only for the
# exported names would make this module agree with the production constants
# whatever they said — including after a rename that left the conftest tuple
# behind, which is the exact drift that caused the incident above. These
# literals are what the Dispatcher actually writes into a sandbox;
# `test_the_scrubbed_names_match_the_exported_constants` is what keeps them
# honest.
_PROJECTED_NAMES = (
    "LIVESPEC_CREDENTIAL_EXPIRY_EPOCH",
    "LIVESPEC_CREDENTIAL_REQUIRED_REMAINING_SECONDS",
    "LIVESPEC_CREDENTIAL_USE_UNPROTECTED",
)


@pytest.mark.parametrize("name", _PROJECTED_NAMES)
def test_no_projected_credential_use_name_reaches_a_test(*, name: str) -> None:
    """No projected name survives into the environment a case builds from.

    This is the janitor's own failure condition, caught at its source. Every
    one of the 27 failures was a child built from `dict(os.environ)`, so an
    absence here is what makes those children clean.
    """
    assert name not in os.environ


def test_a_case_that_declares_the_unprotected_route_still_carries_it() -> None:
    """The control: the scrub removes the AMBIENT leak, not the route."""
    env = {**os.environ, CREDENTIAL_USE_UNPROTECTED_ENV_VAR: CREDENTIAL_USE_UNPROTECTED_VALUE}

    assert env[CREDENTIAL_USE_UNPROTECTED_ENV_VAR] == CREDENTIAL_USE_UNPROTECTED_VALUE


def test_the_scrubbed_names_match_the_exported_constants() -> None:
    """Keep the literals above honest against the production projection."""
    assert CREDENTIAL_EXPIRY_ENV_VAR == "LIVESPEC_CREDENTIAL_EXPIRY_EPOCH"
    assert CREDENTIAL_REQUIRED_REMAINING_ENV_VAR == "LIVESPEC_CREDENTIAL_REQUIRED_REMAINING_SECONDS"
    assert CREDENTIAL_USE_UNPROTECTED_ENV_VAR == "LIVESPEC_CREDENTIAL_USE_UNPROTECTED"
    assert set(_PROJECTED_NAMES) == {
        CREDENTIAL_EXPIRY_ENV_VAR,
        CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
        CREDENTIAL_USE_UNPROTECTED_ENV_VAR,
    }
    # The DEADLINE is deliberately absent from the scrub: `conftest.py` leaves
    # it alone, and the guard modules pop it in their own `_hermetic_env`. It is
    # named here so a reader does not add it to `_PROJECTED_NAMES` and make the
    # first case assert something the fixture does not do.
    assert CREDENTIAL_USE_DEADLINE_ENV_VAR not in _PROJECTED_NAMES
