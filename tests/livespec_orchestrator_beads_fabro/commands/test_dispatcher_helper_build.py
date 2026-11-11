"""Which build a dispatch's helper programs are fetched from, and the refusal before claim.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"Helper programs are fetched in the sandbox from the dispatching build's own
commit", and the scenario "A build commit the forge does not have is refused
before claim". The identity read and the forge probe are exercised here against a
registry, a tree and a runner of the test's own, so nothing reaches the network:
this module is the one the suite-wide hermetic stub leaves unpatched.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_build as build
from livespec_orchestrator_beads_fabro.commands import _dispatcher_pre_dispatch_wall as wall
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_PLUGIN_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_COMMIT = "37e012335ed23ecba9bbcbb829e0fc90f2fdaf3b"
_OTHER_COMMIT = "5be0e21eac36fde34b20225146d2fa53f4fcfb4b"
_REPOSITORY = "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"
_EXIT_PRECONDITION_ERROR = 3


@dataclass
class _Runner:
    """A scripted runner: each call takes the next answer and records its argv."""

    answers: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list[list[str]])
    envs: list[Mapping[str, str | None] | None] = field(
        default_factory=list[Mapping[str, str | None] | None]
    )

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, stdin)
        self.calls.append(argv)
        self.envs.append(env)
        return self.answers.pop(0)


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _registry(*, path: Path, install: Path, commit: str | None) -> Path:
    entry: dict[str, str] = {"projectPath": "/repos/governed", "installPath": str(install)}
    if commit is not None:
        entry["gitCommitSha"] = commit
    _ = path.write_text(json.dumps({"plugins": {_PLUGIN_KEY: [entry]}}), encoding="utf-8")
    return path


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="bug",
        status="ready",
        title="Fetch the helper programs from the dispatching build",
        description="A dispatch whose build commit the forge lacks is refused before claim.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_the_identity_is_the_install_record_naming_the_executing_tree(tmp_path: Path) -> None:
    """A cache install is no checkout, so its commit is the record's, and no git is run."""
    tree = tmp_path / "cache" / "37e012335ed2"
    tree.mkdir(parents=True)
    runner = _Runner(answers=[])

    source = build.read_helper_source(
        runner=runner,
        environ={},
        payload_root=tree,
        install_record=_registry(path=tmp_path / "installed.json", install=tree, commit=_COMMIT),
    )

    assert source == build.HelperSource(repository=_REPOSITORY, commit=_COMMIT)
    assert runner.calls == []


def test_a_retained_payload_takes_the_commit_of_the_install_it_was_copied_from(
    tmp_path: Path,
) -> None:
    """The copy aside is unregistered; the recorded install root is what the record names."""
    install = tmp_path / "cache" / "5be0e21eac36"
    install.mkdir(parents=True)
    payload = tmp_path / "retained"
    payload.mkdir()

    source = build.read_helper_source(
        runner=_Runner(answers=[]),
        environ={"LIVESPEC_INSTALLED_PLUGIN_ROOT": str(install)},
        payload_root=payload,
        install_record=_registry(
            path=tmp_path / "installed.json", install=install, commit=_OTHER_COMMIT
        ),
    )

    assert source == build.HelperSource(repository=_REPOSITORY, commit=_OTHER_COMMIT)


def test_a_source_checkout_falls_back_to_its_own_head(tmp_path: Path) -> None:
    """A checkout's `.claude-plugin/` tree is identified by `HEAD`, read where it sits."""
    tree = tmp_path / "checkout" / ".claude-plugin"
    tree.mkdir(parents=True)
    runner = _Runner(answers=[_ok(stdout=f".claude-plugin/\n{_COMMIT}\n")])

    source = build.read_helper_source(
        runner=runner,
        environ={},
        payload_root=tree,
        install_record=_registry(path=tmp_path / "installed.json", install=tree, commit=None),
    )

    assert source == build.HelperSource(repository=_REPOSITORY, commit=_COMMIT)
    assert runner.calls == [["git", "-C", str(tree), "rev-parse", "--show-prefix", "HEAD"]]


@pytest.mark.parametrize(
    "answer",
    [
        _ok(stdout=f"\n{_COMMIT}\n"),
        _ok(stdout=f"some/other/dir/\n{_COMMIT}\n"),
        CommandResult(exit_code=128, stdout="", stderr="fatal: not a git repository"),
        _ok(stdout=".claude-plugin/\n   \n"),
    ],
    ids=["checkout-top", "enclosing-repository", "no-repository", "no-head"],
)
def test_a_tree_that_is_no_plugin_checkout_has_no_identity(
    tmp_path: Path, answer: CommandResult
) -> None:
    """An enclosing repository's `HEAD` is not this build's commit, so nothing is named."""
    tree = tmp_path / "cache" / "unregistered"
    tree.mkdir(parents=True)

    source = build.read_helper_source(
        runner=_Runner(answers=[answer]),
        environ={},
        payload_root=tree,
        install_record=tmp_path / "absent.json",
    )

    assert source is None


def test_an_absent_tree_has_no_identity_and_runs_no_git(tmp_path: Path) -> None:
    runner = _Runner(answers=[])

    source = build.read_helper_source(
        runner=runner,
        environ={},
        payload_root=tmp_path / "evicted",
        install_record=tmp_path / "absent.json",
    )

    assert source is None
    assert runner.calls == []


def test_the_probe_fetches_exactly_the_commit_into_a_scratch_bare_repository() -> None:
    """A commit-only fetch, never `ls-remote`, which matches ref names and not commits."""
    runner = _Runner(answers=[_ok(), _ok()])

    reading = build.probe_build_commit(
        source=build.HelperSource(repository=_REPOSITORY, commit=_COMMIT), runner=runner
    )

    assert reading == build.BuildReachReading(reachable=True, detail="")
    init, fetch = runner.calls
    assert init[:4] == ["git", "init", "--bare", "--quiet"]
    assert fetch[0:2] == ["git", "-C"]
    assert fetch[2] == init[4]
    assert fetch[3:] == [
        "fetch",
        "--quiet",
        "--depth=1",
        "--filter=tree:0",
        "--no-tags",
        _REPOSITORY,
        _COMMIT,
    ]
    assert runner.envs[1] == {"GIT_TERMINAL_PROMPT": "0"}


def test_a_commit_the_forge_does_not_serve_reads_unreachable_with_the_forge_words() -> None:
    runner = _Runner(
        answers=[
            _ok(),
            CommandResult(
                exit_code=128,
                stdout="",
                stderr=f"fatal: remote error: upload-pack: not our ref {_COMMIT}\n",
            ),
        ]
    )

    reading = build.probe_build_commit(
        source=build.HelperSource(repository=_REPOSITORY, commit=_COMMIT), runner=runner
    )

    assert reading == build.BuildReachReading(
        reachable=False, detail=f"fatal: remote error: upload-pack: not our ref {_COMMIT}"
    )


def test_a_probe_with_no_scratch_repository_reads_unreachable() -> None:
    runner = _Runner(answers=[CommandResult(exit_code=1, stdout="", stderr="disk full\n")])

    reading = build.probe_build_commit(
        source=build.HelperSource(repository=_REPOSITORY, commit=_COMMIT), runner=runner
    )

    assert reading == build.BuildReachReading(
        reachable=False, detail="no scratch repository: disk full"
    )
    assert len(runner.calls) == 1


def _journaled(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_an_unreachable_build_commit_is_refused_naming_the_commit_per_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scenario: the refusal and each item's journal record name the commit."""
    source = build.HelperSource(repository=_REPOSITORY, commit=_COMMIT)
    monkeypatch.setattr(build, "read_helper_source", lambda **_kwargs: source)
    monkeypatch.setattr(
        build,
        "probe_build_commit",
        lambda **_kwargs: build.BuildReachReading(reachable=False, detail="not our ref"),
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    refusal = build.helper_build_reach_refusal(
        items=[_item(item_id="bd-ib-one"), _item(item_id="bd-ib-two")], journal=journal
    )

    assert refusal is not None
    assert _COMMIT in refusal
    assert "not reachable on the forge" in refusal
    records = _journaled(path=journal.path)
    assert [record["work_item_id"] for record in records] == ["bd-ib-one", "bd-ib-two"]
    assert {record["stage"] for record in records} == {"helper-build-reach"}
    assert {record["commit"] for record in records} == {_COMMIT}
    assert {record["repository"] for record in records} == {_REPOSITORY}


def test_a_build_with_no_identity_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build, "read_helper_source", lambda **_kwargs: None)
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    refusal = build.helper_build_reach_refusal(items=[_item(item_id="bd-ib-one")], journal=journal)

    assert refusal is not None
    assert "records no commit" in refusal
    (record,) = _journaled(path=journal.path)
    assert record["commit"] is None
    assert record["stage"] == "helper-build-reach"


def test_a_reachable_build_commit_passes_and_journals_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = build.HelperSource(repository=_REPOSITORY, commit=_COMMIT)
    monkeypatch.setattr(build, "read_helper_source", lambda **_kwargs: source)
    monkeypatch.setattr(
        build,
        "probe_build_commit",
        lambda **_kwargs: build.BuildReachReading(reachable=True, detail=""),
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    assert (
        build.helper_build_reach_refusal(items=[_item(item_id="bd-ib-one")], journal=journal)
        is None
    )
    assert not journal.path.exists()


def test_an_empty_selection_reads_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The drain's idle pass reaches the wall with no items and must spend no forge read."""
    reads: list[object] = []
    monkeypatch.setattr(build, "read_helper_source", lambda **kwargs: reads.append(kwargs))

    assert (
        build.helper_build_reach_refusal(items=[], journal=JournalFile(path=tmp_path / "j")) is None
    )
    assert reads == []


def test_the_wall_refuses_an_unreachable_build_before_any_later_row_or_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row sits in the pre-dispatch wall, whose every refusal lands before admission."""
    for cheaper in (
        "out_of_enum_factory_safety_refusal",
        "implementation_pr_override_refusal",
        "acp_node_override_refusal",
        "session_headroom_screen_refusal",
        "app_reach_refusal",
    ):
        monkeypatch.setattr(wall, cheaper, lambda **_kwargs: None)

    later_rows: list[object] = []
    monkeypatch.setattr(wall, "fabro_currency_refusal", lambda **kwargs: later_rows.append(kwargs))
    source = build.HelperSource(repository=_REPOSITORY, commit=_COMMIT)
    monkeypatch.setattr(build, "read_helper_source", lambda **_kwargs: source)
    monkeypatch.setattr(
        build,
        "probe_build_commit",
        lambda **_kwargs: build.BuildReachReading(reachable=False, detail="not our ref"),
    )
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    args = argparse.Namespace(repo=str(tmp_path), workflow_name=None)

    exit_code = wall.pre_dispatch_wall_exit(
        args=args, repo=tmp_path, items=[_item(item_id="bd-ib-one")], journal=journal
    )

    assert exit_code == _EXIT_PRECONDITION_ERROR
    assert later_rows == []
    (record,) = _journaled(path=journal.path)
    assert record["commit"] == _COMMIT
