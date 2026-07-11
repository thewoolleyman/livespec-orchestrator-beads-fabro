"""Read-only-cache guards for the dark-factory Dispatcher (Slice 3).

Two cache-hostile behaviors are hardened into CLEAN no-ops so the
dispatcher runs correctly from a read-only, flattened plugin cache (the
adopter path), per the self-contained plugin dispatch contract in
SPECIFICATION/contracts.md — operations that presuppose a writable
orchestrator checkout or fleet context degrade cleanly:

(a) The post-merge self-update canary SKIPS cleanly — a deliberate
    `self-update-skipped` journal entry naming the missing writable
    orchestrator checkout — when `_plugin_root()` is not a writable git
    checkout of the orchestrator (a flattened cache has no `.git`),
    instead of attempting a promotion and leaning on the fail-open `0jxs`
    supervisor to SWALLOW the resulting error. The fail-open backstop is
    KEPT; the guard merely removes a never-applicable code path from
    masking behind it.

(b) The fleet-manifest sibling-clone projection renders an EMPTY sibling
    set when no fleet manifest is fetchable (no `gh`, no manifest, a
    non-fleet adopter), so the dispatch PROCEEDS rather than refusing it.

These drive the production functions with NO injected probe: guard (a)
points `_plugin_root()` at a non-git directory via `CLAUDE_PLUGIN_ROOT`
so the real read-only-cache detection runs end-to-end; guard (b) stubs
`_fetch_fleet_manifest_text` to the no-manifest signal. The canary itself
is never launched (the self-machinery hang-guard) — the self-merge path
short-circuits at the read-only-cache guard before any canary subprocess,
proven by the ABSENCE of every canary/promotion journal stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    resolve_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import SiblingClones
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    self_update_after_merge,
)


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


# A merged-file list that touches the dispatcher's OWN command package (a
# self-merge): without the read-only-cache guard this stages + canaries
# the candidate.
_SELF_MERGE_PATHS = (
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/dispatcher.py",
)


def test_self_update_skips_cleanly_on_a_read_only_plugin_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A flattened read-only plugin cache has no `.git`: point the plugin
    # root at a non-git directory so the production read-only-cache
    # detection runs end-to-end and finds no writable orchestrator
    # checkout to promote into. No runner/poster is injected — the guard
    # returns before either default seam could be consulted.
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(cache_root))
    journal = _RecordingJournal()
    self_update_after_merge(
        work_item_id="livespec-impl-beads-roc",
        merged_paths=_SELF_MERGE_PATHS,
        candidate_bin=str(cache_root / "scripts" / "bin" / "dispatcher.py"),
        scratch_root=str(tmp_path / "scratch"),
        repo=tmp_path,
        journal=journal,
    )
    stages = [record["stage"] for record in journal.records]
    # A CLEAN skip — not a swallowed `self-update-error`, and NONE of the
    # canary/promotion stages (the canary never ran).
    assert "self-update-skipped" in stages
    assert "self-update-error" not in stages
    assert "self-update-promoted" not in stages
    assert "self-update-kept-last-known-good" not in stages
    # The skip reason names the read-only-cache cause (a writable
    # orchestrator checkout), not the not-a-self-merge cause.
    skip = next(record for record in journal.records if record["stage"] == "self-update-skipped")
    assert "checkout" in str(skip["reason"]).lower()


def test_resolve_sibling_clones_is_empty_when_no_fleet_manifest_is_fetchable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No fleet manifest is fetchable (no `gh`, no manifest, a non-fleet
    # adopter): the projection renders an EMPTY sibling set rather than
    # an actionable-refusal string the dispatch aborts on.
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: None,
    )
    resolved = resolve_sibling_clones(repo=tmp_path / "adopter-repo")
    assert isinstance(resolved, SiblingClones)
    assert resolved.repos == ()
