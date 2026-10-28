"""The one place a fixture ``just check`` run builds its process environment.

The repository's ``check`` recipe reads ``SKIP_TARGETS`` and merges it into the
skipped-target scope of the green token it records.  The delegated gate client
exports its authority-reading members into that variable, so a test process
running under the gate carries a skip list GitHub CI never has.  A fixture run
that copied ``os.environ`` wholesale would record the gate's own skips in its
token and go red only under the gate.  Building the environment here, with the
variable removed, keeps fixture runs identical on every venue.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

__all__: list[str] = [
    "fixture_check_environment",
]

_SKIP_TARGETS = "SKIP_TARGETS"


def fixture_check_environment(*, overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """The inherited environment minus ``SKIP_TARGETS``, with ``overrides`` applied last.

    Overrides are applied after the removal so a test that WANTS a skip list can
    still set one deliberately.
    """
    environment = {name: value for name, value in os.environ.items() if name != _SKIP_TARGETS}
    if overrides is not None:
        environment.update(overrides)
    return environment
