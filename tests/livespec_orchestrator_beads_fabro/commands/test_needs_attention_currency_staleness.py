"""The ambient dispatcher plugin-currency staleness lane.

Covers the surfacing half of the v089 self-update re-base: the fact reports how
far the operator-provisioned build lags the latest release, it carries no
blocking authority of any kind, and every reading it cannot complete emits
nothing rather than a guessed lag.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._needs_attention_currency_staleness import (
    CurrencyStalenessSeams,
    currency_staleness_items,
    version_lag,
)
from livespec_runtime.attention_item import AttentionItem, validate_attention_item_id

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"


def _build(*, root: Path, name: str, version: str | None) -> Path:
    install = root / name
    install.mkdir(parents=True)
    if version is not None:
        _ = (install / "plugin.json").write_text(
            json.dumps({"name": _PLUGIN_NAME, "version": version}), encoding="utf-8"
        )
    return install


def _marketplace(*, root: Path, tip_version: str | None, ref: str) -> Path:
    """A marketplace registry naming a clone checked out at `ref`."""
    clone = _build(root=root, name="marketplace-clone", version=tip_version)
    record = root / "known_marketplaces.json"
    _ = record.write_text(
        json.dumps({_PLUGIN_NAME: {"source": {"ref": ref}, "installLocation": str(clone)}}),
        encoding="utf-8",
    )
    return record


def _seams(
    *,
    tmp_path: Path,
    provisioned: str | None,
    tip: str | None,
    ref: str = "release",
) -> CurrencyStalenessSeams:
    return CurrencyStalenessSeams(
        plugin_root=_build(root=tmp_path, name="provisioned", version=provisioned),
        marketplace_record=_marketplace(root=tmp_path, tip_version=tip, ref=ref),
    )


def _items(
    *,
    tmp_path: Path,
    provisioned: str | None,
    tip: str | None,
    ref: str = "release",
) -> list[AttentionItem]:
    return currency_staleness_items(
        project_root=tmp_path / "repo",
        repo="repo",
        seams=_seams(tmp_path=tmp_path, provisioned=provisioned, tip=tip, ref=ref),
    )


def test_a_lagging_provisioned_build_surfaces_a_non_blocking_staleness_fact(
    tmp_path: Path,
) -> None:
    """The fact states the lag, disclaims any gating authority, names the remedy."""
    seams = _seams(tmp_path=tmp_path, provisioned="0.95.0", tip="0.97.2")

    items = currency_staleness_items(project_root=tmp_path / "repo", repo="repo", seams=seams)

    assert len(items) == 1
    fact = items[0]
    assert fact.id == "hygiene:dispatcher-currency-staleness:repo"
    assert validate_attention_item_id(id=fact.id)
    assert fact.kind == "hygiene"
    assert "build 0.95.0 lags the latest release 0.97.2" in fact.summary
    assert "by 2 minor version steps." in fact.summary
    # The lag is a distance between identifiers; the lane reads no release
    # history, so it must not be read as a count of published releases.
    assert "not a count of releases published between them" in fact.summary
    # The contract's whole point: this fact is a trigger, never a gate.
    assert "does NOT gate or refuse a dispatch" in fact.summary
    assert "surfaced, never enforced" in fact.summary
    assert "committed dispatcher.minimum_release floor can refuse" in fact.summary
    # It composes with the passing-canary restart surfacing rather than replacing it.
    assert "composes with the passing-canary restart-is-due surfacing" in fact.summary
    assert "just adopt-orchestrator-build <clone> <build>" in fact.summary
    assert "claude plugin update" not in fact.summary
    assert fact.urgency == "low"
    assert fact.source_ref.repo == "repo"
    assert fact.source_ref.path == str(seams.plugin_root)
    assert fact.handoff.kind == "shell"
    assert "adopt-dispatcher-release" in fact.handoff.command
    assert "surfaced, never enforced" in fact.handoff.command
    assert "just adopt-orchestrator-build <clone> <build>" in fact.handoff.command
    assert "claude plugin update" not in fact.handoff.command


def test_a_single_step_behind_renders_the_singular_phrase(tmp_path: Path) -> None:
    items = _items(tmp_path=tmp_path, provisioned="0.97.1", tip="0.97.2")

    assert "by 1 patch version step." in items[0].summary


def test_a_rollover_reports_only_the_leading_differing_component(tmp_path: Path) -> None:
    """`0.97.5` to `0.98.1` is one minor step, never "minus four patch steps"."""
    items = _items(tmp_path=tmp_path, provisioned="0.97.5", tip="0.98.1")

    assert "by 1 minor version step." in items[0].summary
    assert "-4" not in items[0].summary


def test_a_major_step_and_an_unnamed_component_each_render(tmp_path: Path) -> None:
    """Beyond major/minor/patch the component is named positionally, not dropped."""
    major = _items(tmp_path=tmp_path / "major", provisioned="0.97.2", tip="1.0.0")
    deep = _items(tmp_path=tmp_path / "deep", provisioned="1.2.3.4", tip="1.2.3.6")

    assert "by 1 major version step." in major[0].summary
    assert "by 2 component-4 version steps." in deep[0].summary


def test_a_current_build_and_an_ahead_build_each_emit_nothing(tmp_path: Path) -> None:
    """An attention list is not a dashboard: no lag, no item."""
    assert _items(tmp_path=tmp_path / "current", provisioned="0.97.2", tip="0.97.2") == []
    assert _items(tmp_path=tmp_path / "ahead", provisioned="0.98.0", tip="0.97.2") == []


def test_a_shorter_identifier_is_padded_rather_than_treated_as_unorderable() -> None:
    assert version_lag(provisioned="1.2", tip="1.2.1") == (0, 0, 1)
    assert version_lag(provisioned="1.3", tip="1.2.9") is None


def test_a_pre_release_suffix_orders_on_its_release_components() -> None:
    assert version_lag(provisioned="0.97.1-rc.1", tip="0.97.2") == (0, 0, 1)


def test_an_unorderable_identifier_yields_no_lag_rather_than_a_guessed_one(
    tmp_path: Path,
) -> None:
    """A sentinel ordering is what turns an unreadable version into a wrong answer."""
    assert version_lag(provisioned="main", tip="0.97.2") is None
    assert version_lag(provisioned="0.97.1", tip="latest") is None
    assert _items(tmp_path=tmp_path, provisioned="main", tip="0.97.2") == []


def test_an_unreadable_endpoint_emits_nothing_on_either_side(tmp_path: Path) -> None:
    """The undetermined reading is owned by the admission gate and the adoption lane."""
    assert _items(tmp_path=tmp_path / "no-build", provisioned=None, tip="0.97.2") == []
    assert _items(tmp_path=tmp_path / "no-tip", provisioned="0.95.0", tip=None) == []
    # A marketplace clone at any ref other than `release` is not the release tip.
    assert (
        _items(tmp_path=tmp_path / "wrong-ref", provisioned="0.95.0", tip="0.97.2", ref="master")
        == []
    )
