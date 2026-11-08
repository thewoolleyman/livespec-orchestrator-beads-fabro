"""The incident-authority payload decoding lives in its own cohesive module."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro.commands import _incident_authority_lifecycle as lifecycle
from livespec_orchestrator_beads_fabro.commands._incident_rollback_conflict import RollbackConflict

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"


def test_payload_decoding_is_owned_by_its_own_module_and_left_the_lifecycle_module() -> None:
    module_path = Path(lifecycle.__file__).with_name("_incident_authority_decode.py")
    assert module_path.is_file()
    decode = importlib.import_module(f"{_PACKAGE}._incident_authority_decode")
    for name in (
        "INVALID_PAYLOAD",
        "invalid_payload",
        "decode_record",
        "decode_attributed_attempt",
    ):
        assert hasattr(decode, name)
    for name in ("_invalid", "_canonical", "_record", "_attempt", "INVALID_PAYLOAD"):
        assert not hasattr(lifecycle, name)

    refusal = decode.invalid_payload(flag="--x", detail="why")
    assert refusal == AuthorityRefusal(code="incident-action-invalid-payload", detail="--x: why")
    canonical = json.dumps(
        {"receipt": "r", "release_condition": "c"}, sort_keys=True, separators=(",", ":")
    )
    good = decode.decode_record(text=canonical, shape=RollbackConflict, flag="--c")
    assert good == RollbackConflict(receipt="r", release_condition="c")
    bad = decode.decode_record(text=canonical + " ", shape=RollbackConflict, flag="--c")
    assert isinstance(bad, AuthorityRefusal)
    assert bad.detail == "--c: not one canonical JSON object"


@pytest.mark.parametrize(
    ("action", "flag", "attribute"),
    [
        ("record-rollback-conflict", "--rollback-conflict-json", "rollback_conflict_json"),
        ("resolve-rollback-conflict", "--rollback-resolution-json", "rollback_resolution_json"),
    ],
)
def test_a_rollback_payload_that_is_not_its_canonical_record_is_refused_by_name(
    action: str, flag: str, attribute: str
) -> None:
    unused = cast("Any", None)
    refusal = lifecycle.run_lifecycle_action(
        args=argparse.Namespace(action=action, **{attribute: "{ }"}),
        client=unused,
        reading=unused,
        runner=unused,
    )
    assert refusal == AuthorityRefusal(
        code="incident-action-invalid-payload", detail=f"{flag}: not one canonical JSON object"
    )
