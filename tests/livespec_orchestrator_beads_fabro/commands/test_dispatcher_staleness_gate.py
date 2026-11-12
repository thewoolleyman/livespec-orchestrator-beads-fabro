"""Tests for the dispatcher's release-based plugin staleness gate."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_staleness_gate.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_staleness_gate"
_RELEASE_SHA = "9532efb793bc1d2c3a4b5c6d7e8f901234567890"
_MASTER_SHA = "8eb81fae1234567890abcdefabcdefabcdefabcd"
_NEWER_BUILD_SHA = "2164ff74e19f1a2b3c4d5e6f7890123456789abc"


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
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="missing"))


def _module() -> ModuleType:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _ls_remote(*, ref: str, sha: str) -> CommandResult:
    return CommandResult(exit_code=0, stdout=f"{sha}\t{ref}\n", stderr="")


def _checkout_head_argv(*, plugin_root: Path) -> tuple[str, ...]:
    return ("git", "-C", str(plugin_root), "rev-parse", "HEAD")


def test_unestablishable_build_identity_warns_and_proceeds_without_network(
    tmp_path: Path,
) -> None:
    """A plugin root that is neither a checkout nor a hex cache build id NEVER refuses.

    This is the bd-ib-n7ce4n deadlock case observed live on PR #927's CI: the
    container's `git -C <root> rev-parse HEAD` probe fails, the root's name is
    not a release-cache sha prefix, and the gate must warn + proceed WITHOUT
    touching the network — a staleness verdict cannot be proven, so dispatch
    MUST NOT be blocked.
    """
    module = _module()
    cache_root = tmp_path / "plugin"
    cache_root.mkdir()
    runner = _Runner(results={})

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root, runner=runner, cwd=tmp_path
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    assert decision.warnings[0].stage == module.CURRENCY_UNDETERMINED_STAGE
    assert "could not establish the executing build identity" in decision.warnings[0].detail
    assert "currency could not be determined" in decision.warnings[0].detail
    assert runner.calls == [_checkout_head_argv(plugin_root=cache_root)]


def test_short_non_hex_root_name_is_not_treated_as_a_build_id(tmp_path: Path) -> None:
    module = _module()
    cache_root = tmp_path / "abc"
    cache_root.mkdir()
    runner = _Runner(results={})

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root, runner=runner, cwd=tmp_path
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    assert "could not establish the executing build identity" in decision.warnings[0].detail
    assert runner.calls == [_checkout_head_argv(plugin_root=cache_root)]


def test_git_checkout_plugin_root_is_exempt_with_no_probes_or_warnings(
    tmp_path: Path,
) -> None:
    module = _module()
    checkout_root = tmp_path / "checkout"
    checkout_root.mkdir()
    runner = _Runner(
        results={
            _checkout_head_argv(plugin_root=checkout_root): CommandResult(
                exit_code=0,
                stdout=f"{_MASTER_SHA}\n",
                stderr="",
            ),
        }
    )

    decision = module.dispatcher_staleness_decision(
        plugin_root=checkout_root, runner=runner, cwd=tmp_path
    )

    assert decision.refusal is None
    assert decision.warnings == ()
    assert runner.calls == [_checkout_head_argv(plugin_root=checkout_root)]


def test_read_only_cache_build_predating_latest_release_warns_with_performable_remedy(
    tmp_path: Path,
) -> None:
    """The retired refusal. Ambient staleness carries the SAME remedy, non-blocking.

    Before the v089 re-base this was a blocking exit-3 refusal, which is what
    bricked a live session the moment a release was published mid-session. The
    remedy text is preserved because it was always right — only its authority
    to stop a dispatch is gone.
    """
    module = _module()
    cache_root = tmp_path / "b6e4012cafed"
    cache_root.mkdir()
    runner = _Runner(
        results={
            module.latest_release_ref_argv(): _ls_remote(
                ref="refs/heads/release",
                sha=_RELEASE_SHA,
            ),
            module.master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_RELEASE_SHA),
            module.release_comparison_argv(
                release_sha=_RELEASE_SHA,
                build_id="b6e4012cafed",
            ): CommandResult(exit_code=0, stdout="behind\n", stderr=""),
        }
    )

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root, runner=runner, cwd=tmp_path
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    assert "b6e4012cafed" in decision.warnings[0].detail
    assert _RELEASE_SHA[:12] in decision.warnings[0].detail
    assert "just adopt-orchestrator-build <clone> <build>" in decision.warnings[0].detail
    assert "claude plugin update" not in decision.warnings[0].detail


def test_read_only_cache_build_newer_than_latest_release_never_warns_that_it_lags(
    tmp_path: Path,
) -> None:
    """A release cache ahead of the latest release is not stale in the other direction."""
    module = _module()
    cache_root = tmp_path / _NEWER_BUILD_SHA[:12]
    cache_root.mkdir()
    assert hasattr(module, "release_comparison_argv")
    runner = _Runner(
        results={
            module.latest_release_ref_argv(): _ls_remote(
                ref="refs/heads/release",
                sha=_RELEASE_SHA,
            ),
            module.master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_RELEASE_SHA),
            module.release_comparison_argv(
                release_sha=_RELEASE_SHA,
                build_id=_NEWER_BUILD_SHA[:12],
            ): CommandResult(exit_code=0, stdout="ahead\n", stderr=""),
        }
    )

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root,
        runner=runner,
        cwd=tmp_path,
    )

    assert decision.refusal is None
    assert not [warning for warning in decision.warnings if "lags latest release" in warning.detail]


def test_read_only_cache_build_with_unavailable_comparison_never_claims_known_lag(
    tmp_path: Path,
) -> None:
    """An unobservable comparison is not evidence that the build lags the release."""
    module = _module()
    cache_root = tmp_path / _NEWER_BUILD_SHA[:12]
    cache_root.mkdir()
    runner = _Runner(
        results={
            module.latest_release_ref_argv(): _ls_remote(
                ref="refs/heads/release",
                sha=_RELEASE_SHA,
            ),
            module.master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_RELEASE_SHA),
            module.release_comparison_argv(
                release_sha=_RELEASE_SHA,
                build_id=_NEWER_BUILD_SHA[:12],
            ): CommandResult(exit_code=1, stdout="", stderr="gh: unavailable"),
        }
    )

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root,
        runner=runner,
        cwd=tmp_path,
    )

    assert decision.refusal is None
    assert not [warning for warning in decision.warnings if "lags latest release" in warning.detail]


def test_current_release_build_proceeds_when_master_is_ahead_and_warns_with_commit(
    tmp_path: Path,
) -> None:
    module = _module()
    cache_root = tmp_path / _RELEASE_SHA[:12]
    cache_root.mkdir()
    runner = _Runner(
        results={
            module.latest_release_ref_argv(): _ls_remote(
                ref="refs/heads/release",
                sha=_RELEASE_SHA,
            ),
            module.master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_MASTER_SHA),
            module.unreleased_dispatcher_commits_argv(
                release_sha=_RELEASE_SHA,
                master_sha=_MASTER_SHA,
            ): CommandResult(
                exit_code=0,
                stdout="8eb81fa chore: refactor dispatcher admission\n",
                stderr="",
            ),
        }
    )

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root, runner=runner, cwd=tmp_path
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    warning = decision.warnings[0].detail
    assert "8eb81fa chore: refactor dispatcher admission" in warning
    assert "a release must be cut before this code takes effect" in warning


def test_unreleased_master_build_proceeds_when_master_is_ahead_and_warns(
    tmp_path: Path,
) -> None:
    module = _module()
    cache_root = tmp_path / _MASTER_SHA[:12]
    cache_root.mkdir()
    runner = _Runner(
        results={
            module.latest_release_ref_argv(): _ls_remote(
                ref="refs/heads/release",
                sha=_RELEASE_SHA,
            ),
            module.master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_MASTER_SHA),
            module.unreleased_dispatcher_commits_argv(
                release_sha=_RELEASE_SHA,
                master_sha=_MASTER_SHA,
            ): CommandResult(
                exit_code=0,
                stdout="8eb81fa chore: refactor dispatcher admission\n",
                stderr="",
            ),
        }
    )

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root, runner=runner, cwd=tmp_path
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    assert "8eb81fa chore: refactor dispatcher admission" in decision.warnings[0].detail


def test_master_ahead_with_no_dispatcher_commits_names_master_sha(tmp_path: Path) -> None:
    module = _module()
    cache_root = tmp_path / _RELEASE_SHA[:12]
    cache_root.mkdir()
    runner = _Runner(
        results={
            module.latest_release_ref_argv(): _ls_remote(
                ref="refs/heads/release",
                sha=_RELEASE_SHA,
            ),
            module.master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_MASTER_SHA),
        }
    )

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root, runner=runner, cwd=tmp_path
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    assert _MASTER_SHA[:12] in decision.warnings[0].detail


def test_current_release_build_with_no_newer_release_does_not_fire(tmp_path: Path) -> None:
    module = _module()
    cache_root = tmp_path / _RELEASE_SHA[:12]
    cache_root.mkdir()
    runner = _Runner(
        results={
            module.latest_release_ref_argv(): _ls_remote(
                ref="refs/heads/release",
                sha=_RELEASE_SHA,
            ),
            module.master_ref_argv(): _ls_remote(ref="refs/heads/master", sha=_RELEASE_SHA),
        }
    )

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root, runner=runner, cwd=tmp_path
    )

    assert decision.refusal is None
    assert decision.warnings == ()


def test_unobservable_latest_release_probe_warns_without_refusing(tmp_path: Path) -> None:
    module = _module()
    cache_root = tmp_path / "beadf00dbeef"
    cache_root.mkdir()
    runner = _Runner(results={})

    decision = module.dispatcher_staleness_decision(
        plugin_root=cache_root, runner=runner, cwd=tmp_path
    )

    assert decision.refusal is None
    assert len(decision.warnings) == 1
    assert decision.warnings[0].stage == module.CURRENCY_UNDETERMINED_STAGE
    assert "could not inspect latest release" in decision.warnings[0].detail
    assert "currency could not be determined" in decision.warnings[0].detail
