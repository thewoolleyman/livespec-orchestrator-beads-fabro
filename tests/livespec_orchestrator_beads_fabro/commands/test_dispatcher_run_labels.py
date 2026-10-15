"""Tests for the run labels one dispatch stamps beside its correlation triple.

The claim under test is that a candidate entitlement reaches the factory's
own run record in a form the engine admits AND that two repositories render
byte-identically. Both halves matter: an unpassable value would be dropped
by the correlation section's own rule, erasing the entitlement the evidence
is about, and a value either repository's configuration contributed to could
not be joined across repositories at all.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import (
    AcpCandidateIdentity,
)
from livespec_orchestrator_beads_fabro.commands._acp_node_layers import AcpNodeResolution
from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    IDENTIFIER_MAX_BYTES,
    is_identifier_shaped,
)

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_run_labels.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_run_labels"

# An opaque team allowance of exactly the shape the contract calls opaque: a
# router path nothing constrains to the engine's label alphabet.
_OPAQUE_AVAILABILITY_KEY = "https://router.example.test/teams/alpha?plan=pooled"
_OPAQUE_CANDIDATE_KEY = "claude-code/anthropic/claude-opus-4-8 (pooled)"


def _labels_module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _resolution(*, candidates: dict[str, AcpCandidateIdentity]) -> AcpNodeResolution:
    """A resolution carrying nothing but the selected candidate identities."""
    return AcpNodeResolution(nodes={}, inputs={}, run_inputs=(), candidates=candidates)


def _pairs(*, argv_pairs: tuple[str, ...]) -> dict[str, str]:
    return dict(pair.split("=", 1) for pair in argv_pairs)


def test_an_identifier_shaped_entitlement_key_rides_verbatim() -> None:
    """A key the engine admits is not encoded; an operator reads it directly."""
    module = _labels_module()

    assert module.candidate_label_value(key="anthropic.com") == "anthropic.com"
    assert (
        module.candidate_label_value(key="claude-code/anthropic/opus")
        != "claude-code/anthropic/opus"
    )


def test_an_opaque_entitlement_key_renders_as_a_marked_deterministic_digest() -> None:
    """An unpassable key is digested rather than dropped, and marked as encoded."""
    module = _labels_module()

    value = module.candidate_label_value(key=_OPAQUE_AVAILABILITY_KEY)

    assert value.startswith(module.CANDIDATE_LABEL_DIGEST_PREFIX)
    assert is_identifier_shaped(value=value)
    assert len(value.encode("utf-8")) <= IDENTIFIER_MAX_BYTES
    # Re-derivation reproduces it: the encoding is a function of the key, so
    # a second dispatch of the same candidate joins to the first.
    assert module.candidate_label_value(key=_OPAQUE_AVAILABILITY_KEY) == value
    # And it DISCRIMINATES: a digest that collapsed distinct keys onto one
    # value would read as a join while naming the wrong entitlement.
    assert module.candidate_label_value(key=_OPAQUE_CANDIDATE_KEY) != value


def test_a_key_over_the_engines_byte_ceiling_is_encoded_within_it() -> None:
    """An alphanumeric key too long to pass is still carried, inside the limit."""
    module = _labels_module()
    oversize = "a" * (IDENTIFIER_MAX_BYTES + 1)

    value = module.candidate_label_value(key=oversize)

    assert value != oversize
    assert len(value.encode("utf-8")) <= IDENTIFIER_MAX_BYTES
    assert is_identifier_shaped(value=value)


def test_two_repositories_render_one_entitlement_pair_byte_identically(
    tmp_path: Path,
) -> None:
    """The candidate labels are a function of the pair alone, never of the repo.

    Asserted by rendering the SAME identity from two different repositories
    and comparing the candidate label values: the repository label is
    expected to differ, and the entitlement labels are expected not to.
    """
    module = _labels_module()
    identity = AcpCandidateIdentity(
        display_name="Claude Code Opus",
        candidate_key=_OPAQUE_CANDIDATE_KEY,
        availability_key=_OPAQUE_AVAILABILITY_KEY,
    )
    resolution = _resolution(candidates={"implement": identity})

    first = _pairs(
        argv_pairs=module.dispatch_run_label_pairs(
            repo=tmp_path / "livespec-orchestrator-beads-fabro",
            acp_nodes=resolution,
        )
    )
    second = _pairs(
        argv_pairs=module.dispatch_run_label_pairs(
            repo=tmp_path / "livespec-console-beads-fabro",
            acp_nodes=resolution,
        )
    )

    availability_key = f"{module.NODE_LABEL_PREFIX}.implement.{module.AVAILABILITY_LABEL_SUFFIX}"
    candidate_key = f"{module.NODE_LABEL_PREFIX}.implement.{module.CANDIDATE_LABEL_SUFFIX}"
    assert first[availability_key] == second[availability_key]
    assert first[candidate_key] == second[candidate_key]
    assert first[availability_key] != first[candidate_key]
    assert first[module.REPOSITORY_LABEL_KEY] == "livespec-orchestrator-beads-fabro"
    assert second[module.REPOSITORY_LABEL_KEY] == "livespec-console-beads-fabro"


def test_every_node_carries_both_of_its_entitlement_labels_in_node_order() -> None:
    """Two labels per node, nodes sorted, so one configuration renders one argv."""
    module = _labels_module()
    candidates = {
        "review": AcpCandidateIdentity(
            display_name="Codex GPT-5.5",
            candidate_key="codex/openai/gpt-5.5",
            availability_key="openai.com",
        ),
        "implement": AcpCandidateIdentity(
            display_name="Claude Code Opus",
            candidate_key="claude-code/anthropic/opus",
            availability_key="anthropic.com",
        ),
    }

    pairs = module.dispatch_run_label_pairs(
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        acp_nodes=_resolution(candidates=candidates),
    )

    implement_candidate = module.candidate_label_value(key="claude-code/anthropic/opus")
    review_candidate = module.candidate_label_value(key="codex/openai/gpt-5.5")
    assert pairs == (
        "livespec.repository=livespec-orchestrator-beads-fabro",
        "livespec.acp.implement.availability=anthropic.com",
        f"livespec.acp.implement.candidate={implement_candidate}",
        "livespec.acp.review.availability=openai.com",
        f"livespec.acp.review.candidate={review_candidate}",
    )


def test_a_resolution_less_dispatch_carries_the_repository_label_alone() -> None:
    """No adapters resolved means no candidate labels, not an invented one."""
    module = _labels_module()

    pairs = module.dispatch_run_label_pairs(
        repo=Path("/data/projects/livespec-orchestrator-beads-fabro"),
        acp_nodes=None,
    )

    assert pairs == ("livespec.repository=livespec-orchestrator-beads-fabro",)


def test_a_repository_name_the_engine_would_refuse_costs_its_label_only() -> None:
    """Section "Dispatch trace correlation"'s rule, unchanged, for this key."""
    module = _labels_module()
    identity = AcpCandidateIdentity(
        display_name="Claude Code Opus",
        candidate_key="claude-code/anthropic/opus",
        availability_key="anthropic.com",
    )

    pairs = module.dispatch_run_label_pairs(
        repo=Path("/data/projects/not a repository name"),
        acp_nodes=_resolution(candidates={"implement": identity}),
    )

    assert module.REPOSITORY_LABEL_KEY not in _pairs(argv_pairs=pairs)
    assert _pairs(argv_pairs=pairs)["livespec.acp.implement.availability"] == "anthropic.com"
