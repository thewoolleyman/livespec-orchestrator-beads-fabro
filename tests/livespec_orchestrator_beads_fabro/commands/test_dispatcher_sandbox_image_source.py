"""Which source supplies a dispatch's sandbox image, and what the journal says.

`SPECIFICATION/contracts.md` section "Sandbox image source" and Scenario 169:
a dispatch whose resolved factory declares a catalog environment MUST launch
from the image that environment declares on the factory server, the launch
overlay MUST NOT substitute `dispatcher.fabro_sandbox_image` for it, a dispatch
whose factory declares no catalog environment MUST still launch from that key,
and the dispatch journal MUST name which source supplied the image for each
launch.

Measured 2026-10-11 on hp-candidate run 01M4PBFW4MP8: the run declared catalog
environment `livespec-ci`, whose image is `python-agent-v1.93.5`, and `inspect`
reported `sandbox.plan.image` at that tag while the container Petri actually
started (`sandbox.instance.image`) ran `python-agent-v1.92.0` — the value of
this repository's `dispatcher.fabro_sandbox_image`, which the launch overlay
rewrote into the launch. Two sources of truth, so a proof reading the plan
reports an image that did not run.
"""

from __future__ import annotations

import base64
import importlib
import json
from inspect import signature
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_loop,
    _dispatcher_loop_record,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
    DispatchJournalIdentity,
    append_dispatch_id_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_binary_record import (
    EngineBinary,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source"
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
    / "_dispatcher_sandbox_image_source.py"
)

_CONFIGURED_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.92.0"
_CATALOG_ENVIRONMENT = "livespec-ci"
# The image the catalog environment of the same name declares on the factory
# server. The host never reads it; it is the committed workflow's own value
# here, which is exactly what the overlay must leave standing.
_COMMITTED_IMAGE = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.93.5"
_WORKFLOW_WITH_IMAGE = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    f"[run.environment]\n"
    f'id = "{_CATALOG_ENVIRONMENT}"\n'
    "\n"
    f"[environments.{_CATALOG_ENVIRONMENT}]\n"
    'provider = "docker"\n'
    "\n"
    f"[environments.{_CATALOG_ENVIRONMENT}.image]\n"
    f'docker = "{_COMMITTED_IMAGE}"\n'
)
_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"
# The run graph the per-dispatch payload materializer needs: one node timeout
# plus the run-level stall watchdog, which is the shape the literal-duration
# rewrite requires.
_MINIMAL_GRAPH = (
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
# A canned fleet manifest, so the sibling-clone resolution that runs inside
# `materialize_overlay` never reaches a real `gh api` in the hermetic tier.
_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [{ "repo": "livespec", "class": "core" }]\n'
    "}\n"
)


def test_a_dispatch_naming_no_catalog_environment_still_takes_the_committed_key() -> None:
    """`dispatcher.fabro_sandbox_image` supplies the image, and only then.

    The module import rides `importlib` INSIDE the test body, with the file
    existence as the first assertion, so the Red that precedes this module
    fails on a genuine assertion rather than at collection.

    Both branches are asserted in one case because they are one decision: the
    committed key reaches the launch exactly when no catalog environment is
    named, and `None` — the overlay's documented no-op, which leaves the
    committed image table byte-for-byte as shipped — is what the catalog case
    resolves to instead.
    """
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    assert (
        module.overlay_sandbox_image(factory_environment=None, configured_image=_CONFIGURED_IMAGE)
        == _CONFIGURED_IMAGE
    )
    assert (
        module.overlay_sandbox_image(
            factory_environment=_CATALOG_ENVIRONMENT, configured_image=_CONFIGURED_IMAGE
        )
        is None
    )
    # An unset key is still unset: a factory declaring no catalog environment
    # has nothing to substitute either, which is the pre-key no-op.
    assert module.overlay_sandbox_image(factory_environment=None, configured_image=None) is None


def _committed_region(*, rendered: str) -> str:
    """The COMMITTED configuration half of a rendered overlay.

    `render_run_config_overlay` returns the rewritten committed text followed by
    the blocks it materializes, each of which opens with a
    `# --- Dispatcher-materialized` banner. The image table lives in the half
    before the first banner, so that half is what an "unchanged" claim is about.

    IT IS ALSO THE ONLY HALF A BYTE COMPARISON MAY USE, because the materialized
    half is NOT byte-stable across two calls. The refreshing-`gh` block embeds a
    base64 `tar.gz` of the support bundle, and a gzip stream carries the current
    MTIME in bytes 4..8 of its header, so two renders that straddle a one-second
    boundary differ there — measured 2026-10-12 in this sandbox, where
    `github_app_env_present()` is true and the archive differed at exactly byte
    offset 4 across a 1.1-second gap. A whole-text equality assertion therefore
    passes on the ~1 ms spacing of two adjacent calls and fails on the rare
    straddle, which is a time-dependent instrument rather than a measurement of
    this behaviour. That nondeterminism predates this work and is not this
    item's to fix; the comparison is simply aimed at the half that answers the
    question.
    """
    return rendered.split("# --- Dispatcher-materialized", 1)[0]


def test_the_launch_overlay_leaves_a_catalog_dispatch_image_unchanged(tmp_path: Path) -> None:
    """A named catalog environment makes the image rewrite a no-op, byte for byte.

    The measurement is BYTE EQUALITY of the committed-configuration region
    against the render that passes no image at all, not a `docker = ` substring
    check. A substring check passes for any build that happens to write the
    committed tag somewhere while rewriting it elsewhere, and "unchanged" is a
    claim about the bytes — the overlay's own byte-identity case in
    `test_config.py` is the control this mirrors.

    The pin is asserted ABSENT from the whole rendered text rather than only
    from the image table, because the failure this closes was an image reaching
    the launch from the wrong source; a pin that survived anywhere in the
    overlay could still reach it.
    """
    assert "factory_environment" in signature(render_run_config_overlay).parameters

    unchanged = render_run_config_overlay(
        committed_text=_WORKFLOW_WITH_IMAGE,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
    )
    catalog = render_run_config_overlay(
        committed_text=_WORKFLOW_WITH_IMAGE,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        fabro_sandbox_image=_CONFIGURED_IMAGE,
        factory_environment=_CATALOG_ENVIRONMENT,
    )
    assert unchanged is not None
    assert catalog is not None
    assert _committed_region(rendered=catalog) == _committed_region(rendered=unchanged)
    assert f'docker = "{_COMMITTED_IMAGE}"' in catalog
    assert _CONFIGURED_IMAGE not in catalog

    # The control, in the same case so neither reading can stand alone: with NO
    # catalog environment the same pin DOES reach the image table. Without it a
    # renderer that had stopped substituting entirely would pass above.
    substituted = render_run_config_overlay(
        committed_text=_WORKFLOW_WITH_IMAGE,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        fabro_sandbox_image=_CONFIGURED_IMAGE,
        factory_environment=None,
    )
    assert substituted is not None
    assert f'docker = "{_CONFIGURED_IMAGE}"' in substituted
    assert _COMMITTED_IMAGE not in substituted


def _auth_json_far_future(*, now: int) -> str:
    """A fake host Codex auth.json whose access-token JWT outlives any budget."""
    exp = now + 100 * 365 * 24 * 3600
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


def _written_overlay(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    factory_environment: str | None,
) -> str:
    """Materialize one dispatch's overlay and return the bytes it wrote.

    The pin is supplied through `LIVESPEC_FABRO_SANDBOX_IMAGE`, which
    `resolve_fabro_sandbox_image` prefers over the committed
    `dispatcher.fabro_sandbox_image` key. That makes this the STRONGER of the
    two inputs: a catalog environment that wins over the env override wins over
    the committed key too, since both reduce to the one value this function
    resolves. `test_config.py` owns the precedence between the two sources.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_WORKFLOW_WITH_IMAGE, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    now = 1_700_000_000
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setenv("LIVESPEC_FABRO_SANDBOX_IMAGE", _CONFIGURED_IMAGE)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: now)
    monkeypatch.setattr(
        _dispatcher_codex_auth, "read_host_codex_auth", lambda: _auth_json_far_future(now=now)
    )
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="wi-1",
        dispatch_id="disp-1",
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=GitAuthor(name="Operator", email="operator@example.com"),
        review_fix_visit_cap=4,
        factory_environment=factory_environment,
    )
    assert error is None
    return overlay.read_text(encoding="utf-8")


def test_a_dispatch_naming_a_catalog_environment_launches_the_catalog_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The materialized dispatch overlay carries the catalog image, not the pin.

    This is the DISPATCH leg rather than the renderer's: the pin is resolved
    HERE, from the repository's configuration, so a renderer that withholds a
    pin it is handed is still substituting one if this layer keeps handing it
    over. The control — the same fixture with no catalog environment — is in the
    same case, because the catalog assertion alone passes for a build that had
    stopped resolving the pin at all.
    """
    assert "factory_environment" in signature(materialize_overlay).parameters

    catalog = _written_overlay(
        tmp_path=tmp_path / "catalog",
        monkeypatch=monkeypatch,
        factory_environment=_CATALOG_ENVIRONMENT,
    )
    assert f'docker = "{_COMMITTED_IMAGE}"' in catalog
    assert _CONFIGURED_IMAGE not in catalog

    committed_key = _written_overlay(
        tmp_path=tmp_path / "committed-key",
        monkeypatch=monkeypatch,
        factory_environment=None,
    )
    assert f'docker = "{_CONFIGURED_IMAGE}"' in committed_key
    assert _COMMITTED_IMAGE not in committed_key


def test_the_dispatch_hands_the_materializer_its_factorys_catalog_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loop forwards `plan.fabro_factory_environment`, not a re-read.

    Without this the two assertions above hold of a function nothing calls with
    a catalog environment, which is the whole defect restored one layer up. The
    id is read off the PLAN — the one projection of the resolved factory the
    dispatch already stamped — so it cannot disagree with the `--environment`
    the same plan sends the server.
    """
    captured: dict[str, object] = {}
    plan = SimpleNamespace(
        review_fix_visit_cap=4,
        branch="feat/catalog-image",
        integration=object(),
        acp_nodes=None,
        fabro_factory_name="candidate",
        fabro_factory_environment=_CATALOG_ENVIRONMENT,
        fabro_version=None,
    )
    recorded = SimpleNamespace(
        plan=plan,
        committed_workflow=tmp_path / "workflow.toml",
        comments=(),
        payload=SimpleNamespace(graph=None),
        git_author=object(),
    )
    monkeypatch.setattr(_dispatcher_loop, "record_dispatch", lambda **_: recorded)
    monkeypatch.setattr(_dispatcher_loop.selfup, "github_token_supplier", lambda: lambda: "token")
    monkeypatch.setattr(_dispatcher_loop, "read_ratified_lessons", lambda **_: ())
    monkeypatch.setattr(_dispatcher_loop, "minijinja_openers_in_goal_sources", lambda **_: ())
    monkeypatch.setattr(_dispatcher_loop, "resume_checkout_for", lambda **_: None)
    monkeypatch.setattr(_dispatcher_loop, "publish_branch_for", lambda **_: "feat/catalog-image")
    monkeypatch.setattr(_dispatcher_loop, "contract_prompt_variables", lambda **_: {})
    monkeypatch.setattr(_dispatcher_loop, "journaled_proof_rendering", lambda **_: "")
    monkeypatch.setattr(
        _dispatcher_loop,
        "fabro_vault_sink_for_plan",
        lambda **_: SimpleNamespace(release_launch_guard=lambda: None),
    )
    monkeypatch.setattr(_dispatcher_loop, "run_id", lambda: "dispatch-catalog-image")
    monkeypatch.setattr(_dispatcher_loop, "release_pre_run_claim_if_needed", lambda **_: None)
    monkeypatch.setattr(
        _dispatcher_loop, "run_fabro_factory_auth_login", lambda **_: None, raising=False
    )

    def _materialize(**kwargs: object) -> str:
        captured.update(kwargs)
        return "stop after observing the forwarded environment"

    monkeypatch.setattr(_dispatcher_loop, "materialize_overlay", _materialize)
    outcome = _dispatcher_loop.dispatch_one(
        args=SimpleNamespace(),
        repo=tmp_path,
        item=SimpleNamespace(id="wi-catalog-image"),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        janitor=None,
    )
    assert outcome.status == "failed"
    assert captured.get("factory_environment") == _CATALOG_ENVIRONMENT


def _dispatch_id_record(*, tmp_path: Path, factory_environment: str | None) -> dict[str, object]:
    """Journal one dispatch-id record and return it, parsed."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    journal = JournalFile(path=tmp_path / "journal.jsonl")
    plan = build_plan(
        repo=tmp_path,
        work_item_id="wi-image-source",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=tmp_path / "janitor-checkout",
        config_text="{}",
        default_branch="master",
        committed_workflow_text="",
    )
    append_dispatch_id_record(
        journal=journal,
        work_item_id="wi-image-source",
        identity=DispatchJournalIdentity(dispatch_id="disp-1", dispatch_factory=None),
        engine=EngineBinary(path="/global/fabro", version="fabro 0.254.0"),
        started_at_epoch=1.0,
        workflow_toml=tmp_path / "workflow.toml",
        workflow_name="implement-work-item",
        integration=plan.integration,
        merge_hold=plan.merge_hold,
        factory_environment=factory_environment,
    )
    parsed = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8").strip())
    return cast("dict[str, object]", parsed)


def test_the_dispatch_journal_names_which_source_supplied_the_sandbox_image(
    tmp_path: Path,
) -> None:
    """Every launch's record names the source, and the catalog case names the id.

    Both fields are written UNCONDITIONALLY — the committed-key case records an
    explicit null environment rather than omitting the key — for the reason the
    engine fields beside them are: a record that dropped the fields when they
    matched the ordinary case would make "which source supplied this image?"
    answerable only for the dispatches that already looked unusual.
    """
    assert "factory_environment" in signature(append_dispatch_id_record).parameters
    module = importlib.import_module(_MODULE_NAME)

    catalog = module.sandbox_image_source(factory_environment=_CATALOG_ENVIRONMENT)
    assert catalog.source == module.CATALOG_ENVIRONMENT_IMAGE_SOURCE
    assert catalog.environment_id == _CATALOG_ENVIRONMENT
    committed_key = module.sandbox_image_source(factory_environment=None)
    assert committed_key.source == module.COMMITTED_KEY_IMAGE_SOURCE
    assert committed_key.environment_id is None
    # The two source names are the literals `contracts.md` section "Sandbox
    # image source" enumerates, asserted against the spec's own spelling rather
    # than against whatever the module happens to carry.
    assert module.CATALOG_ENVIRONMENT_IMAGE_SOURCE == "catalog_environment"
    assert module.COMMITTED_KEY_IMAGE_SOURCE == "dispatcher.fabro_sandbox_image"

    catalog_record = _dispatch_id_record(
        tmp_path=tmp_path / "catalog", factory_environment=_CATALOG_ENVIRONMENT
    )
    assert catalog_record["stage"] == "dispatch-id"
    assert catalog_record["sandbox_image_source"] == "catalog_environment"
    assert catalog_record["sandbox_image_environment"] == _CATALOG_ENVIRONMENT

    committed_key_record = _dispatch_id_record(
        tmp_path=tmp_path / "committed-key", factory_environment=None
    )
    assert committed_key_record["sandbox_image_source"] == "dispatcher.fabro_sandbox_image"
    assert committed_key_record["sandbox_image_environment"] is None


def test_the_record_names_the_source_for_the_factory_the_plan_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`record_dispatch` forwards the plan's catalog environment to the record.

    Without this the record is correct for whatever it is told and told nothing,
    which is the defect one layer up: the journal would name
    `dispatcher.fabro_sandbox_image` on every launch, including the catalog ones
    whose image it no longer supplies.
    """
    captured: dict[str, object] = {}
    plan = build_plan(
        repo=tmp_path,
        work_item_id="wi-image-source",
        workflow_toml=tmp_path / "overlay.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        fabro_factory_environment=_CATALOG_ENVIRONMENT,
        janitor=None,
        janitor_checkout=tmp_path / "janitor-checkout",
        config_text="{}",
        default_branch="master",
        committed_workflow_text="",
    )
    monkeypatch.setattr(_dispatcher_loop_record, "read_dispatch_labels", lambda **_: ())
    monkeypatch.setattr(
        _dispatcher_loop_record,
        "materialize_dispatch",
        lambda **_: SimpleNamespace(
            committed_workflow=tmp_path / "workflow.toml",
            payload=SimpleNamespace(timeouts=object(), payload_dir=tmp_path),
            workflow_name="implement-work-item",
            acp_nodes=None,
            git_author=object(),
        ),
    )
    monkeypatch.setattr(_dispatcher_loop_record, "dispatch_plan_for_item", lambda **_: plan)
    monkeypatch.setattr(_dispatcher_loop_record, "warn_item_sizing", lambda **_: None)
    monkeypatch.setattr(
        _dispatcher_loop_record, "emit_conformance_premise_notices", lambda **_: None
    )
    monkeypatch.setattr(_dispatcher_loop_record, "read_dispatch_comments", lambda **_: ())
    monkeypatch.setattr(
        _dispatcher_loop_record,
        "engine_binary",
        lambda **_: EngineBinary(path="/global/fabro", version="fabro 0.254.0"),
    )
    monkeypatch.setattr(
        _dispatcher_loop_record, "materialized_workflow_config", lambda **_: tmp_path / "wf.toml"
    )

    def _append(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(_dispatcher_loop_record, "append_dispatch_id_record", _append)
    recorded = _dispatcher_loop_record.record_dispatch(
        args=SimpleNamespace(),
        repo=tmp_path,
        item=SimpleNamespace(id="wi-image-source"),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        janitor=None,
        identity=DispatchJournalIdentity(dispatch_id="disp-1", dispatch_factory=None),
    )
    assert recorded.plan.fabro_factory_environment == _CATALOG_ENVIRONMENT
    assert captured.get("factory_environment") == _CATALOG_ENVIRONMENT
