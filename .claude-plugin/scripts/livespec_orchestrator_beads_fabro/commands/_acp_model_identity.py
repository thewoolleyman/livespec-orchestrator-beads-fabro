"""EXACT emitted model identity: one trailing date suffix stripped, nothing more.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt in a successful fallback run":
"Emitted model identity, normalized only by stripping one trailing `-YYYYMMDD`
date suffix (any broader prefix match is not exact identity), selects built-in
pricing only for the matching built-in candidate and endpoint."

WHY THIS IS ITS OWN MODULE RATHER THAN A HELPER INSIDE THE PRICE TABLE. Two
unrelated tables are keyed by model identity -- the built-in per-token price
table in `_dispatcher_cost_pricing` and the committed model catalog in
`_acp_model_catalog` -- and the contract applies the SAME normalization to both
("the exact-identity rule ... applies to the catalog key", section "Agent and
model catalogs"). A copy of the rule next to each table is two copies of one
fact, and the drift would be silent: one table would price a dated identity and
the other would miss it, which reads as a missing catalog entry rather than as
two normalizers disagreeing.

WHY A PREFIX MATCH IS THE WRONG SHAPE AND NOT MERELY A LOOSER ONE. The shipped
normalizer matched the longest price-table key that was a PREFIX of the emitted
id, which is correct for a dated id and wrong for every other suffix: it
resolved `gpt-5.5-mini` -- a different, CHEAPER, real model -- onto `gpt-5.5`'s
rate, so the derived cost was not an approximation of that model's price but a
confident over-charge attributed to a model the table never named. An
unrecognised identity has to reach the caller AS unrecognised, because that is
the only input from which the no-default rule above it can decide the run cost
is unobservable.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "exact_model_identity",
]

# A trailing release-date suffix, and ONLY that shape: a literal hyphen plus
# exactly eight digits at the very end of the identity. Seven digits, nine
# digits and a dashed calendar date are all deliberately NOT this pattern --
# each is a suffix a looser rule would eat, and none of them is the
# `-YYYYMMDD` form the contract names.
_DATE_SUFFIX = re.compile(r"-\d{8}\Z")


def exact_model_identity(*, raw_model: str) -> str | None:
    """The emitted identity with at most ONE trailing `-YYYYMMDD` stripped, or None.

    `None` means the value names no model at all: blank or whitespace-only
    text, or a value that is nothing BUT a date suffix. Both are returned as
    absences rather than as the empty string, because an empty-string key would
    look up cleanly in a table that happened to carry one and the caller's
    no-default rule turns on telling "no identity" from "an identity I cannot
    price".

    Surrounding whitespace is not part of an identity -- a padded attribute
    value names the same model as its bare form -- so it is stripped before the
    date suffix is considered.
    """
    candidate = raw_model.strip()
    if candidate == "":
        return None
    stripped = _DATE_SUFFIX.sub("", candidate, count=1)
    return stripped if stripped != "" else None
