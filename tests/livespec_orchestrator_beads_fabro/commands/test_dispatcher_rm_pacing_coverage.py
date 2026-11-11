"""Coverage controls for deletion-pacing defaults and unpaced operation."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_rm_pacing import DeletionPacer


class _Journal:
    def append(self, *, record: dict[str, object]) -> None:
        _ = record


def test_default_busy_collection_defers_and_zero_interval_is_unpaced(tmp_path: Path) -> None:
    journal: list[dict[str, object]] = []
    pacer = DeletionPacer(repo=tmp_path, now_epoch=lambda: 7.0)

    assert not pacer.permit(
        factory="petri",
        run_id="ended",
        caller="ended-run-collection",
        has_running_run=True,
        collection=True,
        journal=journal,
    )
    assert journal[0]["next_deletion_may_start_at"] == 7.0

    (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"factories":'
        '{"petri":{"defer_collection_while_active":false,"rm_min_interval_seconds":0}}}}}',
        encoding="utf-8",
    )
    assert pacer.permit(
        factory="petri",
        run_id="cancelled",
        caller="stall-cancel",
        has_running_run=True,
        collection=False,
        journal=journal,
    )
    assert not pacer.permit(
        factory="other",
        run_id="other-ended",
        caller="ended-run-collection",
        has_running_run=True,
        collection=True,
        journal=_Journal(),
    )


def test_worktrees_share_their_factory_deletion_interval(tmp_path: Path) -> None:
    common = tmp_path / "shared" / ".git"
    worktree = common / "worktrees" / "pacing"
    worktree.mkdir(parents=True)
    first_repo = tmp_path / "first"
    second_repo = tmp_path / "second"
    for repo in (first_repo, second_repo):
        repo.mkdir()
        (repo / ".git").write_text(f"gitdir: {worktree}\n", encoding="utf-8")
        (repo / ".livespec.jsonc").write_text(
            '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"factories":'
            '{"petri":{"defer_collection_while_active":false,"rm_min_interval_seconds":60}}}}}',
            encoding="utf-8",
        )

    journal: list[dict[str, object]] = []
    assert DeletionPacer(repo=first_repo, now_epoch=lambda: 9.0).permit(
        factory="petri",
        run_id="first",
        caller="stall-cancel",
        has_running_run=True,
        collection=False,
        journal=journal,
    )
    assert not DeletionPacer(repo=second_repo, now_epoch=lambda: 9.0).permit(
        factory="petri",
        run_id="second",
        caller="stale-item-reap",
        has_running_run=True,
        collection=False,
        journal=journal,
    )

    assert journal[-1]["next_deletion_may_start_at"] == 69.0


def test_idle_factory_deletions_still_observe_the_host_wide_interval(tmp_path: Path) -> None:
    (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro":{"dispatcher":{"factories":'
        '{"petri":{"rm_min_interval_seconds":60}}}}}',
        encoding="utf-8",
    )
    journal: list[dict[str, object]] = []
    pacer = DeletionPacer(repo=tmp_path, now_epoch=lambda: 9.0)

    assert pacer.permit(
        factory="petri",
        run_id="first",
        caller="stale-item-reap",
        has_running_run=False,
        collection=False,
        journal=journal,
    )
    assert not pacer.permit(
        factory="petri",
        run_id="second",
        caller="wall-budget-cancel",
        has_running_run=False,
        collection=False,
        journal=journal,
    )
    assert journal[-1]["next_deletion_may_start_at"] == 69.0


def test_pacing_state_handles_primary_and_incomplete_git_metadata(tmp_path: Path) -> None:
    primary = tmp_path / "primary"
    primary.mkdir()
    (primary / ".git").mkdir()
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / ".git").write_text("", encoding="utf-8")
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / ".git").write_text("not-a-gitdir\n", encoding="utf-8")
    non_worktree = tmp_path / "non-worktree"
    non_worktree.mkdir()
    ordinary_gitdir = tmp_path / "ordinary-gitdir"
    ordinary_gitdir.mkdir()
    (non_worktree / ".git").write_text(f"gitdir: {ordinary_gitdir}\n", encoding="utf-8")
    no_git_metadata = tmp_path / "no-git-metadata"
    no_git_metadata.mkdir()

    for index, repo in enumerate((primary, incomplete, unrelated, non_worktree, no_git_metadata)):
        assert DeletionPacer(repo=repo, now_epoch=lambda: 4.0).permit(
            factory="petri",
            run_id=f"run-{index}",
            caller="wall-budget-cancel",
            has_running_run=True,
            collection=False,
            journal=[],
        )
