"""A record naming NO account still speaks for the whole vendor, and one valve clears both.

Binds `SPECIFICATION/scenarios.md` "## Scenario 186" case "A record without a
credential identity keeps vendor-wide coverage", against two sentences of
`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance" that have to hold TOGETHER:

- "A provider-exhaustion record that carries no credential identity, including
  every record minted before this clause, keeps the vendor-wide coverage stated
  above until it expires or is cleared."
- "The provider valve retires every live provider-exhaustion record of the
  named provider, whether or not the record carries a credential identity."

WHY THE SECOND IS THE DANGEROUS ONE. Once records are keyed per account, the
operator's clearance line is itself a record that names NO account -- so a
valve that retired its own key would retire exactly the provider-only record
and leave every account-named record of that vendor standing. The operator
would read `CLEARED anthropic`, see the exit code 0, and still have every
dispatch refused, with the journal showing a clearance that did what it said.
The two halves of this file are therefore the same claim read from both ends:
an absent account is a WIDE coverage and a NARROW key, and the clearance keys
on the provider rather than on the pair.

"Until it expires" is asserted too, because a record that refused forever would
satisfy every coverage case here -- and the clause's whole first guarantee is
that no record is permanent.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands.dispatcher import main

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"

_NOW = "2026-10-16T17:42:00Z"
_LIVE_EXPIRY = "2099-01-01T00:00:00Z"
_PAST_EXPIRY = "2026-10-16T17:00:00Z"
_EXHAUSTED_ACCOUNT = "1111111111111111"
_ROTATED_ACCOUNT = "2222222222222222"
_REASON = "caam rotated the Anthropic selection and the new account has quota"


def _exhaustion() -> Any:
    return import_module(f"{_PACKAGE}._dispatcher_provider_exhaustion")


def _observation(
    *, identity: str | None, expires_at: str = _LIVE_EXPIRY, provider: str = "anthropic"
) -> dict[str, object]:
    return {
        "at": _NOW,
        "stage": "provider-exhaustion-observed",
        "work_item_id": "bd-observer",
        "provider": provider,
        "credential_identity": identity,
        "governing_condition": "provider_usage_limit",
        "record_expires_at": expires_at,
    }


def _journal(*, tmp_path: Path, records: tuple[dict[str, object], ...]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "fabro-dispatch-journal.jsonl"
    path.write_text("".join(f"{json.dumps(record)}\n" for record in records), encoding="utf-8")
    return path


def _rendered_anthropic() -> Any:
    schema = import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = import_module(f"{_PACKAGE}._acp_node_adapters")
    coverage = import_module(f"{_PACKAGE}._acp_dispatch_coverage")
    return coverage.RenderedCandidate(
        candidate=schema.AcpCandidate(
            adapter=adapters.AcpAdapter(command="claude-adapter", env={}, args=()),
            identity=schema.AcpCandidateIdentity(
                display_name="built-in Anthropic ACP adapter",
                candidate_key="builtin-anthropic-0000000000000000",
                availability_key="anthropic",
            ),
        ),
        builtin=True,
    )


def _covering(*, path: Path, projected: frozenset[str]) -> Any:
    return _exhaustion().covering_provider_exhaustion(
        journal_path=path,
        now_iso=_NOW,
        candidates=(_rendered_anthropic(),),
        projected_identities=projected,
    )


def test_a_provider_only_record_refuses_whatever_account_the_dispatch_projects(
    tmp_path: Path,
) -> None:
    """Scenario 186: an absent account is a wide coverage, not a narrow one."""
    path = _journal(tmp_path=tmp_path, records=(_observation(identity=None),))

    for projected in (
        frozenset({_EXHAUSTED_ACCOUNT}),
        frozenset({_ROTATED_ACCOUNT}),
        frozenset({"3333333333333333"}),
        frozenset(),
    ):
        held = _covering(path=path, projected=projected)
        assert held is not None
        assert held.credential_identity is None


def test_a_provider_only_record_stops_refusing_when_it_expires(tmp_path: Path) -> None:
    """The control: no record is permanent, whatever it names."""
    expired = _journal(
        tmp_path=tmp_path, records=(_observation(identity=None, expires_at=_PAST_EXPIRY),)
    )

    assert _covering(path=expired, projected=frozenset({_ROTATED_ACCOUNT})) is None
    # And it never reached beyond its own vendor while it was live: a dispatch
    # rendering only this vendor's candidates is the one it covers.
    elsewhere = _journal(
        tmp_path=tmp_path / "elsewhere",
        records=(_observation(identity=None, provider="codex"),),
    )
    assert _covering(path=elsewhere, projected=frozenset({_ROTATED_ACCOUNT})) is None


def test_the_operator_valve_retires_every_live_record_of_the_named_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One clearance, both record shapes -- which per-account keying can break.

    The clearance line names no account, so a valve keyed on the pair clears
    the provider-only record and leaves the account-named ones live, while
    telling the operator it cleared the provider.
    """
    exhaustion = _exhaustion()
    path = _journal(
        tmp_path=tmp_path,
        records=(
            _observation(identity=_EXHAUSTED_ACCOUNT),
            _observation(identity=_ROTATED_ACCOUNT),
            _observation(identity=None),
        ),
    )

    exit_code = main(
        argv=[
            "clear-provider-exhaustion",
            "--repo",
            str(tmp_path),
            "--journal",
            str(path),
            "--provider",
            "anthropic",
            "--reason",
            _REASON,
            "--invoker",
            "operator:cwoolley",
        ]
    )

    assert exit_code == 0
    assert "CLEARED  anthropic" in capsys.readouterr().out
    assert (
        exhaustion.live_provider_exhaustions(journal_path=path, now_iso=_NOW) == ()
    ), "the clearance retired only the record that names no account"
    # And every dispatch is admitted again, whichever account it projects.
    assert _covering(path=path, projected=frozenset({_EXHAUSTED_ACCOUNT})) is None
    assert _covering(path=path, projected=frozenset()) is None
    # The three observations survive the clearance: the journal is append-only,
    # so what was observed and who overrode it both remain readable.
    observed = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["stage"] == "provider-exhaustion-observed"
    ]
    assert [record["credential_identity"] for record in observed] == [
        _EXHAUSTED_ACCOUNT,
        _ROTATED_ACCOUNT,
        None,
    ]


def test_a_clearance_leaves_another_vendors_account_named_record_live(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The control for the case above: provider-wide is not journal-wide.

    Without this half, a clearance that simply emptied the live set would
    satisfy every assertion above while retiring ceilings on vendors the
    operator never named.
    """
    exhaustion = _exhaustion()
    path = _journal(
        tmp_path=tmp_path,
        records=(
            _observation(identity=_EXHAUSTED_ACCOUNT),
            _observation(identity=_EXHAUSTED_ACCOUNT, provider="codex"),
        ),
    )

    exit_code = main(
        argv=[
            "clear-provider-exhaustion",
            "--repo",
            str(tmp_path),
            "--journal",
            str(path),
            "--provider",
            "anthropic",
            "--reason",
            _REASON,
            "--invoker",
            "operator:cwoolley",
        ]
    )

    assert exit_code == 0
    _ = capsys.readouterr()
    assert [
        (record.provider, record.credential_identity)
        for record in exhaustion.live_provider_exhaustions(journal_path=path, now_iso=_NOW)
    ] == [("codex", _EXHAUSTED_ACCOUNT)]
