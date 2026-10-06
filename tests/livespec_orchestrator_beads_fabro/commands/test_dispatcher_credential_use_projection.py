"""Projecting credential-use enforcement into a sandbox, exercised by EXECUTION.

`_dispatcher_credential_use_guard` owns the enforcement. This module's subject is
the step that turns that tested helper into dispatch behaviour: how the deadline,
the observed credential EXPIRY and the resolved REQUIREMENT reach a sandbox, and
what happens when they do.

TWO DIFFERENT QUANTITIES ARE GRADED AT STARTUP, and conflating them is the defect
this module's earlier draft carried. The ABSOLUTE DEADLINE bounds how long
execution may continue; the CREDENTIAL'S REMAINING LIFETIME, measured against the
sandbox's own clock, decides whether it may begin at all. A case built on a
snapshot whose access token is the literal `"a"` has no decodable expiry, so it
can only ever measure the first -- which is why the credential cases below mint an
isolated token carrying a real `exp`. The criterion for the second is the same one
admission uses, `remaining > allowance + margin`, re-applied here because the
grade admission took was taken on the HOST at an earlier instant and queueing or
preparation can age the credential below it in between.

An earlier draft justified skipping that second grade by claiming any queue wait
would otherwise fail. That is false: a credential renewed to well beyond the
requirement survives a long wait with room to spare, so the check is satisfiable
rather than a gate nothing passes -- and the fraction of a token's life spent
below the floor is exactly the part that must not start a run.

THESE CASES RUN THE GENERATED SCRIPTS. They parse the rendered overlay with a
real TOML parser, take the `[[run.prepare.steps]]` scripts and the
`[environments.<id>.env]` table it actually declares, and EXECUTE them. A
presence/absence assertion over substrings cannot tell a working projection from
one that writes an empty file and aborts the sandbox, and that distinction is the
whole subject here -- an earlier draft of this projection would have `printf`-ed
an unset variable, failed its own `test -s`, and killed every dispatch that
projected no Codex credential. Only `/workspace` is rebased onto `tmp_path`, so
what runs is the generated text rather than a paraphrase of it.

THE DISCRIMINATOR IS PROTECTION, NOT THE PRESENCE OF A DEADLINE, and getting
that backwards is what made the earlier draft wrong in both directions. A
dispatch that projects a Codex credential IS credential-protected: the guard is
installed, the deadline is stamped, and the startup check runs before any
coding-agent node. A caller that projects NO Codex credential is not protected,
and must keep running normally -- no guard, no deadline, no refusal -- because
installing a guard with nothing to enforce only breaks working execution.
Conversely a dispatch that DOES project the credential while failing to stamp a
deadline is a broken protected projection and must fail closed. Legitimate
configuration and broken protection are different things, and neither is licence
to skip enforcement.
"""

from __future__ import annotations

import base64
import importlib
import inspect
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomli
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    GUARD_REFUSAL_EXIT_CODE,
    GUARD_SCRIPT_PATH,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    codex_freshness_required_seconds,
)

_MODULE_NAME = "_dispatcher_credential_use_projection"
_MODULE_IMPORT = f"livespec_orchestrator_beads_fabro.commands.{_MODULE_NAME}"

_COMMITTED_WORKFLOW_TOML = (
    "_version = 1\n"
    "\n"
    "[workflow]\n"
    'graph = "workflow.fabro"\n'
    "\n"
    "[run.environment]\n"
    'id = "livespec-ci"\n'
)

_ENVIRONMENT_ID = "livespec-ci"

# The in-sandbox root the generated scripts are written against. Rebased onto
# `tmp_path` so the generated text can run here unchanged in every other respect.
_SANDBOX_ROOT = "/workspace"

_FAKE_TOKEN = "test-oauth-token"
_FAKE_GITHUB_TOKEN = "test-github-token"
_GIT_AUTHOR = GitAuthor(name="Operator", email="operator@example.com")
_FAKE_SNAPSHOT = json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "a"}})

_STEP_TIMEOUT_SECONDS = 60

# A representative execution allowance. The REQUIREMENT the cases grade against is
# composed from it by the production composer rather than written as a literal,
# because the requirement is "allowance plus the documented margin" and a literal
# here would assert a figure no configuration produces while still passing for any
# build that happened to agree with it. Resolving an allowance from a SELECTED
# WORKFLOW is `_dispatcher_credential_requirement`'s own subject and is covered by
# its tests; what these cases measure is what the sandbox does with the resolved
# figure it is handed.
_ALLOWANCE_SECONDS = 3600
_REQUIRED_REMAINING_SECONDS = codex_freshness_required_seconds(
    run_budget_seconds=_ALLOWANCE_SECONDS
)

# A deadline comfortably in the future, used by the cases whose subject is the
# CREDENTIAL rather than the deadline. Keeping it future is what makes those cases
# evidence about the credential grade: a refusal cannot be attributed to the
# deadline having passed.
_FUTURE_DEADLINE_SECONDS = 1800


def _auth_json_with_exp(*, exp: int) -> str:
    """Build an isolated Codex auth.json whose access-token JWT carries `exp`.

    A REAL decodable expiry, which is what the credential cases need: the
    snapshot used elsewhere in this module carries the access token `"a"`, which
    has no expiry at all, so a case built on it can only ever measure the
    deadline. No live credential is involved -- these bytes are constructed here
    and never leave the test.
    """
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {"access_token": f"header.{payload}.sig", "refresh_token": "sentinel"},
        }
    )


def _module_path() -> Path:
    """Where the projection module must live, resolved from its own package."""
    package = importlib.import_module("livespec_orchestrator_beads_fabro.commands")
    return Path(str(package.__file__)).parent / f"{_MODULE_NAME}.py"


def _overlay(*, tmp_path: Path, **kwargs: Any) -> str | None:
    return render_run_config_overlay(
        committed_text=_COMMITTED_WORKFLOW_TOML,
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        git_author=_GIT_AUTHOR,
        **kwargs,
    )


def _parsed(*, rendered: str) -> dict[str, Any]:
    """Parse the overlay with a real TOML parser.

    A substring scan would pass against an overlay that is not valid TOML at
    all, which is a failure the engine would hit instead.
    """
    return tomli.loads(rendered)


def _prepare_scripts(*, document: dict[str, Any]) -> list[str]:
    steps = document.get("run", {}).get("prepare", {}).get("steps", [])
    return [str(step["script"]) for step in steps]


def _env_table(*, document: dict[str, Any]) -> dict[str, str]:
    environments = document.get("environments", {})
    return dict(environments.get(_ENVIRONMENT_ID, {}).get("env", {}))


def _rebased(*, text: str, sandbox: Path) -> str:
    """Point the generated script at this test's sandbox root."""
    return text.replace(_SANDBOX_ROOT, str(sandbox))


def _run_step(
    *,
    script: str,
    env: dict[str, str],
    sandbox: Path,
) -> subprocess.CompletedProcess[str]:
    """Execute ONE generated prepare step exactly as the engine's shell would."""
    child_env = dict(os.environ)
    child_env.pop(CREDENTIAL_USE_DEADLINE_ENV_VAR, None)
    child_env.update({key: _rebased(text=value, sandbox=sandbox) for key, value in env.items()})
    return subprocess.run(
        ["/bin/sh", "-c", _rebased(text=script, sandbox=sandbox)],
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT_SECONDS,
        env=child_env,
        check=False,
    )


def _guard_steps(*, document: dict[str, Any]) -> list[str]:
    """The generated steps that mention the guard, in rendered order."""
    return [
        script for script in _prepare_scripts(document=document) if "credential-use-guard" in script
    ]


def _projection(*, deadline: int, expiry: int, required: int) -> Any:
    """Build the projection value the overlay takes.

    Resolved through `importlib` rather than imported at module scope so the
    cases fail on their own assertions while the type does not exist yet, instead
    of dying at collection and proving only unimportability.
    """
    module = importlib.import_module(_MODULE_IMPORT)
    return module.CredentialUseProjection(
        deadline_epoch=deadline,
        credential_expiry_epoch=expiry,
        required_remaining_seconds=required,
    )


@dataclass(frozen=True, kw_only=True)
class _Startup:
    """What ONE protected sandbox's generated prepare sequence did.

    `launched` is the discriminator the credential cases turn on: it is True only
    when EVERY generated prepare step exited zero and the guarded command then
    actually ran. A refusal at any prepare step means no coding-agent node is
    ever reached, which is the difference the assertion is about -- refusing
    before credential use rather than discovering the shortfall mid-turn.
    """

    refusal: subprocess.CompletedProcess[str] | None
    launched: bool
    marker_exists: bool
    sandbox: Path


def _prepare_then_launch(
    *,
    tmp_path: Path,
    snapshot: str,
    deadline: int,
    expiry: int,
    required: int,
) -> _Startup:
    """Run the generated prepare steps IN ORDER, then launch only if all passed.

    This models what the engine does with the rendered overlay: prepare steps run
    in declared order and a non-zero exit aborts the sandbox before any node. The
    agent stand-in is an ordinary command behind the installed guard, so
    "no coding-agent node ran" is OBSERVED as an absent marker file rather than
    assumed from the fact that the case did not call it.
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    rendered = _overlay(
        tmp_path=tmp_path,
        codex_auth_snapshot=snapshot,
        credential_use=_projection(deadline=deadline, expiry=expiry, required=required),
    )
    assert rendered is not None
    document = _parsed(rendered=rendered)
    env = _env_table(document=document)
    steps = _guard_steps(document=document)
    assert len(steps) == 2, steps

    marker = sandbox / "ran"
    for script in steps:
        step = _run_step(script=script, env=env, sandbox=sandbox)
        if step.returncode != 0:
            return _Startup(
                refusal=step, launched=False, marker_exists=marker.exists(), sandbox=sandbox
            )
    guard_on_disk = Path(_rebased(text=GUARD_SCRIPT_PATH, sandbox=sandbox))
    # The install must have produced a NON-EMPTY script. An earlier draft wrote an
    # unset variable here, which is precisely what this asserts against.
    assert guard_on_disk.stat().st_size > 0
    launched = subprocess.run(
        ["/bin/sh", str(guard_on_disk), "--", "/bin/sh", "-c", f"printf done > {marker}"],
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT_SECONDS,
        env={
            **os.environ,
            **{key: _rebased(text=value, sandbox=sandbox) for key, value in env.items()},
        },
        check=False,
    )
    assert launched.returncode == 0, launched.stderr
    return _Startup(refusal=None, launched=True, marker_exists=marker.exists(), sandbox=sandbox)


def test_the_credential_use_projection_is_its_own_cohesive_module() -> None:
    """The projection has its own file, exporting both halves of the seam.

    Asserted on the PATH before the import, so this fails on a genuine assertion
    while the module does not exist rather than dying at collection.
    """
    assert _module_path().is_file(), f"{_MODULE_NAME} is not a module yet"
    module = importlib.import_module(_MODULE_IMPORT)
    assert set(module.__all__) == {
        "CredentialUseProjection",
        "credential_use_env_lines",
        "credential_use_guard_prepare_steps_block",
    }


def test_a_protected_sandbox_installs_a_working_guard_and_admits_fresh_work(
    tmp_path: Path,
) -> None:
    """THE POSITIVE CONTROL, run end to end through the generated scripts.

    A dispatch whose credential has ample runway must come out the other side
    ABLE TO WORK. So the generated install step is executed, the generated
    startup check is executed and must pass, and the guard it wrote is then used
    to launch an ordinary command, which must actually run. An implementation
    that always refuses satisfies every negative case here and fails this one.
    """
    now = int(time.time())
    startup = _prepare_then_launch(
        tmp_path=tmp_path,
        snapshot=_auth_json_with_exp(exp=now + _REQUIRED_REMAINING_SECONDS + 86400),
        deadline=now + _FUTURE_DEADLINE_SECONDS,
        expiry=now + _REQUIRED_REMAINING_SECONDS + 86400,
        required=_REQUIRED_REMAINING_SECONDS,
    )
    assert startup.refusal is None
    assert startup.launched
    assert (startup.sandbox / "ran").read_text(encoding="utf-8") == "done"


def test_a_credential_aged_below_the_required_lifetime_refuses_before_any_agent_node(
    tmp_path: Path,
) -> None:
    """THE A4 NEGATIVE: an aged CREDENTIAL refuses, with the deadline still future.

    The assertion is that "a projected credential aged by queueing or preparation
    below the required remaining worker lifetime causes sandbox startup to refuse
    before a coding-agent node uses it", so the quantity under test is the
    CREDENTIAL'S remaining lifetime, graded against the sandbox's own clock -- not
    the deadline.

    The DEADLINE IS DELIBERATELY FUTURE here. That is what makes this evidence
    about the credential grade: were the deadline past, the same refusal would be
    fully explained by the deadline check and the credential would never have been
    consulted. The expiry leaves exactly the required lifetime, which the
    admission criterion (`remaining > allowance + margin`, strictly greater) does
    not admit -- the credential that would finish its last enforced second with
    zero margin is the one state the margin exists to prevent.

    "Before any agent node" is OBSERVED rather than assumed: the generated prepare
    steps run in order, the launch is attempted only if all of them pass, and the
    absent marker file is what shows the agent stand-in never executed.
    """
    now = int(time.time())
    startup = _prepare_then_launch(
        tmp_path=tmp_path,
        snapshot=_auth_json_with_exp(exp=now + _REQUIRED_REMAINING_SECONDS),
        deadline=now + _FUTURE_DEADLINE_SECONDS,
        expiry=now + _REQUIRED_REMAINING_SECONDS,
        required=_REQUIRED_REMAINING_SECONDS,
    )
    assert startup.refusal is not None
    assert startup.refusal.returncode == GUARD_REFUSAL_EXIT_CODE, startup.refusal.stdout
    # The refusal must name the CREDENTIAL shortfall rather than the deadline, or
    # it would be reporting a cause nobody measured.
    assert "credential" in startup.refusal.stderr.lower()
    assert not startup.launched
    assert not startup.marker_exists


def test_a_deadline_consumed_by_queueing_refuses_at_startup(
    tmp_path: Path,
) -> None:
    """A DEADLINE already passed refuses at the START, credential notwithstanding.

    The sibling of the case above on the other quantity, and kept distinct from it
    precisely because the two are different measurements. Here the credential has
    ample lifetime and the DEADLINE is what has gone: a queue wait that outlasted
    the whole execution allowance. A prepare step exiting non-zero means no
    coding-agent node ever runs.
    """
    now = int(time.time())
    startup = _prepare_then_launch(
        tmp_path=tmp_path,
        snapshot=_auth_json_with_exp(exp=now + _REQUIRED_REMAINING_SECONDS + 86400),
        # Stamped before a queue wait that outlasted it.
        deadline=now - 120,
        expiry=now + _REQUIRED_REMAINING_SECONDS + 86400,
        required=_REQUIRED_REMAINING_SECONDS,
    )
    assert startup.refusal is not None
    assert startup.refusal.returncode == GUARD_REFUSAL_EXIT_CODE, startup.refusal.stdout
    assert "passed" in startup.refusal.stderr
    assert not startup.launched
    assert not startup.marker_exists


def test_an_unprotected_sandbox_keeps_running_normally(tmp_path: Path) -> None:
    """NO Codex projection means NO guard, and ordinary execution is preserved.

    This is the legitimate-configuration half of the discriminator. A caller
    projecting no Codex credential has no credential-use deadline to enforce, so
    installing a guard would either write an empty script and abort the sandbox
    at prepare time, or wrap an ordinary adapter into a launch that can only
    refuse. Neither protects anything; both break working execution.

    The overlay is parsed with a real TOML parser rather than scanned, so a
    projection that emitted a syntactically broken table would be caught here.
    It does NOT execute the unrelated prepare steps the overlay also carries --
    the gh-token refresh, the plugin-cache gate, the factory-provenance marker --
    because those address a real sandbox and would fail here for reasons that
    have nothing to do with this subject. That an INSTALLED guard is non-empty
    and runnable is asserted by the protected cases above, which execute it.
    """
    rendered = _overlay(tmp_path=tmp_path)
    assert rendered is not None
    document = _parsed(rendered=rendered)
    assert _guard_steps(document=document) == []
    assert CREDENTIAL_USE_DEADLINE_ENV_VAR not in _env_table(document=document)

    module = importlib.import_module(_MODULE_IMPORT)
    assert module.credential_use_env_lines(projection=None) == ""
    assert module.credential_use_guard_prepare_steps_block(projection=None) == ""


def test_a_projected_credential_without_enforcement_inputs_fails_closed(
    tmp_path: Path,
) -> None:
    """Codex projected but NO enforcement projected is broken protection, so refuse.

    The mirror of the case above, and the reason that one is not a bypass. Here
    the sandbox genuinely receives a credential, so enforcement is owed; a
    rendered overlay would be an unguarded sandbox holding a live credential.
    The renderer therefore declines to produce one at all, which the dispatch
    path reports as a pre-launch refusal.

    The three enforcement inputs travel as ONE value rather than three optional
    parameters, which is what makes a HALF-WIRED projection unrepresentable
    instead of merely refused: there is no way to supply a deadline while
    omitting the expiry the startup grade needs, so that state cannot be
    constructed and does not need a runtime check to catch it.
    """
    parameters = inspect.signature(render_run_config_overlay).parameters
    assert "credential_use" in parameters
    assert (
        _overlay(
            tmp_path=tmp_path,
            codex_auth_snapshot=_FAKE_SNAPSHOT,
            credential_use=None,
        )
        is None
    )
