"""Integration-tier acceptance for Scenario 95's re-based plugin-currency check.

Binds `SPECIFICATION/scenarios.md` "Scenario 95 — Dispatch admission surfaces
plugin-currency staleness rather than blocking on it" through the REAL
dispatch-admission preflight, `_dispatcher_loop_selection.prepare`: the real
`JournalFile` on disk, the real committed-floor read out of `.livespec.jsonc`,
the real plugin-root resolution through `CLAUDE_PLUGIN_ROOT`, and the real
`build_attention` composition for the fact the first scenario requires. Only the
`CommandRunner` that shells out to `git ls-remote` is stood in — the gate, the
floor, the journal and the lane are all production code.

Driving `prepare` rather than the gate function alone is what makes the
no-refusal claims observable AT ADMISSION: the scenario's first and third
behaviours are about a dispatch NOT being refused, and a gate-level assertion
that a decision carries no refusal cannot show that the admission path actually
went on to load work. `prepare` returning items is that proof; `prepare`
returning `None` is the refusal.

The below-floor case is the control that keeps the other two honest. Without it,
"the dispatch was not refused" would be indistinguishable from "this preflight
can no longer refuse anything at all" — which is precisely the over-correction
the v089 re-base had to avoid when it removed the ambient block.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_selection, needs_attention
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_minimum_release_floor as _floor_module,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_staleness_gate as gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._needs_attention_currency_staleness import (
    CurrencyStalenessSeams,
)
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.needs_attention import SpecNextOutput

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_RELEASE_SHA = "9532efb793bc1d2c3a4b5c6d7e8f901234567890"
# A flattened-cache build id: the gate reads the plugin root's NAME as the
# executing build identity, and a name that is not a sha prefix is the
# unobservable case the third scenario exercises.
_BUILD_ID = "b6e4012cafed"
_CURRENCY_FACT_ID = "hygiene:dispatcher-currency-staleness:repo"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Runner:
    """Stands in for the one shelling-out seam: the `git ls-remote` ref probes."""

    results: dict[tuple[str, ...], CommandResult]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="missing"))


def _release_head_runner() -> _Runner:
    """Both remote heads answer with a sha that is NOT the executing build id."""
    head = CommandResult(exit_code=0, stdout=f"{_RELEASE_SHA}\trefs/heads/release\n", stderr="")
    return _Runner(results={gate.latest_release_ref_argv(): head, gate.master_ref_argv(): head})


def _install_runner(*, monkeypatch: pytest.MonkeyPatch, runner: _Runner) -> None:
    monkeypatch.setattr(gate, "ShellCommandRunner", lambda: runner)


def _manifest(*, root: Path, name: str, version: str) -> Path:
    build = root / name
    build.mkdir(parents=True)
    _ = (build / "plugin.json").write_text(
        json.dumps({"name": _PLUGIN_NAME, "version": version}), encoding="utf-8"
    )
    return build


def _provisioned_build(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, version: str
) -> Path:
    """Provision the executing payload the way the Claude install does.

    The plugin root is exported as `CLAUDE_PLUGIN_ROOT`, so the production
    `plugin_root()` resolution runs for real rather than being patched out.
    """
    build = _manifest(root=tmp_path / "cache", name=name, version=version)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(build))
    _register_install(tmp_path=tmp_path, monkeypatch=monkeypatch, build=build)
    return build


def _register_install(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, build: Path) -> None:
    """Register `build` as what this test's repo resolves, in a hermetic install registry.

    `prepare()` consults the host install registry for the registered-install
    currency finding (bd-ib-h3mm); pointing it at a tmp registry keeps these
    scenarios off the real HOME and lets a test choose which build the repo
    resolves relative to the one the session executes.
    """
    record = tmp_path / "installed_plugins.json"
    _ = record.write_text(
        json.dumps(
            {
                "plugins": {
                    f"{_PLUGIN_NAME}@{_PLUGIN_NAME}": [
                        {"projectPath": str(tmp_path / "repo"), "installPath": str(build)}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_dispatcher_loop_selection, "default_install_record", lambda: record)


def _repo(*, tmp_path: Path, minimum_release: str | None = None) -> Path:
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text("[workflow]\n", encoding="utf-8")
    dispatcher: dict[str, object] = {}
    if minimum_release is not None:
        dispatcher["minimum_release"] = minimum_release
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
                    "dispatcher": dispatcher,
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return repo


def _prepare(*, repo: Path) -> tuple[object, Path]:
    journal = repo / "tmp" / "journal.jsonl"
    args = argparse.Namespace(
        workflow=str(repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"),
        journal=str(journal),
        repo=str(repo),
    )
    return _dispatcher_loop_selection.prepare(args=args, repo=repo), journal


def _records(*, journal: Path) -> list[dict[str, object]]:
    """Every case in this module journals, so an absent file is a real failure.

    Deliberately NOT guarded into an empty list: a missing journal would then be
    indistinguishable from a journal carrying no blocking record, which is the
    exact claim two of these three cases rest on.
    """
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line]


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _snapshot(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    provisioned: Path,
    marketplace_record: Path,
) -> list[AttentionItem]:
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    monkeypatch.setattr(
        needs_attention,
        "default_currency_staleness_seams",
        lambda: CurrencyStalenessSeams(
            plugin_root=provisioned, marketplace_record=marketplace_record
        ),
    )
    return build_attention(project_root=repo, repo_name="repo", include_hygiene=False)


def _marketplace_at_release(*, tmp_path: Path, tip_version: str) -> Path:
    clone = _manifest(root=tmp_path / "marketplace", name="clone", version=tip_version)
    record = tmp_path / "marketplace" / "known_marketplaces.json"
    _ = record.write_text(
        json.dumps({_PLUGIN_NAME: {"source": {"ref": "release"}, "installLocation": str(clone)}}),
        encoding="utf-8",
    )
    return record


def test_scenario95_a_release_published_after_session_start_does_not_refuse_the_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The homelab 2026-08-29 case: the session was current at start, then a release landed.

    No `dispatcher.minimum_release` floor is committed, so the preflight has no
    blocking authority over currency at all: admission proceeds, the journal
    carries a non-blocking record and no blocking one, and the lag is carried by
    the needs-attention fact instead.
    """
    provisioned = _provisioned_build(
        tmp_path=tmp_path, monkeypatch=monkeypatch, name=_BUILD_ID, version="0.95.0"
    )
    _install_runner(monkeypatch=monkeypatch, runner=_release_head_runner())
    repo = _repo(tmp_path=tmp_path)

    prepared, journal = _prepare(repo=repo)

    assert prepared is not None
    records = _records(journal=journal)
    assert [record["stage"] for record in records] == ["dispatcher-staleness-warning"]
    assert all(record["blocking"] is False for record in records)
    assert not any("minimum-release-refused" in str(record["stage"]) for record in records)

    attention = _snapshot(
        repo=repo,
        monkeypatch=monkeypatch,
        provisioned=provisioned,
        marketplace_record=_marketplace_at_release(tmp_path=tmp_path, tip_version="0.97.2"),
    )

    currency = [item for item in attention if item.id == _CURRENCY_FACT_ID]
    assert len(currency) == 1
    assert "build 0.95.0 lags the latest release 0.97.2" in currency[0].summary
    assert "by 2 minor version steps." in currency[0].summary
    assert "does NOT gate or refuse a dispatch" in currency[0].summary


def test_scenario95_a_release_below_the_committed_floor_refuses_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one blocking currency form: a deliberate operator floor, named in the refusal."""
    _ = _provisioned_build(
        tmp_path=tmp_path, monkeypatch=monkeypatch, name=_BUILD_ID, version="0.97.1"
    )
    _install_runner(monkeypatch=monkeypatch, runner=_release_head_runner())
    # In this scenario the PROVISIONED build is the one executing. That used to
    # follow from CLAUDE_PLUGIN_ROOT alone; the floor now judges the retained
    # payload, so the scenario states which tree that is.
    monkeypatch.setattr(
        _floor_module,
        "executing_payload_root",
        lambda: Path(os.environ["CLAUDE_PLUGIN_ROOT"]),
    )
    repo = _repo(tmp_path=tmp_path, minimum_release="0.98.0")

    prepared, journal = _prepare(repo=repo)

    assert prepared is None
    records = _records(journal=journal)
    assert [record["stage"] for record in records] == ["dispatcher-minimum-release-refused"]
    assert records[0]["blocking"] is True
    detail = str(records[0]["detail"])
    assert "0.97.1 is below the committed dispatcher.minimum_release floor 0.98.0" in detail
    assert "restart before dispatching" in detail


def test_scenario95_unobservable_currency_is_recorded_undetermined_and_does_not_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ "Could not tell" gets its own stage so it can never read back as "current"."""
    _ = _provisioned_build(
        tmp_path=tmp_path, monkeypatch=monkeypatch, name="short", version="0.95.0"
    )
    runner = _release_head_runner()
    _install_runner(monkeypatch=monkeypatch, runner=runner)
    repo = _repo(tmp_path=tmp_path)

    prepared, journal = _prepare(repo=repo)

    assert prepared is not None
    records = _records(journal=journal)
    assert [record["stage"] for record in records] == ["dispatcher-currency-undetermined"]
    assert records[0]["blocking"] is False
    assert "could not establish the executing build identity" in str(records[0]["detail"])
    assert "Dispatch proceeds." in str(records[0]["detail"])
    # An unestablishable identity short-circuits BEFORE any network probe, so
    # the deadlock case cannot be re-entered through a slow or absent remote.
    assert gate.latest_release_ref_argv() not in runner.calls


def test_scenario95_a_session_executing_an_older_build_than_its_registered_install_is_surfaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 2026-09-06 stale-session case (bd-ib-h3mm): surfaced with its own stage, never refused.

    The session executes the build it bound at start while the repository's
    registered install has since moved on; both the ambient release lag and the
    registered-install lag are journaled non-blocking, and admission proceeds.
    """
    _ = _provisioned_build(
        tmp_path=tmp_path, monkeypatch=monkeypatch, name=_BUILD_ID, version="0.95.0"
    )
    registered = _manifest(root=tmp_path / "registered", name="6edebb0b0c50", version="0.97.2")
    _register_install(tmp_path=tmp_path, monkeypatch=monkeypatch, build=registered)
    _install_runner(monkeypatch=monkeypatch, runner=_release_head_runner())
    repo = _repo(tmp_path=tmp_path)

    prepared, journal = _prepare(repo=repo)

    assert prepared is not None
    records = _records(journal=journal)
    assert [record["stage"] for record in records] == [
        "dispatcher-staleness-warning",
        "dispatcher-registered-install-lag",
    ]
    assert all(record["blocking"] is False for record in records)
    detail = str(records[1]["detail"])
    assert "executes dispatcher plugin build 0.95.0" in detail
    assert "resolves build 0.97.2" in detail
    assert "Restart the session" in detail
