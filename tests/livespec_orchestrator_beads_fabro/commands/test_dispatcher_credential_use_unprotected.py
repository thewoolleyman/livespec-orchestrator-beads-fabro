"""The guard LAUNCHES each adapter when no Codex credential-use deadline exists.

`bd-ib-meejjz`. A dispatch that routes no node to the `codex-acp` agent
projects no Codex credential, so there is no credential-use deadline for the
sandbox to enforce. The adapter wrap is unconditional at both launch sites --
the `fabro run --input` pairs and the literal commands the payload generator
renders into the graph -- so the guard is still the thing that execs every
coding agent, and it has to launch them rather than refuse.

WHY THIS DOES NOT WEAKEN THE FAIL-CLOSED RULE, which is the only reason this
arm is allowed to exist. The guard refuses when it CANNOT READ a deadline,
because proceeding while blinded would make the whole mechanism decoration.
Here it is not blinded: the host DECLARES, in the projection it wrote, that
this dispatch holds no Codex credential. An absent declaration and an absent
deadline together still refuse, which is asserted below -- so forgetting to
project anything is still the refusing case, and only an explicit statement
changes the answer.

TWO CONTRADICTIONS REFUSE, and both are states a correct projection cannot
produce:

- the declaration beside a deadline, which is a projection that says both
  things at once and leaves no reading of which one governs;
- a declaration whose value is anything but the one recognised marker, which
  is how a half-written or hand-edited env table arrives.

AND THE DECLARATION IS NOT SOMETHING A LAUNCH MAY MAKE FOR ITSELF. It joins
the three enforcement variables in both refusal sets -- the adapter-layer one
and the launch-route one -- because a node able to declare itself unprotected
could disarm a protected dispatch's guard from inside the graph, which is the
same hazard those sets already exist to close and is worse than any of them:
the other three move a bound, this one removes it.

EVERY CASE RUNS THE SHIPPED SCRIPT AGAINST REAL PROCESSES, for the reason the
sibling guard module gives: a predicate returning True is not evidence that a
coding agent started, and a recorded intention to exec is not an exec.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    CREDENTIAL_EXPIRY_ENV_VAR,
    CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    CREDENTIAL_USE_DEADLINE_ENV_VAR,
    GUARD_REFUSAL_EXIT_CODE,
    guard_script_text,
)

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_SETTLE_SECONDS = 10

# The deadline a PROTECTED control is given: comfortably future, so the control
# measures the protected path still working rather than a timing race.
_FRESH_SECONDS = 3600

# THE DECLARATION, SPELLED AS A LITERAL AND BOUND BELOW. These cases predate
# the constants they name, and a Red's test bytes are fixed across its
# Red-to-Green pair -- so reaching for the exported names here would make every
# case fail on a missing attribute rather than on the behaviour it is about.
# `test_the_declaration_names_match_the_exported_constants` is what keeps the
# literals honest: it is the one case that reads the production names, so these
# two strings cannot drift away from what the projection actually writes.
_UNPROTECTED_ENV_VAR = "LIVESPEC_CREDENTIAL_USE_UNPROTECTED"
_UNPROTECTED_VALUE = "1"


def _guard_module() -> Any:
    return importlib.import_module(f"{_PACKAGE}._dispatcher_credential_use_guard")


def _guard(*, tmp_path: Path) -> Path:
    """Render the SHIPPED guard script and make it executable."""
    script = tmp_path / "credential-use-guard.sh"
    _ = script.write_text(guard_script_text(), encoding="utf-8")
    script.chmod(0o755)
    return script


def _hermetic_env() -> dict[str, str]:
    """This process's environment with every credential-use projection removed.

    A factory stage runs this suite INSIDE a guarded launch, so its own process
    carries whatever the Dispatcher projected for that node. Inherited, those
    values decide cases here instead of the ones each case sets.
    """
    env = dict(os.environ)
    for name in (
        CREDENTIAL_USE_DEADLINE_ENV_VAR,
        CREDENTIAL_EXPIRY_ENV_VAR,
        CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
        _UNPROTECTED_ENV_VAR,
    ):
        env.pop(name, None)
    return env


def _run(
    *,
    tmp_path: Path,
    argv: list[str],
    deadline: str | None = None,
    unprotected: str | None = None,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the shipped guard around `argv` under the declared projection."""
    env = _hermetic_env()
    if deadline is not None:
        env[CREDENTIAL_USE_DEADLINE_ENV_VAR] = deadline
    if unprotected is not None:
        env[_UNPROTECTED_ENV_VAR] = unprotected
    return subprocess.run(
        ["/bin/sh", str(_guard(tmp_path=tmp_path)), *argv],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=_SETTLE_SECONDS,
        env=env,
        check=False,
    )


def test_an_unprotected_launch_runs_the_adapter_and_passes_its_status_through(
    tmp_path: Path,
) -> None:
    """The adapter EXECUTES, and the guard is transparent to its exit status."""
    marker = tmp_path / "ran"
    result = _run(
        tmp_path=tmp_path,
        unprotected=_UNPROTECTED_VALUE,
        argv=["--", "/bin/sh", "-c", f"printf done > {marker}; exit 7"],
    )

    assert marker.read_text(encoding="utf-8") == "done"
    assert result.returncode == 7


def test_an_unprotected_launch_preserves_stdin(tmp_path: Path) -> None:
    """ACP is bidirectional stdio, so a launch that reads EOF is dead on arrival.

    Asserted separately from the status pass-through above because a wrapper
    that redirected stdin away still runs the command and still returns its
    status: the defect is invisible to every assertion except one that reads.
    """
    result = _run(
        tmp_path=tmp_path,
        unprotected=_UNPROTECTED_VALUE,
        argv=["--", "/bin/cat"],
        stdin_text="initialize",
    )

    assert result.stdout == "initialize"
    assert result.returncode == 0


def test_an_unprotected_launch_outlives_any_deadline_a_protected_one_would_hit(
    tmp_path: Path,
) -> None:
    """No deadline is enforced: the child runs past where a bound would kill it.

    The DISCRIMINATOR against the two cases above, which a guard that simply
    exec'd fast commands would also pass. The child sleeps well past the TERM
    grace a protected launch spends, so a build still arming a reaper -- against
    an unset or zero deadline, both of which are instants already in the past --
    would kill it and change the exit status.
    """
    result = _run(
        tmp_path=tmp_path,
        unprotected=_UNPROTECTED_VALUE,
        argv=["--", "/bin/sh", "-c", "sleep 7; exit 3"],
    )

    assert result.returncode == 3


def test_an_unprotected_start_check_admits_and_says_no_deadline_is_enforced(
    tmp_path: Path,
) -> None:
    """The prepare-step check passes, so no coding-agent node is blocked.

    A non-zero exit here aborts the sandbox during preparation, so this case is
    what keeps the unprotected projection a dispatchable configuration rather
    than one that fails before any node runs.
    """
    result = _run(
        tmp_path=tmp_path,
        unprotected=_UNPROTECTED_VALUE,
        argv=["--check-start"],
    )

    assert result.returncode == 0
    assert "no Codex credential" in result.stdout


def test_an_absent_declaration_with_no_deadline_still_refuses(tmp_path: Path) -> None:
    """THE FAIL-CLOSED CONTROL: silence is not a declaration.

    Without this case the arm above would be indistinguishable from deleting
    the guard's absent-deadline refusal, which is the one change that would
    turn the whole mechanism into decoration the first time a projection
    changed shape.
    """
    marker = tmp_path / "ran"
    result = _run(tmp_path=tmp_path, argv=["--", "/bin/sh", "-c", f"printf done > {marker}"])

    assert result.returncode == GUARD_REFUSAL_EXIT_CODE
    assert not marker.exists()


def test_a_declaration_beside_a_deadline_refuses(tmp_path: Path) -> None:
    """A projection saying both things at once leaves no reading of which governs."""
    marker = tmp_path / "ran"
    result = _run(
        tmp_path=tmp_path,
        deadline=str(int(time.time()) + _FRESH_SECONDS),
        unprotected=_UNPROTECTED_VALUE,
        argv=["--", "/bin/sh", "-c", f"printf done > {marker}"],
    )

    assert result.returncode == GUARD_REFUSAL_EXIT_CODE
    assert not marker.exists()


def test_an_unrecognised_declaration_value_refuses(tmp_path: Path) -> None:
    """Only the one marker value declares anything; everything else fails closed."""
    marker = tmp_path / "ran"
    result = _run(
        tmp_path=tmp_path,
        unprotected="yes",
        argv=["--", "/bin/sh", "-c", f"printf done > {marker}"],
    )

    assert result.returncode == GUARD_REFUSAL_EXIT_CODE
    assert not marker.exists()


def test_a_protected_launch_still_runs_behind_its_deadline(tmp_path: Path) -> None:
    """THE PROTECTED CONTROL: the ordinary path is untouched by the new arm.

    A fresh deadline still lets an ordinary command finish and still passes its
    status through, which is what separates adding an unprotected arm from
    retiring the protected one.
    """
    marker = tmp_path / "ran"
    result = _run(
        tmp_path=tmp_path,
        deadline=str(int(time.time()) + _FRESH_SECONDS),
        argv=["--", "/bin/sh", "-c", f"printf done > {marker}; exit 5"],
    )

    assert marker.read_text(encoding="utf-8") == "done"
    assert result.returncode == 5


def _declared_env_keys(*, lines: str) -> set[str]:
    """The env-table KEYS `lines` declares, read from the key position only.

    A substring scan cannot answer this question. The guard's own text rides
    this table as a value, and that text necessarily MENTIONS every variable it
    reads -- so a scan for the deadline name finds it inside the script on a
    projection that declares no deadline at all. The key position is the only
    place a declaration can be, and `json.dumps` guarantees a value's newlines
    are escaped, so each physical line here is one declaration.
    """
    return {
        line.split("=", 1)[0].strip()
        for line in lines.splitlines()
        if "=" in line and not line.startswith(" ")
    }


def test_the_unprotected_projection_renders_the_guard_but_no_deadline_names() -> None:
    """The env table declares the marker and the script, and no enforcement name.

    The three enforcement names must be ABSENT rather than empty: the guard's
    startup grade treats exactly one of the expiry pair being present as a
    half-wired projection and fails closed on it, so a projection that emitted
    them blank would refuse every unprotected dispatch at prepare time.
    """
    projection = importlib.import_module(f"{_PACKAGE}._dispatcher_credential_use_projection")
    unprotected = projection.UnprotectedCredentialUse()

    declared = _declared_env_keys(lines=projection.credential_use_env_lines(projection=unprotected))

    assert _UNPROTECTED_ENV_VAR in declared
    for name in (
        CREDENTIAL_USE_DEADLINE_ENV_VAR,
        CREDENTIAL_EXPIRY_ENV_VAR,
        CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    ):
        assert name not in declared
    # The POSITIVE control for the reader above: a protected projection declares
    # all three. Without it, a reader that found nothing anywhere would satisfy
    # every assertion here while measuring the wrong thing entirely.
    protected = _declared_env_keys(
        lines=projection.credential_use_env_lines(
            projection=projection.CredentialUseProjection(
                deadline_epoch=2_000_000_000,
                credential_expiry_epoch=2_000_003_600,
                required_remaining_seconds=1_800,
            )
        )
    )
    assert {
        CREDENTIAL_USE_DEADLINE_ENV_VAR,
        CREDENTIAL_EXPIRY_ENV_VAR,
        CREDENTIAL_REQUIRED_REMAINING_ENV_VAR,
    } <= protected
    assert _UNPROTECTED_ENV_VAR not in protected


def test_the_unprotected_projection_still_installs_the_guard_and_checks_startup() -> None:
    """The launch wrap is unconditional, so the script has to be on disk.

    Rendering no prepare steps here would leave every adapter exec'ing a path
    that does not exist -- the launch renderer splices the guard in whether or
    not a credential was projected -- so the dispatch would die at its first
    coding-agent node on a missing file.
    """
    projection = importlib.import_module(f"{_PACKAGE}._dispatcher_credential_use_projection")
    guard = _guard_module()

    block = projection.credential_use_guard_prepare_steps_block(
        projection=projection.UnprotectedCredentialUse()
    )

    assert guard.GUARD_SCRIPT_PATH in block
    assert "--check-start" in block
    # And a caller projecting NOTHING at all still renders nothing, which is the
    # shape every direct caller of the overlay renderer passes.
    assert projection.credential_use_guard_prepare_steps_block(projection=None) == ""


def test_a_guarded_literal_declaring_itself_unprotected_is_refused() -> None:
    """A node may not declare itself unprotected from inside the graph.

    The engine peels a launch's leading `KEY=value` tokens into the GUARD's own
    environment, so a node spelling this name would disarm the guard on a
    PROTECTED dispatch -- worse than the three enforcement variables already
    refused here, which move the bound rather than remove it.
    """
    guard = _guard_module()
    routes = importlib.import_module(f"{_PACKAGE}._dispatcher_credential_use_routes")
    name = _UNPROTECTED_ENV_VAR
    guard_prefix = " ".join(guard.guarded_acp_command(argv=[]))
    graph = (
        "digraph implement_work_item {\n"
        '  graph [entrypoint="implement"]\n'
        f'  implement [backend="acp", acp.command="{name}=1 {guard_prefix} npx -y acp"]\n'
        "}\n"
    )

    refusal = routes.unguardable_launch_refusal(graph_text=graph, adapter_inputs=frozenset())

    assert refusal is not None
    assert name in refusal


def test_an_adapter_declaring_itself_unprotected_refuses_the_dispatch() -> None:
    """The same name is refused where adapters are VALIDATED, not only wrapped.

    An adapter's env assignments are applied to the guard's own process too, so
    the refusal has to reach the operator as a dispatch refusal naming the
    variable -- the wrap step has no channel to report one.
    """
    layers = importlib.import_module(f"{_PACKAGE}._acp_node_layers")
    catalogs = importlib.import_module(f"{_PACKAGE}._acp_catalogs")
    nodes = importlib.import_module(f"{_PACKAGE}._dispatcher_acp_nodes")
    name = _UNPROTECTED_ENV_VAR

    overlays = nodes.dispatch_acp_overlays(
        overrides=(f"implement={name}=1 /usr/bin/agent",),
        catalogs=catalogs.builtin_catalogs(),
    )
    assert not isinstance(overlays, str), overlays

    refusal = layers.resolve_acp_nodes(
        workflow_inputs={"implement_adapter": "npx -y claude-code-acp"},
        repository={},
        dispatch=overlays,
    )

    assert isinstance(refusal, str), refusal
    assert name in refusal
    assert "implement" in refusal


def test_the_declaration_names_match_the_exported_constants() -> None:
    """Bind the two literals above to the production names they stand for.

    Every other case here spells the declaration itself, which is what lets
    them fail on BEHAVIOUR rather than on a missing attribute. This is the one
    case that reads the exported constants, so a rename that left the literals
    behind fails here instead of turning every case above into a silent test of
    a variable nothing writes.
    """
    guard = _guard_module()

    assert guard.CREDENTIAL_USE_UNPROTECTED_ENV_VAR == _UNPROTECTED_ENV_VAR
    assert guard.CREDENTIAL_USE_UNPROTECTED_VALUE == _UNPROTECTED_VALUE
