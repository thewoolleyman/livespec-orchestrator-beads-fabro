"""The coverage-before-Green instruction as the DISPATCHED implement prompt carries it.

bd-ib-z6fmp. The prompt-tier test beside this one
(`tests/prompts/test_implement_coverage_before_green.py`) reads the COMMITTED
prompt and owns the full phrase inventory. That is a different question from the
one here, and neither answers the other: a committed prompt proves what the
repository wrote, while a run is driven by the prompt the per-dispatch PAYLOAD
carries and by the inputs the Dispatcher supplies with it. An instruction can be
present in the source and absent from the dispatch — the payload is a fresh
`shutil.copytree` into a directory the materializer REMOVES first, and the graph
is rewritten on the way through — so this tier materializes the real committed
payload through `materialize_workflow_payload` and asserts the instruction
survives in the `prompts/implement.md` the run actually reads.

THE CHECK-SUITE BINDING IS THE SECOND HALF, and it is asserted through
production seams rather than a hand-written value. The instruction names the
check as `inputs.sandbox_check_suite`, which is repo-agnostic only if that token
really does resolve to the TARGET repository's own declaration. Three production
facts make it so, and each is measured here: the committed run config DECLARES
that input (an input a workflow does not declare is never sent, so an undeclared
one would arrive as the config's own fail-closed default); the resolved
integration contract projects it from the repository's declaration; and binding
the projected pairs into the dispatched prompt puts THAT repository's suite into
the instruction.

The declared fixture suite is deliberately a value no fleet default could
produce, and the binding is asserted in BOTH directions: the declared suite
appears, and the FLEET DEFAULT does not. A one-directional assertion would pass
for a binding that had silently fallen back to the convention, which is the exact
failure the repo-agnosticism requirement exists to prevent — and it would pass
identically whether the token had been bound from this repository's declaration
or from nothing at all.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_contract import (
    ResolvedIntegrationContract,
    resolve_integration_contract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
    declaration_from_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    SANDBOX_CHECK_SUITE_DEFAULT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    contract_prompt_variables,
    contract_run_inputs,
    contract_workflow_inputs,
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    materialize_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts

# The plugin root in source, anchored the way every other payload test anchors
# it: `.../commands/dispatcher.py` → parents[3] is the `.claude-plugin/` dir.
# A repo-root literal would keep resolving after the bundle moved.
_PLUGIN_ROOT = Path(dispatcher.__file__).resolve().parents[3]
_WORKFLOW_DIR = _PLUGIN_ROOT / ".fabro" / "workflows" / "implement-work-item"
_COMMITTED_WORKFLOW = _WORKFLOW_DIR / "workflow.toml"
_COMMITTED_PROMPT = _WORKFLOW_DIR / "prompts" / "implement.md"

_CHECK_SUITE_INPUT = "sandbox_check_suite"
# The template opener is ASSEMBLED rather than written literally, the fleet
# convention of livespec-dev-tooling-9yb4: a literal pair in this file's text
# poisons goal and ledger rendering wherever that text is later quoted.
_OPEN = "{" + "{"
_CLOSE = "}" + "}"
_CHECK_SUITE_TOKEN = f"{_OPEN} inputs.{_CHECK_SUITE_INPUT} {_CLOSE}"

_HEADING = "## Coverage before Green — run the per-file coverage check FIRST"
# Needles sit WITHIN one physical line of the hard-wrapped prose: one
# straddling a line break fails while the prose says exactly the thing.
_REQUIRED_PHRASES = (
    "Before you attempt ANY Green commit or amend",
    "per-file coverage check over the FULL test suite",
    "Measure coverage over the WHOLE suite.",
    "Do NOT narrow it to the files",
    "this change touched: a logic change drops coverage in files it never",
    "This relaxes NOTHING.",
)

# A declared suite no fleet default can produce, so the binding direction is
# decidable from the bound text alone.
_DECLARED_SUITE = "./fixture-gates --every-target"


def _workflow_layer_adapters() -> dict[str, str]:
    """Each ACP node's adapter as the WORKFLOW-DEFAULTS layer declares it.

    DERIVED from the committed `[run.inputs]` table through the same reader the
    dispatch path uses, never a hand-written node list: the materializer refuses
    a graph whose ACP node rides an input no adapter was resolved for, so a list
    that fell behind a newly added node would fail loudly — but a list that
    happened to cover every node would also freeze this test's idea of the graph
    in place. This reproduces the layer a repository overriding nothing gets.
    """
    declared = workflow_declared_inputs(
        committed_text=_COMMITTED_WORKFLOW.read_text(encoding="utf-8")
    )
    return {name: value for name, value in declared.items() if name.endswith("_adapter")}


def _materialized(*, payload_dir: Path) -> WorkflowPayload:
    """The real committed payload, materialized the way a dispatch materializes it."""
    adapters = _workflow_layer_adapters()
    assert adapters, "no `*_adapter` input found in the committed run config"
    payload = materialize_workflow_payload(
        committed=_COMMITTED_WORKFLOW,
        payload_dir=payload_dir,
        timeouts=default_node_timeouts(),
        adapters=adapters,
    )
    assert isinstance(payload, WorkflowPayload), payload
    return payload


def _dispatched_prompt(*, payload: WorkflowPayload) -> Path:
    return payload.graph.parent / "prompts" / "implement.md"


def _section(*, text: str) -> str:
    """The one coverage-before-Green section of `text`, up to the next H2."""
    assert text.count(_HEADING) == 1, (
        f"the dispatched prompt carries {text.count(_HEADING)} sections headed "
        f"{_HEADING!r}; expected exactly one"
    )
    start = text.index(_HEADING)
    rest = text.index("\n## ", start + len(_HEADING))
    return text[start:rest]


def _resolved_contract(*, repo: Path) -> ResolvedIntegrationContract:
    """One repository's resolved contract, read off its committed declaration."""
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({PLUGIN_BLOCK: {"dispatcher": {"janitor": {"check_suite": _DECLARED_SUITE}}}}),
        encoding="utf-8",
    )
    declaration = declaration_from_config_text(
        config_text=(repo / ".livespec.jsonc").read_text(encoding="utf-8")
    )
    return resolve_integration_contract(declaration=declaration)


def test_the_materialized_payload_is_a_copy_the_run_reads_its_prompt_from(
    tmp_path: Path,
) -> None:
    """Control: the dispatched prompt is the payload's own file, not the committed one."""
    payload = _materialized(payload_dir=tmp_path / "payload")
    dispatched = _dispatched_prompt(payload=payload)

    assert dispatched.is_file()
    assert dispatched != _COMMITTED_PROMPT
    assert tmp_path in dispatched.parents
    # The graph the run receives is the one that names this prompt, so a prompt
    # the graph stopped referencing cannot satisfy the assertions below.
    assert 'prompt="@prompts/implement.md"' in payload.graph.read_text(encoding="utf-8")


def test_the_dispatched_implement_prompt_carries_the_coverage_instruction(
    tmp_path: Path,
) -> None:
    """The instruction survives materialization into the prompt the run reads."""
    payload = _materialized(payload_dir=tmp_path / "payload")
    section = _section(text=_dispatched_prompt(payload=payload).read_text(encoding="utf-8"))

    for phrase in _REQUIRED_PHRASES:
        assert phrase in section, f"the dispatched coverage section omits {phrase!r}"
    assert _CHECK_SUITE_TOKEN in section, (
        "the dispatched coverage section names no check-suite input, so it cannot "
        "resolve to the target repository's own declaration"
    )


def test_the_committed_run_config_declares_the_check_suite_input(tmp_path: Path) -> None:
    """Control: the input the instruction names is one this workflow can receive.

    fabro rejects an `--input` the run config does not declare, and the
    production renderer INTERSECTS what it sends with what the workflow declares
    — so an undeclared input is silently never sent and the prompt would render
    the config's own fail-closed default instead of this repository's suite.
    """
    declared = contract_workflow_inputs(
        committed_text=_COMMITTED_WORKFLOW.read_text(encoding="utf-8")
    )
    resolved = _resolved_contract(repo=tmp_path)

    assert _CHECK_SUITE_INPUT in declared
    assert f"{_CHECK_SUITE_INPUT}={_DECLARED_SUITE}" in contract_run_inputs(
        resolved=resolved, declared=declared
    )


def test_the_dispatched_instruction_binds_the_repository_declared_check_suite(
    tmp_path: Path,
) -> None:
    """Binding the projected inputs puts THIS repository's suite in the instruction."""
    payload = _materialized(payload_dir=tmp_path / "payload")
    resolved = _resolved_contract(repo=tmp_path)
    variables = contract_prompt_variables(resolved=resolved)
    bound = _dispatched_prompt(payload=payload).read_text(encoding="utf-8")
    for name, value in variables.items():
        bound = bound.replace(f"{_OPEN} inputs.{name} {_CLOSE}", value)
    section = _section(text=bound)

    assert _DECLARED_SUITE in section
    assert _CHECK_SUITE_TOKEN not in section
    # BOTH directions: a binding that fell back to the fleet convention — or
    # that never happened — reads identically on the assertion above alone.
    assert shlex.join(SANDBOX_CHECK_SUITE_DEFAULT) not in section
    for phrase in _REQUIRED_PHRASES:
        assert phrase in section, f"the bound coverage section omits {phrase!r}"
