"""The `dispatcher.proof_credential_management` declaration and its refusal ladder.

Covers the WHERE-THE-PROVIDER-OFFERS-A-MANAGEMENT-INTERFACE half of
`SPECIFICATION/contracts.md`'s proof-credential-projection clause (ratified
v114) at the unit tier: what a well-formed per-credential argv pair parses to,
the faults the parse refuses before any run exists, and the environment the two
commands are addressed through. The integration-tier binding for Scenario 134
drives the same declaration through the real dispatch CLI against a hermetic
provider double.

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

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_management"
# Resolved off an existing sibling's own location, so the path is correct from
# any working directory the suite is invoked from.
_MODULE_PATH = Path(cast("str", _commands_anchor.__file__)).parent / (
    "_dispatcher_proof_credential_management.py"
)

# A provider admin command spelled WITHOUT any member of the credential-naming
# marker vocabulary, so the positive cases cannot be passing because a marker
# scan happens to be absent from this module's path.
_MINT_ARGV = ["/usr/local/bin/acme-admin", "proof-key", "mint"]
_REVOKE_ARGV = ["/usr/local/bin/acme-admin", "proof-key", "revoke"]
_NAME = "ACME_STATUS_READER"


def _module() -> ModuleType:
    """The module under test, asserting it exists before importing it."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _block(*, declared: object) -> dict[str, Any]:
    """A `dispatcher` config block declaring `proof_credential_management`."""
    return {"proof_credential_management": declared}


def _well_formed(*, name: str = _NAME) -> dict[str, Any]:
    return {name: {"mint": list(_MINT_ARGV), "revoke": list(_REVOKE_ARGV)}}


def test_an_absent_key_parses_to_no_management_interface() -> None:
    """Declaring none is the normal posture, so absence is not a refusal.

    Every repository in this fleet is in that posture today, which is why the
    empty answer has to be the one the parse returns rather than a fault.
    """
    module = _module()

    assert module.parse_provider_management_interfaces(block={}) == {}


def test_a_well_formed_pair_parses_to_the_two_argvs_under_its_name() -> None:
    """The positive control: one declared name carrying a mint and a revoke argv."""
    module = _module()

    parsed = module.parse_provider_management_interfaces(block=_block(declared=_well_formed()))

    assert set(parsed) == {_NAME}
    interface = parsed[_NAME]
    assert interface.name == _NAME
    assert interface.mint_argv == tuple(_MINT_ARGV)
    assert interface.revoke_argv == tuple(_REVOKE_ARGV)


def test_a_non_object_declaration_is_refused_naming_the_committed_key() -> None:
    """The key is a mapping from one credential name to its argv pair, not a list."""
    module = _module()

    refusal = module.parse_provider_management_interfaces(
        block=_block(declared=[{"mint": _MINT_ARGV, "revoke": _REVOKE_ARGV}])
    )

    assert isinstance(refusal, str)
    assert "dispatcher.proof_credential_management" in refusal
    assert "list" in refusal


def test_a_non_object_entry_is_refused_naming_the_credential() -> None:
    """One entry must be the argv pair, so a bare string cannot stand in for it."""
    module = _module()

    refusal = module.parse_provider_management_interfaces(
        block=_block(declared={_NAME: "/usr/local/bin/acme-admin"})
    )

    assert isinstance(refusal, str)
    assert _NAME in refusal
    assert "str" in refusal


def test_a_missing_mint_argv_is_refused_naming_the_operation() -> None:
    """Both halves are required: a pair that cannot revoke is not a lifecycle."""
    module = _module()

    refusal = module.parse_provider_management_interfaces(
        block=_block(declared={_NAME: {"revoke": list(_REVOKE_ARGV)}})
    )

    assert isinstance(refusal, str)
    assert _NAME in refusal
    assert "mint" in refusal


def test_a_missing_revoke_argv_is_refused_naming_the_operation() -> None:
    """The mirror of the case above, so one operation passing is not the whole pair.

    The REVOKE half is the one a build could plausibly omit and still look
    correct for a whole run — the credential is minted, the sandbox works, and
    the only symptom is a credential that outlives the run that needed it.
    """
    module = _module()

    refusal = module.parse_provider_management_interfaces(
        block=_block(declared={_NAME: {"mint": list(_MINT_ARGV)}})
    )

    assert isinstance(refusal, str)
    assert _NAME in refusal
    assert "revoke" in refusal


def test_an_empty_argv_is_refused() -> None:
    """An empty list is a declared-but-unusable command, not an undeclared one."""
    module = _module()

    refusal = module.parse_provider_management_interfaces(
        block=_block(declared={_NAME: {"mint": [], "revoke": list(_REVOKE_ARGV)}})
    )

    assert isinstance(refusal, str)
    assert _NAME in refusal
    assert "mint" in refusal


def test_an_argv_carrying_a_non_string_token_is_refused() -> None:
    """Every token reaches a subprocess argv, so a non-string is unusable there."""
    module = _module()

    refusal = module.parse_provider_management_interfaces(
        block=_block(
            declared={
                _NAME: {"mint": ["/usr/local/bin/acme-admin", 7], "revoke": list(_REVOKE_ARGV)}
            }
        )
    )

    assert isinstance(refusal, str)
    assert _NAME in refusal
    assert "mint" in refusal


def test_an_argv_carrying_a_blank_token_is_refused() -> None:
    """A whitespace token is an empty argument, which no provider CLI accepts."""
    module = _module()

    refusal = module.parse_provider_management_interfaces(
        block=_block(declared={_NAME: {"mint": list(_MINT_ARGV), "revoke": ["   "]}})
    )

    assert isinstance(refusal, str)
    assert _NAME in refusal
    assert "revoke" in refusal


def test_a_management_entry_naming_no_declared_credential_is_refused() -> None:
    """A dangling entry is the silent-wrong-answer case this grade exists for.

    An operator who declares a management interface believes minting is
    happening. If the name matches no `dispatcher.proof_credentials`
    declaration, nothing is minted and nothing is projected — and the dispatch
    is otherwise perfectly healthy, so the belief is never contradicted.
    """
    module = _module()

    refusal = module.undeclared_management_refusal(
        management=module.parse_provider_management_interfaces(
            block=_block(declared=_well_formed())
        ),
        declared=("ACME_OTHER_READER",),
    )

    assert isinstance(refusal, str)
    assert _NAME in refusal
    assert "dispatcher.proof_credentials" in refusal


def test_a_management_entry_naming_a_declared_credential_passes_that_grade() -> None:
    """The control for the grade above: the ordinary pairing is admitted."""
    module = _module()

    assert (
        module.undeclared_management_refusal(
            management=module.parse_provider_management_interfaces(
                block=_block(declared=_well_formed())
            ),
            declared=(_NAME,),
        )
        is None
    )


def test_the_two_commands_are_addressed_through_the_environment_not_through_argv() -> None:
    """The name, the capability and the per-run scope, as environment keys.

    Asserted as the WHOLE mapping rather than by containment: a surplus key
    would be a fact about the run reaching a provider command that did not ask
    for it, and the per-run scope is what makes revoke addressable without any
    state threaded from mint.
    """
    module = _module()

    assert module.management_environment(name=_NAME, capability="read_only", scope="disp-134") == {
        module.PROOF_CREDENTIAL_NAME_ENV: _NAME,
        module.PROOF_CREDENTIAL_CAPABILITY_ENV: "read_only",
        module.PROOF_CREDENTIAL_SCOPE_ENV: "disp-134",
    }


def test_the_module_declares_its_parse_and_its_addressing() -> None:
    """The public surface the lease and the gate reach, declared in `__all__`."""
    module = _module()

    assert {
        "management_environment",
        "parse_provider_management_interfaces",
        "undeclared_management_refusal",
    } <= set(module.__all__)
