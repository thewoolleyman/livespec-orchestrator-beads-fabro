"""Resolution for the two committed-only per-cycle runtime ceilings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

__all__: list[str] = [
    "ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY",
    "ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY",
    "COMMITTED_ONLY_RUNTIME_CEILING_KEYS",
    "AdoptedCycleCeilings",
    "resolve_adopted_cycle_ceilings",
    "runtime_ceiling_policy_refusal",
]

ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY = "adopted_cycle_product_lloc_ceiling"
ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY = "adopted_cycle_duration_seconds_ceiling"
COMMITTED_ONLY_RUNTIME_CEILING_KEYS: tuple[str, ...] = (
    ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY,
    ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY,
)


@dataclass(frozen=True, kw_only=True)
class AdoptedCycleCeilings:
    """The valid runtime ceilings declared by a repository, if any."""

    product_lloc: int | None
    duration_seconds: int | None


def resolve_adopted_cycle_ceilings(*, cwd: Path) -> AdoptedCycleCeilings | str:
    """Resolve committed runtime ceilings, or return their policy refusal.

    An absent setting has not been adopted. A present setting must be a positive
    integer, and booleans are intentionally excluded despite Python making them
    a subclass of ``int``.
    """
    block = dispatcher_block(cwd=cwd)
    resolved: dict[str, int | None] = {}
    for key in COMMITTED_ONLY_RUNTIME_CEILING_KEYS:
        if key not in block:
            resolved[key] = None
            continue
        value = _positive_integer(value=block[key])
        if value is None:
            return (
                f"dispatcher.{key} must be a positive integer "
                f"(a boolean is not an integer for this setting); got {block[key]!r}"
            )
        resolved[key] = value
    return AdoptedCycleCeilings(
        product_lloc=resolved[ADOPTED_CYCLE_PRODUCT_LLOC_CEILING_KEY],
        duration_seconds=resolved[ADOPTED_CYCLE_DURATION_SECONDS_CEILING_KEY],
    )


def runtime_ceiling_policy_refusal(*, repo: Path) -> str | None:
    """Render an unreadable or invalid ceiling declaration as a pre-claim refusal."""
    resolved = attempt(
        action=lambda: resolve_adopted_cycle_ceilings(cwd=repo),
        exceptions=(LivespecConfigUnreadableError, ConnectionPrefixMissingError),
    )
    if isinstance(resolved, AttemptFailure):
        return f"ERROR: cannot resolve committed runtime ceilings: {resolved.error}\n"
    if isinstance(resolved, str):
        return f"ERROR: invalid committed runtime-ceiling policy: {resolved}\n"
    return None


def _positive_integer(*, value: object) -> int | None:
    """Return a positive non-boolean integer, or ``None`` for every other value."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None
