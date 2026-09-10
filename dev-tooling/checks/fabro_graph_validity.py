# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""fabro_graph_validity — every committed factory graph is one the engine accepts.

A `workflow.fabro` that `fabro validate` rejects takes the WHOLE factory down the
moment it merges: every dispatch dies before any node runs. It has happened
twice. On 2026-07-16 a merged graph left the `review` node with only conditional
outgoing edges (`all_conditional_edges`), and on 2026-09-09 release 0.146.0
shipped the same defect on `pr` and `verify_pr`, reaching five repositories
before the revert. Both times the change carried tests — of DOT structure, of the
built plan — and both times no gate ever asked the engine itself. That is the gap
this module closes: the graphs are handed to `fabro validate`, not to a stand-in.

EVERY CHECKED PAYLOAD, NOT ONE SPELLED PATH. `_checked_workflow_payloads` owns
which directories a payload gate reads — the bundled reserved workflow plus every
directory this repository registers under its own `dispatcher.workflows` — and
this gate reads exactly that set, so it cannot come to disagree with the two
existing payload gates about what "every graph" means. An ENUMERATION CONTROL
then globs each of those directories' parents for a `workflow.fabro` the
enumeration does not name, so a graph added beside the bundle without being
registered fails loudly instead of going unvalidated.

THE NEGATIVE CONTROL IS A MUTANT OF THE REAL GRAPH, not a hand-authored fixture.
For each checked graph the module makes ONE unconditional edge conditional —
choosing a node that already routes conditionally and has exactly one
fallthrough, which is precisely the shape both outages had — and requires
`fabro validate` to REJECT that mutant naming `all_conditional_edges`. A
hand-written fixture can rot into validity, or fail for an unrelated reason and
still look like a working control; a mutant of the committed graph cannot. This
is also what proves the instrument is POINTED CORRECTLY rather than merely
present: a `fabro` that accepts everything, a wrong subcommand, or a graph path
the binary never read all make the mutant pass, and a passing mutant is a
control failure here rather than a clean report.

THE ONE LEVER, AND WHY ITS DEFAULT IS NOT FAIL-CLOSED. `fabro validate` needs the
`fabro` binary, resolved exactly the way a dispatch resolves it
(`resolve_fabro_bin`). The binary is a HOST artifact: it is present for a
developer, for a pre-push, and for the post-merge janitor's fresh host checkout,
and it is structurally ABSENT in a GitHub Actions runner and inside a Fabro
sandbox — where this repository's own in-run janitor gate executes this very
aggregate. A fail-closed default would therefore not harden the factory, it would
stop it: every dispatch would fail its janitor before any graph could be checked.

So absence is never SILENT and never a pass in disguise. When the binary does not
resolve the check emits, at error level, one record per graph naming what was NOT
looked at, plus a summary saying so in as many words, and `LIVESPEC_FABRO_GRAPH_VALIDATION`
selects whether that is fatal:

- `warn_when_fabro_absent` (the default) — report loudly, exit 0. This is what a
  CI job sets EXPLICITLY, so the skip is a declaration visible in the workflow
  file rather than an accident of the runner image.
- `fail_when_fabro_absent` — an unresolvable binary is a FAILURE. Set it wherever
  the binary is expected, so a host that has lost its `fabro` cannot quietly
  degrade into the warn path.

The lever NEVER suppresses a validation that could have run: it is consulted only
on the branch where no binary resolved. A value outside that closed space is a
failure rather than a fallback, so a typo cannot select a weaker mode.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
for _path in (_SCRIPT_DIR, _SCRIPTS, _SCRIPTS / "_vendor"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script; it
# is imported from the installed shared dev-tooling package's vendored copy.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
if str(_DT_VENDOR) not in sys.path:
    sys.path.insert(0, str(_DT_VENDOR))

import structlog  # noqa: E402
from _checked_workflow_payloads import (  # noqa: E402  — sibling private import
    CheckedPayload,
    checked_payloads,
    incompleteness,
)
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_bin  # noqa: E402

__all__: list[str] = [
    "FAIL_WHEN_ABSENT",
    "GRAPH_NAME",
    "LEVER",
    "LEVER_VALUES",
    "WARN_WHEN_ABSENT",
    "Report",
    "Validation",
    "control_failures",
    "main",
    "mutant_text",
    "report",
    "resolved_binary",
    "unenumerated_graphs",
    "validate_graph",
    "validation_findings",
]

GRAPH_NAME = "workflow.fabro"
LEVER = "LIVESPEC_FABRO_GRAPH_VALIDATION"
WARN_WHEN_ABSENT = "warn_when_fabro_absent"
FAIL_WHEN_ABSENT = "fail_when_fabro_absent"
LEVER_VALUES: tuple[str, ...] = (WARN_WHEN_ABSENT, FAIL_WHEN_ABSENT)

# The engine's own name for the defect both outages were, and the only evidence
# that the mutant was rejected FOR THE REASON THE CONTROL INTENDED.
_REJECTION_CODE = "all_conditional_edges"

# What the mutant adds to the one edge it rewrites. Any condition would do; a
# succeeded-outcome guard is the shape the surrounding graphs already use.
_CONTROL_CONDITION = 'condition="outcome=succeeded"'

# One `<src> -> <dst>` edge statement. Anchored on an identifier so a `//` DOT
# comment containing an arrow — of which the committed graphs have several —
# can never be read as an edge.
_EDGE_RE = re.compile(
    r"^[ \t]*(?P<src>[A-Za-z_][A-Za-z0-9_]*)[ \t]*->[ \t]*[A-Za-z_][A-Za-z0-9_]*(?P<attrs>.*)$"
)


@dataclass(frozen=True, kw_only=True)
class Validation:
    """One `fabro validate` invocation: what it exited with and what it said."""

    returncode: int
    output: str


@dataclass(frozen=True, kw_only=True)
class Report:
    """What the check saw. `findings` block the gate; `warnings` are loud and do not."""

    findings: list[str]
    warnings: list[str]


def resolved_binary(*, repo_root: Path) -> str | None:
    """The executable `fabro` this environment has, resolved as a dispatch resolves it.

    `None` means the environment carries no usable binary — never that the graphs
    are fine. The distinction between a bare name and a path matters: the fleet
    credential wrapper sanitises `PATH` while preserving `HOME`, so the resolver
    hands back an absolute home path that a `PATH` lookup would miss entirely.
    """
    candidate = resolve_fabro_bin(cwd=repo_root)
    if os.sep in candidate:
        path = Path(candidate)
        return candidate if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(candidate)


def validate_graph(*, binary: str, graph: Path) -> Validation:
    """Hand ONE graph to the engine, from its own directory so relative refs resolve."""
    completed = subprocess.run(
        [binary, "validate", str(graph)],
        cwd=graph.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    return Validation(
        returncode=completed.returncode, output=f"{completed.stdout}{completed.stderr}"
    )


def unenumerated_graphs(*, payloads: list[CheckedPayload]) -> list[Path]:
    """Every `workflow.fabro` sitting beside a checked payload that nothing enumerates.

    The workflow ROOTS are derived from the checked payloads rather than spelled,
    so registering a variant also widens this control; globbing each root is what
    makes an unregistered sibling graph a finding instead of an unvalidated file.
    """
    known = {payload.directory / GRAPH_NAME for payload in payloads}
    roots = {payload.directory.parent for payload in payloads}
    found = {graph for root in roots for graph in root.glob(f"*/{GRAPH_NAME}")}
    return sorted(found - known)


def mutant_text(*, text: str) -> str | None:
    """The graph with ONE node's only fallthrough edge made conditional.

    Picks a node that ALREADY routes conditionally and has exactly one
    unconditional edge, written without an attribute list — the shape both
    outages had, and the one whose rewrite is a pure append. `None` means no such
    edge exists, which is a control failure rather than a pass: a graph that
    cannot be mutated is a graph whose rejection path was never demonstrated.
    """
    lines = text.splitlines()
    edges = _edges(lines=lines)
    for index, source, attrs in edges:
        siblings = [edge for edge in edges if edge[1] == source]
        conditional = [edge for edge in siblings if "condition=" in edge[2]]
        fallthrough = [edge for edge in siblings if "condition=" not in edge[2]]
        if attrs.strip() != "" or conditional == [] or len(fallthrough) != 1:
            continue
        lines[index] = f"{lines[index]} [{_CONTROL_CONDITION}]"
        return "\n".join(lines) + "\n"
    return None


def _edges(*, lines: list[str]) -> list[tuple[int, str, str]]:
    """Every edge statement as `(line index, source node, attribute text)`."""
    matches = ((index, _EDGE_RE.match(line)) for index, line in enumerate(lines))
    return [
        (index, match.group("src"), match.group("attrs"))
        for index, match in matches
        if match is not None
    ]


def validation_findings(*, binary: str, payloads: list[CheckedPayload]) -> list[str]:
    """Every checked payload the engine refuses, plus every directory that is not whole."""
    found: list[str] = []
    for payload in payloads:
        found.extend(incompleteness(payload=payload))
        graph = payload.directory / GRAPH_NAME
        if not graph.is_file():
            continue
        result = validate_graph(binary=binary, graph=graph)
        if result.returncode != 0:
            verdict = f"`fabro validate` REJECTED {GRAPH_NAME} (exit {result.returncode})"
            found.append(f"{payload.where}: {verdict}: {_condensed(text=result.output)}")
    return found


def control_failures(*, binary: str, payloads: list[CheckedPayload]) -> list[str]:
    """Why a clean report would not be trustworthy: a mutant the engine did not reject."""
    failures: list[str] = []
    for payload in payloads:
        graph = payload.directory / GRAPH_NAME
        if graph.is_file():
            failures.extend(_matcher_failures(binary=binary, payload=payload, graph=graph))
    return failures


def _matcher_failures(*, binary: str, payload: CheckedPayload, graph: Path) -> list[str]:
    """That an all-conditional-edges mutant of THIS graph still reaches a rejection."""
    mutant = mutant_text(text=graph.read_text(encoding="utf-8"))
    if mutant is None:
        unmutatable = "no node has a single unconditional edge to make conditional"
        why = f"{unmutatable}, so no negative control could be built for {GRAPH_NAME}"
        return [f"matcher control: {payload.where}: {why}"]
    result = _validate_mutant(binary=binary, payload=payload, mutant=mutant)
    if result.returncode != 0 and _REJECTION_CODE in result.output:
        return []
    verdict = f"the {_REJECTION_CODE} mutant of {GRAPH_NAME} was not rejected as such"
    detail = f"(exit {result.returncode}): {_condensed(text=result.output)}"
    return [f"matcher control: {payload.where}: {verdict} {detail}"]


def _validate_mutant(*, binary: str, payload: CheckedPayload, mutant: str) -> Validation:
    """Validate the mutant in a scratch COPY of the payload, never in the worktree.

    The whole directory is copied rather than the graph alone: a node prompt
    reference that failed to resolve would make the mutant fail for the wrong
    reason, and a wrong-reason rejection is indistinguishable from the right one
    at the exit code.
    """
    with tempfile.TemporaryDirectory() as scratch:
        clone = Path(scratch) / payload.directory.name
        _ = shutil.copytree(payload.directory, clone)
        graph = clone / GRAPH_NAME
        _ = graph.write_text(mutant, encoding="utf-8")
        return validate_graph(binary=binary, graph=graph)


def _condensed(*, text: str) -> str:
    """The engine's output as one line, so a finding stays greppable."""
    return " | ".join(line.strip() for line in text.splitlines() if line.strip() != "")


def report(*, repo_root: Path) -> Report:
    """Everything this repository's committed factory graphs say, and what blocks."""
    payloads = checked_payloads(repo_root=repo_root)
    stray = f"is a {GRAPH_NAME} no checked payload names, so it would never be validated"
    findings = [
        f"enumeration control: {graph} {stray}; register it under `dispatcher.workflows`"
        for graph in unenumerated_graphs(payloads=payloads)
    ]
    lever = os.environ.get(LEVER, WARN_WHEN_ABSENT)
    if lever not in LEVER_VALUES:
        space = f"outside the closed value space {', '.join(LEVER_VALUES)}"
        findings.append(f"lever control: {LEVER}={lever!r} is {space}")
    binary = resolved_binary(repo_root=repo_root)
    if binary is None:
        absent = _absence_records(payloads=payloads)
        if lever == FAIL_WHEN_ABSENT:
            return Report(findings=[*findings, *absent], warnings=[])
        return Report(findings=findings, warnings=absent)
    findings.extend(validation_findings(binary=binary, payloads=payloads))
    findings.extend(control_failures(binary=binary, payloads=payloads))
    return Report(findings=findings, warnings=[])


def _absence_records(*, payloads: list[CheckedPayload]) -> list[str]:
    """What was NOT looked at, named one graph at a time, then said out loud once."""
    records = [
        f"{payload.where}: {GRAPH_NAME} was NOT validated — no `fabro` binary resolved"
        for payload in payloads
    ]
    lead = "NO factory graph was validated in this environment: `fabro` did not resolve"
    said = "nothing here says the graphs are good — only that they were not looked at"
    remedy = f"Set {LEVER}={FAIL_WHEN_ABSENT} wherever the binary is expected"
    records.append(f"{lead}, so {said}. {remedy}")
    return records


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("fabro_graph_validity")
    found = report(repo_root=Path.cwd())
    for warning in found.warnings:
        log.error(warning, kind="not-validated")
    for finding in found.findings:
        log.error(finding, kind="control" if "control:" in finding else "graph")
    return 1 if found.findings else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
