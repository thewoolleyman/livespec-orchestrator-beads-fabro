"""A public repository's `proof_capture` receives the measured inline rendering.

Binds the capture half of `SPECIFICATION/scenarios.md` Scenario 132 and the
`SPECIFICATION/contracts.md` Proof-of-Done-record clause it realizes: the clause
waives the INLINE half of the record format only where no API-drivable store
satisfies it for a repository, so a repository whose measured release-assets
store DOES satisfy it must receive the inline form. The measurement itself is
`plan/definition-and-proof-of-done/research/003-proof-asset-inline-rendering-measurement-2026-10-01.md`:
anonymous own-origin fetch succeeds on a public repository and 404s on a private
one, so `public` renders inline and everything else takes the authenticated link.

THE RENDERING IS READ OFF THE BYTES THE ENGINE WOULD BE HANDED, not off the
builder. Each case drives the real `dispatcher.main(argv=["dispatch", ...])` and
reads the overlay out of `plan.workflow_toml` from inside the launch stand-in —
the one moment those bytes exist, since `run_dispatch_with_watchdog` unlinks the
overlay when the run returns. A projection asserted in isolation would pass just
as well while nothing threaded the journal path into it, which is exactly the
state this repository was in before `bd-ib-pa73qh`.

THE UNMEASURED LEG IS THE CONTROL, AND ITS ANSWER IS AN ABSENCE. When the forge
cannot answer `gh repo view --json visibility` the gate journals the resolution as
UNOBSERVABLE and the overlay carries no rendering key at all. That is not a gap:
the capture prompt documents the absent value as its authenticated-link fallback
and asks the agent to say it took the fallback, so withholding the key is the ONLY
form that still lets a reader tell that fallback from a measured waiver. Asserting
a projected `authenticated_link` here would therefore be asserting the wrong
behaviour, and the prompt case below is what makes that readable rather than
inferred.

ONLY TWO SEAMS ARE STOOD IN, both of which leave the process: the proof gate's
`CommandRunner` (so the two visibility answers are reachable without a network,
and without scripting the PATH `gh` the master-CI preflight also reads), and
`run_dispatch`. The gate, the journal write, the readback, the overlay render and
the file it writes are all production code.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_loop,
    _dispatcher_run_commands,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets import (
    RENDERING_AUTHENTICATED_LINK,
    RENDERING_INLINE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    PROOF_ASSET_RENDERING_ENV_VAR,
    PROOF_ASSETS_RELEASE_TAG_ENV_VAR,
    PROOF_STORE_JOURNAL_STAGE,
    PUBLISH_BRANCH_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-pa73qh"
_ENV_TABLE_HEADER = "[environments.fabro-sandbox.env]\n"
_RESERVED_DIR = ".fabro/workflows/implement-work-item"
_WORKFLOW_TOML = '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n'
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)
_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)
_CAPTURE_PROMPT = Path(
    ".claude-plugin/.fabro/workflows/implement-work-item/prompts/proof-capture.md"
)


@dataclass(kw_only=True)
class _ProofForge:
    """The proof gate's `CommandRunner`, scripted per forge verb.

    `visibility_exit` is the whole control surface: zero makes the forge ANSWER
    and the measurement reach the journal, non-zero makes it unanswerable and the
    resolution unobservable. Every argv is recorded, because the unmeasured leg's
    claim is partly about what the gate did NOT go on to ask.
    """

    visibility: str = "PUBLIC"
    visibility_exit: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(list(argv))
        if "repo" in argv:
            return CommandResult(
                exit_code=self.visibility_exit,
                stdout=json.dumps({"visibility": self.visibility}),
                stderr="",
            )
        # The standing prerelease is already there, so the gate provisions nothing
        # and the resolution is a plain read — the ordinary state of a repository
        # that has dispatched proof-bearing work before.
        return CommandResult(exit_code=0, stdout=json.dumps({"tagName": "proof-assets"}), stderr="")


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment plus a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("proof-rendering-projection")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_loop_launch.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:proof-rendering-projection")
    for ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed_item() -> WorkItem:
    """One dispatchable, PROOF-BEARING item.

    Proof-bearing is what makes the gate probe at all: a bullet under no proof-mode
    sub-heading is `factory_captured` by default, and an item carrying none would
    return from the gate before any measurement — so every case here would pass
    against a Dispatcher that had never been wired to project a rendering.
    """
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Project the measured proof-asset rendering into the sandbox overlay",
        description=(
            "## Definition of Done\n"
            "\n"
            "- The measured proof-asset rendering reaches the capture stage.\n"
            "\n"
            "References: ## Scenario 132 — A factory-captured proof\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="- The measured proof-asset rendering reaches the capture stage.",
    )
    append_work_item(path=_config(), item=item)
    return item


def _repo(*, tmp_path: Path) -> Path:
    """A governed dispatch target carrying the reserved workflow payload."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "credential_wrapper": ["/usr/local/bin/with-livespec-env.sh", "--"],
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {"wip_cap": 3, "acceptance_mode": "ai-only"},
                },
            }
        ),
        encoding="utf-8",
    )
    workflow = repo / _RESERVED_DIR
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    return repo


def _capturing_run_dispatch(*, overlays: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in that snapshots the overlay the engine would read.

    Read HERE rather than after the call because this is the only moment the file
    exists: `run_dispatch_with_watchdog` unlinks the overlay when the run returns,
    which is correct — it carries this dispatch's credentials — and which makes the
    launch boundary the one honest observation point.
    """

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        overlays.append(plan.workflow_toml.read_text(encoding="utf-8"))
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


def _dispatch(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    forge: _ProofForge,
) -> tuple[int, list[str]]:
    """Drive one real dispatch; report its exit code and the overlay it launched with."""
    overlays: list[str] = []
    monkeypatch.setattr(_dispatcher_run_commands, "ShellCommandRunner", lambda: forge)
    monkeypatch.setattr(
        _dispatcher_loop, "run_dispatch", _capturing_run_dispatch(overlays=overlays)
    )
    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", _ITEM_ID, "--no-close-on-merge"]
    )
    return exit_code, overlays


def _env_table(*, overlay: str) -> str:
    """The run-scoped env table the sandbox receives, isolated from the rest."""
    halves = overlay.split(_ENV_TABLE_HEADER, 1)
    assert len(halves) == 2, "the overlay carries no run-scoped env table"
    return halves[1]


def _store_records(*, repo: Path) -> list[dict[str, object]]:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    return [
        record
        for record in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        if record.get("stage") == PROOF_STORE_JOURNAL_STAGE
    ]


def test_a_public_repositorys_proof_capture_receives_the_inline_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured `inline` reaches the sandbox env, beside the branch and the tag.

    All three keys are asserted in the SAME table, because the clause's value is
    that one capture stage can resolve all three facts without asking anybody: a
    rendering projected into some other section would be a second channel, and a
    rendering projected without the tag would name a form for an upload that has
    nowhere to go.

    The journal is asserted too, and that is the provenance half rather than a
    restatement: the record is what the gate MEASURED, and the env line is what the
    projection READ BACK. If the overlay said `inline` while the record said
    anything else, the projection would be inventing its answer.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    forge = _ProofForge(visibility="PUBLIC")

    exit_code, overlays = _dispatch(repo=repo, monkeypatch=monkeypatch, forge=forge)

    assert (exit_code, len(overlays)) == (0, 1)
    env_table = _env_table(overlay=overlays[0])
    assert f'{PROOF_ASSET_RENDERING_ENV_VAR} = "{RENDERING_INLINE}"\n' in env_table
    assert f'{PUBLISH_BRANCH_ENV_VAR} = "feat/{_ITEM_ID}"\n' in env_table
    assert f'{PROOF_ASSETS_RELEASE_TAG_ENV_VAR} = "proof-assets"\n' in env_table
    assert [
        (record["repository"], record["rendering"], record["inline_waived"])
        for record in _store_records(repo=repo)
    ] == [("repo", RENDERING_INLINE, False)]


def test_an_unmeasured_repositorys_proof_capture_receives_the_link_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A forge that cannot be ASKED projects NO rendering key, which IS the fallback.

    The same item, the same repository, the same dispatch — only the visibility
    answer differs, so this is the discriminator for the case above rather than a
    second fixture that happens to behave differently.

    Three instruments, because the absence alone is ambiguous. The branch key is
    asserted PRESENT, so this is "the rendering was withheld" rather than "the whole
    projection collapsed". The journal is asserted to say `unobservable`, so the
    withholding is traceable to a forge that did not answer rather than to a
    readback that failed. And the dispatch is asserted to have LAUNCHED, because
    an unobservable store must never be reported as an absent one — the refusal
    this gate can issue is reserved for a forge that answered.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    forge = _ProofForge(visibility_exit=1)

    exit_code, overlays = _dispatch(repo=repo, monkeypatch=monkeypatch, forge=forge)

    assert (exit_code, len(overlays)) == (0, 1)
    env_table = _env_table(overlay=overlays[0])
    assert PROOF_ASSET_RENDERING_ENV_VAR not in env_table
    assert f'{PUBLISH_BRANCH_ENV_VAR} = "feat/{_ITEM_ID}"\n' in env_table
    records = _store_records(repo=repo)
    assert len(records) == 1
    assert "unobservable" in records[0]
    assert "rendering" not in records[0]


def test_the_capture_prompt_consumes_the_projected_rendering_and_both_of_its_forms() -> None:
    """The consumer side, so "`proof_capture` receives it" names a real duty.

    Without this the two cases above assert only that an environment variable
    exists. The prompt is the stage that acts on it, and three things have to be
    true of it: it reads the projected name, it defines BOTH forms, and it treats an
    ABSENT value as the authenticated-link fallback while asking the agent to say so
    — which is the whole reason the unmeasured leg withholds the key instead of
    projecting a value.

    Read whitespace-collapsed because the prompt is hard-wrapped: a needle
    straddling a line break fails while the prose says exactly the thing, which is a
    probe that can only fail silently.
    """
    prompt = re.sub(r"\s+", " ", _CAPTURE_PROMPT.read_text(encoding="utf-8"))

    assert f"${PROOF_ASSET_RENDERING_ENV_VAR}" in prompt
    assert f"`{RENDERING_INLINE}` — reference it inline" in prompt
    assert f"`{RENDERING_AUTHENTICATED_LINK}` — the forge cannot render" in prompt
    assert f"When the variable is ABSENT, use `{RENDERING_AUTHENTICATED_LINK}`." in prompt
    assert "Say in your final reply that you took the fallback" in prompt
