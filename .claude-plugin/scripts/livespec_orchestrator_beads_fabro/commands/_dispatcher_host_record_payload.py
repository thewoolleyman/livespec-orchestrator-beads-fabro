"""The caller's evidence payload, read and paired with the item's DECLARED proof modes.

Split out of `_dispatcher_host_record_post` along the cohesion seam between WHAT a host
record asserts and HOW it gets published. That module resolves the target, clears the
refusal ladder and posts; this one answers one question — what did the publishing session
actually exercise, and is it something this item declared?

WHY THE MODE IS LOOKED UP RATHER THAN READ FROM THE PAYLOAD, which is the whole reason
this reading is not a plain JSON parse. The record publishes each assertion's proof MODE,
and the acceptance pass grades the assertion on the leg that mode names. A payload that
could declare its own mode could therefore publish a `factory_captured` assertion as a
host-captured one — and the pass would then grade it against a host replay, on an
assertion whose proof never needed a host at all. So the mode comes from the item's own
Definition of Done, and an assertion the item does not declare is REFUSED rather than
published under a guess.

WHY A CAPTURE'S REPRODUCTION VERDICT IS DROPPED HERE. A `host_recorded` record is the
FIRST leg: there is nothing yet for it to have reproduced, and the acceptance pass admits
passing evidence only from a `host_verified` record. A capture publishing `Reproduced:
yes.` would assert a verdict about itself that no reader may act on — and a publisher who
copied one payload from the other would produce exactly that, without noticing. Dropping
it is a computation, not a courtesy.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    NO_GOVERNING_SCENARIO,
    RecordAssertion,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "Evidence",
    "read_evidence",
]

_BAD_PAYLOAD_REFUSAL = (
    "ERROR: post-host-record refused: {path} is not a JSON object carrying a"
    ' "build" object and an "assertions" array.\n'
)
_UNDECLARED_ASSERTION_REFUSAL = (
    "ERROR: post-host-record refused: {text} is not a host_captured assertion of"
    " work-item {item_id}, so no proof mode can be computed for it. The payload's"
    " assertions must be the item's own.\n"
)
_NO_ASSERTION_REFUSAL = "ERROR: post-host-record refused: the payload names no assertion.\n"


@dataclass(frozen=True, kw_only=True)
class Evidence:
    """The caller's half of a record: the build, and per assertion what it ran."""

    build: BuildIdentity
    assertions: tuple[RecordAssertion, ...]


def read_evidence(
    *,
    record_path: Path,
    work_item_id: str,
    declared: Mapping[str, str],
    verdict_is_replay: bool,
    emit: Callable[[str], None],
) -> Evidence | None:
    """Read the caller's payload and pair each assertion with its DECLARED mode.

    `verdict_is_replay` rather than the verdict itself, because the only thing the read
    needs to know about it is whether a reproduction verdict may be claimed at all — and
    passing the word would invite a second reading of which verdicts are replays.
    """
    payload = _payload(path=record_path)
    if payload is None:
        emit(_BAD_PAYLOAD_REFUSAL.format(path=record_path))
        return None
    build, raw = payload
    assertions: list[RecordAssertion] = []
    for one in raw:
        text = one.get("text")
        if not isinstance(text, str) or text not in declared:
            emit(_UNDECLARED_ASSERTION_REFUSAL.format(text=repr(text), item_id=work_item_id))
            return None
        assertions.append(
            _assertion(
                raw=one,
                text=text,
                mode=declared[text],
                replay=verdict_is_replay,
            )
        )
    if not assertions:
        emit(_NO_ASSERTION_REFUSAL)
        return None
    return Evidence(build=build, assertions=tuple(assertions))


def _assertion(*, raw: Mapping[str, object], text: str, mode: str, replay: bool) -> RecordAssertion:
    """One rendered assertion, with the mode supplied by the ITEM and not the payload.

    `governing_scenario` falls back to the clause's own "no scenario governs it"
    statement rather than to nothing, because for an ITEM record the clause requires
    one or the other and an absent field is a publisher who did not say.

    THE REPRODUCTION VERDICT IS DROPPED FOR A CAPTURE, whatever the payload claims, and
    that is a computation rather than a courtesy. A `host_recorded` record is the FIRST
    leg: there is nothing yet for it to have reproduced, and the acceptance pass admits
    passing evidence only from a `host_verified` record. A capture that published
    `Reproduced: yes.` would therefore assert a verdict about itself that no reader may
    act on — and a publisher who copied one payload from the other would produce it
    without noticing.
    """
    scenario = raw.get("governing_scenario")
    reproduced = raw.get("reproduced")
    return RecordAssertion(
        text=text,
        proof_mode=mode,
        governing_scenario=scenario if isinstance(scenario, str) else NO_GOVERNING_SCENARIO,
        steps=tuple(str(step) for step in _sequence(value=raw.get("steps"))),
        proof=str(raw.get("proof", "")),
        reproduced=reproduced if replay and isinstance(reproduced, bool) else None,
    )


def _payload(*, path: Path) -> tuple[BuildIdentity, tuple[Mapping[str, object], ...]] | None:
    """The caller's payload as a build identity plus raw assertion mappings."""
    text = _read(path=path)
    if text is None:
        return None
    parsed = parse_json(text=text)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    document = cast("dict[str, Any]", parsed)
    build_raw = document.get("build")
    assertions_raw = document.get("assertions")
    if not isinstance(build_raw, dict) or not isinstance(assertions_raw, list):
        return None
    build = cast("dict[str, Any]", build_raw)
    entries = tuple(
        cast("Mapping[str, object]", one)
        for one in cast("list[object]", assertions_raw)
        if isinstance(one, dict)
    )
    return (
        BuildIdentity(
            release_tag=_text(value=build.get("release_tag")),
            installed_build=_text(value=build.get("installed_build")),
            commit=_text(value=build.get("commit")),
        ),
        entries,
    )


def _read(*, path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _sequence(*, value: object) -> Sequence[object]:
    return cast("list[object]", value) if isinstance(value, list) else ()


def _text(*, value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
