"""The ONE text comparison every ACP availability decision is spelled with.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" fixes it exactly: "Text matching is a conjunction after Unicode
case-folding and whitespace normalization, never a regular expression."

THIS LIVES ALONE BECAUSE TWO TABLES USE IT AND THEY MUST NOT DRIFT. The
non-eligible guard markers in `_acp_failure_signals` and the configured
`all_literals` of `_acp_candidate_signatures` are compared against the
same provider diagnostic, and the guard is required to outrank the
configured signature. If the guard normalized differently -- lowercased
rather than case-folded, say, or did not collapse whitespace -- a
diagnostic could satisfy a configured literal while its own guard marker
failed to match, which is precisely the false fallback the non-eligible
list exists to prevent.

CASE-FOLDING, NOT LOWERCASING. `str.casefold` is the Unicode operation
the contract names; `str.lower` differs on exactly the scripts a provider
diagnostic is most likely to be localized into, so using it would make
matching depend on the provider's locale.
"""

from __future__ import annotations

__all__: list[str] = [
    "conjunction_matches",
    "matches_any_conjunction",
    "normalized",
]


def normalized(*, text: str) -> str:
    """One diagnostic or literal reduced to its comparable form.

    Case-folded and whitespace-normalized, which is what makes a literal
    survive the line wrapping, indentation and tab/space drift a provider
    applies to the same sentence on different transports.
    """
    return " ".join(text.casefold().split())


def conjunction_matches(*, literals: tuple[str, ...], text: str) -> bool:
    """Whether EVERY literal appears in the normalized text.

    The empty conjunction cannot arise from parsed configuration -- the
    grammar requires a non-empty array -- and is reported as NO match
    rather than as the vacuous truth `all` would return, because a
    signature matching every diagnostic is the one outcome no caller
    wants.
    """
    if not literals:
        return False
    haystack = normalized(text=text)
    return all(normalized(text=literal) in haystack for literal in literals)


def matches_any_conjunction(*, conjunctions: tuple[tuple[str, ...], ...], text: str) -> bool:
    """Whether any ONE of several conjunctions matches in full."""
    return any(conjunction_matches(literals=literals, text=text) for literals in conjunctions)
