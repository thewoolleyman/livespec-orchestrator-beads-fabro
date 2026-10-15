"""The OVERLAY a no-Codex dispatch actually writes, end to end.

`bd-ib-meejjz`. Three layers had to change for an all-Claude dispatch to stop
being graded, projected and deadline-enforced on a credential no node uses, and
each got its own cover:

- the guard SCRIPT's unprotected arm, in `test_dispatcher_credential_use_unprotected`;
- the RENDERING of an unprotected declaration, in the same module;
- the overlay LEG's decision to answer with that declaration, in
  `test_dispatcher_codex_overlay_leg_routing`.

WHAT NONE OF THOSE COVERS IS THE WIRING BETWEEN THEM, which is the only part a
real dispatch depends on. Each of the three passes against a build where the
leg's declaration never reaches the renderer: the guard cases drive the script
directly, the rendering cases are handed a declaration by the test, and the leg
cases read the leg's return value. A materializer that resolved the declaration
and then passed `None` to the renderer satisfies all three while writing an
overlay that installs no guard and declares nothing — and the sandbox's startup
grade fails CLOSED on silence, so that dispatch dies in preparation rather than
quietly, which is exactly the shape an operator would read as a factory outage.

So this module asserts the ARTIFACT: the `[environments.<id>.env]` table of the
mode-600 overlay the production `materialize_overlay` writes. It is the same
file the sandbox reads, so what it carries is what the guard will see.

EVERY ASSERTION READS THE SET OF ASSIGNED NAMES, NEVER A SUBSTRING OF THE
OVERLAY, and that is a correctness requirement rather than tidiness. The guard
SCRIPT rides this same table as a single-line-encoded value, and that script
READS all four enforcement names — so a substring test for any of them matches
the script's own body and reports every name as present on every dispatch. Both
cases below were first written that way and both failed, the Codex-routed one
by "finding" the unprotected declaration it exists to prove absent. A test that
cannot tell an ASSIGNMENT from a MENTION cannot discriminate the two overlays at
all.

THE CODEX-ROUTED CONTROL IS NOT OPTIONAL. Every assertion below is otherwise
equally satisfied by a materializer that writes the unprotected declaration on
EVERY dispatch — which would disarm the deadline for the dispatches that really
do launch Codex, the one direction this change must not take. The control is the
SAME fixture with the routing declared, and it requires the deadline names, the
projected Codex auth, and the ABSENCE of the unprotected declaration.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_routing import CodexRouting
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_EXPIRY_ENV_VAR,
    CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    CREDENTIAL_USE_UNPROTECTED_ENV_VAR,
    CREDENTIAL_USE_UNPROTECTED_VALUE,
    GUARD_SCRIPT_PATH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import materialize_overlay
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor

_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_REVIEW_FIX_VISIT_CAP = 4

_FLEET_MANIFEST_TEXT = json.dumps(
    {"owner": "thewoolleyman", "members": [{"repo": "livespec", "class": "core"}]}
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

# One ACP node launching from the wrapped adapter input, which is the shape the
# shipped graph uses. A guardable graph deliberately: the launch-route check runs
# on the Codex-routed control, and a graph it refused would make that control fail
# for a reason unrelated to what is asserted here.
_MINIMAL_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s",\n'
    "        backend=acp,\n"
    '        acp.command="{{ inputs.implement_adapter }}"\n'
    "    ]\n"
    "}\n"
)

# The three enforcement names a PROTECTED projection carries. Grouped so each case
# can assert the whole set is present or the whole set is absent: the startup grade
# treats a partial set as a half-wired projection and fails closed on it, so
# "some of them" is a state neither arm may produce.
_ENFORCEMENT_ENV_VARS = (
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    CREDENTIAL_EXPIRY_ENV_VAR,
    CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
)

# The env name a projected host Codex credential rides. Spelled here rather than
# imported because the renderer composes it as a literal; the companion
# `CODEX_HOME` is deliberately not asserted on, since an unprotected dispatch
# still renders the Codex OTEL config and this module is about the CREDENTIAL.
_CODEX_AUTH_ENV_VAR = "CODEX_AUTH_JSON"

_NOW = 1_700_000_000
_FAR_FUTURE = _NOW + 100 * 365 * 24 * 3600

# One `NAME = ` assignment at the start of a line in the overlay's env table.
# Anchored so the guard script's own references to these same names — it rides the
# table as a single-line-encoded value and reads all four — cannot be mistaken for
# assignments. See the module docstring on why a substring test cannot work here.
_ENV_ASSIGNMENT_RE = re.compile(r"(?m)^([A-Z][A-Z0-9_]*) = ")


def _auth_json_with_exp(*, exp: int) -> str:
    """A host Codex `auth.json` whose access-token JWT carries `exp`."""
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": f"header.{payload}.sig", "refresh_token": "host-refresh"},
        }
    )


def _written_overlay(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    codex_routed: bool,
) -> str:
    """Run the production materializer and return the overlay text it wrote.

    The ONLY difference between the two legs is `codex_routed`. Everything else
    — the committed config, the graph, the host credential, the clock — is held
    identical, so each assertion below is attributable to the routing rather
    than to a fixture that differs in some other respect.
    """
    committed = tmp_path / "workflow.toml"
    _ = committed.write_text(_COMMITTED_WORKFLOW_TOML, encoding="utf-8")
    _ = (committed.parent / "workflow.fabro").write_text(_MINIMAL_GRAPH, encoding="utf-8")
    overlay = tmp_path / "overlay.toml"
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _FAKE_TOKEN)
    monkeypatch.setattr(
        _dispatcher_sibling_clones, "fetch_fleet_manifest_text", lambda: _FLEET_MANIFEST_TEXT
    )
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: _NOW)
    # The host credential is present and long-lived in BOTH legs. That is what
    # makes the no-Codex leg's assertions about scoping rather than about an
    # absent credential: a fixture withholding it would produce an overlay with
    # no Codex auth for the wrong reason.
    monkeypatch.setattr(
        _dispatcher_codex_auth,
        "read_host_codex_auth",
        lambda: _auth_json_with_exp(exp=_FAR_FUTURE),
    )
    if codex_routed:
        monkeypatch.setattr(
            _dispatcher_credentials,
            "codex_routing_for_dispatch",
            lambda **_kwargs: CodexRouting(
                routes_codex=True,
                detail=(
                    "resolved ACP candidate keys naming the codex-acp agent: "
                    "codex-acp/openai/gpt-5.1"
                ),
            ),
        )
    error = materialize_overlay(
        committed=committed,
        overlay=overlay,
        repo=tmp_path / "repo",
        work_item_id="bd-ib-meejjz",
        dispatch_id="01M4YT3EKJWT18HB6WFTGMAQP2",
        token=lambda: _FAKE_GITHUB_TOKEN,
        git_author=_GIT_AUTHOR,
        review_fix_visit_cap=_REVIEW_FIX_VISIT_CAP,
        adapter_inputs=frozenset({"implement_adapter"}),
    )
    assert error is None, f"the materializer refused the dispatch: {error}"
    return overlay.read_text(encoding="utf-8")


def test_an_all_claude_overlay_declares_unprotected_and_carries_no_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The artifact a no-Codex dispatch writes: a guard, a declaration, no bound.

    The guard IS still installed, which is the half most easily mistaken for a
    defect and removed. The adapter wrap is unconditional at both launch sites,
    so this script is what execs every coding agent either way; rendering
    nothing here would leave each adapter exec'ing a path that does not exist.
    """
    rendered = _written_overlay(tmp_path=tmp_path, monkeypatch=monkeypatch, codex_routed=False)
    assigned = frozenset(_ENV_ASSIGNMENT_RE.findall(rendered))

    assert CREDENTIAL_USE_UNPROTECTED_ENV_VAR in assigned, (
        "the overlay must carry the host's EXPLICIT declaration that this dispatch "
        "projects no Codex credential; the guard fails closed on silence, so an "
        "overlay that merely omits the deadline refuses every launch in preparation"
    )
    # The VALUE as well as the name, because the guard refuses any value but this
    # one marker -- a half-written table is not a statement -- so an overlay
    # assigning the name with something else refuses every launch just as silence
    # does, and the name alone cannot tell the two apart.
    assert f'{CREDENTIAL_USE_UNPROTECTED_ENV_VAR} = "{CREDENTIAL_USE_UNPROTECTED_VALUE}"' in (
        rendered
    ), "the declaration must carry the one value the guard recognises"
    assert GUARD_SCRIPT_PATH in rendered, (
        "the guard is still installed for an unprotected dispatch, because the "
        "launch wrap is unconditional and the guard is what execs every agent"
    )
    assert not (assigned & frozenset(_ENFORCEMENT_ENV_VARS)), (
        "no enforcement name may ride an unprotected overlay, not even empty: the "
        "startup grade reads a partial enforcement set as a half-wired projection "
        f"and fails closed on it; assigned: {sorted(assigned & frozenset(_ENFORCEMENT_ENV_VARS))}"
    )
    assert _CODEX_AUTH_ENV_VAR not in assigned, (
        "no host Codex credential may be projected into the sandbox of a dispatch "
        "that routes no node to Codex"
    )


def test_a_codex_routed_overlay_still_projects_the_credential_and_its_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control. A Codex-routed dispatch's overlay is unchanged by this work.

    Without it every assertion in the sibling case is equally satisfied by a
    materializer that declares every dispatch unprotected, which would remove
    the bound from the dispatches that really do hold a live Codex credential.
    """
    rendered = _written_overlay(tmp_path=tmp_path, monkeypatch=monkeypatch, codex_routed=True)
    assigned = frozenset(_ENV_ASSIGNMENT_RE.findall(rendered))

    missing = frozenset(_ENFORCEMENT_ENV_VARS) - assigned
    assert not missing, (
        "every enforcement name must ride a Codex-routed overlay: the three "
        "together are what let the sandbox measure the credential and bound its "
        f"use; missing: {sorted(missing)}"
    )
    assert (
        _CODEX_AUTH_ENV_VAR in assigned
    ), "a Codex-routed dispatch still projects the host credential it will use"
    assert GUARD_SCRIPT_PATH in rendered
    assert CREDENTIAL_USE_UNPROTECTED_ENV_VAR not in assigned, (
        "a dispatch holding a live Codex credential must never declare itself "
        "unprotected; that declaration is the one thing that disarms the deadline"
    )
