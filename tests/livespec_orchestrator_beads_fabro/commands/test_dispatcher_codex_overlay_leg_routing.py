"""The POST-CLAIM Codex overlay leg, SCOPED to Codex routing.

`bd-ib-meejjz`. The pre-dispatch wall's gate is only the first of the three
places the host Codex credential is applied unconditionally. This module covers
the second: the overlay leg grades the credential AGAIN -- without renewing it --
and stamps the sandbox's credential-use enforcement inputs from that grade.

WHY SCOPING THE WALL ALONE WOULD HAVE BEEN WORSE THAN DOING NOTHING. The wall
runs BEFORE the claim, and the whole reason the gate was moved there is that a
credential refusal reported after the claim leaves the row `active` with no
factory run -- the stranded shape nothing reaps. So a build that skipped the
pre-claim grade for an all-Claude dispatch while this leg still graded would
move every such refusal from the one position that can report it safely to the
one position that cannot.

WHAT IS MEASURED HERE, AND WHY IT IS A LOG RATHER THAN A RETURN VALUE. "Does
not grade" and "does not project" are claims about INTERACTIONS, and no
end-state assertion can carry either: a leg that read the host credential,
graded it against the floor, stamped the deadline inputs and then happened to
discard them would return a value indistinguishable from one that never looked.
So the requirement resolution, the host credential read, the enforcement-input
stamp and the launch-route check each append to ONE log, and the all-Claude case
asserts that log is EMPTY.

THE CODEX-ROUTED CONTROL IS NOT OPTIONAL. Without it every assertion below is
equally satisfied by deleting the leg, which is the one outcome this change must
not produce. The control runs the SAME inputs through the SAME leg with a
routing that names the `codex-acp` agent and requires the full sequence, in
order, followed by a leg carrying the graded snapshot and the stamped
projection.

WHY THE UNPROTECTED SHAPE IS A DECLARATION AND NOT `None`. The sandbox guard
execs every coding agent whether or not a credential was projected, because the
adapter wrap is unconditional at both launch sites. `None` is what a caller
passes when it says nothing at all, and the guard must keep REFUSING on silence
-- that is what a broken projection looks like. So the leg returns the host's
explicit statement that it read the routing and projected nothing, which is the
only thing that may disarm the deadline.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_LEG_MODULE = f"{_PACKAGE}._dispatcher_codex_overlay_leg"
_PROJECTION_MODULE = f"{_PACKAGE}._dispatcher_credential_use_projection"
_ROUTING_MODULE = f"{_PACKAGE}._dispatcher_codex_routing"
_REQUIREMENT_MODULE = f"{_PACKAGE}._dispatcher_credential_deadline"

_NOW = 1_000_000

# The run budget and margin the stubbed requirement resolves to. Positioned as
# whole figures because nothing here grades a credential against them -- the
# grade itself is stood in, and what is asserted is WHETHER it ran.
_ALLOWANCE = 14_400
_MARGIN = 3_600

# The snapshot the stood-in grade returns, and the three enforcement figures the
# stood-in stamp returns. Both are opaque to this module: they exist so the
# Codex-routed control can assert that what the leg carries out is what its two
# collaborators handed in, rather than something it rebuilt.
_SNAPSHOT = '{"auth_mode": "chatgpt", "tokens": {"access_token": "projected"}}'
_DEADLINE_EPOCH = _NOW + _ALLOWANCE
_EXPIRY_EPOCH = _NOW + _ALLOWANCE + _MARGIN

# The routing details the two cases declare. Carried verbatim into the leg so a
# reader of a failure sees which dispatch shape was being described.
_ALL_CLAUDE_DETAIL = (
    "no resolved ACP candidate key names the codex-acp agent; resolved candidate "
    "keys: claude-acp/anthropic/claude-opus-4-8"
)
_CODEX_DETAIL = "resolved ACP candidate keys naming the codex-acp agent: codex-acp/openai/gpt-5.1"

# The telemetry table's three inputs, each a value the leg cannot derive. They are
# distinguishable literals so the Codex-routed control can assert the table was
# rendered FROM WHAT THE CALLER HANDED IN: a leg resolving the endpoint or either
# correlation id for itself would render a well-formed table that attributes every
# Codex span to the wrong dispatch, which no shape assertion can see.
_OTEL_ENDPOINT = "http://127.0.0.1:44318"
_WORK_ITEM_ID = "bd-ib-meejjz"
_DISPATCH_ID = "01M50FM0207FG8V82VBE1TTDT8"


def _modules() -> tuple[ModuleType, ModuleType, ModuleType, ModuleType]:
    """The four modules under test, imported inside the body.

    Imported here rather than at module scope so this file's Red is a genuine
    assertion failure rather than a collection error: every module below already
    exists, and what does not yet exist is the leg's routing parameter.
    """
    return (
        importlib.import_module(_LEG_MODULE),
        importlib.import_module(_PROJECTION_MODULE),
        importlib.import_module(_ROUTING_MODULE),
        importlib.import_module(_REQUIREMENT_MODULE),
    )


def _stub_leg_collaborators(
    *, monkeypatch: pytest.MonkeyPatch, leg: ModuleType, projection: ModuleType
) -> list[str]:
    """Stand in every collaborator the leg reaches, and log each in call order.

    Each one is stood in rather than exercised because each reads the host
    filesystem, the selected graph or committed configuration for its own
    reasons, and any one of them answering first would shadow the scoping this
    module is about. The LOG is the measurement: the all-Claude case requires it
    empty, and the Codex-routed control requires the full sequence in order.
    """
    requirement_module = importlib.import_module(_REQUIREMENT_MODULE)
    calls: list[str] = []

    def _requirement(**_kwargs: Any) -> Any:
        calls.append("requirement")
        return requirement_module.CredentialLifetimeRequirement(
            execution_allowance_seconds=_ALLOWANCE,
            # Wider than the allowance, so the allowance governs and this case
            # keeps grading the routing it was written against.
            credential_use_window_seconds=_ALLOWANCE * 10,
            credential_queue_allowance_seconds=86_400,
            margin_seconds=_MARGIN,
            detail="test-resolved requirement",
        )

    def _grade(**_kwargs: Any) -> str:
        calls.append("grade")
        return _SNAPSHOT

    def _stamp(**_kwargs: Any) -> Any:
        calls.append("project")
        return projection.CredentialUseProjection(
            deadline_epoch=_DEADLINE_EPOCH,
            credential_expiry_epoch=_EXPIRY_EPOCH,
            required_remaining_seconds=_ALLOWANCE + _MARGIN,
        )

    def _route_check(**_kwargs: Any) -> None:
        calls.append("route-check")

    monkeypatch.setattr(leg, "credential_lifetime_requirement_for", _requirement)
    monkeypatch.setattr(leg, "project_host_codex_auth", _grade)
    monkeypatch.setattr(leg, "credential_use_projection_for", _stamp)
    monkeypatch.setattr(leg, "selected_graph_launch_refusal", _route_check)
    return calls


def test_an_all_claude_dispatch_is_neither_graded_nor_projected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dispatch routing no node to Codex reaches no credential surface at all.

    The `committed` path handed in DOES NOT EXIST, which is a second, independent
    reading of the same claim: the requirement resolution and the launch-route
    check both read that file, so a leg that reached either of them would raise
    rather than return. That is what makes this case fail for the right reason
    even if the call log were ever stubbed into silence.
    """
    leg, projection, routing, _requirement = _modules()
    parameters = inspect.signature(leg.project_codex_overlay_leg).parameters
    assert "codex_routing" in parameters, (
        "the overlay leg must take this dispatch's resolved Codex routing: without "
        "it the leg cannot scope the grade and the enforcement-input stamp away "
        "from a dispatch that routes no node to the codex-acp agent, and a "
        "credential refusal raised here lands AFTER the claim"
    )
    calls = _stub_leg_collaborators(monkeypatch=monkeypatch, leg=leg, projection=projection)

    resolved = leg.project_codex_overlay_leg(
        committed=tmp_path / "absent" / "workflow.toml",
        block={},
        review_fix_visit_cap=2,
        graph_override=None,
        adapter_inputs=frozenset({"implement_adapter"}),
        clock=lambda: _NOW,
        codex_routing=routing.CodexRouting(routes_codex=False, detail=_ALL_CLAUDE_DETAIL),
        sandbox_otel_endpoint=_OTEL_ENDPOINT,
        work_item_id=_WORK_ITEM_ID,
        dispatch_id=_DISPATCH_ID,
    )

    assert calls == [], (
        "an all-Claude dispatch must reach no credential surface, but the leg " f"called: {calls}"
    )
    assert not isinstance(resolved, str), f"the leg refused an all-Claude dispatch: {resolved}"
    assert resolved.snapshot is None, (
        "no Codex credential may be projected into the sandbox of a dispatch that "
        "routes no node to Codex"
    )
    assert isinstance(resolved.credential_use, projection.UnprotectedCredentialUse), (
        "the leg must carry the host's EXPLICIT declaration that nothing was "
        "projected; None is silence, and the guard fails closed on silence"
    )
    assert resolved.otel_config is None, (
        "the Codex telemetry table must be withheld on the SAME arm as the "
        "credential: it is written into the $CODEX_HOME only the credential "
        "projection declares, so a table projected here renders a prepare step "
        'that runs as `mkdir -p ""` and aborts preparation'
    )


def test_a_codex_routed_dispatch_is_graded_and_projected_exactly_as_before(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control. A dispatch that DOES route a node to Codex loses nothing.

    Asserted as the full sequence IN ORDER rather than as a set, because the
    order inside this leg is load-bearing: the requirement sizes the grade, the
    grade produces the snapshot the enforcement inputs are stamped from, and the
    route check runs last among them so a refusal cannot leave a live credential
    behind.
    """
    leg, projection, routing, _requirement = _modules()
    calls = _stub_leg_collaborators(monkeypatch=monkeypatch, leg=leg, projection=projection)

    resolved = leg.project_codex_overlay_leg(
        committed=tmp_path / "workflow.toml",
        block={},
        review_fix_visit_cap=2,
        graph_override=None,
        adapter_inputs=frozenset({"implement_adapter"}),
        clock=lambda: _NOW,
        codex_routing=routing.CodexRouting(routes_codex=True, detail=_CODEX_DETAIL),
        sandbox_otel_endpoint=_OTEL_ENDPOINT,
        work_item_id=_WORK_ITEM_ID,
        dispatch_id=_DISPATCH_ID,
    )

    assert calls == ["requirement", "grade", "project", "route-check"], (
        "a Codex-routed dispatch must still resolve its requirement, grade the "
        f"host credential, stamp the enforcement inputs and check the launch routes, in that order; got: {calls}"
    )
    assert not isinstance(resolved, str), f"the leg refused a Codex-routed dispatch: {resolved}"
    assert (
        resolved.snapshot == _SNAPSHOT
    ), "the leg must carry out the snapshot its grade handed in, not one it rebuilt"
    assert isinstance(resolved.credential_use, projection.CredentialUseProjection), (
        "a Codex-routed dispatch must carry the full three-field projection, which "
        "is what installs the guard's deadline"
    )
    assert resolved.credential_use.deadline_epoch == _DEADLINE_EPOCH
    # The telemetry table, carried on the arm that declares the $CODEX_HOME it is
    # written into. Read for the correlation pair rather than pinned whole: the
    # document's own shape is pinned by `test_dispatcher_codex_otel_config`, while
    # what this leg decides is WHETHER it is rendered and from WHICH inputs — and
    # a leg resolving the endpoint or the ids for itself would produce a
    # well-formed table correlating to the wrong dispatch.
    assert resolved.otel_config is not None, (
        "a Codex-routed dispatch still carries the [otel] table codex-core reads "
        "its trace exporter from; without it Codex exports no span at all"
    )
    for expected in (_OTEL_ENDPOINT, _WORK_ITEM_ID, _DISPATCH_ID):
        assert expected in resolved.otel_config, (
            "the table must be rendered from the inputs the caller handed in; "
            f"missing {expected!r} in: {resolved.otel_config}"
        )
