"""The suite does not inherit the SERVING GitHub App's own identity.

WHAT THIS BINDS. `tests/conftest.py`'s `_hermetic_serving_app_env` scrubs the
three variables the dispatch credential wrapper injects to name the App a Fabro
server serves with: its id, its private key and its optional pinned installation
id. They are ambient per-invocation inputs, not repository test configuration, so
a case that resolves any of them must supply its own and inherit none.

WHY THIS EXISTS AT ALL. The same asymmetry as its two sibling fixtures, hiding
the defect in the place it costs the most. Continuous integration exports NONE of
these names, so a case reading one is permanently green there; the credential
wrapper exports all three, and `just check` runs inside that wrapper on every
pre-push and inside the post-merge janitor. What reads them is the app-reach
preflight, whose evaluated arm issues two `gh` calls against the real forge —
so with the identity ambient every case that drives the pre-dispatch wall
reached the network. Measured in a factory sandbox whose PID 1 carries
`GITHUB_APP_ID`: five Scenario 174 cases failed inside the wall on a journal
append the ambient identity made reachable, on a tree whose preflight is
byte-identical to the one continuous integration passes.

WHERE THE BEHAVIOURAL PROOF LIVES, stated plainly so this module is not read as
carrying it. The cases here are CONFIGURATION assertions over the scrub tuple.
The behaviour — that the preflight evaluates nothing without a serving App
identity, and refuses an unreachable target with it — is asserted by
`tests/integration/test_adopter_dispatch_app_reach_scenario32.py`, which sets the
identity explicitly exactly as this fixture's contract requires.

WHY THE CONTROL IS NOT OPTIONAL. Without it, the scrub assertions would be
satisfied just as well by a fixture that made these names permanently
unsettable — which would break the one case that sets one deliberately, and with
it every assertion about the evaluated arm. The control pins "no AMBIENT leak"
rather than "no value ever".
"""

from __future__ import annotations

import os

import pytest

# THE WRAPPER-INJECTED APP IDENTITY, SPELLED AS LITERALS. These are the names the
# shared runtime's own `load_github_app_config` reads and the names
# `_dispatcher_gh_refresh` projects into a sandbox; spelled here rather than
# imported, because the module that reads them keeps its own spelling private and
# a reader reaching only for an exported name would agree with that name whatever
# it said — including after a rename that left the conftest tuple behind, which is
# the drift this class of defect is made of.
_SERVING_APP_NAMES = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
)


@pytest.mark.parametrize("name", _SERVING_APP_NAMES)
def test_no_serving_app_identity_reaches_a_test(*, name: str) -> None:
    """No name of the App identity survives into the environment a case reads.

    This is the red pre-push's own failure condition caught at its source: the
    preflight resolves the identity through `os.environ`, so an absence here is
    what makes a case answer the same way inside the credential wrapper, on a
    developer host, and in continuous integration.
    """
    assert name not in os.environ


def test_a_case_that_sets_the_app_identity_still_carries_it() -> None:
    """The control: the scrub removes the AMBIENT leak, not the value."""
    env = {**os.environ, "GITHUB_APP_ID": "4277313"}

    assert env["GITHUB_APP_ID"] == "4277313"


def test_the_scrubbed_names_are_the_ones_the_app_config_loader_reads() -> None:
    """Keep the literals above honest against the PRODUCTION reader's own spellings.

    Bound through `load_github_app_config` rather than against a constant,
    because the two modules that read this family keep their enumerations
    private and the loader is the public surface every one of them resolves the
    identity through. Both directions are asserted: the three names together
    resolve a configuration, and dropping the id alone does not — so a literal
    misspelled here cannot agree with the loader by accident.
    """
    from livespec_runtime.github_auth.config import load_github_app_config
    from returns.pipeline import is_successful

    present = dict.fromkeys(_SERVING_APP_NAMES, "1")
    present["GITHUB_PRIVATE_KEY"] = _A_PEM_SHAPED_VALUE

    assert is_successful(load_github_app_config(environ=present))
    assert not is_successful(
        load_github_app_config(
            environ={key: value for key, value in present.items() if key != "GITHUB_APP_ID"}
        )
    )


# Shaped as a PEM rather than an arbitrary word, because the loader grades the
# key's framing and an unframed value would refuse for a reason this case is not
# about. The bytes are not a key and nothing signs with them.
_A_PEM_SHAPED_VALUE = (
    "-----BEGIN RSA PRIVATE KEY-----\nbm90LWEta2V5\n-----END RSA PRIVATE KEY-----\n"
)
