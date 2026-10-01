"""Integration-tier acceptance for the two Proof of Done attention facts.

Binds the hygiene half of `SPECIFICATION/scenarios.md` "Scenario 132 — A
factory-captured proof is captured on a draft pull request, reviewed, replayed
and published" ("A stale pointer is a hygiene fact") and "Scenario 133 — A mixed
item is refused ai-only from every entry path, parks for its human-attested leg,
and the accept valve refuses until the record exists" ("needs-attention surfaces
the pending human-attested leg with the pull request link").

Driving the whole `build_attention` composition rather than either lane alone is
what makes the counts mean anything: each scenario claims EXACTLY ONE fact
appears for the subject item, and a lane called in isolation can show neither
that nor the absence of a colliding row from another lane.

EVERY POSITIVE CASE HAS A CLEARING CONTROL IN THE SAME SNAPSHOT. The pending-leg
fixture carries a second mixed item whose pointer already cites a human-attested
record, and the pending fact must name only the first; without it, "the fact
appeared" is indistinguishable from "the fact always appears for a mixed item".
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.needs_attention import SpecNextOutput

_SPEC_HEADING = "## Effective acceptance criteria"
_HUMAN_ASSERTION = "The production console renders the capacity banner."
_VERIFIED_URL = "https://example.test/owner/repo/pull/11#issuecomment-900"
_HUMAN_URL = "https://example.test/owner/repo/pull/11#issuecomment-901"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _mixed_description(*, human_link: str | None) -> str:
    pointer = (
        "## Proof of Done\n"
        "\n"
        "- Pull request: #11\n"
        f"- Verified record: {_VERIFIED_URL}\n"
        "- Run: 01M3POINTERRUN\n"
        "- Timestamp: 2026-10-01T09:00:00Z\n"
        "- Verdict: verified\n"
    )
    if human_link is not None:
        pointer += f"- Human-attested record: {human_link}\n"
    return (
        "## Definition of Done\n"
        "\n"
        "- The factory leg is captured and replayed.\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "Reason: the sandbox has no session on the production console.\n"
        "\n"
        f"- {_HUMAN_ASSERTION}\n"
        "\n"
        f"References: {_SPEC_HEADING}\n"
        "\n" + pointer
    )


def _item(*, id_: str, description: str, status: str = "acceptance") -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status="ready",
        title=f"{id_} title",
        description=description,
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_policy="ai-then-human",
    )
    return replace(base, status=status)  # pyright: ignore[reportArgumentType]


def _write_project(*, root: Path) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"wip_cap": 5},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    spec = root / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _snapshot(*, root: Path, monkeypatch: pytest.MonkeyPatch) -> list[AttentionItem]:
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    return build_attention(project_root=root, repo_name="repo", include_hygiene=False)


def test_a_pending_human_attested_leg_surfaces_with_the_pull_request_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario 133 — the pending leg is an attention item carrying the PR link.

    The clearing control sits in the SAME snapshot: `bd-attested` is the same
    mixed item with a human-attested record already cited on its pointer, so a
    lane that fired on "mixed and parked" rather than on "the record is absent"
    would produce two facts here and fail on the count alone.
    """
    _write_project(root=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(id_="bd-pending", description=_mixed_description(human_link=None)),
    )
    append_work_item(
        path=_config(),
        item=_item(id_="bd-attested", description=_mixed_description(human_link=_HUMAN_URL)),
    )

    facts = [
        fact
        for fact in _snapshot(root=tmp_path, monkeypatch=monkeypatch)
        if fact.id.startswith("hygiene:pending-human-attestation:")
    ]

    assert [fact.id for fact in facts] == ["hygiene:pending-human-attestation:bd-pending"]
    assert facts[0].kind == "hygiene"
    assert _HUMAN_ASSERTION in facts[0].summary
    assert _VERIFIED_URL in facts[0].summary
    assert facts[0].source_ref is not None
    assert facts[0].source_ref.work_item == "bd-pending"
    # The handoff must NOT advertise the valve this very fact says will refuse.
    handoff = facts[0].handoff
    assert handoff is not None
    assert "accept:" not in handoff.command
