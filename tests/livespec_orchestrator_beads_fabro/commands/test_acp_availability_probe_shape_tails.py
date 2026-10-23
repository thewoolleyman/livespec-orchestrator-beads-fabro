"""The total-function TAILS of the confirmation turn's shape.

Beside `test_acp_availability_probe_shape.py`, which binds the clause. These
are the arms a conforming caller never reaches, because
`availability_probe_refusal` refuses the candidate before any run exists -- and
they are covered anyway, because an unreachable arm is where a later edit puts
a label naming an entitlement nobody declared.

They are a SEPARATE module rather than cases in that one because they were
authored at that Red's Green, and a Red's test bytes are fixed across its
Red-to-Green pair.
"""

from __future__ import annotations

import importlib
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"


def _probe() -> Any:
    return importlib.import_module(f"{_PACKAGE}._acp_availability_probe")


def test_an_identity_less_candidate_is_labelled_with_no_entitlement_at_all() -> None:
    """The marker alone: a label naming an undeclared entitlement reads host-wide."""
    probe = _probe()
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")

    labels = probe.availability_probe_labels(
        candidate=schema.AcpCandidate(adapter=adapters.AcpAdapter(command="legacy-acp"))
    )

    assert labels == (
        f"{probe.AVAILABILITY_PROBE_LABEL_KEY}={probe.AVAILABILITY_PROBE_LABEL_VALUE}",
    )


def test_an_adapter_carrying_a_quote_is_escaped_into_the_attribute_that_holds_it() -> None:
    """A rendered env value may carry quotes; the DOT attribute must survive them."""
    probe = _probe()
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")

    graph = probe.availability_probe_graph(
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(
                command="codex-acp", env={"CODEX_CONFIG": '{"model":"gpt-5.5"}'}
            ),
            identity=schema.AcpCandidateIdentity(
                display_name="GPT 5.5",
                candidate_key="gpt-5.5",
                availability_key="chatgpt",
            ),
        ),
        timeout_seconds=120,
    )

    assert '\\"model\\":\\"gpt-5.5\\"' in graph
    # The prompt is a constant carrying nothing that needs escaping, so the
    # attribute holds it verbatim -- which is what "one fixed minimal prompt"
    # means at the byte level.
    assert '"' not in probe.AVAILABILITY_PROBE_PROMPT
    assert "\\" not in probe.AVAILABILITY_PROBE_PROMPT
