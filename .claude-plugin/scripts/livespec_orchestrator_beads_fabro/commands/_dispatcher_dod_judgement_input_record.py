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

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import DodJudgement

__all__: list[str] = [
    "BOUND_ENDED_CANDIDATE_FIELD",
    "input_usage_lines",
]

_DECIDING_CANDIDATE_FIELD = "deciding-candidate"
_DECIDING_INPUT_TOKENS_FIELD = "deciding-candidate-input-tokens"
_DECIDING_INPUT_USAGE_FIELD = "deciding-candidate-input-usage"
BOUND_ENDED_CANDIDATE_FIELD = "bound-ended-candidate"
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
        f"{BOUND_ENDED_CANDIDATE_FIELD}{_FIELD_SEPARATOR}{candidate}"
        for candidate in judgement.bound_ended_candidates
    )
    return lines
