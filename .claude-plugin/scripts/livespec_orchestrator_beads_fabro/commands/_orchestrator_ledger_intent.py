"""`orchestrator ledger-intent-scan` subcommand — surface unstated ledger intent.

Per the `capture-spec-drift` clause of `SPECIFICATION/contracts.md`, the
ledger-intent scan
is the SECOND of the two drift sources: a read-only pass over the Ledger that
surfaces recorded work-item intent the ratified specification does not state,
decided by the shared spec-stated judgement of `livespec_runtime.spec_stated`.
This module is the machine surface under it; the per-finding consent flow and
the propose-change handoff stay in the skill, which reads this envelope.

CLI shape (the orchestrator-CLI convention — explicit addressing, injected
references, `--json` everywhere):

    orchestrator.py ledger-intent-scan --judge-cli <json-argv>
                                       [--since-version <vN>]
                                       [--coverage-point <value>]
                                       [--project-root <path>]
                                       [--spec-target <path>]
                                       [--json]

Every invocation appends an attributed ATTEMPT record to the repository's
detection-coverage anchor, and a completed-coverage record only when the shared
writer finds the pass claimable; `--coverage-point` is how a caller that walked
the merges supplies the frontier such a record carries. `_ledger_intent_coverage`
owns that projection and records why an absent point withholds coverage rather
than being invented.

THE JUDGE IS INJECTED AND REQUIRED. `livespec_runtime.spec_stated` reaches a
model only through the `run_model` callable its caller supplies — it opens no
socket and holds no credential — so the provider binding is this flag, invoked
with the rendered prompt on standard input and answering on standard output.
Required rather than defaulted: there is no judgement without a judge, and a
default would make a scan that reached no model report the clean empty answer
that is indistinguishable from a population the spec already states.

AN UNREADABLE VERDICT IS A FAILURE TO MEASURE AND NEVER AN ABSENT FINDING. A
model response the shared parser refuses is foreign input that did not validate,
so it exits 4 — the wire-shape code — naming every item it could not judge.
Reporting those items as "no drift" would be the one answer the detector exists
to make impossible: a clean negative over a population nobody judged.

AND A JUDGE THAT COULD NOT ANSWER AT ALL TAKES THAT SAME PATH. A judge CLI
exiting non-zero — a provider outage, an expired credential, a rate limit — is
the routine failure, not the exotic one, so `_verdict` captures it and reports
it as an unjudged item rather than letting it unwind past the recording below.
An escaping error would exit through `orchestrator.main` having appended
nothing, leaving the anchor unable to distinguish a pass that was attempted and
failed from one that was never run.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_runtime.spec_stated import (
    ModelRunner,
    SpecStatedParseError,
    SpecStatedVerdict,
    judge,
)
from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._ledger_intent_coverage import record_scan
from livespec_orchestrator_beads_fabro.commands._ledger_intent_cut import (
    SpecVersionCut,
    latest_spec_version_cut,
    spec_version_cut,
)
from livespec_orchestrator_beads_fabro.commands._ledger_intent_scan import (
    LedgerIntentFinding,
    finding_for,
    intent_statement,
    scan_population,
)
from livespec_orchestrator_beads_fabro.commands._orchestrator_shared import InjectedCliError
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from returns.result import Result

    from livespec_orchestrator_beads_fabro.commands._orchestrator_shared import CliContext
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["InjectedJudge", "judge_runner", "run_ledger_intent_scan"]

_EXIT_PRECONDITION_ERROR = 3
_EXIT_VALIDATION_ERROR = 4


@dataclass(frozen=True, kw_only=True)
class InjectedJudge:
    """The shared judgement's `run_model` seam, over an injected reference CLI.

    A callable OBJECT rather than a closure, because the shared `ModelRunner`
    alias the library calls through is POSITIONAL by contract — a nested `def`
    taking one positional argument is the one shape this package's keyword-only
    rule has no exemption for, while `__call__` is a dunder and is exempt.

    The prompt travels on STANDARD INPUT rather than as an argument: it carries
    the whole spec tree, so an argv form would exceed the platform argument
    limit on any real tree and would put the prompt in the host process table.
    """

    judge_cli: list[str]

    def __call__(self, prompt: str) -> str:
        completed = subprocess.run(  # noqa: S603 — fixed form over a caller-injected argv.
            self.judge_cli,
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise InjectedCliError(
                argv=self.judge_cli,
                detail=f"exit {completed.returncode}: {completed.stderr.strip()}",
            )
        return completed.stdout


def judge_runner(*, judge_cli: list[str]) -> ModelRunner:
    """The injected judge, as the callable the shared judgement runs through."""
    return InjectedJudge(judge_cli=judge_cli)


def run_ledger_intent_scan(
    *,
    context: CliContext,
    judge_cli: list[str],
    since_version: int | None = None,
    coverage_point: str | None = None,
    as_json: bool,
) -> int:
    """Run the ledger-intent scan: select, judge, emit, record.

    `since_version` is the parsed `--since-version` value, and `None` means the
    flag was omitted. The distinction decides BOTH readings the ratified clause
    separates: which version's cut bounds the captured-since set, and whether
    the live set widens it.

    THE RECORDING IS LAST AND UNCONDITIONAL once a population was established,
    because "every invocation" includes one that could not read a verdict —
    which is precisely the pass whose coverage must not be credited. Only the
    refusal above it returns first, and it returns before any work: a scan that
    could not establish its own population has nothing to record a scope for.
    """
    cut = _resolved_cut(spec_root=context.spec_root, since_version=since_version)
    if cut is None:
        detail = _unresolved_cut_detail(context=context, since_version=since_version)
        _ = write_stderr(text=f"ERROR: {detail}\n")
        return _EXIT_PRECONDITION_ERROR
    config = resolve_store_config(cwd=context.project_root, work_items_arg=None)
    population = scan_population(
        items=materialize_work_items(records=read_work_items(path=config)).values(),
        cut=cut.instant,
        include_live=since_version is None,
    )
    findings, unjudged = _judged(context=context, judge_cli=judge_cli, population=population)
    _emit(findings=findings, scanned=len(population), cut_instant=cut.instant, as_json=as_json)
    for item_id, detail in unjudged:
        _ = write_stderr(text=f"ERROR: the judgement could not be read for {item_id}: {detail}\n")
    scan_exit = _EXIT_VALIDATION_ERROR if unjudged else 0
    record = record_scan(
        config=config,
        project_root=context.project_root,
        since_version=since_version,
        surfaced=tuple(one.item_id for one in findings) + tuple(one for one, _ in unjudged),
        exit_code=scan_exit,
        coverage_point=coverage_point,
    )
    if record.narration is not None:
        label = "ERROR" if record.anchor_refused else "NOTE"
        _ = write_stderr(text=f"{label}: {record.narration}\n")
    if record.anchor_refused:
        return scan_exit or _EXIT_PRECONDITION_ERROR
    return scan_exit


def _judged(
    *, context: CliContext, judge_cli: list[str], population: tuple[WorkItem, ...]
) -> tuple[list[LedgerIntentFinding], list[tuple[str, str]]]:
    """Judge every item of the population, keeping the unreadable ones apart.

    The unreadable list carries the ITEM ID beside its detail, because the id
    is what the coverage record counts as a surfaced candidate and the detail
    is what the operator needs — one combined string would make the record's
    candidate key a sentence.
    """
    spec_tree = read_current_specification(spec_root=context.spec_root).files
    run_model = judge_runner(judge_cli=judge_cli)
    findings: list[LedgerIntentFinding] = []
    unjudged: list[tuple[str, str]] = []
    for item in population:
        judged = _verdict(
            spec_tree=spec_tree,
            statement=intent_statement(item=item),
            run_model=run_model,
        )
        if isinstance(judged, AttemptFailure):
            unjudged.append((item.id, str(judged.error)))
            continue
        if not is_successful(judged):
            unjudged.append((item.id, judged.failure().detail))
            continue
        finding = finding_for(item=item, verdict=judged.unwrap())
        if finding is not None:
            findings.append(finding)
    return findings, unjudged


def _verdict(
    *, spec_tree: Mapping[str, str], statement: str, run_model: ModelRunner
) -> Result[SpecStatedVerdict, SpecStatedParseError] | AttemptFailure:
    """One item's verdict, with a judge that could not answer on the same track.

    A judge CLI that EXITS NON-ZERO is the routine provider failure — an
    outage, an expired credential, a rate limit — and it is a failure to
    measure exactly as a response the parser refuses is. So it is captured
    here rather than left to unwind: `run_ledger_intent_scan` writes the
    attempt record the detection-coverage contract owes every invocation
    AFTER this loop, so an error that escaped it would exit through
    `orchestrator.main` having recorded nothing — a pass that was attempted
    and failed leaving the anchor indistinguishable from one never run, which
    is the one state the unconditional attempt record exists to rule out.

    The capture is NARROW on purpose. Only `InjectedCliError` is caught, so a
    judge binding that fails in some way this package has not modelled still
    unwinds and is seen, rather than being folded into "could not read a
    verdict" and reported as though the scan understood it.
    """
    return attempt(
        action=lambda: judge(spec_tree=spec_tree, statement=statement, run_model=run_model),
        exceptions=(InjectedCliError,),
    )


def _resolved_cut(*, spec_root: Path, since_version: int | None) -> SpecVersionCut | None:
    """The cut this invocation is scoped by, or `None` when none is readable."""
    if since_version is None:
        return latest_spec_version_cut(spec_root=spec_root)
    return spec_version_cut(spec_root=spec_root, version=since_version)


def _unresolved_cut_detail(*, context: CliContext, since_version: int | None) -> str:
    """Why the scan refused, naming the version whose cut could not be read.

    The version is NAMED rather than left implicit: an operator who mistyped
    `--since-version` and one whose spec tree carries no revision record have
    the same symptom and opposite remedies.
    """
    scope = (
        "the latest ratified spec version"
        if since_version is None
        else f"spec version v{since_version:03d}"
    )
    return (
        f"no revision record under {context.spec_root}/history/ records a cut "
        f"instant for {scope}, so the population of work-items captured on or "
        "after that cut cannot be established; the scan refuses rather than "
        "reporting an answer over a population nobody scoped."
    )


def _emit(
    *,
    findings: list[LedgerIntentFinding],
    scanned: int,
    cut_instant: str,
    as_json: bool,
) -> None:
    if as_json:
        payload = {
            "findings": [one.projection() for one in findings],
            "scanned": scanned,
            "cut": cut_instant,
        }
        _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return
    if not findings:
        _ = write_stdout(text=f"(no ledger-intent drift among {scanned} work-item(s))\n")
        return
    for one in findings:
        target = one.generalization_target or "(no generalization target)"
        _ = write_stdout(text=f"{one.item_id}  {one.kind}  {target}\n")
