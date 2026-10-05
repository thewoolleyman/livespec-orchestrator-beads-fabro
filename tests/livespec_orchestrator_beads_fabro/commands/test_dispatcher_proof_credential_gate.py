"""The dispatch-path proof-credential gate over a whole selection.

The IMPURE, selection-level entry point of
`SPECIFICATION/contracts.md`'s proof-credential-projection clause (ratified
v114), split out of `_dispatcher_proof_credentials` by cohesion. That module's
own docstring says every fault IT names is a fault in COMMITTED CONFIGURATION
and it is pure over a block; this gate reads the target repository off disk,
grades the Dispatcher's LIVE ENVIRONMENT, and WRITES the dispatch journal — a
different concern on all three counts.

The module under test is imported through `importlib` inside each test body
rather than at module top, so the first Red of this extraction fails on a
genuine assertion about the module's absence instead of dying at collection.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import cast

import livespec_orchestrator_beads_fabro.commands._acp_candidate_secrets as _commands_anchor
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    PLUGIN_BLOCK,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials import (
    COPIED_PROVISIONING,
    MINTED_PROVISIONING,
    PROOF_CREDENTIAL_JOURNAL_STAGE,
)

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_gate"
_SOURCE_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials"
# Resolved off an existing sibling's own location, so the path is correct from
# any working directory the suite is invoked from.
_MODULE_PATH = Path(cast("str", _commands_anchor.__file__)).parent / (
    "_dispatcher_proof_credential_gate.py"
)

_NAME = "ACME_STATUS_READER"
_VALUE = "acme-observer-value"
_MANAGED_NAME = "ACME_MINTED_READER"
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


def _read_only(*, name: str = _NAME, purpose: str = "observe build status") -> dict[str, str]:
    return {"name": name, "purpose": purpose, "capability": "read_only"}


@dataclass(kw_only=True)
class _Journal:
    """A recording stand-in for `JournalFile`, offering only the `append` seam."""

    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def _governed_repo(
    *, tmp_path: Path, declared: object | None, managed: object | None = None
) -> Path:
    """A repository whose committed configuration declares `proof_credentials`."""
    dispatcher: dict[str, object] = {} if declared is None else {"proof_credentials": declared}
    if managed is not None:
        dispatcher["proof_credential_management"] = managed
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({PLUGIN_BLOCK: {"dispatcher": dispatcher}}), encoding="utf-8"
    )
    return tmp_path


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
        declared=[_read_only(), _read_only(name="GITHUB_TOKEN", purpose="observe the forge")],
    )
    journal = _Journal()

    refusal = module.proof_credentials_refusal_for_items(
        repo=repo,
        environ={_NAME: _VALUE, "GITHUB_TOKEN": "minted-token-value"},
        wrapper_text="[]",
        work_item_ids=["bd-ib-first"],
        journal=journal,
    )

    assert refusal is None
    assert [
        (record["name"], record["provisioning"], record["work_item_id"], record["stage"])
        for record in journal.records
    ] == [
        (_NAME, COPIED_PROVISIONING, "bd-ib-first", PROOF_CREDENTIAL_JOURNAL_STAGE),
        ("GITHUB_TOKEN", MINTED_PROVISIONING, "bd-ib-first", PROOF_CREDENTIAL_JOURNAL_STAGE),
    ]
    assert _VALUE not in json.dumps(journal.records)
    assert "minted-token-value" not in json.dumps(journal.records)


def test_a_managed_declaration_is_journaled_as_minted_through_the_dispatch_gate(
    tmp_path: Path,
) -> None:
    """Read off the JOURNAL, over a repository whose committed provider is declared.

    The clause's own requirement is about what the dispatch journal records per
    declaration, and the record builder asserted alone would pass while nothing
    threaded the resolved providers into the gate that writes it.
    """
    module = _module()
    repo = _governed_repo(
        tmp_path=tmp_path, declared=[_read_only(name=_MANAGED_NAME)], managed=_MANAGED
    )
    journal = _Journal()

    refusal = module.proof_credentials_refusal_for_items(
        repo=repo, environ={}, wrapper_text="[]", work_item_ids=["bd-ib-first"], journal=journal
    )

    assert refusal is None
    assert [(record["name"], record["provisioning"]) for record in journal.records] == [
        (_MANAGED_NAME, MINTED_PROVISIONING)
    ]


def test_every_dispatched_item_gets_its_own_records(tmp_path: Path) -> None:
    """A drain wave projects one overlay per item, so each item carries its own record.

    Keyed per item rather than once per repository because the projection is
    per-dispatch: reading the journal for one item must show what THAT dispatch
    projected, not what some sibling in the same wave did.
    """
    module = _module()
    journal = _Journal()

    _ = module.proof_credentials_refusal_for_items(
        repo=_governed_repo(tmp_path=tmp_path, declared=[_read_only()]),
        environ={_NAME: _VALUE},
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
    journal = _Journal()

    refusal = module.proof_credentials_refusal_for_items(
        repo=_governed_repo(tmp_path=tmp_path, declared=[_read_only(name="BEADS_DOLT_PASSWORD")]),
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

    assert (
        module.proof_credentials_refusal_for_items(
            repo=_governed_repo(tmp_path=tmp_path, declared=[_read_only()]),
            environ={_NAME: _VALUE},
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


def test_the_selection_gate_is_gone_from_the_committed_configuration_module() -> None:
    """The extraction MOVED the selection gate; it did not copy it.

    Asserted on the public surface rather than on the source bytes, because a
    re-export shim would leave the name importable from both modules and that is
    exactly the shape a size-split must not take.
    """
    module = _module()
    source = importlib.import_module(_SOURCE_MODULE_NAME)

    assert "proof_credentials_refusal_for_items" in module.__all__
    assert "proof_credentials_refusal_for_items" not in source.__all__
    assert not hasattr(source, "proof_credentials_refusal_for_items")
