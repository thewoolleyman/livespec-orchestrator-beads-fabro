"""Which agents REFUSE an unpinned candidate, and the one escape hatch.

`SPECIFICATION/contracts.md` section "Built-in ACP node defaults": "A candidate
whose `agent` is `codex-acp`, primary or fallback, MUST carry both `model` and
`effort`, and the Dispatcher MUST refuse before claim one that does not."

WHY THIS IS NOT A GENERAL RULE, which is the whole reason it needs a module of
its own rather than a line in the renderer. An entry declaring NO `effort` is
ordinarily admissible: it is the candidate taking the adapter's own default, and
every agent has one. Making `effort` mandatory everywhere would refuse the
un-pinned Claude disposition default this repository ships. So the requirement
is a property of PARTICULAR AGENTS, and the set is named here where the reason
can be recorded beside it.

WHY `codex-acp` IS IN THE SET, with the mechanism rather than a preference. The
sandbox image bakes a `codex-acp` build whose models-manager cannot decode the
present-day model catalog -- the reasoning tier the gpt-5.6 line introduced is an
unknown variant to it -- so it silently falls back to its baked static list. An
adapter carrying no pin therefore runs whatever that decode failure leaves
behind: nobody chose it, and it moves whenever either the catalog or the baked
adapter changes. A pin is what makes the model a decision.

WHY THE SET IS KEYED ON THE AGENT ID RATHER THAN ON A CATALOG FLAG. A flag would
be the more general design, and it is deliberately not taken: the catalog's key
set is CLOSED and ratified, so adding a field to it is a specification change
rather than an implementation choice. The contract names `codex-acp` literally,
so this build does too, and the day the obligation becomes a catalog field is
the day the catalog grammar ratifies one.

THE OPT-OUT IS NOT AN EXCEPTION HERE BECAUSE IT CANNOT REACH HERE. The explicit
un-pinned escape hatch is a MANUAL-form candidate -- a `command` plus an `env`
naming the baked path -- and the manual form never resolves an `agent`, so it
never consults this module. That is the contract's "there is no structured
spelling of the opt-out" made structural: an operator who disables the pin does
so in a form that visibly spells out the whole adapter.
"""

from __future__ import annotations

__all__: list[str] = [
    "PIN_REQUIRED_AGENTS",
    "codex_pin_refusal",
]

# The agents whose candidates MUST carry both `model` and `effort`.
PIN_REQUIRED_AGENTS: frozenset[str] = frozenset({"codex-acp"})


def codex_pin_refusal(*, agent: str, effort: str, key: str) -> str | None:
    """The unpinned-candidate refusal for one entry's declared values, or `None`.

    Takes the two VALUES rather than the parsed entry so this module imports
    nothing: `_acp_structured_render` owns that type and is this module's own
    caller, so depending on it here would close an import cycle.

    Only `effort` is checked. A missing `model` is already refused by the
    structured form's own grammar, which requires it of EVERY agent, and
    duplicating that check here would give one fault two messages -- the
    operator would fix the one they were shown and then meet the other.
    """
    if agent not in PIN_REQUIRED_AGENTS or effort != "":
        return None
    return (
        f"{key}.effort is required because agent {agent!r} must carry both model and "
        f"effort: its baked build cannot decode the current model catalog, so an unpinned "
        f"adapter runs whatever its stale static list resolves. Add an effort, or use the "
        f"manual form naming the baked path to opt out of the pin explicitly"
    )
