"""The primitive readers the CLOSED ACP candidate grammar is spelled with.

Every object in the availability-signature grammar of
`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" is CLOSED: an unknown key REFUSES the whole configuration rather
than being ignored, and an incomplete or wrong-typed field refuses naming
the key an operator has to edit. Three parsers -- candidate, signature and
pricing -- ask the same handful of questions about a raw value, so the
questions live here once instead of drifting apart in three places.

WHY THE VALUE READERS RETURN `None` RATHER THAN A REFUSAL STRING. A refusal
has to name the FULLY-QUALIFIED configuration path, and only the caller
knows it. A reader that returned the message would either have to be handed
that path -- making every call site pass it twice -- or emit one naming the
field alone, and a message an operator cannot map back to a line is exactly
what this grammar's refusals exist to avoid. The two KEY-SET checks are the
exception: their message is entirely about keys they can already see, so
they take the path and return the finished refusal.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, cast

__all__: list[str] = [
    "bounded_int",
    "finite_price",
    "missing_keys_refusal",
    "non_empty_text",
    "string_map",
    "string_tuple",
    "unknown_keys_refusal",
]


def unknown_keys_refusal(
    *, entry: Mapping[str, Any], allowed: frozenset[str], key: str
) -> str | None:
    """Refuse a table carrying a key the closed grammar does not define.

    Ignoring an unknown key is the failure mode this replaces: a
    misspelled `candidate_key` would leave the candidate silently
    unidentified, and the operator would only find out when a hold failed
    to skip the candidate they thought they had named.
    """
    unknown = sorted(set(entry) - allowed)
    if not unknown:
        return None
    return (
        f"{key} carries unknown key {unknown[0]!r}; "
        f"allowed keys are {', '.join(sorted(allowed))}"
    )


def missing_keys_refusal(
    *, entry: Mapping[str, Any], required: frozenset[str], key: str
) -> str | None:
    """Refuse an INCOMPLETE object, naming every field it still owes.

    The whole set is reported rather than the first miss, because these
    objects are all-or-none by contract -- a pricing table missing three
    of its four prices is one edit, not three round trips.
    """
    missing = sorted(required - set(entry))
    if not missing:
        return None
    return f"{key} is incomplete; it must also declare {', '.join(missing)}"


def non_empty_text(*, value: object) -> str | None:
    """The value as text when it is a non-blank string, else `None`.

    Blank-but-present is rejected alongside the wrong type because an
    empty `candidate_key` is not an identity: it would collide with every
    other empty one the moment identities are compared as pairs.
    """
    if not isinstance(value, str) or value.strip() == "":
        return None
    return value


def string_tuple(*, value: object) -> tuple[str, ...] | None:
    """The value as a tuple of strings, or `None` when it is not one."""
    if not isinstance(value, list):
        return None
    items = cast("list[object]", value)
    if not all(isinstance(item, str) for item in items):
        return None
    return tuple(cast("list[str]", items))


def string_map(*, value: object) -> Mapping[str, str] | None:
    """The value as a string-to-string table, or `None` when it is not one."""
    if not isinstance(value, dict):
        return None
    table = cast("dict[str, object]", value)
    if not all(isinstance(item, str) for item in table.values()):
        return None
    return {key: str(item) for key, item in table.items()}


def bounded_int(*, value: object, low: int, high: int) -> int | None:
    """The value as an integer inside `[low, high]`, else `None`.

    `bool` is excluded explicitly. Python makes it an `int` subclass, so a
    configuration writing `exit_code: true` would otherwise resolve to the
    exit code 1 -- a real, plausible value nobody wrote.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < low or value > high:
        return None
    return value


def finite_price(*, value: object) -> float | None:
    """The value as a finite, non-negative USD-per-million price, else `None`.

    Infinity and NaN are refused along with negatives: a price is summed
    into a run cost, and either of those turns every downstream total into
    the same unusable value while looking like a configured number.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        return None
    return number
