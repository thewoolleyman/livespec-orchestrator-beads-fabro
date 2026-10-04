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
import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_proof_credential_providers as providers,
)
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


@dataclass(kw_only=True)
class _MintOnlyProvider:
    """A hermetic provider management interface offering only the MINT verb.

    Deliberately HALF a provider, and the omission is the point. The seam's own
    grades — a refused mint, an over-granted capability, a re-keyed name, a
    declined revoke — are covered in
    `test_dispatcher_proof_credential_providers.py`, and the revoke's place in
    the run lifecycle is covered by the integration binding for Scenario 134.
    What the cases below measure is the DECLARATION side of the same clause:
    which declarations reach a provider at all, what the journal says about
    each, and what the overlay projects for one. Nothing here revokes, so
    carrying a `revoke` would be a line asserting nothing.
    """

    refusal: str | None = None
    mint_calls: list[tuple[str, str]] = field(default_factory=list)

    def mint(
        self, *, name: str, capability: str, dispatch_id: str
    ) -> providers.MintedProofCredential | str:
        self.mint_calls.append((name, dispatch_id))
        if self.refusal is not None:
            return self.refusal
        return providers.MintedProofCredential(
            name=name,
            capability=capability,
            value=f"minted-value-for-{name}",
            revocation_handle=f"handle-{name}",
        )


def _register_provider(
    *,
    monkeypatch: pytest.MonkeyPatch,
    provider: _MintOnlyProvider,
    name: str = "ACME_STATUS_READER",
) -> None:
    """Register one provider management interface, as a shipped adapter would be.

    Patched on the PROVIDER module rather than on the module under test, because
    that is where `provider_for` reads the registry — a double installed anywhere
    else would leave the real (empty) registry answering every question while the
    test looked wired.
    """
    monkeypatch.setattr(providers, "PROOF_CREDENTIAL_PROVIDERS", {name: provider})


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


def test_the_module_declares_the_gate_and_the_projection() -> None:
    """The public surface the dispatch path reaches, declared in `__all__`."""
    module = _module()

    assert {"proof_credentials_env_lines", "proof_credentials_refusal"} <= set(module.__all__)


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


def test_a_present_read_only_value_passes_the_gate_and_projects_one_overlay_line() -> None:
    """The positive control: the declared name reaches the sandbox env table.

    Asserted on BOTH halves of one declaration, because a gate that admitted
    everything and a projection that rendered nothing each look like success on
    their own.
    """
    module = _module()
    block = _block(declared=[_read_only()])
    environ = {"ACME_STATUS_READER": "acme-observer-value"}

    assert module.proof_credentials_refusal(block=block, environ=environ, wrapper_text="[]") is None
    assert (
        module.proof_credentials_env_lines(block=block, environ=environ)
        == 'ACME_STATUS_READER = "acme-observer-value"\n'
    )


def test_a_minted_name_is_neither_refused_for_absence_nor_projected_twice() -> None:
    """A credential the Dispatcher mints per run needs no host value and no second line.

    The overlay already projects `GITHUB_TOKEN` from the installation token it
    mints for this dispatch. A second TOML line under the same key would make the
    WHOLE overlay unparseable — one repository's declaration turning into a
    dispatch-wide failure — and refusing it for an absent host value would refuse
    a credential the Dispatcher itself supplies.
    """
    module = _module()
    block = _block(declared=[_read_only(name="GITHUB_TOKEN", purpose="observe the forge")])

    assert module.proof_credentials_refusal(block=block, environ={}, wrapper_text="[]") is None
    assert module.proof_credentials_env_lines(block=block, environ={}) == ""


def test_a_refused_declaration_projects_nothing() -> None:
    """The projection is fail-closed: a declaration the gate refuses renders no line.

    The gate runs before the overlay on every dispatch path, so this arm should be
    unreachable in production. It is asserted anyway because the alternative shape
    — a builder that renders whatever it can parse — is the fail-open one, and the
    cost of being wrong here is a projected credential nobody admitted.
    """
    module = _module()

    assert (
        module.proof_credentials_env_lines(
            block=_block(declared=[_read_only(name="BEADS_DOLT_PASSWORD")]),
            environ={"BEADS_DOLT_PASSWORD": "store-password"},
        )
        == ""
    )


def test_a_copied_name_whose_value_is_absent_projects_no_line() -> None:
    """The projection skips an absent value rather than rendering it empty.

    The gate refuses this case before the overlay is reached, so this is the
    projection's own fail-closed arm: an empty TOML value would put a name into
    the sandbox environment that resolves to nothing, which reads to a proof
    stage exactly like a revoked credential.
    """
    module = _module()

    assert (
        module.proof_credentials_env_lines(block=_block(declared=[_read_only()]), environ={}) == ""
    )


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


def test_an_absent_declaration_projects_nothing_and_refuses_nothing() -> None:
    """The normal posture: a repository declaring no proof credential is untouched."""
    module = _module()

    assert module.proof_credentials_refusal(block={}, environ={}, wrapper_text="[]") is None
    assert module.proof_credentials_env_lines(block={}, environ={}) == ""


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


def test_a_provider_backed_declaration_is_journaled_as_minted_beside_a_copied_sibling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The journal value turns on whether the declaration's provider can mint one.

    The two declarations are deliberately on OPPOSITE sides of the split in ONE
    pass, because a record that always said `minted` would satisfy a
    single-declaration assertion just as well — and the whole point of the
    clause's journal requirement is that a reader can tell the two apart. The
    only difference between them is the registry: both are plain `read_only`
    declarations whose values the environment supplies.
    """
    module = _module()
    _register_provider(monkeypatch=monkeypatch, provider=_MintOnlyProvider())
    repo = _governed_repo(
        tmp_path=tmp_path,
        declared=[
            _read_only(),
            _read_only(name="ACME_METRICS_READER", purpose="observe published metrics"),
        ],
    )
    journal = _Journal()

    refusal = module.proof_credentials_refusal_for_items(
        repo=repo,
        environ={"ACME_METRICS_READER": "metrics-value"},
        wrapper_text="[]",
        work_item_ids=["bd-ib-first"],
        journal=journal,
    )

    assert refusal is None
    assert [(record["name"], record["provisioning"]) for record in journal.records] == [
        ("ACME_STATUS_READER", module.MINTED_PROVISIONING),
        ("ACME_METRICS_READER", module.COPIED_PROVISIONING),
    ]


def test_a_provider_backed_declaration_needs_no_wrapper_supplied_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The absent-value grade does not apply to a declaration that is minted per run.

    Refusing it for an absent host value would refuse a credential that is about
    to exist — and worse, it would make adopting a provider adapter require the
    wrapper to keep injecting the very long-lived credential the mint exists to
    retire. The copied control beside it is what proves the grade still fires.
    """
    module = _module()
    _register_provider(monkeypatch=monkeypatch, provider=_MintOnlyProvider())
    block = _block(declared=[_read_only()])

    assert module.proof_credentials_refusal(block=block, environ={}, wrapper_text="[]") is None
    assert isinstance(
        module.proof_credentials_refusal(
            block=_block(declared=[_read_only(name="ACME_METRICS_READER")]),
            environ={},
            wrapper_text="['/usr/local/bin/with-acme-env.sh', '--']",
        ),
        str,
    )


def test_each_provider_backed_declaration_is_minted_once_for_this_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One credential per provider-backed declaration per run, carrying the dispatch id.

    The DISPATCH ID reaching the provider is asserted because "one per run" is
    the clause's own requirement: a mint that ignored it would be
    indistinguishable from a long-lived credential fetched once and reused.
    """
    module = _module()
    provider = _MintOnlyProvider()
    _register_provider(monkeypatch=monkeypatch, provider=provider)
    repo = _governed_repo(
        tmp_path=tmp_path,
        declared=[_read_only(), _read_only(name="ACME_METRICS_READER")],
    )

    lease = module.mint_declared_proof_credentials(repo=repo, dispatch_id="01DISPATCH")

    assert provider.mint_calls == [("ACME_STATUS_READER", "01DISPATCH")]
    assert [credential.name for credential in lease.minted] == ["ACME_STATUS_READER"]
    assert lease.overlay_values() == {"ACME_STATUS_READER": "minted-value-for-ACME_STATUS_READER"}


def test_a_repository_with_no_provider_backed_declaration_mints_nothing(
    tmp_path: Path,
) -> None:
    """The copied control: the ordinary posture leases nothing and calls no provider.

    This is what keeps the minting path from changing the behaviour of every
    repository that declares a credential the host already holds — the clause
    makes minting a SHOULD conditioned on the provider offering an interface, so
    a declaration with no provider must come out exactly as it did before.
    """
    module = _module()
    repo = _governed_repo(tmp_path=tmp_path, declared=[_read_only()])

    assert module.mint_declared_proof_credentials(repo=repo, dispatch_id="01DISPATCH").minted == ()


def test_a_refused_mint_refuses_the_dispatch_naming_the_declaration_and_the_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider that mints nothing refuses the dispatch rather than falling back.

    The fallback is the tempting shape and it is the wrong one: copying the
    host's own credential when the mint fails would silently undo the clause for
    exactly the declarations it applies to, and the dispatch would look healthy.
    The refusal names the committed key so an operator knows where to look.
    """
    module = _module()
    _register_provider(
        monkeypatch=monkeypatch,
        provider=_MintOnlyProvider(refusal="the management API returned 503"),
    )
    repo = _governed_repo(tmp_path=tmp_path, declared=[_read_only()])

    refusal = module.mint_declared_proof_credentials(repo=repo, dispatch_id="01DISPATCH")

    assert isinstance(refusal, str)
    assert "dispatcher.proof_credentials" in refusal
    assert "ACME_STATUS_READER" in refusal
    assert "the management API returned 503" in refusal


def test_the_mint_hands_back_a_declaration_refusal_rather_than_minting(
    tmp_path: Path,
) -> None:
    """Fail-closed: a declaration the parse refuses is never carried to a provider.

    The pre-dispatch gate refuses this case before the mint is reached, so this
    arm should be unreachable in production. It is asserted anyway because the
    alternative shape — mint whatever parses — would hand a withheld name to a
    third-party management interface.
    """
    module = _module()
    repo = _governed_repo(tmp_path=tmp_path, declared=[_read_only(name="BEADS_DOLT_PASSWORD")])

    refusal = module.mint_declared_proof_credentials(repo=repo, dispatch_id="01DISPATCH")

    assert isinstance(refusal, str)
    assert "withheld" in refusal


def test_the_overlay_projects_the_minted_value_for_a_provider_backed_declaration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lease's value reaches the sandbox under the DECLARED name.

    The environment deliberately carries a DIFFERENT value under the same name,
    so the projected line is evidence the lease won rather than evidence that
    some value was available: a build that ignored the lease would render the
    host's copy here and look identical in shape.
    """
    module = _module()
    _register_provider(monkeypatch=monkeypatch, provider=_MintOnlyProvider())
    lease = module.mint_declared_proof_credentials(
        repo=_governed_repo(tmp_path=tmp_path, declared=[_read_only()]),
        dispatch_id="01DISPATCH",
    )

    rendered = module.proof_credentials_env_lines(
        block=_block(declared=[_read_only()]),
        environ={"ACME_STATUS_READER": "the-hosts-own-long-lived-copy"},
        lease=lease,
    )

    assert rendered == 'ACME_STATUS_READER = "minted-value-for-ACME_STATUS_READER"\n'


def test_a_provider_backed_declaration_with_no_lease_projects_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed again, and in the one direction that matters most here.

    A provider-backed declaration whose lease carries no entry projects NOTHING
    rather than falling back to the host's own copy of the credential. That
    fallback is precisely the posture the mint exists to retire, so taking it
    silently on a missing lease would make the clause unobservable — the overlay
    would look right and the sandbox would hold a long-lived credential.
    """
    module = _module()
    _register_provider(monkeypatch=monkeypatch, provider=_MintOnlyProvider())

    assert (
        module.proof_credentials_env_lines(
            block=_block(declared=[_read_only()]),
            environ={"ACME_STATUS_READER": "the-hosts-own-long-lived-copy"},
        )
        == ""
    )


def test_the_copied_projection_is_unchanged_by_the_minting_path(tmp_path: Path) -> None:
    """The copied control for the projection, read through the real repository entry point.

    Unchanged from the behaviour the declaration clause landed with: a
    declaration whose provider has no management interface is still projected
    from the wrapper-supplied environment, and the lease parameter it now accepts
    changes nothing for it.
    """
    module = _module()
    repo = _governed_repo(tmp_path=tmp_path, declared=[_read_only()])

    assert (
        module.proof_credentials_overlay_env(
            repo=repo, environ={"ACME_STATUS_READER": "acme-observer-value"}
        )
        == 'ACME_STATUS_READER = "acme-observer-value"\n'
    )
