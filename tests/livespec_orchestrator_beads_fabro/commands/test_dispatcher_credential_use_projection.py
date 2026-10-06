"""Projecting the absolute credential-use deadline, exercised by EXECUTION.

`_dispatcher_credential_use_guard` owns the enforcement. This module's subject is
the step that turns that tested helper into dispatch behaviour: how the deadline
and the guard REACH a sandbox, and what happens when they do.

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

# Far below any allowance this repository's workflow resolves -- the committed
# configuration resolves hundreds of thousands of seconds -- so a startup check
# that ADMITS this is demonstrably grading the absolute deadline rather than
# re-applying the admission floor. See the case that uses it.
_SHORT_REMAINING_SECONDS = 120


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


@dataclass(frozen=True, kw_only=True)
class _Installed:
    """One protected sandbox after its generated install step has run."""

    guard: Path
    env: dict[str, str]
    check_script: str
    sandbox: Path


def _installed_guard(*, tmp_path: Path, deadline: int) -> _Installed:
    """Render a protected overlay, run its install step, return what it produced.

    Shared by the cases that need a working installation before measuring what
    the startup check decides, so each of those cases asserts about the DECISION
    rather than re-deriving the installation.
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    rendered = _overlay(
        tmp_path=tmp_path,
        codex_auth_snapshot=_FAKE_SNAPSHOT,
        credential_use_deadline_epoch=deadline,
    )
    assert rendered is not None
    document = _parsed(rendered=rendered)
    env = _env_table(document=document)
    steps = _guard_steps(document=document)
    assert len(steps) == 2, steps

    install = _run_step(script=steps[0], env=env, sandbox=sandbox)
    assert install.returncode == 0, install.stderr
    guard_on_disk = Path(_rebased(text=GUARD_SCRIPT_PATH, sandbox=sandbox))
    # The install must have produced a NON-EMPTY script. The earlier draft wrote
    # an unset variable here, which is precisely what this asserts against.
    assert guard_on_disk.stat().st_size > 0
    return _Installed(
        guard=guard_on_disk,
        env=env,
        check_script=steps[1],
        sandbox=sandbox,
    )


def _launch_under(*, installed: _Installed, deadline: int) -> None:
    """Launch an ordinary command through the installed guard; it must RUN.

    The positive half of every admitting case: a guard that installs and checks
    cleanly but cannot actually launch anything would satisfy both of those and
    still leave the sandbox unable to work.
    """
    marker = installed.sandbox / "ran"
    launched = subprocess.run(
        ["/bin/sh", str(installed.guard), "--", "/bin/sh", "-c", f"printf done > {marker}"],
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT_SECONDS,
        env={**os.environ, CREDENTIAL_USE_DEADLINE_ENV_VAR: str(deadline)},
        check=False,
    )
    assert launched.returncode == 0, launched.stderr
    assert marker.read_text(encoding="utf-8") == "done"


def test_the_credential_use_projection_is_its_own_cohesive_module() -> None:
    """The projection has its own file, exporting both halves of the seam.

    Asserted on the PATH before the import, so this fails on a genuine assertion
    while the module does not exist rather than dying at collection.
    """
    assert _module_path().is_file(), f"{_MODULE_NAME} is not a module yet"
    module = importlib.import_module(_MODULE_IMPORT)
    assert set(module.__all__) == {
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
    deadline = int(time.time()) + 3600
    installed = _installed_guard(tmp_path=tmp_path, deadline=deadline)

    check = _run_step(
        script=installed.check_script,
        env=installed.env,
        sandbox=installed.sandbox,
    )
    assert check.returncode == 0, check.stderr
    assert "budget remain" in check.stdout

    _launch_under(installed=installed, deadline=deadline)


def test_a_queue_aged_credential_refuses_at_startup_before_any_agent_node(
    tmp_path: Path,
) -> None:
    """A deadline consumed by queueing or preparation refuses at the START.

    The generated startup check is EXECUTED, and its refusal is what stops the
    sandbox: a prepare step exiting non-zero means no coding-agent node ever
    runs, which is the difference between refusing before credential use and
    discovering the shortfall mid-turn.
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    rendered = _overlay(
        tmp_path=tmp_path,
        codex_auth_snapshot=_FAKE_SNAPSHOT,
        # Stamped before a queue wait that outlasted it.
        credential_use_deadline_epoch=int(time.time()) - 120,
    )
    assert rendered is not None
    document = _parsed(rendered=rendered)
    env = _env_table(document=document)
    steps = _guard_steps(document=document)

    assert _run_step(script=steps[0], env=env, sandbox=sandbox).returncode == 0
    check = _run_step(script=steps[1], env=env, sandbox=sandbox)
    assert check.returncode == GUARD_REFUSAL_EXIT_CODE, check.stdout
    assert "passed" in check.stderr


def test_a_deadline_below_the_admission_floor_still_admits_while_it_is_future(
    tmp_path: Path,
) -> None:
    """Remaining BELOW the admission requirement, deadline STILL FUTURE: admit.

    This is the case that separates enforcing a DEADLINE from re-applying the
    ADMISSION FLOOR at startup, and it is the one an over-strict implementation
    fails. The admission requirement this repository resolves is hundreds of
    thousands of seconds; the deadline here leaves two minutes. Queue and
    preparation delay legitimately consume the original budget, so a sandbox
    whose remaining runway is a fraction of the admission requirement must still
    START and still be able to RUN -- otherwise no dispatch would survive any
    queue wait at all, and the enforcement would have become a second, stricter
    admission gate applied where no renewal is possible.

    The absolute deadline is what bounds it: the launch below is admitted, and
    the guard still holds the instant it was stamped with.
    """
    deadline = int(time.time()) + _SHORT_REMAINING_SECONDS
    installed = _installed_guard(tmp_path=tmp_path, deadline=deadline)

    check = _run_step(
        script=installed.check_script,
        env=installed.env,
        sandbox=installed.sandbox,
    )
    assert check.returncode == 0, check.stderr
    assert "budget remain" in check.stdout

    _launch_under(installed=installed, deadline=deadline)


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
    assert module.credential_use_env_lines(deadline_epoch=None) == ""
    assert module.credential_use_guard_prepare_steps_block(deadline_epoch=None) == ""


def test_a_projected_credential_without_a_deadline_fails_closed(tmp_path: Path) -> None:
    """Codex projected but NO deadline stamped is broken protection, so refuse.

    The mirror of the case above, and the reason that one is not a bypass. Here
    the sandbox genuinely receives a credential, so enforcement is owed; a
    rendered overlay would be an unguarded sandbox holding a live credential.
    The renderer therefore declines to produce one at all, which the dispatch
    path reports as a pre-launch refusal.
    """
    parameters = inspect.signature(render_run_config_overlay).parameters
    assert "credential_use_deadline_epoch" in parameters
    assert (
        _overlay(
            tmp_path=tmp_path,
            codex_auth_snapshot=_FAKE_SNAPSHOT,
            credential_use_deadline_epoch=None,
        )
        is None
    )
