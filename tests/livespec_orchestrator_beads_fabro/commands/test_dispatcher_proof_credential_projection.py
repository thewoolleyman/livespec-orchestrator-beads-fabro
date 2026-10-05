"""The overlay env lines projecting a repository's declared proof credentials.

The projection half of `SPECIFICATION/contracts.md`'s proof-credential-projection
clause (ratified v114), split out of `_dispatcher_proof_credentials` by cohesion:
that module answers what a repository DECLARED and what refuses it, while this
one answers how an admitted declaration reaches the sandbox. The split is what
keeps the declaration module inside its file-size ceiling as the minted
provisioning path lands beside the copied one.

The module under test is imported through `importlib` inside each test body
rather than at module top, so the first Red of this extraction fails on a
genuine assertion about the module's absence instead of dying at collection.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets as _commands_anchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_projection"
_SOURCE_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials"
# Resolved off an existing sibling's own location, so the path is correct from
# any working directory the suite is invoked from.
_COMMANDS_DIR = Path(cast("str", _commands_anchor.__file__)).parent
_MODULE_PATH = _COMMANDS_DIR / "_dispatcher_proof_credential_projection.py"

_NAME = "ACME_STATUS_READER"
_VALUE = "acme-observer-value"

# One declaration whose provider exposes a management interface, plus the value
# this run minted from it. The host value below is deliberately DIFFERENT, so a
# projection reading the wrong source is visible rather than merely equal.
_MANAGED_NAME = "ACME_MINTED_READER"
_MINTED_VALUE = "acme-minted-for-this-run"
_HOST_VALUE = "acme-host-held-value"
_MANAGED = {
    _MANAGED_NAME: {
        "mint": ["/usr/local/bin/acme-admin", "proof-key", "mint"],
        "revoke": ["/usr/local/bin/acme-admin", "proof-key", "revoke"],
    }
}


def _module() -> ModuleType:
    """The module under test, asserting it exists before importing it."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def _read_only(*, name: str = _NAME) -> dict[str, str]:
    return {
        "name": name,
        "purpose": "observe the published build status of the deliverable",
        "capability": "read_only",
    }


def _block(*, declared: object, managed: object | None = None) -> dict[str, Any]:
    """A `dispatcher` config block declaring `proof_credentials`."""
    block: dict[str, Any] = {"proof_credentials": declared}
    if managed is not None:
        block["proof_credential_management"] = managed
    return block


def _repo(
    *,
    tmp_path: Path,
    declared: list[dict[str, str]] | None,
    managed: object | None = None,
) -> Path:
    """A repository whose committed configuration declares `proof_credentials`."""
    dispatcher: dict[str, object] = {} if declared is None else {"proof_credentials": declared}
    if managed is not None:
        dispatcher["proof_credential_management"] = managed
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({PLUGIN_BLOCK: {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )
    return tmp_path


def test_a_present_declared_value_renders_one_overlay_line() -> None:
    """The positive control: the declared name reaches the sandbox env table."""
    module = _module()

    assert (
        module.proof_credentials_env_lines(
            block=_block(declared=[_read_only()]), environ={_NAME: _VALUE}
        )
        == f'{_NAME} = "{_VALUE}"\n'
    )


def test_an_absent_value_renders_nothing() -> None:
    """Fail-closed: a declared name the environment does not carry is skipped.

    The gate runs before this on every dispatch path, so a dispatch never
    reaches here with an absent value. It is asserted anyway because the
    alternative — projecting the key with an empty value — hands the sandbox a
    credential-shaped nothing and the proof stage fails somewhere else entirely.
    """
    module = _module()

    assert (
        module.proof_credentials_env_lines(block=_block(declared=[_read_only()]), environ={}) == ""
    )


def test_a_refused_declaration_renders_nothing() -> None:
    """A declaration the parse refuses projects no line at all.

    The fail-open shape — render whatever parses — would project a credential
    nobody admitted, which is the expensive direction to be wrong in.
    """
    module = _module()

    assert (
        module.proof_credentials_env_lines(
            block=_block(declared=[_read_only(name="BEADS_DOLT_PASSWORD")]),
            environ={"BEADS_DOLT_PASSWORD": "store-password"},
        )
        == ""
    )


def test_a_name_the_dispatcher_already_projects_renders_no_second_line() -> None:
    """`GITHUB_TOKEN` is minted and projected by the overlay's own credential table.

    A second TOML line under the same key makes the WHOLE overlay unparseable,
    so one repository's declaration would become a dispatch-wide failure.
    """
    module = _module()

    assert (
        module.proof_credentials_env_lines(
            block=_block(declared=[_read_only(name="GITHUB_TOKEN")]), environ={}
        )
        == ""
    )


def test_a_repository_declaring_nothing_renders_nothing(tmp_path: Path) -> None:
    """The entry point the overlay materializer calls, over an undeclared repository."""
    module = _module()

    assert (
        module.proof_credentials_overlay_env(
            repo=_repo(tmp_path=tmp_path, declared=None), environ={_NAME: _VALUE}
        )
        == ""
    )


def test_the_overlay_entry_point_resolves_the_repositorys_own_declaration(
    tmp_path: Path,
) -> None:
    """The repository-to-block resolution lives here, beside the parse that reads it."""
    module = _module()

    assert (
        module.proof_credentials_overlay_env(
            repo=_repo(tmp_path=tmp_path, declared=[_read_only()]), environ={_NAME: _VALUE}
        )
        == f'{_NAME} = "{_VALUE}"\n'
    )


def test_a_managed_declaration_projects_the_minted_value_not_the_host_value() -> None:
    """A provider-minted credential renders what THIS RUN minted.

    The host value is present under the same spelling and must NOT be what
    reaches the sandbox: a projection that preferred the environment would be
    byte-identical to the pre-minting build on every repository whose host
    happens to hold a copy, which is the case an operator is most likely to have.
    """
    module = _module()

    assert (
        module.proof_credentials_env_lines(
            block=_block(declared=[_read_only(name=_MANAGED_NAME)], managed=_MANAGED),
            environ={_MANAGED_NAME: _HOST_VALUE},
            minted={_MANAGED_NAME: _MINTED_VALUE},
        )
        == f'{_MANAGED_NAME} = "{_MINTED_VALUE}"\n'
    )


def test_an_unmanaged_sibling_still_projects_the_wrapper_supplied_value() -> None:
    """The copied control, in the SAME declaration as the minted one.

    Asserted as one rendering of two declarations rather than two renderings of
    one, because the sources are chosen PER declaration and a build that picked
    one source for the whole repository would satisfy either case alone.
    """
    module = _module()

    assert (
        module.proof_credentials_env_lines(
            block=_block(declared=[_read_only(name=_MANAGED_NAME), _read_only()], managed=_MANAGED),
            environ={_MANAGED_NAME: _HOST_VALUE, _NAME: _VALUE},
            minted={_MANAGED_NAME: _MINTED_VALUE},
        )
        == f'{_MANAGED_NAME} = "{_MINTED_VALUE}"\n{_NAME} = "{_VALUE}"\n'
    )


def test_a_managed_declaration_with_nothing_minted_projects_nothing() -> None:
    """Fail-closed on the minted source too, and NOT onto the host value.

    A mint that did not happen must leave the name absent rather than silently
    falling back to the host's credential — a fallback would turn a provider
    outage into an undetectable downgrade from a per-run credential to a
    long-lived one.
    """
    module = _module()

    assert (
        module.proof_credentials_env_lines(
            block=_block(declared=[_read_only(name=_MANAGED_NAME)], managed=_MANAGED),
            environ={_MANAGED_NAME: _HOST_VALUE},
        )
        == ""
    )


def test_a_dangling_management_declaration_projects_nothing() -> None:
    """The projection is fail-closed on a management fault, like any other refusal."""
    module = _module()

    assert (
        module.proof_credentials_env_lines(
            block=_block(declared=[_read_only()], managed=_MANAGED),
            environ={_NAME: _VALUE},
        )
        == ""
    )


def test_the_overlay_entry_point_carries_the_minted_values_through(tmp_path: Path) -> None:
    """The materializer's entry point forwards what the lease minted.

    Threaded rather than re-derived: the mint happened once, earlier on this
    dispatch, and a second mint here would hand the sandbox a credential the
    revoke leg has no scope for.
    """
    module = _module()

    assert (
        module.proof_credentials_overlay_env(
            repo=_repo(
                tmp_path=tmp_path, declared=[_read_only(name=_MANAGED_NAME)], managed=_MANAGED
            ),
            environ={},
            minted={_MANAGED_NAME: _MINTED_VALUE},
        )
        == f'{_MANAGED_NAME} = "{_MINTED_VALUE}"\n'
    )


def test_the_projection_names_are_gone_from_the_declaration_module() -> None:
    """The extraction MOVED the projection; it did not copy it.

    Asserted on the public surface rather than on the source bytes, because a
    re-export shim would leave the names importable from both modules and that
    is exactly the shape a size-split must not take.
    """
    module = _module()
    source = importlib.import_module(_SOURCE_MODULE_NAME)

    assert {"proof_credentials_env_lines", "proof_credentials_overlay_env"} <= set(module.__all__)
    assert not {"proof_credentials_env_lines", "proof_credentials_overlay_env"} & set(
        source.__all__
    )
    assert not hasattr(source, "proof_credentials_env_lines")
