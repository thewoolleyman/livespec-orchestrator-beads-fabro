# pyright: reportMissingImports=none, reportMissingTypeStubs=none, reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""seam_equivalence — the three integration-input surfaces say the same thing, statically.

`SPECIFICATION/contracts.md`, the repository-integration-contract section's
typed-workflow-inputs clause, requires that the set of `inputs.*` tokens the
`implement-work-item` workflow references, the set of inputs the Dispatcher
renders from the `ResolvedIntegrationContract`, and the schema's projectable
fields be IDENTICAL, and that every such token sit in a position the engine
renders. This module is the entry point of that check. It answers a templating
question statically instead of by a production dispatch, which is the whole
point: a token the engine silently drops costs one dispatch to discover and
gives no error when it happens.

EVERY REGISTERED VARIANT IS CHECKED, NOT ONLY THE BUNDLE. The clause "A
registered variant is the reserved workflow's peer, not its exception" requires
this check to read the bundle AND every directory this repository registers
under its own `dispatcher.workflows`. `_checked_workflow_payloads` owns that
enumeration for both payload gates; each directory is then read, compared and
CONTROLLED on its own, and every finding names the directory it came from. The
comparand is the ONE Dispatcher-rendered set for all of them — see
`rendered_input_names` for why a per-variant comparand would pass the exact
defect the rule exists to catch.

IT OWNS THE READING AND THE CONTROLS, NOT THE RULES. Two sibling private
modules carry the two concerns that change for their own reasons:
`_seam_equivalence_scan` knows where a token may sit and which positions the
pinned engine expands, and `_seam_equivalence_findings` knows the three input
families and what a disagreement between the surfaces is called. What is left
here is what a CHECK does: resolve the payloads, read them, render what the
Dispatcher would send, compose the findings, and refuse to report a clean
payload it could not have seen.

THREE POSITIVE CONTROLS, because this check reports an ABSENCE. The committed
payload references no integration token today — the payload edit that introduces
them is a separate, attended change — so a broken scanner would print exactly
what a conformant payload prints, forever. `main` therefore refuses to report a
clean payload unless all three hold:

- the DISCOVERY control asserts the scan of EACH checked payload reached its
  files and returned the tokens that are actually there (the six per-node
  adapter tokens, each in an `acp.command`), so a mis-scoped path, a pattern
  that cannot match, or a registered directory that scans to nothing fails
  loudly instead of passing silently. It is evaluated PER DIRECTORY: a
  repository-wide control would be satisfied by the bundle alone and would then
  certify a variant it never read;
- the COMPLETENESS control asserts each checked directory holds a whole
  workflow, so an unreadable or half-written registered directory is a finding
  naming that directory rather than a silent skip;
- the MATCHER control asserts the checked-in fixture graph, which carries an
  integration token in a `timeout` attribute and another in a comment, still
  produces non-rendered-position findings through the SAME scan path.

Output discipline: `print` and direct `sys.stderr.write` are banned here, so
diagnostics flow through structlog (JSON to stderr).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent
_SCRIPTS = _REPO_ROOT / ".claude-plugin" / "scripts"
for _path in (_SCRIPT_DIR, _SCRIPTS, _SCRIPTS / "_vendor"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# structlog is the only sanctioned stderr surface for an enforcement script
# (per the `no_write_direct` ban on direct `sys.stderr.write`). It is not
# vendored in this repo's own tree, so it is imported from the installed
# `livespec_dev_tooling` package's vendored copy.
#
# The two scan/findings modules beside it are sibling PRIVATE modules in this
# same directory. This file's own directory is on `sys.path` above, so the
# sibling imports resolve both under `python <path>` and under the
# importlib-by-path load the paired test uses.
import livespec_dev_tooling  # noqa: E402

_DT_VENDOR = Path(livespec_dev_tooling.__file__).resolve().parent / "_vendor"
# APPEND, never insert at the front: since livespec-dev-tooling v1.90.0 that
# `_vendor` also carries a PARTIAL `livespec_runtime` (the github_budget
# modules only, no `work_items`), and putting it ahead of this repo's own
# `_vendor` shadowed the full copy every plugin module imports, so every
# check in this directory died on `No module named
# 'livespec_runtime.work_items'` (livespec-dev-tooling-8o8e.24 is the
# two-copies class). Appending keeps `structlog` resolvable while this
# repo's full vendored runtime keeps precedence.
if str(_DT_VENDOR) not in sys.path:
    sys.path.append(str(_DT_VENDOR))

import structlog  # noqa: E402
from _checked_workflow_payloads import (  # noqa: E402  — sibling private import
    CheckedPayload,
    bundle_payload,
    checked_payloads,
    incompleteness,
)
from _seam_equivalence_findings import (  # noqa: E402  — sibling private import
    Finding,
    equivalence_findings,
    non_rendered_occurrences,
    policy_declaration_findings,
    position_findings,
    referenced_integration_inputs,
    schema_findings,
    scoping_findings,
)
from _seam_equivalence_scan import (  # noqa: E402  — sibling private import
    OUTSIDE_ATTRIBUTE_POSITION,
    Occurrence,
    graph_occurrences,
    prompt_occurrences,
    run_config_occurrences,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (  # noqa: E402
    NODE_INPUT_CANDIDATES,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (  # noqa: E402
    contract_run_inputs,
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan_build import (  # noqa: E402
    resolve_repo_integration_contract,
)

__all__: list[str] = [
    "control_failures",
    "declared_inputs",
    "fixture_path",
    "main",
    "payload_dir",
    "payload_findings",
    "payload_occurrences",
    "rendered_input_names",
]

_FIXTURE_RELPATH = ("dev-tooling", "checks", "fixtures", "seam_equivalence_control.fabro.txt")
_CONFIG_RELPATH = (".livespec.jsonc",)
_ADAPTER_POSITION = "acp.command"


def payload_dir(*, repo_root: Path) -> Path:
    """The bundled `implement-work-item` payload every registered variant is held to."""
    return bundle_payload(repo_root=repo_root).directory


def fixture_path(*, repo_root: Path) -> Path:
    """The positive-control graph carrying known non-rendered token positions."""
    return repo_root.joinpath(*_FIXTURE_RELPATH)


def payload_occurrences(*, payload: CheckedPayload) -> list[Occurrence]:
    """Every token across one payload's graph, run config, and node prompts.

    A file the directory does not hold reads as empty rather than raising: an
    incomplete directory is what the completeness control reports, by name, and
    an exception here would take the whole scan down with it instead.
    """
    root = payload.directory
    occurrences = graph_occurrences(
        text=_file_text(path=root / "workflow.fabro"), venue="workflow.fabro"
    )
    occurrences.extend(
        run_config_occurrences(text=_file_text(path=root / "workflow.toml"), venue="workflow.toml")
    )
    for prompt in sorted((root / "prompts").glob("*.md")):
        occurrences.extend(
            prompt_occurrences(
                text=prompt.read_text(encoding="utf-8"), venue=f"prompts/{prompt.name}"
            )
        )
    return occurrences


def _file_text(*, path: Path) -> str:
    """One payload file's text, or empty when the directory does not hold it."""
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def declared_inputs(*, payload: CheckedPayload) -> dict[str, str]:
    """Every input this payload's `[run.inputs]` table declares, with its default."""
    run_config = payload.directory / "workflow.toml"
    return dict(workflow_declared_inputs(committed_text=_file_text(path=run_config)))


def rendered_input_names(*, repo_root: Path) -> frozenset[str]:
    """The ONE set of integration inputs the Dispatcher renders, off the BUNDLE.

    Rendered THROUGH the projection, off a contract resolved from this
    repository's own declaration, rather than re-derived from the schema: the
    question is what the Dispatcher sends, and it sends the intersection of the
    contract's projectable fields with what the payload declares.

    ONE set for every checked directory, deliberately, and this is the load-bearing
    half. Re-deriving the comparand from each VARIANT's own `[run.inputs]` table
    would let a variant that declares fewer inputs shrink its own comparand and
    pass the equality vacuously -- which is precisely the "a variant referencing
    fewer tokens is a finding, not a pass" rule of the peer clause. Against the
    single bundle-derived set, that variant reports `rendered-input-without-token`
    for every input it dropped.
    """
    resolved = resolve_repo_integration_contract(
        config_text=repo_root.joinpath(*_CONFIG_RELPATH).read_text(encoding="utf-8"),
        default_branch=None,
    )
    pairs = contract_run_inputs(
        resolved=resolved, declared=declared_inputs(payload=bundle_payload(repo_root=repo_root))
    )
    return frozenset(pair.split("=", 1)[0] for pair in pairs)


def payload_findings(*, repo_root: Path) -> list[Finding]:
    """Every way this repository's checked payloads break the seam equivalence."""
    rendered = rendered_input_names(repo_root=repo_root)
    findings: list[Finding] = []
    for payload in checked_payloads(repo_root=repo_root):
        findings.extend(
            _located(
                findings=_directory_findings(payload=payload, rendered=rendered),
                where=payload.where,
            )
        )
    findings.extend(schema_findings())
    return findings


def _directory_findings(*, payload: CheckedPayload, rendered: frozenset[str]) -> list[Finding]:
    """Every way ONE checked directory breaks the seam equivalence."""
    occurrences = payload_occurrences(payload=payload)
    findings = position_findings(occurrences=occurrences)
    findings.extend(
        equivalence_findings(
            referenced=referenced_integration_inputs(occurrences=occurrences), rendered=rendered
        )
    )
    declared = declared_inputs(payload=payload)
    findings.extend(scoping_findings(declared=declared))
    findings.extend(policy_declaration_findings(declared=declared))
    return findings


def _located(*, findings: list[Finding], where: str) -> list[Finding]:
    """The same findings, each naming the directory that produced it.

    The rules module takes only sets and knows no filesystem, which is what
    keeps it readable and testable with no payload on disk; attributing a
    finding to a directory is this module's job, exactly like reading one.
    """
    return [
        Finding(kind=finding.kind, subject=finding.subject, detail=f"{where}: {finding.detail}")
        for finding in findings
    ]


def control_failures(*, repo_root: Path) -> list[str]:
    """Why a clean report on `repo_root` would not be trustworthy, if it would not."""
    failures: list[str] = []
    for payload in checked_payloads(repo_root=repo_root):
        failures.extend(incompleteness(payload=payload))
        failures.extend(_discovery_failures(payload=payload))
    fixture = fixture_path(repo_root=repo_root)
    if not fixture.is_file():
        failures.append(f"matcher control: the fixture is missing at {fixture}")
        return failures
    occurrences = graph_occurrences(text=fixture.read_text(encoding="utf-8"), venue=fixture.name)
    failures.extend(_matcher_failures(occurrences=occurrences))
    return failures


def _discovery_failures(*, payload: CheckedPayload) -> list[str]:
    """That the scan of THIS directory still returns the tokens that are in it."""
    occurrences = payload_occurrences(payload=payload)
    seen = {
        occurrence.name for occurrence in occurrences if occurrence.position == _ADAPTER_POSITION
    }
    missing = f"the graph scan found no `{_ADAPTER_POSITION}` token"
    return [
        f"discovery control: {payload.where}: {missing} for node {node}"
        for node, candidates in sorted(NODE_INPUT_CANDIDATES.items())
        if not any(name in seen for name in candidates)
    ]


def _matcher_failures(*, occurrences: list[Occurrence]) -> list[str]:
    """That the fixture's known non-rendered positions still reach a reported finding."""
    expected = non_rendered_occurrences(occurrences=occurrences)
    positions = {occurrence.position for occurrence in expected}
    failures = [
        f"matcher control: the fixture produced no non-rendered occurrence at `{position}`"
        for position in ("timeout", OUTSIDE_ATTRIBUTE_POSITION)
        if position not in positions
    ]
    reported = position_findings(occurrences=occurrences)
    if len(reported) != len(expected):
        counts = f"{len(expected)} non-rendered occurrence(s), {len(reported)} finding(s)"
        failures.append(f"matcher control: the fixture and its findings disagree — {counts}")
    return failures


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("seam_equivalence")
    repo_root = Path.cwd()
    findings = payload_findings(repo_root=repo_root)
    for finding in findings:
        log.error(finding.detail, kind=finding.kind, input_name=finding.subject)
    failures = control_failures(repo_root=repo_root)
    for failure in failures:
        log.error(failure, kind="control")
    return 1 if findings or failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
