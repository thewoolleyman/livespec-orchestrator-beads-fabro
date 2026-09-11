"""The operator's EXACT clearance valve for one typed availability hold.

Binds the last clause of `SPECIFICATION/contracts.md` section
"Factory-configurable ACP fallback priority": "An exact scope/key
clearance valve MUST be attributed, reason-required, append-only, and
refuse a nonexistent live target; the legacy provider valve addresses
legacy records only."

THE SEPARATION CONTROL IS THE ONE THAT MATTERS MOST, and it is asserted
in BOTH directions over one journal carrying both kinds of record: an
exact ACP clearance must leave a live legacy provider record standing,
and the legacy valve must leave a live typed hold standing. A single
shared stage name would pass every other test in this file and fail only
these two.

APPEND-ONLY IS ASSERTED ON THE FILE, not on the return value. The
observation line must still be present, byte-for-byte, after the
clearance -- a valve that retired a hold by rewriting its record would
otherwise look identical from the outside.

Everything is HERMETIC: journals live in `tmp_path`, the invoker is
supplied through the documented flag, the command's wall clock is
pinned, and nothing reaches a provider. The clock is STUBBED rather than
the fixture instants floated forward, because the valve reads `now` only
to decide which observations are still LIVE -- against a real clock every
case below would pass or fail on how close the suite happened to run to
a fifteen-minute boundary.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_hold_clear"

_OCCURRED = "2026-09-11T12:00:00Z"
_NOW = "2026-09-11T12:05:00Z"


def _module() -> Any:
    """Import the clearance module, proving its file exists first."""
    assert (_COMMANDS / f"{_MODULE}.py").is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _failure(*, scope: str, hold_key: str, candidate_key: str | None) -> Any:
    classifier = importlib.import_module(f"{_PACKAGE}._acp_failure_classifier")
    return classifier.AcpAvailabilityFailure(
        cause="quota",
        scope=scope,
        hold_key=hold_key,
        availability_key=hold_key,
        candidate_key=candidate_key,
        source="protocol.message",
    )


def _observation(*, scope: str, hold_key: str, candidate_key: str | None) -> dict[str, Any]:
    records = importlib.import_module(f"{_PACKAGE}._acp_hold_records")
    built = records.hold_observation_record(
        failure=_failure(scope=scope, hold_key=hold_key, candidate_key=candidate_key),
        evidence_kind="candidate-attempt",
        evidence_id=f"run-1:{scope}:{hold_key}:{candidate_key}",
        occurred_at=_OCCURRED,
        work_item_id="bd-ib-5ltgny",
        node="implement",
    )
    assert isinstance(built, dict)
    return dict(built)


def _legacy_observation() -> dict[str, Any]:
    """One unexpired record of the LEGACY provider-exhaustion valve."""
    return {
        "at": _OCCURRED,
        "stage": "provider-exhaustion-observed",
        "work_item_id": "bd-ib-5ltgny",
        "provider": "codex",
        "governing_condition": "provider_usage_limit",
        "record_expires_at": "2026-09-11T12:15:00Z",
    }


def _journal(*, tmp_path: Path, records: tuple[dict[str, Any], ...]) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "journal.jsonl"
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8"
    )
    return path


def _argv(*, path: Path, **overrides: str) -> list[str]:
    flags = {
        "--scope": "availability-domain",
        "--hold-key": "codex",
        "--reason": "the account allowance reset",
        "--invoker": "human:tester",
        "--journal": str(path),
        "--repo": str(path.parent),
    }
    flags.update(overrides)
    return ["clear-acp-availability-hold", *(item for pair in flags.items() for item in pair)]


def _run(*, argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    """Drive the subcommand through the dispatcher CLI on a pinned clock."""
    monkeypatch.setattr(_module(), "utc_now_iso", lambda: _NOW)
    dispatcher = importlib.import_module(f"{_PACKAGE}.dispatcher")
    return dispatcher.main(argv=argv)


def _lines(*, path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _precondition_error() -> int:
    return int(
        importlib.import_module(f"{_PACKAGE}._dispatcher_command_common").EXIT_PRECONDITION_ERROR
    )


def test_an_exact_clearance_is_append_only_attributed_and_reason_bearing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The happy path, asserted on the FILE rather than the exit code alone."""
    observation = _observation(scope="availability-domain", hold_key="codex", candidate_key=None)
    path = _journal(tmp_path=tmp_path, records=(observation,))
    before = path.read_text(encoding="utf-8")
    assert _run(argv=_argv(path=path), monkeypatch=monkeypatch) == 0
    # APPEND-ONLY: the observation line survives byte-for-byte.
    assert path.read_text(encoding="utf-8").startswith(before)
    clearance = _lines(path=path)[-1]
    ledger = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    assert clearance["stage"] == ledger.CLEARED_STAGE
    assert clearance["reason"] == "the account allowance reset"
    assert clearance["observation_ids"] == [observation["observation_id"]]
    # Attribution is STAMPED by the append layer, not asserted by the caller.
    assert clearance["invoker"] == "human:tester"
    assert "at" in clearance
    assert ledger.read_acp_hold_ledger(journal_path=path, now_iso=_NOW).holds == ()
    assert "CLEARED" in capsys.readouterr().out


def test_a_candidate_scoped_clearance_names_its_exact_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Candidate scope addresses one entitlement, never the domain around it."""
    domain = _observation(scope="availability-domain", hold_key="codex", candidate_key=None)
    exact = _observation(scope="candidate", hold_key="codex", candidate_key="gpt-5-5")
    sibling = _observation(scope="candidate", hold_key="codex", candidate_key="gpt-5-5-mini")
    path = _journal(tmp_path=tmp_path, records=(domain, exact, sibling))
    argv = _argv(path=path, **{"--scope": "candidate", "--candidate-key": "gpt-5-5"})
    assert _run(argv=argv, monkeypatch=monkeypatch) == 0
    ledger = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    live = ledger.read_acp_hold_ledger(journal_path=path, now_iso=_NOW)
    # The sibling candidate and the whole domain are untouched.
    assert {hold.observation_id for hold in live.holds} == {
        domain["observation_id"],
        sibling["observation_id"],
    }


def test_the_valve_refuses_a_blank_reason_and_an_unattributed_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clearance is a human act that states its own justification."""
    invoker = importlib.import_module(f"{_PACKAGE}._dispatcher_invoker")
    path = _journal(
        tmp_path=tmp_path,
        records=(_observation(scope="availability-domain", hold_key="codex", candidate_key=None),),
    )
    blank = _argv(path=path, **{"--reason": "   "})
    assert _run(argv=blank, monkeypatch=monkeypatch) == _precondition_error()
    assert "--reason is blank" in capsys.readouterr().err
    monkeypatch.delenv(invoker.INVOKER_ENV_VAR, raising=False)
    anonymous = [
        "clear-acp-availability-hold",
        "--scope",
        "availability-domain",
        "--hold-key",
        "codex",
        "--reason",
        "it is back",
        "--journal",
        str(path),
        "--repo",
        str(tmp_path),
    ]
    assert _run(argv=anonymous, monkeypatch=monkeypatch) == _precondition_error()
    assert "asserted no identity" in capsys.readouterr().err
    # Nothing was written on either refusal.
    assert len(_lines(path=path)) == 1


def test_a_half_specified_target_is_refused_rather_than_widened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each scope has one key shape; the nearest match is never substituted."""
    path = _journal(
        tmp_path=tmp_path,
        records=(
            _observation(scope="availability-domain", hold_key="codex", candidate_key=None),
            _observation(scope="candidate", hold_key="codex", candidate_key="gpt-5-5"),
        ),
    )
    # Candidate scope with no candidate key would otherwise clear the
    # whole domain an operator never named.
    keyless = _argv(path=path, **{"--scope": "candidate"})
    assert _run(argv=keyless, monkeypatch=monkeypatch) == _precondition_error()
    assert "pass --candidate-key" in capsys.readouterr().err
    overspecified = _argv(path=path, **{"--candidate-key": "gpt-5-5"})
    assert _run(argv=overspecified, monkeypatch=monkeypatch) == _precondition_error()
    assert "cannot address" in capsys.readouterr().err
    assert len(_lines(path=path)) == 2


def test_a_nonexistent_live_target_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clearance against no observation would assert an override that never happened."""
    path = _journal(
        tmp_path=tmp_path,
        records=(_observation(scope="availability-domain", hold_key="codex", candidate_key=None),),
    )
    other_domain = _argv(path=path, **{"--hold-key": "anthropic"})
    assert _run(argv=other_domain, monkeypatch=monkeypatch) == _precondition_error()
    assert "nothing to clear" in capsys.readouterr().err
    # The candidate form of the same refusal renders its exact pair.
    absent_pair = _argv(path=path, **{"--scope": "candidate", "--candidate-key": "absent"})
    assert _run(argv=absent_pair, monkeypatch=monkeypatch) == _precondition_error()
    assert "codex/absent" in capsys.readouterr().err
    assert len(_lines(path=path)) == 1


def test_an_expired_observation_is_not_a_clearable_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Expiry already retired it, so there is nothing left for the valve to retire."""
    path = _journal(
        tmp_path=tmp_path,
        records=(_observation(scope="availability-domain", hold_key="codex", candidate_key=None),),
    )
    monkeypatch.setattr(_module(), "utc_now_iso", lambda: "2026-09-11T12:20:00Z")
    dispatcher = importlib.import_module(f"{_PACKAGE}.dispatcher")
    assert dispatcher.main(argv=_argv(path=path)) == _precondition_error()
    assert "nothing to clear" in capsys.readouterr().err


def test_neither_valve_retires_the_other_valve_s_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The separation control, asserted in BOTH directions on one journal."""
    ledger = importlib.import_module(f"{_PACKAGE}._acp_hold_ledger")
    exhaustion = importlib.import_module(f"{_PACKAGE}._dispatcher_provider_exhaustion")
    typed = _observation(scope="availability-domain", hold_key="codex", candidate_key=None)
    path = _journal(tmp_path=tmp_path, records=(typed, _legacy_observation()))
    assert _run(argv=_argv(path=path), monkeypatch=monkeypatch) == 0
    # The typed clearance retired the typed hold...
    assert ledger.read_acp_hold_ledger(journal_path=path, now_iso=_NOW).holds == ()
    # ...and left the legacy provider record standing.
    assert (
        exhaustion.active_provider_exhaustion(provider="codex", journal_path=path, now_iso=_NOW)
        is not None
    )
    # The mirror direction: the legacy clearance leaves a typed hold alone.
    mirror = _journal(
        tmp_path=tmp_path / "mirror",
        records=(
            typed,
            _legacy_observation(),
            {
                "at": "2026-09-11T12:06:00Z",
                "invoker": "human:tester",
                **exhaustion.provider_exhaustion_clearance_record(
                    provider="codex", reason="restarted"
                ),
            },
        ),
    )
    assert (
        exhaustion.active_provider_exhaustion(
            provider="codex", journal_path=mirror, now_iso="2026-09-11T12:07:00Z"
        )
        is None
    )
    assert (
        len(ledger.read_acp_hold_ledger(journal_path=mirror, now_iso="2026-09-11T12:07:00Z").holds)
        == 1
    )


def test_the_repo_default_resolves_the_journal_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An omitted `--repo` falls back to the current directory, as the sibling valve does."""
    monkeypatch.chdir(tmp_path)
    argv = [
        "clear-acp-availability-hold",
        "--scope",
        "availability-domain",
        "--hold-key",
        "codex",
        "--reason",
        "it is back",
        "--invoker",
        "human:tester",
    ]
    assert _run(argv=argv, monkeypatch=monkeypatch) == _precondition_error()
    assert "nothing to clear" in capsys.readouterr().err
