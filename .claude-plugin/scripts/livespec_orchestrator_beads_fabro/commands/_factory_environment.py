"""The sandbox environment ONE factory declares, as READ rather than graded.

Split out of `_config` for the same reason `_node_timeouts` and
`_workflow_variants` are: what a `dispatcher.factories` entry's `environment`
key MEANS belongs beside its own reader rather than inside the general
connection-resolution module. `_config._factory_target_for` is the
config-reading seam that feeds it, and `_dispatcher_factory_environment` is
where the reading is GRADED — the pre-claim refusal and the id the `fabro run`
argv carries.

WHY THE KEY EXISTS. On the Petri-era engine the server selects a run's sandbox
environment from the run intent's `environment_id` ALONE, and that selection
OVERRIDES the `[run.environment]` id the workflow declares (the workflow's env
and resources overlays still apply to whichever environment was selected). A
`fabro run` carrying no `--environment` sends `default`, so a dispatch to a
candidate server landed in that server's default environment —
`buildpack-deps:noble`, with no `mise` on PATH — and died in a prepare step
with `sh: 1: mise: not found`. Nothing in that failure names the placement, so
it reads as a work-item failure. Environments are server-managed catalog
entries, so the id is a property OF THE FACTORY and belongs on its entry.

WHY TWO FIELDS WHERE A `str | None` WOULD READ MORE SIMPLY. `absent` and
`declared but not a non-empty string` are different answers with different
remedies, and the `_optional_str` projection `_config` applies to every other
optional entry key maps both onto None. Collapsed that way, a typo'd, empty or
null `environment` is indistinguishable from a factory that declares none — so
the dispatch would emit no flag and land in the server's default environment,
which is precisely the failure the key exists to remove, restored silently by
the shape of its own reading. Keeping `declared` apart is what leaves the
grade something to refuse.

WHY THE KEY IS OPT-IN RATHER THAN DEFAULTED. The pinned 0.254 engine has no
`--environment` flag at all and keeps selecting from `workflow.toml`, so a
default id would make every dispatch to that engine fail at argument parsing.
An ABSENT key is therefore a complete answer — this factory selects whatever
its own server selects today — and it is the answer every entry that predates
the key gives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__: list[str] = [
    "FACTORY_ENVIRONMENT_KEY",
    "NO_FACTORY_ENVIRONMENT",
    "FactoryEnvironment",
    "factory_environment_from_entry",
]

# PUBLIC because the key's own NAME is part of what a refusal says, and the
# refusal is rendered two modules away: a surface spelling it for itself would
# send an operator to a key that is one rename away from not existing.
FACTORY_ENVIRONMENT_KEY = "environment"


@dataclass(frozen=True, kw_only=True)
class FactoryEnvironment:
    """A factory entry's `environment` key as read, never graded.

    `declared` answers whether the entry carries the key at all;
    `environment_id` carries the catalog id when, and only when, the declared
    value is a non-empty string. The two are independent on purpose: the
    `declared` / no-id pairing IS the unusable declaration, and it is the one
    shape the grade refuses.
    """

    declared: bool = False
    environment_id: str | None = None


# The reading every entry that carries no `environment` key yields. A named
# constant rather than a bare `FactoryEnvironment()` at each site so the
# absent answer has one identity a caller can compare against.
NO_FACTORY_ENVIRONMENT = FactoryEnvironment()


def factory_environment_from_entry(*, entry: dict[str, Any]) -> FactoryEnvironment:
    """Read one `dispatcher.factories` entry's optional `environment` key.

    Membership decides `declared`, never the value's own shape: an explicit
    `null` or `""` is something an operator WROTE, and reporting it as an
    absent key would hand it the conforming path.
    """
    if FACTORY_ENVIRONMENT_KEY not in entry:
        return NO_FACTORY_ENVIRONMENT
    value = entry[FACTORY_ENVIRONMENT_KEY]
    usable = isinstance(value, str) and value != ""
    return FactoryEnvironment(declared=True, environment_id=value if usable else None)
