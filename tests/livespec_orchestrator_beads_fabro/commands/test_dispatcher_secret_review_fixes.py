"""Regression coverage for the accepted native-secret review findings.

These cases bind the failure modes found across the two review rounds: server
rejections must be scrubbed before they are shortened, references must stay
stable across rotations, malformed channel declarations must fail closed,
factory authentication must precede vault writes, and residual detection must
search the exact JSON/TOML rendering that the overlay renderer emits.
"""

from __future__ import annotations

import inspect
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_io_fabro_launcher as launcher_module,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop as loop_module
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_overlay as overlay_module
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_watch_poll as poll_module,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_contract import (
    resolve_integration_contract,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_declaration import (
    declaration_from_config_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_wall_budget import (
    DEFAULT_RUN_WALL_BUDGET,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    COMMITTED_RUN_CONFIG_IMAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SECRET_CHANNEL_INLINE_OVERLAY,
    SECRET_CHANNEL_NATIVE_SECRETS,
    RoutedOverlay,
    SecretChannelRefusal,
    VaultSecret,
    resolve_secret_channel,
    route_secrets_through_vault,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_vault import FabroVaultSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_window import (
    DEFAULT_STALL_WINDOW,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import LivenessSample
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog_observation import (
    ObservedRun,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroRunSummary

_REVIEW_VAULT_KEY = "LIVESPEC_DISPATCH_REVIEW_GITHUB_TOKEN"


@dataclass(kw_only=True)
class _RejectingRunner:
    """A vault command runner that echoes the submitted value in its failure."""

    rejection: str

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv, cwd, timeout_seconds, env, stdin
        return CommandResult(exit_code=2, stdout="", stderr=self.rejection)


@dataclass(kw_only=True)
class _SignallingRunner:
    """A successful vault runner that announces its first invocation."""

    entered: threading.Event

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv, cwd, timeout_seconds, env, stdin
        self.entered.set()
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _AliveSequence:
    """The launch thread's liveness across two watchdog discovery polls."""

    alive: list[bool]

    def is_alive(self) -> bool:
        return self.alive.pop(0)


def _route(*, text: str, value_name: str, scope: str) -> RoutedOverlay | SecretChannelRefusal:
    """Call the routing seam across the Red interface transition.

    Before the fix the seam has no launch scope; after it, the same helper passes
    the scope. Keeping that compatibility here makes Red fail on the behavioural
    assertion (shared keys), rather than on an unexpected-keyword ``TypeError``.
    """
    route = cast(
        "Callable[..., RoutedOverlay | SecretChannelRefusal]",
        route_secrets_through_vault,
    )
    kwargs: dict[str, object] = {
        "overlay_text": text,
        "channel": SECRET_CHANNEL_NATIVE_SECRETS,
        "env_names": (value_name,),
    }
    if "scope" in inspect.signature(route_secrets_through_vault).parameters:
        kwargs["scope"] = scope
    return route(**kwargs)


def test_rejection_is_scrubbed_before_its_excerpt_is_taken() -> None:
    """A long echoed credential cannot leave a recognizable truncated prefix."""
    value = "long-credential-canary-" + ("v" * 600)
    runner = _RejectingRunner(rejection=f"server rejected {value}: invalid value")
    sink = FabroVaultSink(
        fabro_bin="/usr/local/bin/fabro",
        server_url=None,
        runner=runner,
        cwd=Path("/workspace/repo"),
    )
    message = cast(
        "str",
        sink.set(
            secret=VaultSecret(
                env_name="GITHUB_TOKEN",
                secret_name=_REVIEW_VAULT_KEY,
                value=value,
            )
        ),
    )
    assert "long-credential-canary-" not in message
    assert "<value withheld>" in message


def test_rotated_launches_reuse_the_same_vault_reference() -> None:
    """Credential rotation changes the vault value, not the immutable bundle."""
    first = _route(
        text=f"[environments.sandbox.env]\nGITHUB_TOKEN = {json.dumps('first-value')}\n",
        value_name="GITHUB_TOKEN",
        scope="dispatch-first",
    )
    second = _route(
        text=f"[environments.sandbox.env]\nGITHUB_TOKEN = {json.dumps('second-value')}\n",
        value_name="GITHUB_TOKEN",
        scope="dispatch-second",
    )
    assert isinstance(first, RoutedOverlay)
    assert isinstance(second, RoutedOverlay)
    assert first.secrets[0].secret_name == second.secrets[0].secret_name
    assert first.overlay_text == second.overlay_text
    assert first.secrets[0].value != second.secrets[0].value


@pytest.mark.parametrize("declared", ["", None, 7, []])
def test_an_explicitly_malformed_channel_declaration_refuses(declared: object) -> None:
    """Only an absent declaration defaults; an explicit bad value cannot inline."""
    resolved = resolve_secret_channel(
        block={"factories": {"candidate": {"secret_channel": declared}}},
        factory="candidate",
    )
    assert isinstance(resolved, SecretChannelRefusal)
    assert "secret_channel" in resolved.message
    assert SECRET_CHANNEL_INLINE_OVERLAY in resolved.message


def test_factory_authentication_precedes_vault_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh dev-token factory is logged in before its first secret store."""
    events: list[str] = []
    plan = SimpleNamespace(
        review_fix_visit_cap=4,
        branch="feat/review-fix",
        # The whole-run wall budget this dispatch resolved. A REAL budget rather
        # than an omission for the reason the resolved contract below is real:
        # the watch loop grades every running poll against it, so a double that
        # carries none fails on its own shape rather than on the ORDER this case
        # is about.
        run_wall_budget=DEFAULT_RUN_WALL_BUDGET,
        # A REAL resolved contract rather than a bare `object()`. The overlay leg
        # now reads one more answer off it — whether the gitignored
        # worktree-discipline pack is a premise of this sandbox — and a double that
        # carries no resolutions fails on its own shape rather than on the ORDER
        # this case is about (bd-ib-tlmq3m).
        integration=resolve_integration_contract(
            declaration=declaration_from_config_text(config_text="{}")
        ),
        acp_nodes=None,
        fabro_factory_name="candidate",
        # That factory's declared catalog environment, which keys the overlay's
        # env table. None is a factory declaring none and is the neutral answer
        # here for the same reason the image source below is: this case is about
        # the ORDER of the factory login against the first vault store, and a
        # double missing the field fails on its absence rather than on that
        # order (bd-ib-kyeor4).
        fabro_factory_environment=None,
        # The resolved client build the dispatch hands the materializer, which
        # decides how the written config names its graph. None is the pinned
        # posture and the neutral one for this case: it is about the ORDER of
        # the factory login against the first vault store, and a double missing
        # the field would fail on its absence rather than on that order.
        fabro_version=None,
        # The resolved sandbox image source, neutral here for the same reason:
        # this case is about that order, not about which image the launch
        # carries, so the double carries the no-declaration answer.
        sandbox_image=COMMITTED_RUN_CONFIG_IMAGE,
    )
    recorded = SimpleNamespace(
        plan=plan,
        committed_workflow=tmp_path / "workflow.toml",
        comments=(),
        payload=SimpleNamespace(graph=None),
        git_author=object(),
    )
    monkeypatch.setattr(loop_module, "record_dispatch", lambda **_: recorded)
    monkeypatch.setattr(loop_module.selfup, "github_token_supplier", lambda: lambda: "token")
    monkeypatch.setattr(loop_module, "read_ratified_lessons", lambda **_: ())
    monkeypatch.setattr(loop_module, "minijinja_openers_in_goal_sources", lambda **_: ())
    # The overlay PROJECTION's own inputs, patched on `_dispatcher_loop_overlay`
    # because that is the module that calls them. The factory login and the
    # vault sink stay on `_dispatcher_loop`, which is what keeps this case's
    # ordering claim meaningful: the two events it compares are raised from
    # opposite sides of that seam.
    monkeypatch.setattr(overlay_module, "resume_checkout_for", lambda **_: None)
    monkeypatch.setattr(overlay_module, "publish_branch_for", lambda **_: "feat/review-fix")
    monkeypatch.setattr(overlay_module, "contract_prompt_variables", lambda **_: {})
    monkeypatch.setattr(overlay_module, "journaled_proof_rendering", lambda **_: "")
    monkeypatch.setattr(
        loop_module,
        "fabro_vault_sink_for_plan",
        lambda **_: SimpleNamespace(release_launch_guard=lambda: None),
    )
    monkeypatch.setattr(loop_module, "run_id", lambda: "dispatch-secret-review")
    monkeypatch.setattr(loop_module, "release_pre_run_claim_if_needed", lambda **_: None)
    monkeypatch.setattr(
        loop_module,
        "run_fabro_factory_auth_login",
        lambda **_: events.append("factory-auth"),
        raising=False,
    )

    def materialize(**_: object) -> str:
        events.append("vault-materialization")
        return "stop after observing the ordering"

    monkeypatch.setattr(overlay_module, "materialize_overlay", materialize)
    outcome = loop_module.dispatch_one(
        args=SimpleNamespace(),
        repo=tmp_path,
        # The four fields the dispatch reads off a work-item on the way to the
        # overlay: the id for the publish branch, the title and acceptance
        # criteria the publication-metadata renderer shapes into the pull
        # request's title and body, and the description the proof-grade
        # projection resolves this item's `factory_captured` assertions from
        # (bd-ib-kcq6pu). This control is about ORDERING, so the values are
        # placeholders -- but they have to be PRESENT, because each renderer
        # reads a typed `WorkItem` and a defensive read there would hide a real
        # wiring fault behind an empty title or an empty assertion set.
        item=SimpleNamespace(
            id="wi-secret-review",
            title="a secret-review ordering control",
            description="",
            acceptance_criteria=None,
        ),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        janitor=None,
    )
    assert outcome.status == "failed"
    assert events == ["factory-auth", "vault-materialization"]


def test_residual_guard_matches_the_overlay_renderers_exact_encoding() -> None:
    """Encoded newlines, controls and non-ASCII cannot evade residual refusal."""
    value = "first line\nsecond line\x01snowman:\u2603"
    bundle = (
        "[environments.sandbox.env]\n"
        f"GITHUB_TOKEN = {json.dumps(value)}\n"
        "\n[[run.prepare.steps]]\n"
        f"script = {json.dumps(f'use duplicated credential {value}')}\n"
    )
    result = _route(text=bundle, value_name="GITHUB_TOKEN", scope="dispatch-residual")
    assert isinstance(result, SecretChannelRefusal)
    assert "resolved value still appears" in result.message
    assert value not in result.message


def test_same_factory_vault_writes_wait_for_the_prior_worker_snapshot() -> None:
    """A second launch cannot replace any stable key before the first snapshots all."""
    server = "https://hp-xubuntu.example.invalid:32278/review-round-two"
    first_entered = threading.Event()
    second_entered = threading.Event()
    first = FabroVaultSink(
        fabro_bin="fabro",
        server_url=server,
        runner=_SignallingRunner(entered=first_entered),
        cwd=Path("/workspace/first"),
    )
    second = FabroVaultSink(
        fabro_bin="fabro",
        server_url=server,
        runner=_SignallingRunner(entered=second_entered),
        cwd=Path("/workspace/second"),
    )
    secret = VaultSecret(
        env_name="GITHUB_TOKEN",
        secret_name=_REVIEW_VAULT_KEY,
        value="review-concurrency-canary",
    )
    assert first.set(secret=secret) is None
    assert first_entered.is_set()

    second_result: list[str | None] = []
    thread = threading.Thread(target=lambda: second_result.append(second.set(secret=secret)))
    thread.start()
    # The wait is only a negative observation; the positive release/join below
    # proves the thread was genuinely attempting the store rather than never run.
    second_was_blocked = not second_entered.wait(timeout=0.1)
    getattr(first, "release_launch_guard", lambda: None)()
    thread.join(timeout=2.0)
    getattr(second, "release_launch_guard", lambda: None)()

    assert second_was_blocked
    assert not thread.is_alive()
    assert second_result == [None]


def test_launch_guard_releases_only_after_the_worker_reports_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runnable is too early; running follows the candidate's vault snapshot."""
    assert "on_worker_running" in inspect.signature(WatchedFabroLauncher).parameters
    events: list[str] = []
    discovered = iter(
        (
            FabroRunSummary(
                run_id="01RUNNABLE",
                status_kind="runnable",
                goal=None,
                work_item_id="bd-ib-review",
                total_usd_micros=None,
            ),
            FabroRunSummary(
                run_id="01RUNNING",
                status_kind="running",
                goal=None,
                work_item_id="bd-ib-review",
                total_usd_micros=None,
            ),
        )
    )

    def discover(**_: object) -> ObservedRun:
        run = next(discovered)
        events.append(run.status_kind)
        # The poll's observation, which carries the run AND the record the
        # read returned; this double names no record, which is what the
        # listing route reports and what a per-run read carrying no running
        # instant reports.
        return ObservedRun(run=run, record=None)

    launcher = WatchedFabroLauncher(
        sleep=lambda _seconds: None,
        clock=lambda: 0.0,
        on_worker_running=lambda: events.append("released"),
    )
    monkeypatch.setattr(poll_module, "observed_run", discover)
    monkeypatch.setattr(
        poll_module,
        "stamped_attribution",
        lambda **kwargs: kwargs["attribution"],
    )
    monkeypatch.setattr(
        launcher_module,
        "liveness_sample",
        lambda **_: LivenessSample(last_event_epoch=None, observed_at=0.0),
    )
    _ = launcher._watch(  # noqa: SLF001 - exercises the exact snapshot-release boundary.
        plan=SimpleNamespace(
            repo=Path("/workspace/repo"),
            work_item_id="bd-ib-review",
            stall_window=DEFAULT_STALL_WINDOW,
            # The whole-run wall budget every running poll is graded against.
            # A REAL budget rather than an omission: the loop grades it before
            # the stall arm, so a double carrying none fails on its own shape
            # rather than on the release boundary this case is about.
            run_wall_budget=DEFAULT_RUN_WALL_BUDGET,
        ),
        runner=cast("CommandRunner", object()),
        journal=cast("JournalWriter", object()),
        thread=cast("threading.Thread", _AliveSequence(alive=[True, True, True, True, False])),
        # Never set: this run's `fabro run` call is still outstanding, so the
        # watch is governed by the alive sequence above exactly as before the
        # signal existed. The signal's own arm is covered in the watchdog
        # tests, against the launcher rather than this release boundary.
        run_returned=threading.Event(),
        port=cast("FabroPort", object()),
    )

    assert events == ["runnable", "running", "released"]


def test_dispatch_wires_the_vault_guard_to_the_worker_running_boundary() -> None:
    """The sink's held transaction reaches the production watched launcher."""
    source = inspect.getsource(loop_module._dispatch_one_locked)  # noqa: SLF001
    assert "on_worker_running=secret_sink.release_launch_guard" in source
    assert "secret_sink.release_launch_guard()" in source
