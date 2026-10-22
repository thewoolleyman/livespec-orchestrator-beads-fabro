"""Scenario 228 — the freshness requirement is the SMALLER of two figures.

Binds `SPECIFICATION/scenarios.md` "Scenario 228 — The credential freshness
requirement is the smaller of the execution allowance and the bounded
credential-use window", and the worker-credential-projection paragraph of
`SPECIFICATION/contracts.md` that states the worker's maximum run budget.

WHY THIS HEADING NEEDED A TEST AT ALL, stated here because it is the whole
point of the clause. The execution allowance is derived by SUMMING the visit
caps, retry budgets and resolved node timeouts of the selected graph, so a
ratified graph change that adds one cycle through an existing loop multiplies
into it: v175's recapture route took the shipped graph's allowance to 902955
seconds and its freshness requirement to 906555, which is MORE than the 864000
seconds a freshly renewed Codex credential carries. Every Codex-routed dispatch
then refused at the gate with no run and no claim, and no configuration in the
repository could buy it back — the requirement exceeded what the host can mint.
That is the defect the smaller-of-two rule retires: the requirement is now
bounded by limits the FACTORY enforces (the credential queue allowance plus the
whole-run wall budget) rather than by a sum over a graph.

WHY THE MODULE PATH IS ASSERTED BEFORE THE IMPORT. A top-level import of a
module that does not exist yet dies at COLLECTION, which proves only that the
module is unimportable and runs no assertion at all. Asserting the path first
makes the Red a genuine assertion failure about the behaviour being absent, and
the import then happens inside the test body where the module exists.
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

_COMMANDS = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_WINDOW_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_window"
_QUEUE_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_queue_allowance"
_PAYLOAD_MODULE = (
    "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement_payload"
)

# Scenario 228's own figures, kept as named constants so a reader can check each
# against the Gherkin rather than against an arithmetic expression.
_EXECUTION_ALLOWANCE_SECONDS = 902_955
_QUEUE_ALLOWANCE_SECONDS = 86_400
_RUN_WALL_BUDGET_SECONDS = 21_600
_CREDENTIAL_USE_WINDOW_SECONDS = _QUEUE_ALLOWANCE_SECONDS + _RUN_WALL_BUDGET_SECONDS
_MARGIN_SECONDS = 3_600
_REQUIRED_LIFETIME_SECONDS = 111_600
_FRESH_CREDENTIAL_LIFETIME_SECONDS = 864_000

# The guard case's own deadline, kept short so a real child can be observed
# dying by it, plus the slack a loaded host's scheduler costs. The guard sends
# TERM a five-second grace BEFORE the deadline and KILL at it, so a deadline
# below that grace would assert nothing about the ordering.
_GUARD_DEADLINE_SECONDS = 8
_GUARD_SLACK_SECONDS = 20


def test_scenario228_the_bounded_window_governs_when_it_is_smaller() -> None:
    """The window is 108000, so 111600 is required and the window is named.

    Both halves are asserted, and the second is why the first is evidence: a
    figure alone does not say which of the two produced it, and an operator
    reading a refusal needs to know whether to shorten a node timeout or to
    raise the queue allowance. The credential comparison closes the loop on the
    defect — the same graph that priced a fresh credential out now fits inside
    one with 752400 seconds to spare.
    """
    assert (_COMMANDS / "_dispatcher_credential_window.py").is_file(), (
        "the governing-figure arithmetic has no module yet, so the freshness "
        "requirement is still the raw execution allowance"
    )
    window_module = importlib.import_module(_WINDOW_MODULE)

    window = window_module.credential_use_window_seconds(
        queue_allowance_seconds=_QUEUE_ALLOWANCE_SECONDS,
        run_wall_budget_seconds=_RUN_WALL_BUDGET_SECONDS,
    )
    assert window == _QUEUE_ALLOWANCE_SECONDS + _RUN_WALL_BUDGET_SECONDS

    governing = window_module.governing_run_budget(
        execution_allowance_seconds=_EXECUTION_ALLOWANCE_SECONDS,
        credential_use_window_seconds=window,
    )
    assert governing.seconds == window
    assert governing.figure == window_module.CREDENTIAL_USE_WINDOW_FIGURE
    assert governing.seconds + _MARGIN_SECONDS == _REQUIRED_LIFETIME_SECONDS
    assert _REQUIRED_LIFETIME_SECONDS < _FRESH_CREDENTIAL_LIFETIME_SECONDS


def test_scenario228_the_execution_allowance_governs_when_it_is_smaller() -> None:
    """A 60000-second allowance under a 108000-second window governs at 60000.

    The MIRROR of the case above, and it is not redundant: a derivation that
    returned the window unconditionally would satisfy the first case exactly and
    would bound every dispatch at the queue window however short its graph.
    """
    assert (_COMMANDS / "_dispatcher_credential_window.py").is_file()
    window_module = importlib.import_module(_WINDOW_MODULE)

    governing = window_module.governing_run_budget(
        execution_allowance_seconds=60_000,
        credential_use_window_seconds=window_module.credential_use_window_seconds(
            queue_allowance_seconds=_QUEUE_ALLOWANCE_SECONDS,
            run_wall_budget_seconds=_RUN_WALL_BUDGET_SECONDS,
        ),
    )
    assert governing.seconds == 60_000
    assert governing.figure == window_module.EXECUTION_ALLOWANCE_FIGURE
    assert governing.seconds + _MARGIN_SECONDS == 63_600


def test_scenario228_the_queue_allowance_defaults_to_one_day() -> None:
    """A repository declaring nothing resolves the documented 86400 seconds.

    Asserted through the RESOLUTION rather than against the constant, because
    the constant is what a reader of this module would check and the resolution
    is what a dispatch receives: a default declared and never read is the one
    shape a constant-only assertion cannot tell from a working one.
    """
    assert (_COMMANDS / "_dispatcher_credential_queue_allowance.py").is_file(), (
        "the credential queue allowance has no module yet, so no dispatch can "
        "resolve the bounded credential-use window"
    )
    queue_module = importlib.import_module(_QUEUE_MODULE)

    resolved = queue_module.credential_queue_allowance_from_block(block={})
    assert resolved.seconds == _QUEUE_ALLOWANCE_SECONDS
    assert resolved.seconds == queue_module.DEFAULT_CREDENTIAL_QUEUE_ALLOWANCE_SECONDS


def test_scenario228_the_resolved_requirement_is_bounded_by_the_window() -> None:
    """THIS repository's own shipped graph resolves 111600, not its raw allowance.

    The subject is the repository's own committed workflow and `.livespec.jsonc`
    rather than a fixture, which is the whole point: the defect was that the
    SHIPPED graph's allowance crossed a credential ceiling, so a fixture graph
    would grade an allowance no dispatch ever derives. Both figures are read off
    the one resolution, because the requirement has to carry the allowance it
    did NOT use as well as the figure it did — an operator comparing a refusal
    against a status reading needs to see which of the two moved.
    """
    requirement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_requirement"
    ).resolve_credential_lifetime_requirement(repo=_REPO_ROOT)

    assert hasattr(requirement, "governing_figure"), (
        "the resolved requirement names no governing figure, so the freshness "
        "gate is still demanding the raw execution allowance"
    )
    assert requirement.credential_use_window_seconds == _CREDENTIAL_USE_WINDOW_SECONDS
    assert requirement.execution_allowance_seconds > _CREDENTIAL_USE_WINDOW_SECONDS
    assert requirement.allowance_seconds == _CREDENTIAL_USE_WINDOW_SECONDS
    assert requirement.required_seconds == _REQUIRED_LIFETIME_SECONDS
    window_module = importlib.import_module(_WINDOW_MODULE)
    assert requirement.governing_figure == window_module.CREDENTIAL_USE_WINDOW_FIGURE


def test_scenario228_both_surfaces_report_the_same_figure_and_name_what_governed() -> None:
    """ONE renderer, so the status and manual-renewal surfaces cannot drift apart.

    Asserted as EQUALITY of the two rendered objects rather than needle by
    needle: the clause's requirement is that the two surfaces report the SAME
    figure, and two independently drifting renderers that each mention a
    governing figure satisfy a containment check just as well.

    Both branches are rendered from the same pair of requirements, because a
    renderer that hard-coded either name would satisfy one case alone — and the
    execution-allowance branch is the one that bounds a repository whose graph
    is short, which is every adopter's first dispatch.
    """
    assert (_COMMANDS / "_dispatcher_credential_requirement_payload.py").is_file(), (
        "no shared renderer projects the requirement, so the status and "
        "manual-renewal surfaces report no governing figure at all"
    )
    payload_module = importlib.import_module(_PAYLOAD_MODULE)
    window_module = importlib.import_module(_WINDOW_MODULE)

    bounded = _requirement(execution_allowance_seconds=_EXECUTION_ALLOWANCE_SECONDS)
    shorter = _requirement(execution_allowance_seconds=60_000)

    assert payload_module.credential_requirement_payload(requirement=bounded) == {
        "governing_budget_seconds": _CREDENTIAL_USE_WINDOW_SECONDS,
        "governing_figure": window_module.CREDENTIAL_USE_WINDOW_FIGURE,
        "required_remaining_seconds": _REQUIRED_LIFETIME_SECONDS,
        "execution_allowance_seconds": _EXECUTION_ALLOWANCE_SECONDS,
        "credential_use_window_seconds": _CREDENTIAL_USE_WINDOW_SECONDS,
        "credential_queue_allowance_seconds": _QUEUE_ALLOWANCE_SECONDS,
    }
    assert payload_module.credential_requirement_payload(requirement=shorter) == {
        "governing_budget_seconds": 60_000,
        "governing_figure": window_module.EXECUTION_ALLOWANCE_FIGURE,
        "required_remaining_seconds": 63_600,
        "execution_allowance_seconds": 60_000,
        "credential_use_window_seconds": _CREDENTIAL_USE_WINDOW_SECONDS,
        "credential_queue_allowance_seconds": _QUEUE_ALLOWANCE_SECONDS,
    }


def _requirement(*, execution_allowance_seconds: int) -> object:
    """One requirement carrying Scenario 228's window and a chosen allowance."""
    deadline_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_deadline"
    )
    return deadline_module.CredentialLifetimeRequirement(
        execution_allowance_seconds=execution_allowance_seconds,
        credential_use_window_seconds=_CREDENTIAL_USE_WINDOW_SECONDS,
        credential_queue_allowance_seconds=_QUEUE_ALLOWANCE_SECONDS,
        margin_seconds=_MARGIN_SECONDS,
        detail="",
    )


def test_scenario228_the_worker_deadline_uses_the_governing_figure() -> None:
    """The projection instant plus the SAME figure the freshness gate requires.

    The join is what this case adds, and it is the clause's own requirement
    ("so the host gate and the in-sandbox guard use one figure"): each half was
    already covered alone, and two surfaces that each derive a plausible figure
    are exactly the shape that disagrees across a container boundary with
    nothing in either record to say which arithmetic was wrong.

    Both figures are read off ONE requirement rather than supplied, so the
    deadline is compared against the gate's own comparand. The credential is
    given far more lifetime than the window needs, which is what makes the
    GOVERNING FIGURE the binding term rather than the expiry cap beside it —
    with a short expiry the same assertion would hold for a deadline derived
    from no allowance at all.
    """
    assert (_COMMANDS / "_dispatcher_credential_window.py").is_file()
    projection_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_projection"
    )
    requirement = _requirement(execution_allowance_seconds=_EXECUTION_ALLOWANCE_SECONDS)
    projected_at = 1_000_000
    expiry = projected_at + _FRESH_CREDENTIAL_LIFETIME_SECONDS

    projected = projection_module.credential_use_projection_for(
        codex_snapshot=_codex_snapshot(exp=expiry),
        allowance_seconds=requirement.allowance_seconds,
        margin_seconds=requirement.margin_seconds,
        now_epoch=projected_at,
    )

    assert requirement.allowance_seconds == _CREDENTIAL_USE_WINDOW_SECONDS
    assert projected.deadline_epoch == projected_at + requirement.allowance_seconds
    assert projected.required_remaining_seconds == requirement.required_seconds


def test_scenario228_a_coding_agent_still_running_at_the_deadline_is_stopped() -> None:
    """The guard's reaper, EXECUTED, so the deadline is a bound rather than a field.

    A projected deadline is only a bound if something enforces it, and the
    enforcement is POSIX sh inside the sandbox — so this runs the shipped guard
    bytes against a real sleeping child and asserts the child is gone BY the
    instant the deadline names. Asserting the projection alone would certify a
    number nobody acts on.
    """
    guard_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard"
    )
    with tempfile.TemporaryDirectory() as directory:
        guard = Path(directory) / "guard.sh"
        _ = guard.write_text(guard_module.guard_script_text(), encoding="utf-8")
        deadline = int(time.time()) + _GUARD_DEADLINE_SECONDS
        started = time.monotonic()
        completed = subprocess.run(
            ["/bin/sh", str(guard), "--", "/bin/sh", "-c", "sleep 600"],
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                guard_module.CREDENTIAL_USE_DEADLINE_ENV_VAR: str(deadline),
            },
        )

    assert completed.returncode != 0, completed.stdout
    # BY the deadline, not after it: the grace is spent inside the allowance.
    assert time.monotonic() - started <= _GUARD_DEADLINE_SECONDS + _GUARD_SLACK_SECONDS
    assert int(time.time()) >= deadline - _GUARD_SLACK_SECONDS


def test_scenario228_the_start_check_grades_the_credential_with_budget_remaining() -> None:
    """An aged CREDENTIAL refuses while the whole wall budget still remains.

    The clause requires BOTH measurements at the start check and says they are
    different ones. This case establishes the premise the other measurement
    reads — the time remaining before the deadline is at least the resolved
    whole-run wall budget — and asserts the launch is refused anyway, on the
    credential. Without that premise an implementation that graded only the
    queue would satisfy the refusal and never read the credential at all.

    The credential is given EXACTLY the required lifetime, which the admission
    criterion (strictly greater) does not admit: the credential that would
    finish its last enforced second with zero margin is the one state the
    margin exists to prevent.
    """
    guard_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard"
    )
    now = int(time.time())
    deadline = now + _CREDENTIAL_USE_WINDOW_SECONDS
    assert deadline - now >= _RUN_WALL_BUDGET_SECONDS, "the budget premise does not hold"

    with tempfile.TemporaryDirectory() as directory:
        guard = Path(directory) / "guard.sh"
        _ = guard.write_text(guard_module.guard_script_text(), encoding="utf-8")
        completed = subprocess.run(
            ["/bin/sh", str(guard), "--check-start"],
            capture_output=True,
            text=True,
            check=False,
            env={
                **os.environ,
                guard_module.CREDENTIAL_USE_DEADLINE_ENV_VAR: str(deadline),
                guard_module.CREDENTIAL_EXPIRY_ENV_VAR: str(now + _REQUIRED_LIFETIME_SECONDS),
                guard_module.CREDENTIAL_REQUIRED_REMAINING_ENV_VAR: str(_REQUIRED_LIFETIME_SECONDS),
            },
        )

    assert completed.returncode == guard_module.GUARD_REFUSAL_EXIT_CODE, completed.stdout
    # The refusal must name the CREDENTIAL shortfall and not the deadline, or it
    # reports a cause nobody measured.
    assert "remaining lifetime" in completed.stderr
    assert "passed" not in completed.stderr


def _codex_snapshot(*, exp: int) -> str:
    """A Codex auth snapshot whose access token carries one expiry claim."""
    claims = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    token = f"header.{claims}.signature"
    return json.dumps({"tokens": {"access_token": token}})
