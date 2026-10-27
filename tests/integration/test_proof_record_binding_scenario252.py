"""Scenario 252 — A record binding, not merging-run inference, selects proof.

The acceptance pass sees every Proof of Done comment on the merged pull
request.  A verified record can have been produced by an earlier dispatch, so
the current merge's resolved Fabro identifiers are deliberately absent from
this fixture: the record's own binding is the authority that lets it count.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
    EffectiveCriteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import proof_leg
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import proof_records

_ASSERTION = "The acceptance pass selects a record from its binding."
_ITEM_ID = "bd-ib-poh6jg"
_PR_NUMBER = 3164
_MERGED_HEAD = "a" * 40
_BINDING_MODULE = (
    Path(__file__).parents[2]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_proof_binding.py"
)


def test_scenario252_selects_a_verified_record_by_its_own_binding() -> None:
    """The binding outlives a merging-run resolver that omitted its producer."""
    assert "work_item_id" in inspect.signature(proof_leg).parameters

    records = proof_records(
        comments=[
            {
                "url": "https://example.test/comments/verified",
                "body": (
                    "Proof of Done — verified — run earlier-dispatch — t\n"
                    f"Binds: {_ITEM_ID} — pull request #{_PR_NUMBER} — head {_MERGED_HEAD}\n\n"
                    f"## Assertion 1 — {_ASSERTION}\n\nReproduced: yes.\n"
                ),
            }
        ]
    )
    criteria = EffectiveCriteria(
        text=_ASSERTION,
        source=DESCRIPTION_DEFINITION_OF_DONE_SOURCE,
        assertions=(_ASSERTION,),
        proof_modes=(PROOF_MODE_FACTORY_CAPTURED,),
    )

    leg = proof_leg(
        criteria=criteria,
        records=records,
        run_ids=("merging-run-only",),
        reason="fixture",
        work_item_id=_ITEM_ID,
        pr_number=_PR_NUMBER,
        merged_head=_MERGED_HEAD,
    )

    assert leg.record is records[0]
    assert [check.passed for check in leg.checks] == [True]


def test_scenario252_inventories_each_record_with_one_binding_verdict() -> None:
    """Malformed, legacy, stale and superseded records cannot silently count."""
    assert _BINDING_MODULE.is_file()
    binding = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_proof_binding"
    )
    records = proof_records(
        comments=[
            _comment(url="human", verdict="human_attested", run_id="chad"),
            _comment(url="bound", verdict="verified", binding=_binding()),
            _comment(
                url="elsewhere",
                verdict="verified",
                binding=_binding(item="bd-ib-other"),
            ),
            _comment(url="legacy", verdict="captured", run_id="earlier-dispatch"),
            _comment(url="legacy-host", verdict="host_verified", run_id="session-1"),
            _comment(url="unknown", verdict="verified", run_id="unknown-dispatch"),
            _comment(url="malformed", verdict="verified", binding="Binds: incomplete"),
            _comment(
                url="stale",
                verdict="verified",
                binding=_binding(head="b" * 40),
            ),
            _comment(
                url="superseded",
                verdict="verified",
                binding=_binding(),
            ),
            _comment(
                url="correction",
                verdict="verified",
                binding=_binding(),
                supersedes="https://example.test/comments/superseded",
            ),
        ]
    )

    inventory = binding.proof_record_inventory(
        records=records,
        work_item_id=_ITEM_ID,
        pull_request=_PR_NUMBER,
        merged_head=_MERGED_HEAD,
        dispatch_ids=("earlier-dispatch",),
    )

    assert [entry.verdict for entry in inventory.entries] == [
        "human-attested",
        "bound",
        "bound-elsewhere",
        "legacy-matched",
        "legacy-host",
        "unbindable",
        "unbindable",
        "bound",
        "superseded",
        "bound",
    ]
    assert [entry.record.url for entry in inventory.unbindable] == [
        "unknown",
        "malformed",
    ]
    assert [entry.record.url for entry in inventory.factory_records] == ["bound", "correction"]
    assert [entry.record.url for entry in inventory.host_records] == ["legacy-host"]
    assert inventory.entries[7].stale_head is True


def _binding(*, item: str = _ITEM_ID, head: str = _MERGED_HEAD) -> str:
    return f"Binds: {item} — pull request #{_PR_NUMBER} — head {head}"


def _comment(
    *,
    url: str,
    verdict: str,
    run_id: str = "earlier-dispatch",
    binding: str | None = None,
    supersedes: str | None = None,
) -> dict[str, str]:
    lines = [f"Proof of Done — {verdict} — run {run_id} — t"]
    if binding is not None:
        lines.append(binding)
    if supersedes is not None:
        lines.append(f"Supersedes: {supersedes}")
    return {"url": url, "body": "\n".join(lines)}
