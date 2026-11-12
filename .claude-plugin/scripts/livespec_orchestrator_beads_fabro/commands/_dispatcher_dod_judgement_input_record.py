"""What a taken verdict's record says about its deciding candidate's input.

Split out of `_dispatcher_dod_judgement_record` by cohesion: that module
assembles and reads back the whole verdict record, while this owns ONE of the
three groups of lines the record carries — the input the deciding candidate's
requests reported, and the candidates the bound ended on the way to it. The
measurement these lines report is `_dispatcher_dod_judgement_usage`'s; this is
only how that measurement is WRITTEN DOWN, which is why the two are separate
modules rather than one.

Two properties an editor must not invert.

The usage MARK is rendered UNCONDITIONALLY while the token total is rendered
only when one was measured, and the asymmetry is the whole point of carrying a
mark at all. A total is absent for two unrelated reasons — no request reported
one, or the transcript named a request nothing accounted for — and the figure
alone cannot tell them apart, so a record carrying a bare number would report a
PARTIAL total as the candidate's real use. `unreported` is therefore a stated
value and never an omitted line.

The bound-ended candidates are listed whenever the bound ended anything, not
only on a chain that returned no verdict. On a chain that went on to decide,
that list is the record of what the earlier candidates spent; on one that did
not, it is the other half of the absent `deciding-candidate` line — and it is
that PAIR that distinguishes an exhausted chain from a taking that ran no
candidate at all. The two send an operator to opposite places, one to the
item's own size and the other to an outage, so neither half is evidence alone.

`BOUND_ENDED_CANDIDATE_FIELD` is public because the record module's
`_REPEATED_FIELDS` has to name it: the key is written once per candidate, so a
field map that collapsed it to its last occurrence would report one ended
candidate however many the bound actually ended.
"""

from __future__ import annotations

from collections.abc import Sequence

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import DodJudgement
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_usage import (
    HOST_JUDGEMENT_INPUT_LIMIT,
)

__all__: list[str] = [
    "BOUND_ENDED_CANDIDATE_FIELD",
    "bound_ended_lines",
    "input_bound_detail_lines",
    "input_usage_lines",
]

_DECIDING_CANDIDATE_FIELD = "deciding-candidate"
_DECIDING_INPUT_TOKENS_FIELD = "deciding-candidate-input-tokens"
_DECIDING_INPUT_USAGE_FIELD = "deciding-candidate-input-usage"
_TOTAL_INPUT_TOKENS_FIELD = "total-input-tokens"
_TOTAL_INPUT_USAGE_FIELD = "total-input-usage"
_HOST_INPUT_LIMIT_FIELD = "host-judgement-input-limit"
BOUND_ENDED_CANDIDATE_FIELD = "bound-ended-candidate"
_SUBJECT_SIZE_FIELD = "subject-size-characters"
_CARRIED_RIDER_COUNT_FIELD = "carried-rider-count"
_INPUT_LIMIT_CAUSE = "input-limit-reached"
_FIELD_SEPARATOR = ": "


def input_usage_lines(*, judgement: DodJudgement) -> list[str]:
    """The record lines naming one taking's deciding input, in record order."""
    lines: list[str] = []
    if judgement.deciding_candidate is not None:
        lines.append(f"{_DECIDING_CANDIDATE_FIELD}{_FIELD_SEPARATOR}{judgement.deciding_candidate}")
    if judgement.input_tokens is not None:
        lines.append(f"{_DECIDING_INPUT_TOKENS_FIELD}{_FIELD_SEPARATOR}{judgement.input_tokens}")
    lines.append(f"{_DECIDING_INPUT_USAGE_FIELD}{_FIELD_SEPARATOR}{judgement.input_usage}")
    lines.extend(
        total_input_lines(
            total_tokens=judgement.total_input_tokens,
            usage=judgement.total_input_usage,
        )
    )
    lines.extend(
        bound_ended_lines(
            candidates=judgement.bound_ended_candidates,
            input_tokens=judgement.bound_ended_input_tokens,
        )
    )
    return lines


def bound_ended_lines(
    *, candidates: Sequence[str], input_tokens: Sequence[int | None] = ()
) -> list[str]:
    """One record line per candidate the input bound ended, in chain order.

    Shared by the taken-verdict record and the did-not-run record, because a
    chain the bound exhausted returns no verdict and its only record is the
    second one.
    """
    lines: list[str] = []
    for index, candidate in enumerate(candidates):
        lines.append(f"{BOUND_ENDED_CANDIDATE_FIELD}{_FIELD_SEPARATOR}{candidate}")
        tokens = input_tokens[index] if index < len(input_tokens) else None
        if tokens is not None:
            candidate_usage = f"candidate={candidate} total-input-tokens={tokens}"
            lines.extend(
                (
                    f"bound-ended-candidate-input-tokens{_FIELD_SEPARATOR}{candidate_usage}",
                    f"{_TOTAL_INPUT_TOKENS_FIELD}{_FIELD_SEPARATOR}{tokens}",
                )
            )
    return lines


def total_input_lines(
    *, total_tokens: int | None, usage: str, input_limited: bool = False
) -> list[str]:
    """Render the taking-wide input total and its optional governing bound."""
    lines = (
        []
        if total_tokens is None
        else [f"{_TOTAL_INPUT_TOKENS_FIELD}{_FIELD_SEPARATOR}{total_tokens}"]
    )
    lines.append(f"{_TOTAL_INPUT_USAGE_FIELD}{_FIELD_SEPARATOR}{usage}")
    if input_limited:
        lines.append(f"{_HOST_INPUT_LIMIT_FIELD}{_FIELD_SEPARATOR}{HOST_JUDGEMENT_INPUT_LIMIT}")
    return lines


def input_bound_detail_lines(
    *, cause: str, subject_characters: int | None, carried_rider_count: int | None
) -> list[str]:
    """Render the subject measurement that explains an input-bound ending."""
    if cause != _INPUT_LIMIT_CAUSE or subject_characters is None or carried_rider_count is None:
        return []
    return [
        f"{_SUBJECT_SIZE_FIELD}{_FIELD_SEPARATOR}{subject_characters}",
        f"{_CARRIED_RIDER_COUNT_FIELD}{_FIELD_SEPARATOR}{carried_rider_count}",
    ]
