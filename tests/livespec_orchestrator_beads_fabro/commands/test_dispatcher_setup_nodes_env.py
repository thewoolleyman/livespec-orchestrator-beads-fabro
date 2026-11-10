"""A setup step's payload rides the run's environment table, not the node (bd-ib-dpsiwz).

The engine's compact fidelity re-sends every completed command stage's script to
every later agent request and sends no environment, so a step that carries a helper
program keeps the bytes in an environment entry and only a short command in its
script. A command node has no environment of its own that the engine is known to
read, so the entries are hoisted into the run's environment table under names unique
to the step, and the step's script is rewritten to read them.
"""

from __future__ import annotations

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    MAX_PAYLOAD_VALUE_BYTES,
    PrepareStep,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_setup_nodes import (
    append_env_lines,
    hoist_step_env,
    splice_setup_nodes,
)

_GRAPH = """digraph G {
    start [shape=Mdiamond]
    exit [shape=Msquare]
    start -> exit
}
"""
_OVERLAY = """[workflow]
graph = "workflow.fabro"

[run.environment]
id = "sandbox"

[environments.sandbox]

[environments.sandbox.env]
CLAUDE_CODE_OAUTH_TOKEN = "t"
"""


def test_each_steps_variables_get_names_unique_to_the_step() -> None:
    hoisted = hoist_step_env(
        steps=[
            PrepareStep(script='printf %s "$PAYLOAD" > /a', env={"PAYLOAD": "first"}),
            PrepareStep(script='printf %s "$PAYLOAD" > /b', env={"PAYLOAD": "second"}),
            PrepareStep(script="echo bare"),
        ]
    )
    assert hoisted.env == {
        "LIVESPEC_SETUP_1__PAYLOAD": "first",
        "LIVESPEC_SETUP_2__PAYLOAD": "second",
    }
    assert [step.script for step in hoisted.steps] == [
        'printf %s "$LIVESPEC_SETUP_1__PAYLOAD" > /a',
        'printf %s "$LIVESPEC_SETUP_2__PAYLOAD" > /b',
        "echo bare",
    ]
    assert all(not step.env for step in hoisted.steps)


def test_a_name_is_rewritten_whole_and_never_at_the_front_of_a_longer_one() -> None:
    script = (
        ': "${PAYLOAD:?missing}"; printf %s "$PAYLOAD_0" > /a; '
        'printf %s "$PAYLOAD" >> /a; x=$MY_PAYLOAD'
    )
    hoisted = hoist_step_env(
        steps=[PrepareStep(script=script, env={"PAYLOAD": "p", "PAYLOAD_0": "zero"})]
    )
    assert hoisted.steps[0].script == (
        ': "${LIVESPEC_SETUP_1__PAYLOAD:?missing}"; printf %s "$LIVESPEC_SETUP_1__PAYLOAD_0" > /a; '
        'printf %s "$LIVESPEC_SETUP_1__PAYLOAD" >> /a; x=$MY_PAYLOAD'
    )


def test_steps_with_no_env_hoist_to_themselves_and_an_empty_mapping() -> None:
    steps = (PrepareStep(script="echo one"), PrepareStep(script="echo two"))
    hoisted = hoist_step_env(steps=steps)
    assert hoisted.steps == steps
    assert hoisted.env == {}


def test_the_hoisted_entries_land_in_the_overlays_environment_table() -> None:
    appended = append_env_lines(
        overlay_text=_OVERLAY, env={"LIVESPEC_SETUP_1__PAYLOAD": 'a "quoted" {{ value }}\nline'}
    )
    assert appended is not None
    table = tomli.loads(appended)["environments"]["sandbox"]["env"]
    assert table["LIVESPEC_SETUP_1__PAYLOAD"] == 'a "quoted" {{ value }}\nline'
    assert table["CLAUDE_CODE_OAUTH_TOKEN"] == "t"


def test_a_missing_final_newline_is_supplied_before_the_entries() -> None:
    appended = append_env_lines(
        overlay_text=_OVERLAY.rstrip("\n"), env={"LIVESPEC_SETUP_1__X": "x"}
    )
    assert appended is not None
    assert tomli.loads(appended)["environments"]["sandbox"]["env"]["LIVESPEC_SETUP_1__X"] == "x"


def test_nothing_to_append_leaves_the_overlay_untouched_even_without_a_table() -> None:
    assert append_env_lines(overlay_text="[workflow]\n", env={}) == "[workflow]\n"


@pytest.mark.parametrize(
    "overlay",
    [
        '[workflow]\ngraph = "workflow.fabro"\n',
        _OVERLAY + '\n[run.checkpoint]\ncommit_timeout = "5m"\n',
    ],
    ids=["no-environment-table", "environment-table-not-last"],
)
def test_an_overlay_the_entries_cannot_be_read_back_from_is_refused(overlay: str) -> None:
    assert append_env_lines(overlay_text=overlay, env={"LIVESPEC_SETUP_1__X": "x"}) is None


def test_a_value_the_renderer_refuses_is_refused_not_truncated() -> None:
    oversized = "x" * (MAX_PAYLOAD_VALUE_BYTES + 1)
    assert append_env_lines(overlay_text=_OVERLAY, env={"LIVESPEC_SETUP_1__X": oversized}) is None


def test_an_environment_table_header_the_parse_reads_differently_is_refused() -> None:
    spaced = _OVERLAY.replace("[environments.sandbox.env]", '[environments."sandbox".env]')
    assert append_env_lines(overlay_text=spaced, env={"LIVESPEC_SETUP_1__X": "x"}) is None


def test_a_table_that_does_not_parse_after_the_append_is_refused() -> None:
    broken = _OVERLAY + 'LIVESPEC_SETUP_1__X = "already declared"\n'
    assert append_env_lines(overlay_text=broken, env={"LIVESPEC_SETUP_1__X": "x"}) is None


def test_a_node_cannot_carry_an_env_so_a_step_still_holding_one_is_refused() -> None:
    step = PrepareStep(script="echo one", env={"PAYLOAD": "p"})
    assert splice_setup_nodes(graph_text=_GRAPH, steps=[step]) is None
    hoisted = hoist_step_env(steps=[step])
    assert splice_setup_nodes(graph_text=_GRAPH, steps=hoisted.steps) is not None
