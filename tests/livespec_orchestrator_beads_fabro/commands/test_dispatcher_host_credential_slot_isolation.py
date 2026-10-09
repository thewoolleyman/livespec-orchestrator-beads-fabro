"""The suite's isolation from THIS host's factory-credential rotation state.

`select_factory_credential` reads two AMBIENT host inputs — the caam-published
`selected-account.json` under the invoking user's home, and the
`CLAUDE_CODE_OAUTH_TOKEN__<PROFILE>` pool slots the credential wrapper injects
— and when they agree it names the slot. Both callers then read that slot's
value out of the real process environment, which OVERRIDES the token a test
supplied under the unnumbered `CLAUDE_CODE_OAUTH_TOKEN`.

Measured on the dispatching host 2026-10-09 (work-item bd-ib-vvs645): the
record named profile `anthropic-1` and the wrapper injected
`CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_1`, so four dispatcher tests received the
REAL host token where they had supplied `test-oauth-token`, and every
post-merge janitor — which runs `just check` INSIDE that wrapper — went red
while the same aggregate passed outside it. Continuous integration carries no
slot variables at all, so the fallback to the caller's token hid the defect
there permanently.

The isolation itself is one autouse fixture in `tests/conftest.py`; this module
is its paired test, and its shape is load-bearing. The hostile host condition
is established by a MODULE-scoped fixture precisely so it outranks that
FUNCTION-scoped scrub: pytest runs broader-scoped fixtures first, so the
hostile state is in place BEFORE the scrub runs and the scrub is what has to
undo it. A test that planted the slot variable in its own body would re-create
it AFTER the scrub and could never measure the fix.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_sibling_clones
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
    ClaudeCredentialStatus,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_env import (
    check_credential_env,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import (
    materialize_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    selected_account_record_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor

# The exact shape measured on the dispatching host: the rotation loop published
# profile `anthropic-1`, and the wrapper injected the matching pool slot. The
# slot name is spelled out rather than derived so this fixture states the
# hostile condition literally, the way an operator reading `printenv` sees it.
_PUBLISHED_PROFILE = "anthropic-1"
_SLOT_ENV = "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_1"
# Stand-ins for the two values that compete. Bound to locals before use so
# ruff's hardcoded-credential rules do not flag the literals, the same
# indirection the existing overlay tests use.
_SLOT_TOKEN = "host-wrapper-slot-token"
_TEST_TOKEN = "test-oauth-token"
_GITHUB_TOKEN = "test-github-token"
_FALLBACK_WARNING = "factory credential slot fallback"

_GIT_AUTHOR = GitAuthor(name="Chad Woolley", email="thewoolleyman@gmail.com")
# The shipped default's review-fix VISIT cap: three repair rounds plus the
# initial review visit. Immaterial to what these cases measure — the graph
# below guards no edge on it — but a real rendered value rather than an
# invented one.
_REVIEW_FIX_VISIT_CAP = 4

_FLEET_MANIFEST_TEXT = (
    "{\n"
    '  "owner": "thewoolleyman",\n'
    '  "members": [{ "repo": "livespec", "class": "core" }]\n'
    "}\n"
)

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


@pytest.fixture(scope="module", autouse=True)
def _host_credential_rotation_state(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Reproduce the dispatching host: a published record AND its wrapper slot.

    MODULE-scoped on purpose — see this module's docstring. The record path is
    composed through the selector's own `selected_account_record_path` rather
    than restated here, so the fixture cannot drift from the location the
    product actually reads.
    """
    home = tmp_path_factory.mktemp("published-selection-home")
    record = selected_account_record_path(home=home)
    record.parent.mkdir(parents=True)
    _ = record.write_text(json.dumps({"profile": _PUBLISHED_PROFILE}), encoding="utf-8")
    with pytest.MonkeyPatch.context() as hostile:
        hostile.setenv("HOME", str(home))
        hostile.setenv(_SLOT_ENV, _SLOT_TOKEN)
        yield


def _usable_status() -> ClaudeCredentialStatus:
    return ClaudeCredentialStatus(
        condition="usable",
        present=True,
        usable=True,
        http_status=200,
        error_type=None,
        input_tokens=8,
        output_tokens=1,
        message="CLAUDE_CODE_OAUTH_TOKEN is usable.",
        remedy="No action required.",
    )


def _workflow_toml(*, tmp_path: Path) -> Path:
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    return committed


def test_credential_gate_receives_the_token_the_test_supplied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The gate probes the test's own token, not the host's selected slot."""
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _TEST_TOKEN)
    probed: list[str] = []

    def recording_probe(*, token: str) -> ClaudeCredentialStatus:
        probed.append(token)
        return _usable_status()

    assert check_credential_env(repo=tmp_path, probe=recording_probe) is None
    assert probed == [_TEST_TOKEN]


def test_run_config_overlay_projects_the_token_the_test_supplied(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The rendered overlay carries the test's token, not the host's."""
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _TEST_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    overlay = tmp_path / "overlay.toml"

    error = materialize_overlay(
        committed=_workflow_toml(tmp_path=tmp_path),
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="bd-ib-vvs645",
        dispatch_id="dispatch-1",
        token=lambda: _GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
    )

    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    assert f'{CLAUDE_OAUTH_TOKEN_ENV} = "{_TEST_TOKEN}"' in rendered
    assert _SLOT_TOKEN not in rendered


def test_a_real_dispatch_still_honours_the_published_profile_slot(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Restoring the slot restores the rotation-following selection verbatim.

    The scrub isolates the SUITE; it must not change what the Dispatcher does
    on a real dispatch. Setting the slot back inside the test body — after the
    function-scoped scrub has run — is exactly the live condition, and the
    silent stderr proves the slot was SELECTED rather than fallen back to.
    """
    monkeypatch.setenv(CLAUDE_OAUTH_TOKEN_ENV, _TEST_TOKEN)
    monkeypatch.setenv(_SLOT_ENV, _SLOT_TOKEN)
    probed: list[str] = []

    def recording_probe(*, token: str) -> ClaudeCredentialStatus:
        probed.append(token)
        return _usable_status()

    assert check_credential_env(repo=tmp_path, probe=recording_probe) is None
    assert probed == [_SLOT_TOKEN]
    assert _FALLBACK_WARNING not in capsys.readouterr().err
