"""`take-candidate-canary` — file one FIXTURE canary work-item and dispatch it.

A candidate canary measures the ENGINE: a candidate Fabro build, a re-pinned
carrier, a restarted factory host. Whatever brief it carries is therefore
instrumentation, not work, and the one property that instrumentation must have
is that it cannot fail for a reason of its own. Canaries 5 and 6 of plan
`fabro-currency` did exactly that — both reached the `dod_gate` node and were
refused, because the canary reused a real backlog item whose `References` line
named a heading that governs something else. An item-quality refusal is
indistinguishable, at the surface an operator watches, from the engine fault the
canary was taken to look for; the second canary repeated the first's mistake for
that reason.

So the brief is a COMMITTED FIXTURE, reviewed once through the ordinary gates
and thereafter rendered mechanically. This module is the renderer and the filing
seam; the operator-facing procedure that files one and dispatches it to a named
factory is the runbook recipe, which shells to this module rather than
assembling a brief of its own.

WHY THE PLACEHOLDERS ARE NOT DOUBLED-BRACE TOKENS. A doubled-brace
template-interpolation pair anywhere in a work-item's own text makes that item
undispatchable: dispatch graph construction fails on a template variable whose
name appears only in the record and never in the workflow, and the Dispatcher's
escaper is self-cancelling because the goal is rendered twice. A fixture whose
whole purpose is to be dispatchable cannot carry that hazard, so the two
substitution points are spelled `@@…@@` and are plain string replacement.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_runtime.work_items.rank import key_between
from returns.io import IOResult
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
)
from livespec_orchestrator_beads_fabro.errors import WorkItemNotFoundError
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "CANARY_MARKER_RELPATH",
    "CANARY_TEMPLATE_RELPATH",
    "CanaryFiling",
    "CanaryFixture",
    "file_candidate_canary",
    "main",
    "marker_entry_findings",
    "render_canary_fixture",
]

# The committed fixture the brief is rendered from, and the dedicated marker file
# the fixture's one assertion names. The canary's WHOLE change is one appended
# line in the latter, which is what keeps a canary's diff incapable of failing
# for a reason of its own.
CANARY_TEMPLATE_RELPATH = "orchestrator-image/candidate-canary-work-item-template.md"
CANARY_MARKER_RELPATH = "orchestrator-image/candidate-canary-log.md"

# The two field markers of the committed template, each matched as a line of its
# own. The template's own prose refers to them in backticks for exactly that
# reason: a sentence about a marker must not be readable AS the marker.
_TITLE_MARKER = "TITLE:"
_DESCRIPTION_MARKER = "DESCRIPTION:"
_ID_PLACEHOLDER = "@@CANARY_ID@@"
_FACTORY_PLACEHOLDER = "@@CANARY_FACTORY@@"
_NEWLINE = "\n"

# The marker file's own grammar, which is the whole of what the check suite has
# to accept for a canary's edit to merge: one heading, then one `- ` line per
# canary taken.
_MARKER_ENTRIES_HEADING = "## Entries"
_MARKER_ENTRY_PREFIX = "- "

# What the filed fixture IS, as ledger fields. A canary is instrumentation, so
# it is admitted without a human valve (`auto`) -- waiting for an approval would
# make the canary's latency a property of whoever is awake -- and it is a plain
# `task` of freeform origin, tied to no gap and to no plan epic.
_FIXTURE_TYPE = "task"
_FIXTURE_ORIGIN = "freeform"
_FIXTURE_FILED_STATUS = "backlog"
_ADMISSION_AUTO = "auto"
# The intake Definition-of-Ready answers, affirmed HERE rather than asked. Each
# is a property of the committed fixture, settled when the fixture was reviewed:
# one coherent done, verifiable by the suite without a human, factory-eligible,
# dependency-free, repo-targeted, and above the triage floor. A canary that
# stopped to ask them would be asking about a file nobody edited.
_FIXTURE_CHECKLIST = DefinitionOfReadyChecklist(
    single_coherent_done=True,
    autonomously_verifiable=True,
    autonomy_tiered=True,
    dependency_linked=True,
    repo_targeted=True,
    above_floor=True,
)
_EXIT_FILING_REFUSED = 3


@dataclass(frozen=True, kw_only=True)
class CanaryFixture:
    """One rendered canary brief: the work-item title and description to file.

    The description is carried whole rather than as a parsed Definition of Done,
    because the ratified clause allows exactly one parse of that section and it
    is not this module's. What reaches the ledger is the text; what grades it is
    the sanctioned parse, reading the same bytes.
    """

    title: str
    description: str


@dataclass(frozen=True, kw_only=True)
class CanaryFiling:
    """One filed canary: the minted work-item id and the status intake routed it to.

    The status is carried rather than asserted here because routing belongs to
    the shared intake gate, not to this door. An operator who sees anything but
    `ready` is looking at a fixture the gate declined, and the dispatch that
    follows will refuse on its own terms with its own reason — which is better
    than this module inventing a verdict about a decision it did not make.
    """

    item_id: str
    status: str


def render_canary_fixture(*, template_text: str, item_id: str, factory: str) -> CanaryFixture:
    """Render the committed fixture template for one canary.

    Pure: a function of the template text and the two substitution values, so
    the brief a dispatch would carry is gradeable without filing anything.

    A template missing either field marker is a BUG, not an expected failure —
    the file is committed and the test suite parses it — so the lookups below
    raise rather than returning a half-rendered brief that would reach the
    ledger looking plausible.
    """
    lines = template_text.splitlines()
    title_line = next(line for line in lines if line.startswith(_TITLE_MARKER))
    body_start = 1 + next(
        index for index, line in enumerate(lines) if line.strip() == _DESCRIPTION_MARKER
    )
    return CanaryFixture(
        title=_substituted(
            text=title_line.removeprefix(_TITLE_MARKER).strip(),
            item_id=item_id,
            factory=factory,
        ),
        description=_substituted(
            text=_NEWLINE.join(lines[body_start:]).strip() + _NEWLINE,
            item_id=item_id,
            factory=factory,
        ),
    )


def marker_entry_findings(*, marker_text: str) -> tuple[str, ...]:
    """Every way the candidate-canary log's entry list is malformed, or an empty tuple.

    This is what makes "the check suite accepts the canary's edit" a measured
    property rather than an absence of objection. The suite grades the COMMITTED
    log through this function and grades it again with the fixture's own entry
    appended, so the one edit a canary makes is known-accepted before any canary
    makes it; the malformed cases are what stop that acceptance from being
    vacuous.

    Findings rather than a boolean, and one line each naming the offending
    element and the remedy, because that is the shape every other grading
    surface in this repository reports — an operator reading a janitor failure
    needs the line that is wrong, not a verdict on the file.
    """
    lines = marker_text.splitlines()
    heading_index = next(
        (index for index, line in enumerate(lines) if line.strip() == _MARKER_ENTRIES_HEADING),
        None,
    )
    if heading_index is None:
        return (_absent_heading_finding(),)
    entries = [line for line in lines[heading_index + 1 :] if line.strip()]
    if not entries:
        return (_empty_entry_list_finding(),)
    return tuple(
        _malformed_entry_finding(line=line)
        for line in entries
        if not line.startswith(_MARKER_ENTRY_PREFIX)
    )


def file_candidate_canary(
    *, path: StoreConfig, repo_root: Path, factory: str, now_iso: str
) -> IOResult[CanaryFiling, WorkItemNotFoundError | PolicySettingUnreadable]:
    """File one FRESH canary work-item rendered from the committed fixture template.

    Fresh every time, never reused: a canary's record carries the run it belongs
    to, and a reused item would accumulate the comments, claims and audit of
    every canary before it — so the brief the next dispatch renders would grow
    with each one, which is the opposite of a fixture.

    Filed through the shared capture seam rather than through a store write of
    its own. That seam validates the committed ceilings before its first ledger
    mutation and then routes the record through the one intake gate every other
    filing door uses, so a canary cannot enter the ledger by a path with
    different rules. `factory` is the name the DISPATCH will be routed to; it
    reaches the record only as text in the brief, because routing is the
    dispatcher's argument and not a property of the item.
    """
    fixture_template = (repo_root / CANARY_TEMPLATE_RELPATH).read_text(encoding="utf-8")
    item_id = new_work_item_id(prefix=path.prefix)
    fixture = render_canary_fixture(
        template_text=fixture_template, item_id=item_id, factory=factory
    )
    routed = file_captured_work_item(
        path=path,
        item=WorkItem(
            id=item_id,
            type=_FIXTURE_TYPE,
            status=_FIXTURE_FILED_STATUS,
            title=fixture.title,
            description=fixture.description,
            origin=_FIXTURE_ORIGIN,
            gap_id=None,
            rank=key_between(a=None, b=None),
            assignee=None,
            depends_on=(),
            captured_at=now_iso,
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy=_ADMISSION_AUTO,
        ),
        checklist=_FIXTURE_CHECKLIST,
    )
    return routed.map(lambda status: CanaryFiling(item_id=item_id, status=status))


def main(*, argv: list[str] | None = None) -> int:
    """File one canary and print its id, for the recipe's dispatch leg to consume.

    stdout carries EXACTLY the minted id and nothing else, because the recipe
    passes it straight to the dispatcher's `--item`; everything a human wants to
    read goes to stderr. Dispatch is deliberately NOT performed here: the
    dispatcher owns every pre-dispatch refusal, the journal and the claim, and a
    second door into it would be a second place those could drift.
    """
    parser = argparse.ArgumentParser(prog="take-candidate-canary")
    _ = parser.add_argument(
        "--factory",
        dest="factory",
        required=True,
        help="the configured factory name this canary will be dispatched to",
    )
    _ = parser.add_argument("--project-root", dest="project_root", default=None)
    args = parser.parse_args(argv)
    repo_root = Path(args.project_root) if args.project_root is not None else Path.cwd()
    filed = file_candidate_canary(
        path=resolve_store_config(cwd=repo_root, work_items_arg=None),
        repo_root=repo_root,
        factory=args.factory,
        now_iso=utc_now_iso(),
    )
    if not is_successful(filed):
        _ = write_stderr(text=f"ERROR: {unsafe_perform_io(filed.failure())}\n")
        return _EXIT_FILING_REFUSED
    record = unsafe_perform_io(filed.unwrap())
    _ = write_stderr(text=_filed_narration(record=record, factory=args.factory))
    _ = write_stdout(text=f"{record.item_id}\n")
    return 0


def _filed_narration(*, record: CanaryFiling, factory: str) -> str:
    return (
        f"filed candidate canary {record.item_id} at {record.status}"
        f" for factory {factory}{_NEWLINE}"
    )


def _absent_heading_finding() -> str:
    return (
        f"the candidate-canary log carries no `{_MARKER_ENTRIES_HEADING}` heading,"
        " so there is no entry list for a canary to append to; restore the heading"
        " rather than appending beneath the prose"
    )


def _empty_entry_list_finding() -> str:
    return (
        f"the candidate-canary log carries no entry under `{_MARKER_ENTRIES_HEADING}`;"
        " the file is append-only and keeps at least its seed entry, so an empty"
        " list means entries were removed rather than added"
    )


def _malformed_entry_finding(*, line: str) -> str:
    return (
        f"the candidate-canary log line {line!r} does not begin with"
        f" `{_MARKER_ENTRY_PREFIX}`, so it is not one entry; make the canary's change"
        " exactly one appended entry line and edit nothing else"
    )


def _substituted(*, text: str, item_id: str, factory: str) -> str:
    return text.replace(_ID_PLACEHOLDER, item_id).replace(_FACTORY_PLACEHOLDER, factory)
