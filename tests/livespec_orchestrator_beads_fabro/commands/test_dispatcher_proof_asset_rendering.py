"""The measured proof-asset rendering, projected into the sandbox overlay.

`SPECIFICATION/contracts.md`'s Proof-of-Done-record clause waives the
inline-rendering half only where no API-drivable store satisfies it for a
repository. The pre-dispatch gate MEASURES that per repository and journals the
answer, but until this slice the sandbox received only two of the three keys the
capture prompt reads, so a PUBLIC repository's image proof rendered as an
authenticated link -- outside the ratified text rather than merely untidy.

The blocker was mechanical, and that is why the decomposition is asserted here
beside the projection: `_dispatcher_loop` stood at exactly the 250-LLOC hard
ceiling, so the one call site that could thread the resolution into the overlay
could not take another argument until the module was split.
"""

from __future__ import annotations

import base64
import importlib
import json
from inspect import signature
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
    dispatcher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_assets import RENDERING_INLINE
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    PROOF_ASSET_RENDERING_ENV_VAR,
    PROOF_ASSETS_RELEASE_TAG_ENV_VAR,
    PUBLISH_BRANCH_ENV_VAR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_release import (
    proof_store_journal_record,
)

# The committed shapes the overlay materializer needs: a config carrying the
# `[workflow] graph` it absolutizes and the `[run.environment] id` whose env
# table it appends to, plus a graph with the one node timeout and the run-level
# stall watchdog the literal-duration rewrite requires. Mirrors the fixtures the
# sibling overlay tests use rather than inventing a second shape.
_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)
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
_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [{ "repo": "livespec", "class": "core" }]\n'
    "}\n"
)

_ITEM_ID = "bd-ib-pa73qh"
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_HUNDRED_YEARS_SECONDS = 100 * 365 * 24 * 3600
_NOW_EPOCH = 1_700_000_000
# Bound to names so ruff's hardcoded-password rule does not flag the literals.
_FAKE_OAUTH_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"


def _fresh_codex_auth(*, exp: int) -> str:
    """A host `auth.json` whose access-token JWT expires far in the future."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-132",
            },
        }
    )


def _measured_journal(*, path: Path, repository: str, rendering: str) -> Path:
    """A dispatch journal carrying ONE per-repository store record.

    Built through `proof_store_journal_record` rather than a hand-written dict, so
    the reader under test is asserted against the record shape the gate actually
    appends: a fixture spelling the keys itself could keep passing after the gate
    renamed one.
    """
    record = {
        "stage": "proof-asset-store",
        "work_item_id": _ITEM_ID,
        **proof_store_journal_record(
            repository=repository,
            tag="proof-assets",
            visibility="PUBLIC" if rendering == RENDERING_INLINE else "private",
            rendering=rendering,
            created=False,
        ),
    }
    _ = path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return path


def _committed_workflow(*, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    committed = root / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (root / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return committed


def _hermetic_overlay_inputs(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in the host reads the materializer performs before the render."""
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_OAUTH_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: _NOW_EPOCH)
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: _fresh_codex_auth(exp=_NOW_EPOCH + _HUNDRED_YEARS_SECONDS),
    )


def test_the_dispatch_sequence_and_the_lock_scope_are_separate_modules() -> None:
    """The decomposition the projection needed, pinned both ways.

    `_dispatcher_loop` stood at exactly the hard LLOC ceiling, so the sequence that
    calls the overlay materializer could not take another argument. The split cuts
    at the thinnest seam available: the lock SCOPE on one side, the SEQUENCE that
    runs inside it on the other, with nothing crossing that was not already a
    parameter. Pinned as GONE from the module it left, so the move cannot regress
    into a re-export shim that leaves both halves in one file.
    """
    commands_dir = Path(dispatcher.__file__).parent
    scope_path = commands_dir / "_dispatcher_dispatch_scope.py"

    assert scope_path.is_file()

    scope = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_scope"
    )
    loop = importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_loop")
    assert scope.__all__ == ["dispatch_one"]
    assert loop.__all__ == ["dispatch_one_locked"]
    assert not hasattr(loop, "dispatch_one")
    assert not hasattr(loop, "_dispatch_one_locked")
    assert dispatcher.dispatch_one is scope.dispatch_one


def test_the_overlay_projects_the_measured_rendering_beside_the_branch_and_the_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All three keys reach the sandbox from the production materializer.

    Asserted on the overlay FILE the Dispatcher writes rather than on the helper
    that renders the lines, because what the capture stage reads is the file: a
    helper that returned the right text while nothing threaded it into the overlay
    is exactly the residual this slice closes.
    """
    assert "journal_path" in signature(materialize_overlay).parameters

    _hermetic_overlay_inputs(monkeypatch=monkeypatch)
    repo = tmp_path / "repo"
    committed = _committed_workflow(root=tmp_path / "workflow")
    overlay = tmp_path / "overlay.toml"
    journal = _measured_journal(
        path=tmp_path / "journal.jsonl", repository=repo.name, rendering=RENDERING_INLINE
    )

    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=repo,
        work_item_id=_ITEM_ID,
        dispatch_id="disp-pa73qh",
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        journal_path=journal,
    )

    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    assert f'{PUBLISH_BRANCH_ENV_VAR} = "feat/{_ITEM_ID}"' in rendered
    assert f'{PROOF_ASSETS_RELEASE_TAG_ENV_VAR} = "proof-assets"' in rendered
    assert f'{PROOF_ASSET_RENDERING_ENV_VAR} = "{RENDERING_INLINE}"' in rendered
