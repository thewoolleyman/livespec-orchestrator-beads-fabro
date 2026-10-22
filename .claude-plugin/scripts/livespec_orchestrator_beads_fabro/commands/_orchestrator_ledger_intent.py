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
                                       [--project-root <path>]
                                       [--spec-target <path>]
                                       [--json]

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
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_runtime.spec_stated import ModelRunner, judge
from returns.pipeline import is_successful

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._ledger_intent_cut import (
    latest_spec_version_cut,
)
from livespec_orchestrator_beads_fabro.commands._ledger_intent_scan import (
    LedgerIntentFinding,
    finding_for,
    intent_statement,
    scan_population,
)
from livespec_orchestrator_beads_fabro.commands._orchestrator_shared import InjectedCliError
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._orchestrator_shared import CliContext

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


def run_ledger_intent_scan(*, context: CliContext, judge_cli: list[str], as_json: bool) -> int:
    """Run the ledger-intent scan: select, judge, emit."""
    cut = latest_spec_version_cut(spec_root=context.spec_root)
    if cut is None:
        _ = write_stderr(
            text=(
                "ERROR: no ratified spec version under "
                f"{context.spec_root}/history/ records a cut instant, so the "
                "population of work-items captured since the latest cut cannot "
                "be established; the scan refuses rather than reporting an "
                "unscoped answer.\n"
            ),
        )
        return _EXIT_PRECONDITION_ERROR
    config = resolve_store_config(cwd=context.project_root, work_items_arg=None)
    population = scan_population(
        items=materialize_work_items(records=read_work_items(path=config)).values(),
        cut=cut.instant,
        include_live=True,
    )
    spec_tree = read_current_specification(spec_root=context.spec_root).files
    run_model = judge_runner(judge_cli=judge_cli)
    findings: list[LedgerIntentFinding] = []
    unjudged: list[str] = []
    for item in population:
        judged = judge(
            spec_tree=spec_tree,
            statement=intent_statement(item=item),
            run_model=run_model,
        )
        if not is_successful(judged):
            unjudged.append(f"{item.id}: {judged.failure().detail}")
            continue
        findings.append(finding_for(item=item, verdict=judged.unwrap()))
    _emit(findings=findings, scanned=len(population), cut_instant=cut.instant, as_json=as_json)
    for narration in unjudged:
        _ = write_stderr(text=f"ERROR: the judgement could not be read for {narration}\n")
    return _EXIT_VALIDATION_ERROR if unjudged else 0


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
