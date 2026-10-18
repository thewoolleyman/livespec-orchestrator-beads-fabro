"""The sandbox prepare chain installs the worktree-discipline pack (bd-ib-tlmq3m).

This is the PREPARE-CHAIN half of the work-item; the sibling
`test_dispatcher_sandbox_worktree_pack_recipe` owns the recipe-identity half.

WHY THE OVERLAY AND NOT `workflow.toml`. Two independent reasons, and either
alone would decide it. The committed run config is FORKED per repository --
`_dispatcher_paths.workflow_toml` resolves a dispatch target's own copy ahead of
the bundled one -- so a prepare step written into the bundle covers one consumer
and silently omits the rest, which is the rationale
`_dispatcher_default_branch_fetch` and `_dispatcher_factory_provenance` already
record. And `constraints.md`'s fleet-toolchain-literal ban SCANS that payload, so
the invocation cannot be spelled there at all: it has to arrive from the
fleet-defaults module, which is where `SANDBOX_CHECKOUT_PROVISION_DEFAULT` lives.

WHY A MATERIALIZED STEP IS LATE ENOUGH TO WORK. Every Dispatcher-materialized
block is appended AFTER the committed chain, which is a requirement here rather
than an accident: `install-worktree-pack` runs `uv run python -m
livespec_dev_tooling.install_worktree_pack`, so it needs the committed
`uv sync --all-groups` to have populated the sandbox virtual environment first.
A step rendered ahead of that would fail in preparation and kill every dispatch.

THE PREMISE IS READ OFF THE ARM AND NEVER THE VALUE, which is the discipline
`fleet_toolchain_is_the_host_janitor_premise` states for the host venue: "a
repository is free to declare exactly the fleet convention, and a value
comparison would then read a deliberate declaration as an inheritance". The
consequence is asserted below and is deliberate -- a repository that DECLARES its
own sandbox check suite is declaring that it owns what runs in that venue, and it
owns that venue's provisioning with it, exactly as the host-janitor fleet default
provisions INSIDE its own suite. Imposing this recipe on such a repository would
run a recipe it may not have and fail the prepare step.

EVERY CASE RESOLVES A REAL CONTRACT from `.livespec.jsonc`-shaped text through
`build_plan` rather than hand-building a resolution. A hand-built `FleetDefault`
would satisfy the premise assertions while saying nothing about the resolution a
dispatch actually carries, which is the "instrument pointed at the wrong
population" trap AGENTS.md catalogues.

THE IMPORTLIB PATTERN is the repository's established form for an
extract-to-a-new-module slice: the module is imported INSIDE the test body behind
a genuine `is_file()` assertion, so the Red fails on an assertion rather than
dying at collection. The overlay parameter is guarded the same way, by asserting
the signature carries it -- an unexpected-keyword `TypeError` is not an assertion
either.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_overlay
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    SANDBOX_CHECKOUT_PROVISION_DEFAULT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_resolver import (
    Declared,
    FleetDefault,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_schema import (
    SANDBOX_CHECK_SUITE_FIELD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_overlay import (
    DispatchOverlay,
    materialize_dispatch_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_record import RecordedDispatch
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import WorkflowPayload
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import VaultSecret
from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_worktree_pack"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_sandbox_worktree_pack.py"
)
_OVERLAY_PARAMETER = "provision_worktree_pack"
_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
_OAUTH_TOKEN = "oauth-token-value-that-must-not-leak"
_GITHUB_TOKEN = "github-token-value-that-must-not-leak"
_MATERIALIZED_MARKER = "# --- Dispatcher-materialized"
_ITEM_ID = "bd-ib-packless"
_SYNC_STEP = "uv sync --all-groups"
# The vault key the sink-double control stores under. A NAME, never a value —
# which is the half of that control worth asserting.
_PROBE_VAULT_KEY = "LIVESPEC_DISPATCH_PACK_PROBE_REFERENCE"
# A repository that declares the compat pin and nothing about its check suite, so
# the sandbox gate resolves to this fleet's own default.
_INHERITING_CONFIG = '{"livespec-orchestrator-beads-fabro": {"compat": {"pinned": "master"}}}'


def _declaring_config() -> str:
    """The same repository DECLARING its own sandbox check suite.

    THE KEY IS BUILT FROM THE SCHEMA'S OWN LOOKUP PATH rather than spelled, and
    that is not tidiness — a hand-spelled key is how this fixture was wrong on its
    first writing. `dispatcher.janitor_check_suite` reads as the obvious name and
    the schema's path is the NESTED `dispatcher.janitor.check_suite`, so the
    declaration landed somewhere nothing resolves: the field fell through to its
    fleet default and the negative case asserted nothing at all while looking
    exactly like a negative case that worked.

    The declared VALUE is deliberately this fleet's own invocation, which is what
    makes the case able to fail for its real reason: a premise comparing values
    rather than resolution arms would read this deliberate declaration as an
    inheritance and pass.
    """
    declaration: dict[str, Any] = {}
    cursor = declaration
    segments = SANDBOX_CHECK_SUITE_FIELD.path.split(".")
    for segment in segments[:-1]:
        cursor[segment] = {}
        cursor = cursor[segment]
    cursor[segments[-1]] = list(SANDBOX_CHECKOUT_PROVISION_DEFAULT)
    declaration["compat"] = {"pinned": "master"}
    return json.dumps({"livespec-orchestrator-beads-fabro": declaration})


_DECLARING_CONFIG = _declaring_config()


def test_the_prepare_chain_runs_the_pack_installer_as_a_materialized_step(
    tmp_path: Path,
) -> None:
    """The rendered run config carries the installer as a Dispatcher-rendered step.

    Scoped to the MATERIALIZED region deliberately: a committed step cannot be
    mistaken for a rendered one, which is the claim that makes this reach a
    repository carrying its own forked `workflow.toml`.

    The argv is compared against the fleet default rather than against a spelled
    command, so a renderer that invoked some other installer fails here.
    """
    rendered = _rendered(tmp_path=tmp_path, provision=True)

    assert _materialized_pack_argv(rendered=rendered) == [list(SANDBOX_CHECKOUT_PROVISION_DEFAULT)]


def test_the_step_is_rendered_after_the_committed_chain_that_provisions_its_venv(
    tmp_path: Path,
) -> None:
    """It lands after `uv sync`, because the installer runs through that venv.

    This is the ordering claim no single-step execution can see. The committed
    region is the text BEFORE the first materialized marker, so the assertion is
    about position in the submitted config rather than about a convention someone
    remembered.
    """
    committed = (
        _COMMITTED_WORKFLOW_TOML
        + "\n[[run.prepare.steps]]\n"
        + f"script = {json.dumps(_SYNC_STEP)}\n"
    )

    rendered = _rendered(tmp_path=tmp_path, provision=True, committed_text=committed)

    assert rendered.index(_SYNC_STEP) < rendered.index(_MATERIALIZED_MARKER)
    assert _materialized_pack_argv(rendered=rendered) == [list(SANDBOX_CHECKOUT_PROVISION_DEFAULT)]


def test_a_repository_whose_sandbox_gate_is_its_own_is_imposed_no_recipe(
    tmp_path: Path,
) -> None:
    """No premise, no step — and the rest of the overlay is untouched.

    The second assertion is what says the absence is this block's rather than a
    refusal of the whole overlay, which would read identically at the first.
    """
    rendered = _rendered(tmp_path=tmp_path, provision=False)

    assert _materialized_pack_argv(rendered=rendered) == []
    assert _MATERIALIZED_MARKER in rendered


def test_the_premise_is_the_resolution_arm_and_not_the_resolved_value(
    tmp_path: Path,
) -> None:
    """An inheriting repository provisions; a declaring one does not.

    Both arms are resolved from real `.livespec.jsonc` text, and the declaring one
    declares EXACTLY the fleet invocation — so a premise that compared values
    would answer `True` for both, and this case is what catches it.

    THE FIRST ASSERTION IS A CONTROL on the fixture rather than on the premise:
    it establishes that the declaring config actually reached `Declared`. Without
    it a declaration keyed on a path the schema does not carry falls through to
    the fleet default, and the negative case below then passes for the wrong
    reason — which is exactly how this fixture was wrong on its first writing.
    """
    inheriting = _plan(repo=tmp_path, config_text=_INHERITING_CONFIG).integration
    declaring = _plan(repo=tmp_path, config_text=_DECLARING_CONFIG).integration
    attribute = SANDBOX_CHECK_SUITE_FIELD.attribute

    assert isinstance(
        declaring.resolutions[attribute], Declared
    ), f"the declaring fixture did not reach Declared: {declaring.resolutions[attribute]}"
    assert isinstance(inheriting.resolutions[attribute], FleetDefault)

    premise = _module().fleet_toolchain_is_the_sandbox_gate_premise

    assert premise(resolved=inheriting)
    assert not premise(resolved=declaring)


def test_a_direct_caller_that_asks_for_nothing_renders_the_overlay_it_always_did(
    tmp_path: Path,
) -> None:
    """The parameter DEFAULTS off, so no other dispatch sees a byte of it.

    The block renderer is also asserted directly, because "renders nothing" is a
    claim about bytes that an overlay assertion alone attributes to the overlay
    rather than to this block.
    """
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
    )

    assert rendered is not None
    assert _materialized_pack_argv(rendered=rendered) == []
    assert _module().sandbox_worktree_pack_prepare_steps_block(provision=False) == ""


def test_the_dispatch_path_itself_decides_the_premise_from_its_resolved_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one caller a real dispatch goes through actually forwards the premise.

    Without this the overlay would render the step only when asked and nothing
    would ask — a renderer that is correct and never reached, which every
    assertion above is satisfied by. The premise is asserted to be read off the
    plan's ALREADY-RESOLVED contract rather than re-read at this seam, which is
    the resolve-once-project-everywhere discipline the integration contract
    states.

    Both arms sit in ONE case on purpose: a leg that forwarded a constant rather
    than the resolution would satisfy either arm alone, and the two readings have
    to disagree for the forwarding to mean anything.
    """
    assert _MODULE_PATH.is_file(), f"the sandbox pack provisioning has no module at {_MODULE_PATH}"

    assert (
        _forwarded_premise(tmp_path=tmp_path, monkeypatch=monkeypatch, text=_INHERITING_CONFIG)
        is True
    )
    assert (
        _forwarded_premise(tmp_path=tmp_path, monkeypatch=monkeypatch, text=_DECLARING_CONFIG)
        is False
    )


def _forwarded_premise(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> object | None:
    """What the dispatch leg actually hands the materializer for one declaration.

    The materializer is replaced by a recorder rather than driven for real: the
    claim under test is which value this leg DERIVES, and a real materialization
    would mint credentials and write a mode-600 file to establish nothing further.

    The sink assertion is what makes the stub's reach checkable: with the
    materializer replaced, the leg must store NOTHING, so a recording sink whose
    stored set is empty says the measurement was taken on the derivation alone.
    """
    recorder: dict[str, object] = {}

    def _record(**kwargs: Any) -> str | None:
        recorder.update(kwargs)
        return None

    monkeypatch.setattr(_dispatcher_loop_overlay, "materialize_overlay", _record)
    overlay = _overlay(tmp_path=tmp_path, text=text)

    assert materialize_dispatch_overlay(overlay=overlay) is None
    assert (
        _OVERLAY_PARAMETER in recorder
    ), f"the dispatch leg forwarded no {_OVERLAY_PARAMETER}: {sorted(recorder)}"
    assert isinstance(overlay.secret_sink, _Sink)
    assert overlay.secret_sink.stored == []
    return recorder[_OVERLAY_PARAMETER]


def test_the_recording_vault_sink_double_can_observe_a_store() -> None:
    """The control on the double above: an EMPTY stored set has to mean something.

    A sink that silently dropped every call would satisfy the emptiness assertion
    in `_forwarded_premise` whatever the leg did, which is the "instrument
    incapable of returning a hit" trap. This is the positive case for the
    instrument — and it also pins that the record carries the secret's NAME and
    never its value.
    """
    sink = _Sink()

    assert (
        sink.set(
            secret=VaultSecret(
                env_name="GITHUB_TOKEN",
                secret_name=_PROBE_VAULT_KEY,
                value=_GITHUB_TOKEN,
            )
        )
        is None
    )
    assert sink.stored == [_PROBE_VAULT_KEY]
    assert _GITHUB_TOKEN not in sink.stored


def _module() -> ModuleType:
    """The new module, behind the genuine assertion that it exists at all."""
    assert _MODULE_PATH.is_file(), f"the sandbox pack provisioning has no module at {_MODULE_PATH}"
    return importlib.import_module(_MODULE)


def _rendered(*, tmp_path: Path, provision: bool, committed_text: str | None = None) -> str:
    """Render the overlay, after asserting it ACCEPTS the premise at all.

    The signature assertion is what keeps the Red honest: without it, a build with
    no such parameter fails on an unexpected-keyword `TypeError` rather than on an
    assertion naming what is missing.
    """
    parameters = inspect.signature(render_run_config_overlay).parameters
    assert (
        _OVERLAY_PARAMETER in parameters
    ), f"render_run_config_overlay takes no {_OVERLAY_PARAMETER}: {sorted(parameters)}"

    rendered = render_run_config_overlay(
        committed_text=committed_text or _COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_OAUTH_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        **{_OVERLAY_PARAMETER: provision},
    )
    assert rendered is not None
    return rendered


def _materialized_pack_argv(*, rendered: str) -> list[list[str]]:
    """Every pack-installing step the DISPATCHER rendered, as the ARGV a shell gets.

    Tokenized rather than string-matched: the argv is what decides which installer
    runs, while the QUOTING is `shlex.join`'s business, so asserting the string
    would pin a decision this block does not own.

    Selected by the installer RECIPE rather than by the whole command line, so a
    step that reached the right recipe through some other runner is still returned
    and then fails the argv comparison with an actionable diff.

    Only TOML BASIC strings are decoded. Several sibling blocks render their script
    as a multi-line LITERAL string (`script = '''`), which carries no JSON at all
    on that line, and this block's own script is `json.dumps`-ed — so the narrowing
    cannot hide the step being looked for. The positive cases above are what hold
    that claim: if the renderer ever stopped emitting a basic string, they fail
    rather than reporting an absence.

    THE RECIPE IS LOOKED FOR IN THE SCRIPT TEXT, AND THAT IS WHAT SELECTS A STEP;
    tokenizing happens only to the step already selected. A sibling block's basic
    string may carry a QUOTED HEREDOC whose payload is arbitrary text — the
    proof-grade block ships the record reader's own source that way
    (bd-ib-kcq6pu) — and `shlex` cannot model a heredoc, so an apostrophe in that
    payload raises `No closing quotation` and this helper would report an
    instrument failure for every case rather than an answer about this block. A
    payload the shell never lexes must not decide whether this scan can run.
    """
    materialized = rendered[rendered.index(_MATERIALIZED_MARKER) :]
    recipe = SANDBOX_CHECKOUT_PROVISION_DEFAULT[-1]
    prefix = 'script = "'
    argv: list[list[str]] = []
    for line in materialized.splitlines():
        if not line.startswith(prefix):
            continue
        script = json.loads(line[len("script = ") :])
        assert isinstance(script, str)
        if recipe not in script:
            continue
        argv.append(shlex.split(script))
    return argv


def _plan(*, repo: Path, config_text: str) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id=_ITEM_ID,
        workflow_toml=repo / "wf.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor-co",
        config_text=config_text,
        default_branch="master",
        fabro_factory_name="hp",
    )


def _overlay(*, tmp_path: Path, text: str) -> DispatchOverlay:
    """One dispatch's overlay inputs, carrying a REAL resolved plan.

    Everything except the plan is the minimum the leg needs to reach its single
    `materialize_overlay` call: that call is stubbed in the case above, so nothing
    here is read for its own sake.
    """
    return DispatchOverlay(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        recorded=_recorded(tmp_path=tmp_path, text=text),
        overlay_file=tmp_path / "overlay.toml",
        dispatch_id="0f6d2f1a9f1c4f0b9d3a2c5e7b8a4d61",
        token=lambda: _GITHUB_TOKEN,
        secret_sink=_Sink(),
    )


def _recorded(*, tmp_path: Path, text: str) -> RecordedDispatch:
    return RecordedDispatch(
        plan=_plan(repo=tmp_path, config_text=text),
        committed_workflow=tmp_path / "wf.toml",
        payload=WorkflowPayload(
            payload_dir=tmp_path / "payload",
            graph=tmp_path / "payload" / "workflow.fabro",
            timeouts=NodeTimeouts(configured={}, stall_seconds=900, stall_layer="workflow-default"),
            node_seconds={},
            node_commands={},
        ),
        git_author=GitAuthor(name="Factory", email="factory@example.invalid"),
        comments=(),
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="active",
        title="A sandbox that never installed the worktree-discipline pack",
        description="Its janitor exited 127 on a pack member that was never there.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-18T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


@dataclass(kw_only=True)
class _Sink:
    """A vault sink that RECORDS rather than stores, so a reached store is visible.

    It records instead of raising deliberately. A raising double asserts "this is
    never reached" only for the one call site that happens to run, and says nothing
    when the leg is changed to store somewhere else first; a recording one lets the
    caller assert the stored set is EMPTY, which is the same claim stated positively
    and checkable at the point that cares.
    """

    stored: list[str] = field(default_factory=list)

    def set(self, *, secret: VaultSecret) -> str | None:
        """Record the secret NAME — never its value — and store nothing."""
        self.stored.append(secret.secret_name)
        return None
