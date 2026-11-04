"""Tests for the selection-level Fabro currency gate.

`tests/integration/test_fabro_currency_admission_scenario130.py` drives the gate
through the real pre-dispatch wall. This module covers the selection-level
properties that wall cannot show: that an EMPTY selection costs no read, that a
serverless target is surfaced rather than refused or silently passed, that TWO
configured targets are each evaluated against their OWN serving commit, and that
the production seams resolve when no caller supplies them.

TARGET-AWARENESS IS ASSERTED WITH ONE CURRENT TARGET BESIDE ONE STALE ONE, which
is the only shape that can fail for the right reason: a gate that evaluated a
single fleet-global surrogate would return one verdict for both, and both a
both-current and a both-stale fixture would agree with it.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_fabro_currency_gate as gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    CONDITION_OUT_OF_WINDOW,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_sources import (
    compare_argv,
    releases_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_HP_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_VPS_SERVER = "https://vps.perch-rudd.ts.net:32276"
_HP_BIN = "/home/ubuntu/.fabro/bin/fabro-hp"
_VPS_BIN = "/home/ubuntu/.fabro/bin/fabro-vps"
_HP_COMMIT = "8869e88"
_VPS_COMMIT = "977cb67"
_CURRENT_TAG = "v0.378.0-nightly.0"
# Deliberately NOT the 0.254 carrier: the one ratified transition admits that
# series, so a stale-target fixture built on it would stop being stale the moment
# the exception landed and this module's target-awareness claim would evaporate.
_STALE_TAG = "v0.300.0"
_NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Runner:
    results: dict[tuple[str, ...], CommandResult]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="unstubbed"))


def _releases_stdout() -> str:
    rows = [
        {"tag": _CURRENT_TAG, "published_at": "2026-10-10T01:00:00Z"},
        {"tag": _STALE_TAG, "published_at": "2026-07-30T12:00:00Z"},
    ]
    return "\n".join(json.dumps(row) for row in rows) + "\n"


def _two_target_runner() -> _Runner:
    """hp serves a commit descended from the CURRENT tag; vps from the stale one."""
    results: dict[tuple[str, ...], CommandResult] = {
        tuple(releases_argv()): CommandResult(exit_code=0, stdout=_releases_stdout(), stderr=""),
        (_HP_BIN, "version", "--json"): CommandResult(
            exit_code=0, stdout=json.dumps({"server": {"git_sha": _HP_COMMIT}}), stderr=""
        ),
        (_VPS_BIN, "version", "--json"): CommandResult(
            exit_code=0, stdout=json.dumps({"server": {"git_sha": _VPS_COMMIT}}), stderr=""
        ),
        tuple(compare_argv(base=_CURRENT_TAG, head=_HP_COMMIT)): CommandResult(
            exit_code=0, stdout="identical\n", stderr=""
        ),
        tuple(compare_argv(base=_CURRENT_TAG, head=_VPS_COMMIT)): CommandResult(
            exit_code=0, stdout="diverged\n", stderr=""
        ),
        tuple(compare_argv(base=_STALE_TAG, head=_VPS_COMMIT)): CommandResult(
            exit_code=0, stdout="ahead\n", stderr=""
        ),
    }
    return _Runner(results=results)


def _repo(*, tmp_path: Path, factories: dict[str, object], default: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                _PLUGIN_NAME: {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"default_factory": default, "factories": factories},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return repo


def _two_factory_repo(*, tmp_path: Path) -> Path:
    return _repo(
        tmp_path=tmp_path,
        default="hp",
        factories={
            "hp": {"server": _HP_SERVER, "bin": _HP_BIN},
            "vps": {"server": _VPS_SERVER, "bin": _VPS_BIN},
        },
    )


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.\n",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="The dispatched slice is verified green.",
    )


def _args(*, repo: Path, factory: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(repo=str(repo), factory=factory, fabro_bin="fabro")


def _records(*, journal_path: Path) -> list[dict[str, object]]:
    if not journal_path.exists():
        return []
    text = journal_path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def test_an_empty_selection_is_answered_without_any_read(tmp_path: Path) -> None:
    """The drain reaches the wall on every pass that finds no ready work.

    Grading there would spend a paginated forge round trip and one engine round
    trip per configured target on a pass that was never going to dispatch.
    """
    repo = _two_factory_repo(tmp_path=tmp_path)
    runner = _Runner(results={})
    journal_path = tmp_path / "journal.jsonl"

    refusal = gate.fabro_currency_refusal(
        args=_args(repo=repo),
        repo=repo,
        items=[],
        journal=JournalFile(path=journal_path),
        runner=runner,
        now=_NOW,
    )

    assert refusal is None
    assert runner.calls == []
    assert _records(journal_path=journal_path) == []


def test_the_production_seams_resolve_when_no_caller_supplies_them(tmp_path: Path) -> None:
    """The wall passes neither runner nor clock, so the defaults ARE production.

    Driven on an empty selection so the defaults are constructed without spending
    a real forge or engine call — the construction is the claim, not the reads.
    """
    repo = _two_factory_repo(tmp_path=tmp_path)

    refusal = gate.fabro_currency_refusal(
        args=_args(repo=repo),
        repo=repo,
        items=[],
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
    )

    assert refusal is None


def test_the_clock_seam_reports_a_timezone_aware_utc_instant() -> None:
    """A naive instant would make every calendar-day comparison here ill-defined."""
    instant = gate.currency_instant()

    assert instant.tzinfo is not None
    assert instant.utcoffset() == timezone.utc.utcoffset(None)


def test_a_current_target_is_admitted_with_no_refusal_and_no_refusal_record(
    tmp_path: Path,
) -> None:
    repo = _repo(
        tmp_path=tmp_path, default="hp", factories={"hp": {"server": _HP_SERVER, "bin": _HP_BIN}}
    )
    journal_path = tmp_path / "journal.jsonl"

    refusal = gate.fabro_currency_refusal(
        args=_args(repo=repo),
        repo=repo,
        items=[_item(item_id="bd-ib-aaa")],
        journal=JournalFile(path=journal_path),
        runner=_two_target_runner(),
        now=_NOW,
    )

    assert refusal is None
    assert _records(journal_path=journal_path) == []


def test_a_serverless_target_is_surfaced_non_blocking_and_costs_no_read(
    tmp_path: Path,
) -> None:
    """Neither refused nor silently passed over.

    Refusing would impose an admission condition on every repository that has not
    declared a factory; passing in silence would read as a currency reading that
    was taken and succeeded, which is the fail-open the gate exists to close.
    """
    repo = _repo(tmp_path=tmp_path, default="local", factories={"local": {}})
    runner = _Runner(results={})
    journal_path = tmp_path / "journal.jsonl"

    refusal = gate.fabro_currency_refusal(
        args=_args(repo=repo),
        repo=repo,
        items=[_item(item_id="bd-ib-aaa")],
        journal=JournalFile(path=journal_path),
        runner=runner,
        now=_NOW,
    )

    assert refusal is None
    assert runner.calls == []
    records = _records(journal_path=journal_path)
    assert [record["stage"] for record in records] == [gate.FABRO_CURRENCY_UNEVALUATED_STAGE]
    assert records[0]["blocking"] is False
    assert records[0]["reason"] == "no-declared-server"
    assert records[0]["target"] == "local"


def test_each_configured_target_is_evaluated_against_its_own_serving_commit(
    tmp_path: Path,
) -> None:
    """One current target beside one stale one, selected by per-item pin.

    A gate reading a single fleet-global surrogate returns ONE verdict for both,
    and that is indistinguishable from a correct gate on any fixture where the two
    targets agree — which is why they are made to disagree here.
    """
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
    from livespec_orchestrator_beads_fabro.store import append_work_item, record_dispatch_factory

    repo = _two_factory_repo(tmp_path=tmp_path)
    config = store_config(repo=repo)
    hp_item = _item(item_id="bd-ib-hp")
    vps_item = _item(item_id="bd-ib-vps")
    append_work_item(path=config, item=hp_item)
    append_work_item(path=config, item=vps_item)
    record_dispatch_factory(path=config, work_item_id=hp_item.id, factory="hp")
    record_dispatch_factory(path=config, work_item_id=vps_item.id, factory="vps")
    journal_path = tmp_path / "journal.jsonl"

    refusal = gate.fabro_currency_refusal(
        args=_args(repo=repo),
        repo=repo,
        items=[hp_item, vps_item],
        journal=JournalFile(path=journal_path),
        runner=_two_target_runner(),
        now=_NOW,
    )

    assert refusal is not None
    # ONE refusal, and it names the STALE target rather than the current one.
    records = _records(journal_path=journal_path)
    assert [record["target"] for record in records] == ["vps"]
    assert records[0]["condition"] == CONDITION_OUT_OF_WINDOW
    assert records[0]["stage"] == gate.FABRO_CURRENCY_REFUSED_STAGE
    assert "vps" in refusal
    assert _VPS_COMMIT in refusal
    assert _STALE_TAG in refusal


def test_an_explicit_factory_choice_overrides_every_items_recorded_pin(
    tmp_path: Path,
) -> None:
    """`--factory vps` evaluates vps even for an item pinned to hp.

    The same precedence the dispatch itself applies, so the gate cannot admit a
    target the dispatch is not going to use.
    """
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
    from livespec_orchestrator_beads_fabro.store import append_work_item, record_dispatch_factory

    repo = _two_factory_repo(tmp_path=tmp_path)
    config = store_config(repo=repo)
    hp_item = _item(item_id="bd-ib-hp")
    append_work_item(path=config, item=hp_item)
    record_dispatch_factory(path=config, work_item_id=hp_item.id, factory="hp")
    journal_path = tmp_path / "journal.jsonl"

    refusal = gate.fabro_currency_refusal(
        args=_args(repo=repo, factory="vps"),
        repo=repo,
        items=[hp_item],
        journal=JournalFile(path=journal_path),
        runner=_two_target_runner(),
        now=_NOW,
    )

    assert refusal is not None
    assert [record["target"] for record in _records(journal_path=journal_path)] == ["vps"]


def test_a_recorded_pin_does_not_hide_the_factory_a_fresh_dispatch_would_reach(
    tmp_path: Path,
) -> None:
    """The item records the CURRENT factory; the repository's default is the stale one.

    The route is undecided at the wall — recovery routing assigns it AFTER the
    pre-dispatch wall this gate runs inside — so the gate has to grade every
    target the selection could reach, which is the recorded pin a resume would
    take AND the placement a fresh dispatch would take. Grading only the pin
    admits a dispatch onto exactly the unadmissible engine this gate exists to
    refuse: the fresh dispatch is submitted to `dispatcher.default_factory` while
    the gate reported on a factory the item merely used to run on.

    The fixture is inverted relative to every other case here — the PIN is
    current and the DEFAULT is stale — because that is the only arrangement a
    pin-only gate fails on. With the stale target pinned, a pin-only gate and a
    union gate both refuse, and the fixture would agree with the defect.
    """
    from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
    from livespec_orchestrator_beads_fabro.store import append_work_item, record_dispatch_factory

    repo = _repo(
        tmp_path=tmp_path,
        default="vps",
        factories={
            "hp": {"server": _HP_SERVER, "bin": _HP_BIN},
            "vps": {"server": _VPS_SERVER, "bin": _VPS_BIN},
        },
    )
    config = store_config(repo=repo)
    hp_item = _item(item_id="bd-ib-hp")
    append_work_item(path=config, item=hp_item)
    record_dispatch_factory(path=config, work_item_id=hp_item.id, factory="hp")
    journal_path = tmp_path / "journal.jsonl"

    refusal = gate.fabro_currency_refusal(
        args=_args(repo=repo),
        repo=repo,
        items=[hp_item],
        journal=JournalFile(path=journal_path),
        runner=_two_target_runner(),
        now=_NOW,
    )

    assert refusal is not None
    assert "vps" in refusal
    assert [record["target"] for record in _records(journal_path=journal_path)] == ["vps"]
