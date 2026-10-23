"""Coverage for the attention row an admission-required ACP chain's wait produces.

Binds the enumerated availability wait of `SPECIFICATION/contracts.md`, whose
wait-completeness clause among the orchestrator-owned attention facts reads:
"an item waiting because an admission-required ACP chain has no eligible
candidate ... likewise stays `ready`. The wait item MUST name the governing
condition and scheduled reevaluation instant."

EVERY FIXTURE HOLD EXPIRES IN THE FAR FUTURE, and that is what makes the rows
deterministic rather than merely stable-looking. `_reevaluate_at` is the
EARLIEST governing expiry whenever one parses, so a live hold fixes the
instant the row prints independently of when the pass runs -- which is the
ordinary shape of an availability wait, and the only shape under which two
real-clock passes can be compared for byte-identity at all.
"""

from __future__ import annotations

import argparse
import importlib
import json
import shlex
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_needs_attention_availability_wait.py"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE_NAME = f"{_PACKAGE}._needs_attention_availability_wait"
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_FAR_FUTURE = "2099-01-01T00:15:00Z"
_LATER_STILL = "2099-01-01T00:45:00Z"

_GRAPH = """
    graph [stall_timeout="7200s"]
    start [shape=Mdiamond, label="Start"]
    exit  [shape=Msquare, label="Exit"]
    implement [backend="acp", acp.command="a", timeout="60s"]
    gate [shape=parallelogram, timeout="60s"]
    start -> implement
    implement -> gate
    gate -> exit [label="green", condition="outcome=succeeded"]
"""

_MANIFEST = """[workflow]
graph = "workflow.fabro"

[run.inputs]
implement_adapter = "adapter-primary"
"""

_CHAIN = {
    "livespec-orchestrator-beads-fabro": {
        "dispatcher": {
            "acp_nodes": {
                "implement": {
                    "display_name": "Primary",
                    "candidate_key": "primary",
                    "availability_key": "codex",
                    "command": "adapter-primary",
                    "fallbacks": [
                        {
                            "display_name": "Fallback",
                            "candidate_key": "fallback",
                            "availability_key": "anthropic",
                            "command": "adapter-fallback",
                        }
                    ],
                }
            }
        }
    }
}


def _item(*, id_: str, status: str = "ready", **overrides: object) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status=status,  # pyright: ignore[reportArgumentType]
        title=f"{id_} title",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _hold(*, observation_id: str, hold_key: str, expires_at: str) -> dict[str, object]:
    return {
        "stage": "acp-availability-observed",
        "schema_version": 1,
        "observation_id": observation_id,
        "scope": "availability-domain",
        "hold_key": hold_key,
        "candidate_key": None,
        "cause": "quota",
        "occurred_at": "2026-09-12T11:50:00Z",
        "expires_at": expires_at,
    }


def _exhausted_repo(root: Path) -> Path:
    """A repository whose only ACP chain is emptied by two live domain holds."""
    workflow = root / ".fabro" / "workflows" / "implement-work-item"
    workflow.mkdir(parents=True)
    (workflow / "workflow.toml").write_text(_MANIFEST, encoding="utf-8")
    (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    (root / ".livespec.jsonc").write_text(json.dumps(_CHAIN), encoding="utf-8")
    journal = root / _JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        "".join(
            json.dumps(record, sort_keys=True) + "\n"
            for record in (
                _hold(observation_id="obs-codex", hold_key="codex", expires_at=_LATER_STILL),
                _hold(observation_id="obs-anthropic", hold_key="anthropic", expires_at=_FAR_FUTURE),
            )
        ),
        encoding="utf-8",
    )
    return root


def _availability_wait_items(**kwargs: object) -> list[Any]:
    module = importlib.import_module(_MODULE_NAME)
    return module.availability_wait_items(**kwargs)


def _availability_wait_handoff(**kwargs: object) -> Any:
    module = importlib.import_module(_MODULE_NAME)
    return module.availability_wait_handoff(**kwargs)


def _skip_reason(*, name: str) -> str:
    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    return getattr(preflight, name)


def _governing_hold(*, scope: str, hold_key: str, candidate_key: str | None) -> Any:
    wait_module = importlib.import_module(f"{_PACKAGE}._acp_availability_wait")
    return wait_module.GoverningHold(
        observation_id=f"obs-{hold_key}",
        scope=scope,
        hold_key=hold_key,
        candidate_key=candidate_key,
        cause="quota",
        expires_at=_FAR_FUTURE,
    )


def _wait(*, governing_condition: str, holds: tuple[Any, ...] = (), **overrides: object) -> Any:
    """One `AvailabilityWait` value, which every consumer may legitimately build."""
    wait_module = importlib.import_module(f"{_PACKAGE}._acp_availability_wait")
    return wait_module.AvailabilityWait(
        node="implement",
        nodes=("implement",),
        governing_condition=governing_condition,
        reevaluate_at=_FAR_FUTURE,
        holds=holds,
        unobservable_observations=0,
        **overrides,  # pyright: ignore[reportArgumentType]
    )


def _parsed_valve(*, command: str, subcommand: str, module: str, adder: str) -> argparse.Namespace:
    """Parse one advertised command through the valve's OWN argument surface.

    The envelope's "executable as advertised" clause asks for the advertiser
    and the enforcer to be bound mechanically. A string assertion over the
    rendered command binds nothing: it would keep passing after the valve
    renamed a flag, which is exactly when the advertised remedy stops working.
    """
    valve = importlib.import_module(f"{_PACKAGE}.{module}")
    parser = argparse.ArgumentParser(prog=subcommand)
    getattr(valve, adder)(parser=parser)
    words = shlex.split(command)
    assert subcommand in words
    return parser.parse_args(words[words.index(subcommand) + 1 :])


def test_the_wait_row_names_the_governing_condition_and_the_reevaluation_instant(
    tmp_path: Path,
) -> None:
    """The two facts the clause requires of the wait item, on one high-urgency row."""
    assert _MODULE_PATH.is_file()
    repo = _exhausted_repo(tmp_path)

    attention = _availability_wait_items(
        project_root=repo, repo="repo", items=[_item(id_="bd-waiting")]
    )

    assert [item.id for item in attention] == ["hygiene:acp-availability-wait:bd-waiting"]
    row = attention[0]
    assert row.kind == "hygiene"
    assert row.urgency == "high"
    assert row.source_ref.work_item == "bd-waiting"
    assert "governing_condition=typed-availability-hold" in row.summary
    # The earliest governing expiry, which is the first moment the situation
    # could change at all -- never the later hold's, and never a clock reading.
    assert f"scheduled_reevaluation_at={_FAR_FUTURE}" in row.summary


def test_a_viable_chain_composes_no_wait_row(tmp_path: Path) -> None:
    """Nothing is waiting, so nothing is reported: the row clears with the hold."""
    assert _MODULE_PATH.is_file()
    repo = _exhausted_repo(tmp_path)
    (repo / _JOURNAL).write_text("", encoding="utf-8")

    assert _availability_wait_items(project_root=repo, repo="repo", items=[_item(id_="bd-x")]) == []


def test_only_ready_factory_safe_items_are_reported_as_waiting(tmp_path: Path) -> None:
    """A host-routed item and a non-ready item are not held by this wait."""
    assert _MODULE_PATH.is_file()
    repo = _exhausted_repo(tmp_path)

    attention = _availability_wait_items(
        project_root=repo,
        repo="repo",
        items=[
            _item(id_="bd-host", factory_safety="host-only"),
            _item(id_="bd-backlog", status="backlog"),
            _item(id_="bd-ready"),
        ],
    )

    assert [item.source_ref.work_item for item in attention] == ["bd-ready"]


def test_a_live_typed_hold_offers_the_exact_scope_and_key_clearance_valve(
    tmp_path: Path,
) -> None:
    """The valve names the record whose expiry the scheduled instant came from.

    The EARLIEST governing expiry is both the instant the row reports and the
    hold whose clearance would actually shorten the wait, so a valve naming the
    later record would advertise a clearance that changes nothing an operator
    can observe.
    """
    assert _MODULE_PATH.is_file()
    repo = _exhausted_repo(tmp_path)

    attention = _availability_wait_items(
        project_root=repo, repo="repo", items=[_item(id_="bd-waiting")]
    )

    parsed = _parsed_valve(
        command=attention[0].handoff.command,
        subcommand="clear-acp-availability-hold",
        module="_acp_hold_clear",
        adder="add_clear_acp_availability_hold_arguments",
    )
    assert attention[0].handoff.kind == "shell"
    assert (parsed.scope, parsed.hold_key, parsed.candidate_key) == (
        "availability-domain",
        "anthropic",
        None,
    )
    assert parsed.repo == str(repo)
    assert parsed.reason != ""


def test_a_candidate_scoped_hold_carries_its_candidate_key_into_the_valve(
    tmp_path: Path,
) -> None:
    """A candidate-scoped clearance that omitted its key is refused by the valve."""
    assert _MODULE_PATH.is_file()

    handoff = _availability_wait_handoff(
        project_root=tmp_path,
        wait=_wait(
            governing_condition=_skip_reason(name="TYPED_HOLD_SKIP"),
            holds=(_governing_hold(scope="candidate", hold_key="codex", candidate_key="gpt-5-5"),),
        ),
    )

    parsed = _parsed_valve(
        command=handoff.command,
        subcommand="clear-acp-availability-hold",
        module="_acp_hold_clear",
        adder="add_clear_acp_availability_hold_arguments",
    )
    assert (parsed.scope, parsed.hold_key, parsed.candidate_key) == (
        "candidate",
        "codex",
        "gpt-5-5",
    )


def test_a_legacy_provider_record_offers_the_legacy_provider_valve(tmp_path: Path) -> None:
    """The legacy blanket is retired by its own vendor-wide valve, not the typed one."""
    assert _MODULE_PATH.is_file()

    handoff = _availability_wait_handoff(
        project_root=tmp_path,
        wait=_wait(
            governing_condition=_skip_reason(name="LEGACY_HOLD_SKIP"),
            legacy_provider="anthropic",
        ),
    )

    parsed = _parsed_valve(
        command=handoff.command,
        subcommand="clear-provider-exhaustion",
        module="_dispatcher_provider_exhaustion_clear",
        adder="add_clear_provider_exhaustion_arguments",
    )
    assert parsed.provider == "anthropic"
    assert parsed.reason != ""


def test_the_pure_wait_names_the_legacy_provider_its_first_emptied_node_was_held_by(
    tmp_path: Path,
) -> None:
    """The provider the valve needs is read off the skip the filter recorded.

    Re-deriving it from the journal here would be a second reading of one
    evaluation, and the two could name different vendors for one refusal.
    """
    assert _MODULE_PATH.is_file()
    _ = tmp_path
    wait_module = importlib.import_module(f"{_PACKAGE}._acp_availability_wait")
    preflight = importlib.import_module(f"{_PACKAGE}._acp_candidate_preflight")
    verdict_module = importlib.import_module(f"{_PACKAGE}._acp_preflight_verdict")
    node = preflight.NodePreflight(
        node="implement",
        enabled=True,
        candidates=(),
        skipped=(
            preflight.SkippedCandidate(
                availability_key="anthropic",
                candidate_key="claude",
                reason=preflight.LEGACY_HOLD_SKIP,
                hold_key="anthropic",
            ),
        ),
    )

    wait = wait_module.availability_wait(
        verdict=verdict_module.AcpPreflightVerdict(
            fallback_enabled=True,
            success_critical=("implement",),
            exhausted=("implement",),
            nodes=(node,),
        ),
        holds=(),
        now_iso="2026-09-12T12:00:00Z",
        reprobe_interval_seconds=900,
    )

    assert wait is not None
    assert wait.governing_condition == preflight.LEGACY_HOLD_SKIP
    assert wait.legacy_provider == "anthropic"


@pytest.mark.parametrize(
    "condition",
    [
        "OUTSTANDING_CONFIRMATION_SKIP",
        "UNAVAILABLE_EVIDENCE_SKIP",
        "PROBE_SKIP",
        "HEADROOM_SKIP",
    ],
)
def test_a_wait_no_live_hold_governs_hands_off_an_inspection_instead(
    tmp_path: Path, condition: str
) -> None:
    """None of these four names a record an operator could retire."""
    assert _MODULE_PATH.is_file()

    handoff = _availability_wait_handoff(
        project_root=tmp_path, wait=_wait(governing_condition=_skip_reason(name=condition))
    )

    assert handoff.kind == "shell"
    assert "fabro-dispatch-journal.jsonl" in handoff.command
    assert "clear-" not in handoff.command
    assert "resolve-blocked" not in handoff.command


def test_another_nodes_live_hold_never_becomes_this_rows_advertised_clearance(
    tmp_path: Path,
) -> None:
    """`holds` spans every emptied node, so it cannot decide this row's target.

    A node emptied by an outstanding confirmation arrives beside a SIBLING
    node's typed hold. Clearing that hold releases a chain this row is not
    about, leaving the named node exactly as empty as before — which is the
    "clearance of a nonexistent live hold" the clause forbids advertising.
    """
    assert _MODULE_PATH.is_file()

    handoff = _availability_wait_handoff(
        project_root=tmp_path,
        wait=_wait(
            governing_condition=_skip_reason(name="OUTSTANDING_CONFIRMATION_SKIP"),
            holds=(
                _governing_hold(scope="availability-domain", hold_key="codex", candidate_key=None),
            ),
        ),
    )

    assert "clear-acp-availability-hold" not in handoff.command
    assert "fabro-dispatch-journal.jsonl" in handoff.command
