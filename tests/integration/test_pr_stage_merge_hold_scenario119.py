"""Bind Scenario 119: a per-item merge hold publishes the pull request and merges only on release.

Binds `SPECIFICATION/scenarios.md` "Scenario 119 -- A per-item merge hold
publishes the pull request and merges only on release" and the per-item merge
hold clause of `SPECIFICATION/contracts.md`. The unit tier covers each seam of
the hold alone (`test_dispatcher_merge_hold_rendering`,
`test_drive_merge_hold_valve`, `test_needs_attention_merge_hold`); nothing walked
publish-under-hold through release in one arc, which is what this module does.

THE ARC IS ONE JOURNEY OVER REAL PARTS. A dispatch plan is built from a declared
`dispatcher.merge_mode` and the shipped run config, so the `merge_mode` and
`merge_hold` inputs the `pr` stage receives are the ones the Dispatcher would
render. The same plan is journaled through the production
`append_dispatch_id_record`. The shipped `pr` node bytes (taken through
`parse_dot_graph`, never retyped) then run under `bash` in a real git clone
against a `gh` stub, and the production `set-merge-hold:<id>:off` valve releases
the hold through the same stub. Only the forge CLI and the engine's run
inventory are stood in; both stages write one forge state file, so the release
acts on the very pull request the held stage published.

EVERY CLAIM CARRIES THE CONTROL THAT RETURNS THE OTHER ANSWER.

- "No auto-merge request was armed" is an ABSENCE, and it passes equally against
  a build that never arms anything. The control leg runs the same stage with
  `merge_hold` false and requires the arming call, bound to the proved head and
  carrying the declared strategy.
- "The release arms the journaled strategy" is only evidence if the
  configuration would have said something else. The repository's declaration is
  rewritten between dispatch and release, and the module asserts that a plan
  resolved from the REWRITTEN declaration would arm a different flag, so the
  squash the release arms cannot have come from configuration.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_merge_hold import (
    read_merge_held_work_item_ids,
    update_work_item_merge_hold,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
    append_dispatch_id_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    dispatch_fabro_run_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_binary_record import (
    EngineBinary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv import pr_arm_argv
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_head import (
    PROOF_HEAD_PROGRAM_FILENAME,
    proof_head_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PR_TITLE_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
    PUBLISH_HEAD_STATE_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    COMMITTED_RUN_CONFIG_IMAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_IMPLEMENT_GRAPH = _WORKFLOW_DIR / "workflow.fabro"
_RUN_CONFIG = _WORKFLOW_DIR / "workflow.toml"

_ITEM_ID = "bd-ib-xigh7o"
_BRANCH = f"feat/{_ITEM_ID}"
_PR_NUMBER = 4242
_HEAD = "1111111111111111111111111111111111111111"
_DISPATCH_MODE = "squash"
_RELEASE_TIME_MODE = "rebase"


def _declaration(*, merge_mode: str) -> str:
    return json.dumps(
        {
            "livespec-orchestrator-beads-fabro": {
                "connection": {
                    "tenant": "livespec-impl-beads",
                    "prefix": "bd",
                    "server_user": "livespec-impl-beads",
                    "database": "livespec-impl-beads",
                    "bd_path": "bd",
                    "fake": True,
                },
                "dispatcher": {"merge_mode": merge_mode},
            }
        }
    )


_STORE = StoreConfig(
    tenant="livespec-impl-beads",
    prefix="bd",
    server_user="livespec-impl-beads",
    database="livespec-impl-beads",
    bd_path="bd",
    fake=True,
)

# A forge stub reached through `PATH` (the stage) or by path (the valve's runner).
# One state file serves both, so a pull request published by the stage is the one
# the release acts on, and every argv is recorded: what was ASKED of the forge is
# itself under assertion. A single `--json` field prints bare, the way `--jq`
# renders it; a comma list prints the JSON object the valve's own view parses.
_GH_STUB = r"""#!%(python)s
import json, os, sys

state_path = os.environ["LIVESPEC_FAKE_FORGE"]
with open(state_path) as handle:
    state = json.load(handle)
argv = sys.argv[1:]
state["calls"].append(argv)


def finish(code=0):
    with open(state_path, "w") as handle:
        json.dump(state, handle)
    sys.exit(code)


verb = argv[1] if len(argv) > 1 else ""
armed = state["autoMergeRequest"]

if verb == "list":
    print(state["number"])
    finish()

if verb == "view":
    field = argv[argv.index("--json") + 1]
    values = {
        "number": state["number"],
        "state": state["state"],
        "headRefOid": state["head"],
        "isDraft": "true" if state["isDraft"] else "false",
        "autoMergeRequest": armed,
        "mergeCommit": None,
        "comments": state["comments"],
    }
    if "," in field:
        print(json.dumps({name: values[name] for name in field.split(",")}))
    elif field == "comments":
        print(json.dumps({"comments": state["comments"]}))
    elif field == "autoMergeRequest":
        print("" if armed is None else json.dumps(armed))
    elif field == "mergeCommit":
        print("")
    elif field in values:
        print(values[field])
    else:
        sys.stderr.write("unstubbed --json field: %%s\n" %% field)
        finish(2)
    finish()

if verb == "edit":
    finish()

if verb == "ready":
    state["isDraft"] = False
    finish()

if verb == "merge":
    state["autoMergeRequest"] = {"enabledAt": "now"}
    finish()

sys.stderr.write("unstubbed gh invocation: %%s\n" %% " ".join(argv))
finish(2)
"""


@pytest.fixture(autouse=True)
def _fresh_tenant() -> None:
    reset_fake_singleton()


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status="active",
        title="Bind the per-item merge hold heading",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="b1k",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-29T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _plan(*, host: Path, config_text: str, merge_hold: bool) -> DispatchPlan:
    return build_plan(
        repo=host,
        work_item_id=_ITEM_ID,
        workflow_toml=host / "wf.toml",
        goal_file=host / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=host / "janitor-co",
        config_text=config_text,
        default_branch="master",
        merge_hold=merge_hold,
        committed_workflow_text=_RUN_CONFIG.read_text(encoding="utf-8"),
    )


def _proof_record(*, verdict: str) -> dict[str, str]:
    return {
        "body": (
            f"Proof of Done — {verdict} — run r — 2026-10-29T00:00:00Z\n{PUBLISH_HEAD_LABEL}: {_HEAD}\n"
        )
    }


@dataclass(frozen=True, kw_only=True)
class _Done:
    returncode: int
    stdout: str
    stderr: str


@dataclass(kw_only=True)
class _Arc:
    """One item's world: the host checkout, a sandbox clone and the shared forge."""

    host: Path
    clone: Path
    forge_state: Path
    stub: Path
    plugins_root: Path
    plan: DispatchPlan
    run_inputs: dict[str, str]
    valve_calls: list[tuple[str, ...]]

    def forge(self) -> dict[str, object]:
        return cast("dict[str, object]", json.loads(self.forge_state.read_text(encoding="utf-8")))

    def merge_calls(self) -> list[list[str]]:
        calls = cast("list[list[str]]", self.forge()["calls"])
        return [call for call in calls if call[:2] == ["pr", "merge"]]

    def issued(self, *, verb: str) -> bool:
        calls = cast("list[list[str]]", self.forge()["calls"])
        return any(call[:2] == ["pr", verb] for call in calls)

    def _env(self) -> dict[str, str]:
        return {
            "PATH": f"{self.stub.parent}:/usr/local/bin:/usr/bin:/bin",
            "HOME": str(self.clone.parent / "home"),
            "LIVESPEC_FAKE_FORGE": str(self.forge_state),
        }

    def run_pr_stage(self) -> subprocess.CompletedProcess[str]:
        graph = parse_dot_graph(text=_IMPLEMENT_GRAPH.read_text(encoding="utf-8"))
        assert not isinstance(graph, str), graph
        script = (
            graph.nodes["pr"]["script"]
            .replace("{{ inputs.merge_mode }}", self.run_inputs["merge_mode"])
            .replace("{{ inputs.merge_hold }}", self.run_inputs["merge_hold"])
        )
        env = self._env()
        env["LIVESPEC_PUBLISH_BRANCH"] = _BRANCH
        env[SANDBOX_CLAUDE_PLUGINS_ROOT_ENV_VAR] = str(self.plugins_root)
        env[PR_TITLE_ENV_VAR] = "feat: bind the merge hold"
        return subprocess.run(
            ["bash", "-c", script],
            cwd=self.clone,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def valve_runner(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> _Done:
        """The valve's command seam: forge calls reach the stub, engine calls an idle factory."""
        self.valve_calls.append(argv)
        if argv[0] != "gh":
            return _Done(returncode=0, stdout="[]", stderr="")
        done = subprocess.run(
            [str(self.stub), *argv[1:]],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=self._env(),
        )
        return _Done(returncode=done.returncode, stdout=done.stdout, stderr=done.stderr)


def _arc(*, root: Path, merge_hold: bool) -> _Arc:
    """Dispatch one item under `squash`, leaving a draft pull request awaiting its `pr` stage."""
    host = root / "host"
    host.mkdir()
    config_text = _declaration(merge_mode=_DISPATCH_MODE)
    _ = (host / ".livespec.jsonc").write_text(config_text, encoding="utf-8")
    append_work_item(path=_STORE, item=_item())
    if merge_hold:
        update_work_item_merge_hold(path=_STORE, item_id=_ITEM_ID, value=True)

    plan = _plan(host=host, config_text=config_text, merge_hold=merge_hold)
    (host / "tmp").mkdir()
    append_dispatch_id_record(
        journal=JournalFile(path=host / "tmp" / "fabro-dispatch-journal.jsonl"),
        work_item_id=_ITEM_ID,
        identity=DispatchJournalIdentity(dispatch_id="d-xigh7o", dispatch_factory=None),
        engine=EngineBinary(path="/global/fabro", version="fabro 0.254.0"),
        started_at_epoch=1.0,
        workflow_toml=host / "wf.toml",
        workflow_name="implement-work-item",
        integration=plan.integration,
        merge_hold=plan.merge_hold,
        sandbox_image=COMMITTED_RUN_CONFIG_IMAGE,
    )
    run_inputs = dict(token.split("=", 1) for token in dispatch_fabro_run_inputs(plan=plan))

    clone = root / "clone"
    clone.mkdir()
    for argv in (
        ["git", "init", "--quiet", "--initial-branch=master"],
        ["git", "config", "user.email", "test@example.invalid"],
        ["git", "config", "user.name", "Test"],
    ):
        _ = subprocess.run(argv, cwd=clone, check=True, capture_output=True)
    state_dir = clone / ".git" / PUBLICATION_STATE_GIT_PATH
    state_dir.mkdir(parents=True)
    _ = (state_dir / PUBLISH_HEAD_STATE_FILENAME).write_text(_HEAD, encoding="utf-8")

    bin_dir = root / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    _ = stub.write_text(_GH_STUB % {"python": sys.executable}, encoding="utf-8")
    stub.chmod(0o755)
    plugins_root = root / "plugins"
    plugins_root.mkdir()
    _ = (plugins_root / PROOF_HEAD_PROGRAM_FILENAME).write_text(
        proof_head_program_source(), encoding="utf-8"
    )

    forge_state = root / "forge.json"
    _ = forge_state.write_text(
        json.dumps(
            {
                "number": _PR_NUMBER,
                "state": "OPEN",
                "head": _HEAD,
                "isDraft": True,
                "autoMergeRequest": None,
                "comments": [
                    _proof_record(verdict=VERDICT_CAPTURED),
                    _proof_record(verdict=VERDICT_VERIFIED),
                ],
                "calls": [],
            }
        ),
        encoding="utf-8",
    )
    return _Arc(
        host=host,
        clone=clone,
        forge_state=forge_state,
        stub=stub,
        plugins_root=plugins_root,
        plan=plan,
        run_inputs=run_inputs,
        valve_calls=[],
    )


def test_a_held_pr_stage_publishes_unarmed_and_the_release_arms_the_journaled_method(
    tmp_path: Path,
) -> None:
    """Publish under hold, then release: the pull request merges only because the release armed it.

    The dispatch declares `squash`; the repository's declaration then moves to
    `rebase`, so the strategy the release arms can only have come from the record
    the dispatch journaled.
    """
    arc = _arc(root=tmp_path, merge_hold=True)
    assert arc.run_inputs["merge_hold"] == "true"
    assert arc.run_inputs["merge_mode"] == _DISPATCH_MODE

    held = arc.run_pr_stage()

    assert held.returncode == 0, held.stderr
    assert "LIVESPEC_PR_HELD" in held.stderr
    stdout_lines = held.stdout.splitlines()
    assert f"PR_NUMBER={_PR_NUMBER}" in stdout_lines
    assert "MERGE_HOLD=held" in stdout_lines
    # Published: the pull request is open at the head this run pushed, and readied.
    forge = arc.forge()
    assert forge["state"] == "OPEN"
    assert forge["head"] == _HEAD
    assert forge["isDraft"] is False
    assert arc.issued(verb="ready")
    # Held: no auto-merge request was sent, and none stands on the pull request.
    assert arc.merge_calls() == []
    assert forge["autoMergeRequest"] is None
    assert read_merge_held_work_item_ids(path=_STORE) == frozenset({_ITEM_ID})

    # The hold stands while the declaration moves: a plan resolved from the
    # release-time declaration would arm a different strategy than the journaled one.
    drifted = _declaration(merge_mode=_RELEASE_TIME_MODE)
    _ = (arc.host / ".livespec.jsonc").write_text(drifted, encoding="utf-8")
    from_configuration = pr_arm_argv(
        plan=_plan(host=arc.host, config_text=drifted, merge_hold=False), number=_PR_NUMBER
    )
    assert from_configuration[4] == f"--{_RELEASE_TIME_MODE}"

    released = run_human_valve_action(
        repo=arc.host,
        action_id=f"set-merge-hold:{_ITEM_ID}:off",
        runner=arc.valve_runner,
    )

    assert released["status"] == "green", released
    assert any("ps" in call for call in arc.valve_calls if call[0] != "gh")
    assert arc.merge_calls() == [
        ["pr", "merge", str(_PR_NUMBER), f"--{_DISPATCH_MODE}", "--auto", "--delete-branch"]
    ]
    assert arc.forge()["autoMergeRequest"] is not None
    assert read_merge_held_work_item_ids(path=_STORE) == frozenset()


def test_an_unheld_pr_stage_arms_auto_merge_with_the_declared_merge_mode(tmp_path: Path) -> None:
    """The control: the same stage, same declaration, hold off -- arms exactly as it did before the hold.

    Without this leg the held assertions pass equally against a stage that never
    arms anything.
    """
    arc = _arc(root=tmp_path, merge_hold=False)
    assert arc.run_inputs["merge_hold"] == "false"
    assert arc.run_inputs["merge_mode"] == _DISPATCH_MODE

    result = arc.run_pr_stage()

    assert result.returncode == 0, result.stderr
    assert "LIVESPEC_PR_READY_AND_ARMED" in result.stderr
    assert "MERGE_HOLD=held" not in result.stdout
    assert f"PR_NUMBER={_PR_NUMBER}" in result.stdout
    assert arc.merge_calls() == [
        [
            "pr",
            "merge",
            f"--{_DISPATCH_MODE}",
            "--auto",
            "--delete-branch",
            "--match-head-commit",
            _HEAD,
            str(_PR_NUMBER),
        ]
    ]
    assert arc.forge()["autoMergeRequest"] is not None
