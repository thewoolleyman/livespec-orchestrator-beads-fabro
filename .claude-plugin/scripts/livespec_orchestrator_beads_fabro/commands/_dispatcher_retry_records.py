"""The retry-discipline record: what a refused or failed dispatch leaves behind.

PURE, and the ONE place the record format lives. The format has a writer (a
dispatch that ended badly, or one an operator named a change for) and a reader
(the next dispatch's pre-dispatch guard), and those two are the whole mechanism:
the guard refuses on what the previous attempt RECORDED, so a render and a parse
that disagreed would be a guard that silently never arms. Keeping both halves in
one module makes that drift structurally impossible — the same argument
`_plan_completeness_evidence` makes for the completeness-review comment.

THE RECORD LIVES ON THE WORK-ITEM'S LEDGER TIMELINE, not in the dispatch
journal, and the distinction is load-bearing. The journal lives in the `tmp/`
tree of whichever host ran the dispatch, so a journal-only signature is
invisible to the next dispatch from any other clone — and this fleet's ledger
writers may share nothing but the Beads server. The journal still carries every
write, because an operator triaging ONE dispatch reads that and not the ledger.

THE KINDS ARE NOT INTERCHANGEABLE. A `refusal-signature` is written when a
dispatch ends in a failure or an admission refusal. A `named-change` record is
NOT an outcome — it is the reason an operator gave for overriding an armed
signature — so it must never arm or clear the guard: reading it as an outcome
would clear the guard on the strength of the override itself, which is the one
thing an override must not do.

A CAPACITY DEFERRAL IS NOT A FAILURE AND EARNS NO RECORD. The work-in-progress
cap defers an item that nothing is wrong with, so a signature there would arm
the guard on the strength of the queue being full and demand a named change for
a re-dispatch that is the ordinary next act. The writer's filter is what enforces
that; `UNCLASSIFIED_ERROR_CLASS` is deliberately not reachable from it.

THE SOURCE-MODULE TABLE IS DECLARED, NOT DISCOVERED. A refusing stage is a
STRING on a dispatch outcome and nothing at runtime links it to the module that
decided it, so the mapping is written down here. A stage this table does not name
resolves to the empty string and the refusal reports its comparison as
UNDETERMINED rather than guessing a path: an invented path would resolve to a
readable file whose bytes happened to match, which is a byte-identity claim about
two files nobody compared.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

__all__: list[str] = [
    "NAMED_CHANGE_KIND",
    "REFUSAL_SIGNATURE_KIND",
    "RETRY_DISCIPLINE_PREFIX",
    "UNCLASSIFIED_ERROR_CLASS",
    "UNKNOWN_BUILD_VERSION",
    "ExecutingBuild",
    "GuardState",
    "RetryRecord",
    "guard_state",
    "one_line",
    "parse_retry_record",
    "render_retry_record",
    "retry_records",
    "stage_source_module",
]

# The marker every record in this family opens with. ONE prefix for every kind,
# so a reader recognizes the family before it reads the kind.
RETRY_DISCIPLINE_PREFIX = "livespec-dispatch-retry-discipline"

REFUSAL_SIGNATURE_KIND = "refusal-signature"
NAMED_CHANGE_KIND = "named-change"

# The class a refusal signature carries when the attempt recorded no engine
# category and no degraded step. An explicit NAME rather than an empty string,
# so a reader can tell "nothing classified this" apart from "the class was
# lost", and so the repeat test compares two stated classes.
UNCLASSIFIED_ERROR_CLASS = "unclassified"

# The version a build whose manifest does not parse is recorded under. Recorded
# rather than omitted: an absent key is what a record from a build predating
# that key looks like, so omission would make an unreadable manifest
# indistinguishable from an older record format.
UNKNOWN_BUILD_VERSION = "unknown"

_COMMANDS = "scripts/livespec_orchestrator_beads_fabro/commands"
# Every refusing stage this plugin's dispatch outcomes name, mapped to the
# source module that decided it, RELATIVE to the plugin root. Relative because
# the comparison reads one path under TWO roots — the root the signature
# recorded and the root this build executes from — which is the whole reason a
# record carries a root at all. `admission-held` is the ADMISSION VALVE's own
# refusal, which arrives as a failed outcome at that stage.
_STAGE_SOURCE_MODULES: dict[str, str] = {
    "admission-held": f"{_COMMANDS}/_dispatcher_admission.py",
    "configuration": f"{_COMMANDS}/_dispatcher_factory_size_gate.py",
    "fabro-run": f"{_COMMANDS}/_dispatcher_engine.py",
    "stale-run-reap": f"{_COMMANDS}/_dispatcher_engine.py",
}

_KINDS = frozenset({REFUSAL_SIGNATURE_KIND, NAMED_CHANGE_KIND})
_COMMENT_BODY_KEY = "text"

_KIND_FIELD = "kind"
_STAGE_FIELD = "stage"
_ERROR_CLASS_FIELD = "error-class"
_BUILD_VERSION_FIELD = "build-version"
_PLUGIN_ROOT_FIELD = "plugin-root"
_RECORDED_AT_FIELD = "recorded-at"
_REASON_FIELD = "reason"
_OVERRODE_STAGE_FIELD = "overrode-stage"
_OVERRODE_ERROR_CLASS_FIELD = "overrode-error-class"


@dataclass(frozen=True, kw_only=True)
class ExecutingBuild:
    """One orchestrator build, as a record names it.

    BOTH fields, always. The version is what an operator reads; the plugin root
    is what locates that build's own copy of a source module on this host, which
    is the only way a byte-identity comparison between two builds can be taken
    at all.
    """

    version: str
    plugin_root: str


@dataclass(frozen=True, kw_only=True)
class RetryRecord:
    """One retry-discipline record, whichever kind it is.

    ONE dataclass for every kind rather than one per kind, because the guard
    reads a single ordered timeline and the fields the kinds share — the stage,
    the class, the build, the instant — are exactly the fields a refusal quotes.
    The override fields are empty on every kind but `named-change`.
    """

    kind: str
    stage: str
    error_class: str
    build: ExecutingBuild
    recorded_at: str
    reason: str = ""
    overrode_stage: str = ""
    overrode_error_class: str = ""


@dataclass(frozen=True, kw_only=True)
class GuardState:
    """What one item's timeline says about whether the guard is armed."""

    signature: RetryRecord | None


def render_retry_record(*, record: RetryRecord) -> str:
    """The comment body one record is written as.

    EVERY field is emitted on every kind, empty values included. An omitted key
    is what a record from a build predating that key looks like, so a reader
    could not tell "this kind carries no reason" from "the reason was lost".
    """
    return (
        "\n".join(
            (
                RETRY_DISCIPLINE_PREFIX,
                f"{_KIND_FIELD}: {record.kind}",
                f"{_STAGE_FIELD}: {record.stage}",
                f"{_ERROR_CLASS_FIELD}: {record.error_class}",
                f"{_BUILD_VERSION_FIELD}: {record.build.version}",
                f"{_PLUGIN_ROOT_FIELD}: {record.build.plugin_root}",
                f"{_RECORDED_AT_FIELD}: {record.recorded_at}",
                f"{_REASON_FIELD}: {one_line(text=record.reason)}",
                f"{_OVERRODE_STAGE_FIELD}: {record.overrode_stage}",
                f"{_OVERRODE_ERROR_CLASS_FIELD}: {record.overrode_error_class}",
            )
        )
        + "\n"
    )


def one_line(*, text: str) -> str:
    """`text` with every run of whitespace collapsed to one space.

    The record format is line-oriented, so a multi-line reason would truncate at
    the first newline and the stored reason would differ from the one the
    operator typed with nothing to show it. PUBLIC because the surfaces that
    quote a reason back must quote the same single line the record stored.
    """
    return " ".join(text.split())


def parse_retry_record(*, text: str) -> RetryRecord | None:
    """One comment body read back as a record, or `None` when it is not one.

    `None` is deliberately the same answer for an unrelated comment, a body
    whose first line is not the family prefix, and a body whose `kind` is not
    one this build knows. The caller needs no finer distinction: none of them is
    a record this build may act on, and the remedy for every one is the same.
    """
    fields = _record_fields(text=text)
    kind = fields.get(_KIND_FIELD, "")
    if kind not in _KINDS:
        return None
    return RetryRecord(
        kind=kind,
        stage=fields.get(_STAGE_FIELD, ""),
        error_class=fields.get(_ERROR_CLASS_FIELD, ""),
        build=ExecutingBuild(
            version=fields.get(_BUILD_VERSION_FIELD, ""),
            plugin_root=fields.get(_PLUGIN_ROOT_FIELD, ""),
        ),
        recorded_at=fields.get(_RECORDED_AT_FIELD, ""),
        reason=fields.get(_REASON_FIELD, ""),
        overrode_stage=fields.get(_OVERRODE_STAGE_FIELD, ""),
        overrode_error_class=fields.get(_OVERRODE_ERROR_CLASS_FIELD, ""),
    )


def retry_records(*, comments: Sequence[Mapping[str, object]]) -> tuple[RetryRecord, ...]:
    """Every retry record on one item's timeline, IN COMMENT ORDER.

    The order is the whole input to `guard_state`, and it comes from the comment
    LISTING rather than from any field of the record: a ledger comment cannot be
    edited or deleted, so append order IS chronological order, while `created_at`
    is `omitempty`-sparse and absent on records this plugin's own in-memory
    tenant writes.

    The body is read from `text`, which is the key `bd comments --json` uses.
    Neither `body` nor `content` is that key, and reaching for either yields an
    empty string per comment — the identical observation to a timeline carrying
    no records at all.
    """
    parsed: list[RetryRecord] = []
    for comment in comments:
        body = comment.get(_COMMENT_BODY_KEY)
        if not isinstance(body, str):
            continue
        record = parse_retry_record(text=body)
        if record is not None:
            parsed.append(record)
    return tuple(parsed)


def guard_state(*, records: Sequence[RetryRecord]) -> GuardState:
    """Whether the guard is armed for this timeline, and by which signature.

    The scan runs BACKWARDS and stops at the first record that is a dispatch
    OUTCOME. Everything else — which today is only a `named-change` record — is
    skipped, because the reason an operator gave is not a statement about how
    the attempt ended.
    """
    for record in reversed(records):
        if record.kind == REFUSAL_SIGNATURE_KIND:
            return GuardState(signature=record)
    return GuardState(signature=None)


def stage_source_module(*, stage: str) -> str:
    """The declared source module for a refusing stage, or `""` when unknown."""
    return _STAGE_SOURCE_MODULES.get(stage, "")


def _record_fields(*, text: str) -> dict[str, str]:
    """The `key: value` header of one body, or `{}` when it carries none."""
    lines = text.split("\n\n", maxsplit=1)[0].splitlines()
    if not lines or lines[0].strip() != RETRY_DISCIPLINE_PREFIX:
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        key, separator, value = line.partition(":")
        if separator == "":
            continue
        fields[key.strip()] = value.strip()
    return fields
