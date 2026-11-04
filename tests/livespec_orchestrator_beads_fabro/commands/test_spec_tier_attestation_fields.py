"""The attestation's comparison block tolerates a line that is not a field.

A reader that took every line of the leading block as a `key: value` pair would
refuse an attestation over one stray line a person added by hand, and the item
would silently lose a release a human had deliberately granted. The stray line is
ignored and the fields around it are still read.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._spec_tier_attestation import (
    SPEC_TIER_ATTESTATION_MARKER,
    recorded_attestation,
)


def test_a_line_without_a_separator_inside_the_block_is_ignored() -> None:
    body = "\n".join(
        [
            SPEC_TIER_ATTESTATION_MARKER,
            "",
            "actor: human:chad",
            "a stray line a person added",
            "heading: ## Clause A",
            "spec-file: contracts.md",
            "spec-version: 7",
            "clause-digest: sha256:aa",
            "input-digest: bb",
        ]
    )

    recorded = recorded_attestation(comments=(body,))

    assert recorded is not None
    assert recorded.actor == "human:chad"
    assert recorded.heading == "## Clause A"
    assert recorded.input_digest == "bb"
