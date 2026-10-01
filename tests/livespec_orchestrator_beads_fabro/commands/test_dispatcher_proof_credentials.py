"""The `dispatcher.proof_credentials` declaration parse and its refusal ladder.

Covers `SPECIFICATION/contracts.md`'s proof-credential-projection clause
(ratified v114) at the unit tier: what a well-formed declaration parses to, and
the four faults the parse refuses before any run exists. The integration-tier
binding for Scenario 134 drives the same ladder through the real dispatch CLI.

The module under test is imported through `importlib` inside each test body
rather than at module top, so the first Red of a new-module slice fails on a
genuine assertion about the module's absence instead of dying at collection.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets as _commands_anchor

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials"
# Resolved off an existing sibling's own location, so the path is correct from
# any working directory the suite is invoked from.
_MODULE_PATH = Path(cast("str", _commands_anchor.__file__)).parent / (
    "_dispatcher_proof_credentials.py"
)


def _module() -> ModuleType:
    """The module under test, asserting it exists before importing it."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _block(*, declared: object) -> dict[str, Any]:
    """A `dispatcher` config block declaring `proof_credentials`."""
    return {"proof_credentials": declared}


def _read_only(
    *, name: str = "ACME_STATUS_READER", purpose: str = "observe build status"
) -> dict[str, str]:
    return {"name": name, "purpose": purpose, "capability": "read_only"}


def test_an_absent_declaration_parses_to_no_credentials() -> None:
    """A repository declaring nothing carries no proof credentials and no refusal."""
    module = _module()

    assert module.parse_proof_credentials(block={}) == ()


def test_a_well_formed_declaration_parses_to_its_three_fields() -> None:
    """Name, purpose and capability survive the parse verbatim, in declaration order."""
    module = _module()

    parsed = module.parse_proof_credentials(
        block=_block(
            declared=[
                _read_only(),
                _read_only(name="ACME_METRICS_READER", purpose="observe published metrics"),
            ]
        )
    )

    assert [credential.name for credential in parsed] == [
        "ACME_STATUS_READER",
        "ACME_METRICS_READER",
    ]
    assert parsed[0].purpose == "observe build status"
    assert parsed[1].capability == module.READ_ONLY_CAPABILITY


def test_a_declaration_that_is_not_a_list_is_refused_naming_the_key() -> None:
    """The key is a LIST of objects; a mapping or a string is not a shorter spelling."""
    module = _module()

    refusal = module.parse_proof_credentials(block=_block(declared=_read_only()))

    assert isinstance(refusal, str)
    assert "dispatcher.proof_credentials" in refusal


def test_an_entry_that_is_not_an_object_is_refused_naming_its_position() -> None:
    """A bare name in the list is not a shorthand for a declaration object.

    Refused at its INDEX, because an entry carrying no `name` field cannot be
    named any other way and an operator editing a multi-entry list needs to know
    which one to fix.
    """
    module = _module()

    refusal = module.parse_proof_credentials(block=_block(declared=["ACME_STATUS_READER"]))

    assert isinstance(refusal, str)
    assert "[0]" in refusal


def test_an_entry_missing_a_required_field_is_refused_naming_the_field() -> None:
    """All three fields are required: a declaration carrying names only is the point."""
    module = _module()

    refusal = module.parse_proof_credentials(
        block=_block(declared=[{"name": "ACME_STATUS_READER", "capability": "read_only"}])
    )

    assert isinstance(refusal, str)
    assert "purpose" in refusal


def test_an_over_scoped_capability_is_refused_naming_the_declaration_and_the_capability() -> None:
    """`read_only` is the whole enumeration today; anything else is over-scoped.

    The refusal names BOTH the declaration and the rejected capability, which is
    Scenario 134's own requirement — a message naming only the key would not tell
    an operator which of several declarations to fix, and one naming only the
    capability would not say where it was written.
    """
    module = _module()

    refusal = module.parse_proof_credentials(
        block=_block(
            declared=[
                {
                    "name": "ACME_DEPLOY_RUNNER",
                    "purpose": "run the deploy smoke suite on the host",
                    "capability": "host_execute",
                }
            ]
        )
    )

    assert isinstance(refusal, str)
    assert "ACME_DEPLOY_RUNNER" in refusal
    assert "host_execute" in refusal
    assert module.READ_ONLY_CAPABILITY in refusal


def test_a_credential_shaped_purpose_is_refused_naming_the_position_and_the_marker() -> None:
    """A declaration carries NAMES ONLY, so a pasted value in `purpose` is refused.

    The refusal names the position (`purpose`) and the marker that matched, never
    the surrounding text — the same discipline the adapter-configuration scan
    this reuses already keeps, because a refusal is journaled.
    """
    module = _module()

    refusal = module.parse_proof_credentials(
        block=_block(
            declared=[
                {
                    "name": "ACME_STATUS_READER",
                    "purpose": "observe build status with secret sk-acme-live",
                    "capability": "read_only",
                }
            ]
        )
    )

    assert isinstance(refusal, str)
    assert "ACME_STATUS_READER" in refusal
    assert "purpose" in refusal
    assert "secret" in refusal
    assert "sk-acme-live" not in refusal


def test_a_credential_shaped_name_is_refused_at_the_name_position() -> None:
    """The name arm of the same scan, so neither field is scanned alone."""
    module = _module()

    refusal = module.parse_proof_credentials(
        block=_block(declared=[_read_only(name="ACME_API_KEY")])
    )

    assert isinstance(refusal, str)
    assert "name" in refusal
    assert "api_key" in refusal
