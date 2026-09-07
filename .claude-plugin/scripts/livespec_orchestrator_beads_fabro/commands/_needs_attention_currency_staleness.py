"""Ambient dispatcher plugin-currency staleness, SURFACED and never enforced.

This lane is the surfacing half of the v089 self-update re-base ratified in
`SPECIFICATION/contracts.md`.
Ambient release-staleness lost its blocking authority at dispatch admission —
plugin builds bind at SESSION START while the release ref MOVES, so a blocking
comparison refused every live session's dispatches the moment a release was
published mid-session. Freshness pressure has to be carried by SOMETHING, and
this fact is that something: it states how far the operator-provisioned build
lags the latest release and names the restart-and-update remedy.

⛔ THIS FACT MUST NEVER GATE A DISPATCH, AND THAT IS A CONTRACT RATHER THAN A
DEFAULT. It is a surfaced TRIGGER in exactly the sense the detection-coverage
staleness facts are: it composes into the needs-attention snapshot, an operator
reads it, and an operator acts. The only blocking currency form that remains is
a deliberate committed `dispatcher.minimum_release` floor, which lives in
`_dispatcher_minimum_release_floor.py` and never in this lane. Nothing here
returns an exit code, appends to the dispatch journal, or is consulted by the
admission path — the composition is a pure read.

IT COMPOSES WITH THE PASSING-CANARY "RESTART IS DUE" SURFACING, IT DOES NOT
REPLACE IT. The two answer different questions: the canary says a NEWLY
PROVISIONED payload has been validated and will take effect on the next start,
while this fact says the CURRENTLY PROVISIONED payload has fallen behind the
release channel and has not been updated at all. A host can be in either state,
both, or neither.

THE LAG IS A DISTANCE BETWEEN TWO VERSION IDENTIFIERS, NOT A COUNT OF RELEASES
PUBLISHED BETWEEN THEM, and the summary says so in its own words. Only the two
endpoints are observable from here — no release history is read — so a reader
who took "2 minor version steps" for "2 releases were published" would be
reading a number this lane cannot know. Stating the caveat on the fact is
cheaper than a reader deriving a release count that was never measured.

BOTH ENDPOINTS ARE READ FROM PARSED `plugin.json` MANIFESTS, never from a cache
directory name: cache directories are keyed by commit AND by version, both
shapes coexist, and a name-based identity silently misreads one of them. The
release tip comes from the marketplace clone checked out at the `release` ref
for the same reason `_needs_attention_release_adoption` reads it there — the
newest build materialised in the shared cache is a different question, and the
two have been measured a full release apart with both readings correct.

AN UNREADABLE ENDPOINT EMITS NOTHING HERE, AND THAT IS DELIBERATE RATHER THAN AN
OVERSIGHT. This lane can only report a lag it measured, and the two surfaces
that own "the instrument could not be read" already exist and are fail-closed:
the dispatch-admission gate records `dispatcher-currency-undetermined` under its
own journal stage, and the sibling `_needs_attention_release_adoption` lane
raises a high-urgency item when the release tip is unreadable while adopters
exist. A third item for the same host condition would double-report it, not
harden it.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import plugin_root
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_release_adoption import (
    read_build_version,
    release_tip_version,
)

__all__: list[str] = [
    "CurrencyStalenessSeams",
    "currency_staleness_items",
    "default_currency_staleness_seams",
    "version_lag",
]

# The plugin whose currency this lane reports — an identity, not an observation,
# for the same reason the adoption lane hardcodes it: the governed project's own
# manifest names the PROJECT, so deriving the key from it asks the marketplace
# registry for a key that does not exist and the lane goes silent everywhere.
_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_FACT_TYPE = "dispatcher-currency-staleness"
_UPDATE_REMEDY = (
    "claude plugin update livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
)
_COMPONENT_NAMES = ("major", "minor", "patch")


@dataclass(frozen=True, slots=True, kw_only=True)
class CurrencyStalenessSeams:
    """The two manifests this lane reads, injectable for hermetic coverage.

    Defaulted to production by `default_currency_staleness_seams` (the real
    plugin root and the real marketplace registry under HOME) and overridden in
    tests with tmp files, so every tier is covered without HOME monkeypatching.
    """

    plugin_root: Path
    marketplace_record: Path


def default_currency_staleness_seams() -> CurrencyStalenessSeams:  # pragma: no cover
    """The production manifests (integration-covered, not unit-covered)."""
    return CurrencyStalenessSeams(
        plugin_root=plugin_root(),
        marketplace_record=Path.home() / ".claude" / "plugins" / "known_marketplaces.json",
    )


def version_lag(*, provisioned: str, tip: str) -> tuple[int, ...] | None:
    """The componentwise distance from `provisioned` up to `tip`, or `None`.

    `None` is the answer "no fact to report" and covers two different
    situations on purpose, because neither is a lag: the provisioned build is
    current or ahead, or one of the identifiers carries a non-numeric component
    and the pair therefore has no orderable distance at all. A guessed ordering
    would be worse than silence — the admission gate's undetermined stage is
    where an unorderable release is recorded.
    """
    left = _components(version=provisioned)
    right = _components(version=tip)
    if left is None or right is None:
        return None
    width = max(len(left), len(right))
    padded_left = left + (0,) * (width - len(left))
    padded_right = right + (0,) * (width - len(right))
    if padded_right <= padded_left:
        return None
    return tuple(
        right_part - left_part
        for left_part, right_part in zip(padded_left, padded_right, strict=True)
    )


def currency_staleness_items(
    *,
    project_root: Path,
    repo: str,
    seams: CurrencyStalenessSeams,
) -> list[AttentionItem]:
    """Compose the non-blocking staleness fact, or nothing when there is no lag.

    `project_root` names the repository this snapshot is FOR: it addresses the
    handoff command. It is never the source of the plugin identity, which is
    fixed above.
    """
    provisioned = read_build_version(install_path=seams.plugin_root)
    tip = release_tip_version(marketplace_record=seams.marketplace_record, plugin_name=_PLUGIN_NAME)
    if provisioned is None or tip is None:
        return []
    lag = version_lag(provisioned=provisioned, tip=tip)
    if lag is None:
        return []
    return [
        ConformanceContext(project_root=project_root, repo=repo).candidate(
            id=f"hygiene:{_FACT_TYPE}:{repo}",
            kind="hygiene",
            urgency="medium",
            summary=(
                f"Dispatcher plugin currency is stale for {repo}: the operator-provisioned "
                f"build {provisioned} lags the latest release {tip} by {_lag_phrase(lag=lag)}. "
                "That is the distance between the two version identifiers, not a count of "
                "releases published between them. This fact does NOT gate or refuse a "
                "dispatch — ambient staleness is surfaced, never enforced, and only a "
                "committed dispatcher.minimum_release floor can refuse on currency. It "
                "composes with the passing-canary restart-is-due surfacing rather than "
                f"replacing it. Run `{_UPDATE_REMEDY}` and restart to adopt the release."
            ),
            source_ref=SourceRef(repo=repo, path=str(seams.plugin_root)),
            handoff=Handoff(
                kind="shell",
                command=_handoff_command(
                    project_root=project_root, provisioned=provisioned, tip=tip
                ),
            ),
        )
    ]


def _components(*, version: str) -> tuple[int, ...] | None:
    """The numeric components of a released-version identifier, or `None`.

    A pre-release suffix is dropped before the split, so `1.2.3-rc.1` orders on
    its release components; anything else non-numeric yields `None` rather than
    a sentinel, because a sentinel is what turns an unreadable identifier into
    a confident wrong ordering.
    """
    release, _, _suffix = version.strip().removeprefix("v").partition("-")
    chunks = release.split(".")
    if not all(chunk.isdecimal() for chunk in chunks):
        return None
    return tuple(int(chunk) for chunk in chunks)


def _lag_phrase(*, lag: tuple[int, ...]) -> str:
    """Render the lag at its LEADING differing component.

    Only the first component that differs is reported. Later components can run
    negative across a rollover — `0.97.5` to `0.98.1` differs by one minor step
    and minus four patch steps — and "minus four patch steps behind" is not a
    quantity any reader can act on.

    The differing components are collected in full rather than short-circuited
    on the first hit: `version_lag` only ever returns a tuple with at least one
    non-zero component, so the short-circuit's exhaustion arc is unreachable and
    would sit permanently uncovered against this repository's branch bar.
    """
    differing = [(position, step) for position, step in enumerate(lag) if step != 0]
    index, steps = differing[0]
    plural = "" if steps == 1 else "s"
    return f"{steps} {_component_name(index=index)} version step{plural}"


def _component_name(*, index: int) -> str:
    if index < len(_COMPONENT_NAMES):
        return _COMPONENT_NAMES[index]
    return f"component-{index + 1}"


def _handoff_command(*, project_root: Path, provisioned: str, tip: str) -> str:
    prompt = (
        f"adopt-dispatcher-release in repository {project_root}. The operator-provisioned "
        f"dispatcher build is {provisioned} and the latest release is {tip}. Run "
        f"`{_UPDATE_REMEDY}` and restart so the newer payload takes effect. Do not convert "
        "this staleness into a dispatch refusal: it is surfaced, never enforced."
    )
    return f"cd {shlex.quote(str(project_root))} && codex exec {shlex.quote(prompt)} < /dev/null"
