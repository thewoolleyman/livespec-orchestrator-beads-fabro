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
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets as _commands_anchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
)

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


@dataclass(kw_only=True)
class _Journal:
    """A recording stand-in for `JournalFile`, offering only the `append` seam."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _governed_repo(*, tmp_path: Path, declared: object | None) -> Path:
    """A repository whose committed configuration declares `proof_credentials`."""
    dispatcher: dict[str, object] = {} if declared is None else {"proof_credentials": declared}
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({PLUGIN_BLOCK: {"dispatcher": dispatcher}}), encoding="utf-8"
    )
    return tmp_path


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


def test_the_module_declares_the_gate_and_the_parse() -> None:
    """The public surface the dispatch path reaches, declared in `__all__`.

    The PROJECTION is deliberately absent from this set: it moved to
    `_dispatcher_proof_credential_projection`, and its own module asserts that
    neither name survives here as a re-export.
    """
    module = _module()

    assert {"parse_proof_credentials", "proof_credentials_refusal"} <= set(module.__all__)


def test_a_withheld_store_credential_is_refused_as_withheld_not_as_credential_shaped() -> None:
    """The store credential is refused BY NAME, and the discrimination is the point.

    `BEADS_DOLT_PASSWORD` case-folds to text the credential-shaped marker scan
    also matches, so a ladder that scanned for a pasted value FIRST would report
    the generic fault and the withheld refusal would be unreachable for the
    exact declaration it exists to refuse. This asserts both halves: the withheld
    refusal fires, and the credential-shaped refusal does NOT.
    """
    module = _module()

    refusal = module.parse_proof_credentials(
        block=_block(
            declared=[
                _read_only(name="BEADS_DOLT_PASSWORD", purpose="observe the ledger from the proof")
            ]
        )
    )

    assert isinstance(refusal, str)
    assert "BEADS_DOLT_PASSWORD" in refusal
    assert "withheld" in refusal
    assert "reads as a literal credential" not in refusal


def test_the_durable_app_private_key_is_withheld_too() -> None:
    """The second withheld class, so one name passing is not the whole set."""
    module = _module()

    refusal = module.parse_proof_credentials(
        block=_block(declared=[_read_only(name="GITHUB_PRIVATE_KEY", purpose="observe the forge")])
    )

    assert isinstance(refusal, str)
    assert "GITHUB_PRIVATE_KEY" in refusal
    assert "withheld" in refusal


def test_an_absent_value_is_refused_naming_the_name_and_the_credential_wrapper() -> None:
    """A declared name the Dispatcher's environment does not carry refuses.

    The refusal names the target's credential wrapper because that is the thing
    an operator has to change: the Dispatcher cannot mint this credential, so
    "absent" means the wrapper did not inject it.
    """
    module = _module()

    refusal = module.proof_credentials_refusal(
        block=_block(declared=[_read_only()]),
        environ={},
        wrapper_text="['/usr/local/bin/with-acme-env.sh', '--']",
    )

    assert isinstance(refusal, str)
    assert "ACME_STATUS_READER" in refusal
    assert "with-acme-env.sh" in refusal


def test_a_present_read_only_value_passes_the_gate() -> None:
    """The positive control for the gate: a declaration it admits.

    Without it, every refusal below is equally consistent with a gate that
    refuses each declaration it is handed. The PROJECTION half of this control
    lives in the projection module's own tests.
    """
    module = _module()
    block = _block(declared=[_read_only()])
    environ = {"ACME_STATUS_READER": "acme-observer-value"}

    assert module.proof_credentials_refusal(block=block, environ=environ, wrapper_text="[]") is None


def test_a_minted_name_is_not_refused_for_an_absent_host_value() -> None:
    """A credential the Dispatcher mints per run needs no host value.

    The overlay already projects `GITHUB_TOKEN` from the installation token it
    mints for this dispatch, so refusing it for an absent host value would refuse
    a credential the Dispatcher itself supplies.
    """
    module = _module()
    block = _block(declared=[_read_only(name="GITHUB_TOKEN", purpose="observe the forge")])

    assert module.proof_credentials_refusal(block=block, environ={}, wrapper_text="[]") is None


def test_the_gate_hands_back_the_declaration_refusal_verbatim() -> None:
    """One message reaches the operator, not a wrapping of a wrapping.

    The gate composes the parse rather than re-deriving its grades, so an operator
    reading a dispatch refusal sees the same sentence the parse produced — which
    is what makes the parse's own tests evidence about what a dispatch reports.
    """
    module = _module()
    over_scoped = {
        "name": "ACME_DEPLOY_RUNNER",
        "purpose": "run the deploy smoke suite on the host",
        "capability": "host_execute",
    }
    block = _block(declared=[over_scoped])

    assert module.proof_credentials_refusal(
        block=block, environ={}, wrapper_text="[]"
    ) == module.parse_proof_credentials(block=block)


def test_an_absent_declaration_refuses_nothing() -> None:
    """The normal posture: a repository declaring no proof credential is untouched."""
    module = _module()

    assert module.proof_credentials_refusal(block={}, environ={}, wrapper_text="[]") is None


def test_each_declaration_is_journaled_by_name_with_how_it_was_provisioned(
    tmp_path: Path,
) -> None:
    """One record per declaration per dispatched item: the name, and minted-or-copied.

    The two declarations are deliberately on OPPOSITE sides of the provisioning
    split, in one pass, because a record that always said `copied` would satisfy
    a single-declaration assertion just as well. `GITHUB_TOKEN` is the name the
    Dispatcher mints per run; the ACME reader is copied from the wrapper-supplied
    environment.

    The record is also asserted NOT to carry either value. A journal is a durable
    artifact, and the clause this realizes requires journals and records to carry
    names and never values.
    """
    module = _module()
    repo = _governed_repo(
        tmp_path=tmp_path,
        declared=[
            _read_only(),
            _read_only(name="GITHUB_TOKEN", purpose="observe the forge"),
        ],
    )
    journal = _Journal()

    refusal = module.proof_credentials_refusal_for_items(
        repo=repo,
        environ={"ACME_STATUS_READER": "acme-observer-value", "GITHUB_TOKEN": "minted-token-value"},
        wrapper_text="[]",
        work_item_ids=["bd-ib-first"],
        journal=journal,
    )

    assert refusal is None
    assert [
        (record["name"], record["provisioning"], record["work_item_id"], record["stage"])
        for record in journal.records
    ] == [
        (
            "ACME_STATUS_READER",
            module.COPIED_PROVISIONING,
            "bd-ib-first",
            module.PROOF_CREDENTIAL_JOURNAL_STAGE,
        ),
        (
            "GITHUB_TOKEN",
            module.MINTED_PROVISIONING,
            "bd-ib-first",
            module.PROOF_CREDENTIAL_JOURNAL_STAGE,
        ),
    ]
    assert "acme-observer-value" not in json.dumps(journal.records)
    assert "minted-token-value" not in json.dumps(journal.records)


def test_every_dispatched_item_gets_its_own_records(tmp_path: Path) -> None:
    """A drain wave projects one overlay per item, so each item carries its own record.

    Keyed per item rather than once per repository because the projection is
    per-dispatch: reading the journal for one item must show what THAT dispatch
    projected, not what some sibling in the same wave did.
    """
    module = _module()
    repo = _governed_repo(tmp_path=tmp_path, declared=[_read_only()])
    journal = _Journal()

    _ = module.proof_credentials_refusal_for_items(
        repo=repo,
        environ={"ACME_STATUS_READER": "acme-observer-value"},
        wrapper_text="[]",
        work_item_ids=["bd-ib-first", "bd-ib-second"],
        journal=journal,
    )

    assert [record["work_item_id"] for record in journal.records] == [
        "bd-ib-first",
        "bd-ib-second",
    ]


def test_a_refused_declaration_is_returned_and_journals_no_projection_record(
    tmp_path: Path,
) -> None:
    """The refusal is the answer; nothing was projected, so nothing is recorded as projected.

    The control matters more than the refusal here: a gate that wrote a projection
    record alongside a refusal would leave a journal claiming a credential reached
    a sandbox that was never launched.
    """
    module = _module()
    repo = _governed_repo(tmp_path=tmp_path, declared=[_read_only(name="BEADS_DOLT_PASSWORD")])
    journal = _Journal()

    refusal = module.proof_credentials_refusal_for_items(
        repo=repo,
        environ={"BEADS_DOLT_PASSWORD": "store-password"},
        wrapper_text="[]",
        work_item_ids=["bd-ib-first"],
        journal=journal,
    )

    assert isinstance(refusal, str)
    assert journal.records == []


def test_an_absent_value_refuses_through_the_selection_gate_too(tmp_path: Path) -> None:
    """The environment grade is reachable from the dispatch path, not only in isolation.

    Paired with the withheld case above because the two faults take different arms
    of the same gate: one is decided by the declaration alone and one needs the
    environment, and a gate wired to only the first would pass this.
    """
    module = _module()
    journal = _Journal()

    refusal = module.proof_credentials_refusal_for_items(
        repo=_governed_repo(tmp_path=tmp_path, declared=[_read_only()]),
        environ={},
        wrapper_text="['/usr/local/bin/with-acme-env.sh', '--']",
        work_item_ids=["bd-ib-first"],
        journal=journal,
    )

    assert isinstance(refusal, str)
    assert "with-acme-env.sh" in refusal
    assert journal.records == []


def test_the_gate_is_callable_without_a_journal(tmp_path: Path) -> None:
    """The journal is optional, so the gate runs from a caller holding none."""
    module = _module()
    repo = _governed_repo(tmp_path=tmp_path, declared=[_read_only()])

    assert (
        module.proof_credentials_refusal_for_items(
            repo=repo,
            environ={"ACME_STATUS_READER": "acme-observer-value"},
            wrapper_text="[]",
            work_item_ids=["bd-ib-first"],
        )
        is None
    )


def test_a_repository_declaring_nothing_journals_nothing(tmp_path: Path) -> None:
    """The normal posture leaves the journal untouched rather than writing an empty record."""
    module = _module()
    journal = _Journal()

    refusal = module.proof_credentials_refusal_for_items(
        repo=_governed_repo(tmp_path=tmp_path, declared=None),
        environ={},
        wrapper_text="[]",
        work_item_ids=["bd-ib-first"],
        journal=journal,
    )

    assert refusal is None
    assert journal.records == []
