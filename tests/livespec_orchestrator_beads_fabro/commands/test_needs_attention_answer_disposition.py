"""The effective answer disposition each attention item carries in `--json`.

v104 ratified `needs-attention --json` carrying every attention item's effective
answer disposition — who may answer a work-item resting at `blocked` /
`blocked_reason: needs-human` — and said that until a first-class field ratifies
in the `livespec-runtime`-owned attention envelope, it MAY ride the existing
per-item `summary` string. So these cases assert against the COMPOSED envelope
rather than the in-memory lane: an enrichment that does not survive composition
into the bytes a console reads is worth nothing.

Two properties beyond the plain presence of the disposition are load-bearing.

The per-item label must beat the global, and it must beat it ASYMMETRICALLY —
the ledger case below runs `answer:human` against a `consensus` global, which is
the only configuration in which honoring the label and ignoring it give
different answers.

And the row must not ADVERTISE an answer press. The ratified
advertiser-and-enforcer binding forbids the `resolve-blocked` lane from offering
an answer handoff the effective disposition would refuse, and the way this lane
satisfies it is by offering none: the handoff stays the plain
`resolve-blocked:<work-item-id>:ready` action. The final case pins that, so a
later enrichment cannot quietly turn the report into an offer.

The module under test is reached through `importlib` rather than a top-level
import because the Red half of this file's own ritual must fail on an assertion,
not on a missing module.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention, render_json
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = (
    _REPO_ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_needs_attention_answer_disposition.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_answer_disposition"

_PARKED = "bd-parked"
_HUMAN_SENTENCE = "Effective answer disposition human"
_CONSENSUS_SENTENCE = "Effective answer disposition consensus"


def _module() -> Any:
    # The genuine Red assertion: the module does not exist yet, and an import
    # placed at file scope would fail at COLLECTION instead, which proves only
    # unimportability rather than unimplemented behavior.
    assert _MODULE_PATH.is_file()
    return import_module(_MODULE_NAME)


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _write_config(*, project_root: Path, answer_disposition: str | None) -> None:
    dispatcher = {} if answer_disposition is None else {"answer_disposition": answer_disposition}
    _ = (project_root / ".livespec.jsonc").write_text(
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
                    "dispatcher": dispatcher,
                }
            }
        ),
        encoding="utf-8",
    )


def _seed_parked(*, answer_label: str | None = None) -> None:
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=_PARKED,
            type="task",
            status="blocked",
            title=f"{_PARKED} title",
            description="d",
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
            blocked_reason="needs-human",
        ),
    )
    if answer_label is not None:
        make_beads_client(config=_config()).update_issue(
            issue_id=_PARKED, add_labels=[answer_label]
        )


def _no_spec_next(*, project_root: Path) -> None:
    """Keep composition hermetic — `spec_next` would reach a live CORE checkout."""
    _ = project_root


def _parked_entry(*, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The composed envelope's one `resolve-blocked` row, as JSON."""
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    attention = build_attention(project_root=project_root, repo_name="repo", include_hygiene=False)
    payload = json.loads(render_json(attention=attention))
    rows = [
        entry for entry in payload["attention"] if entry["id"] == f"valve:resolve-blocked:{_PARKED}"
    ]
    assert len(rows) == 1
    return rows[0]


def test_the_json_row_carries_the_global_default_when_no_label_overrides_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unconfigured repository parks its items under the safe default, `human`."""
    _ = _module()
    _write_config(project_root=tmp_path, answer_disposition=None)
    _seed_parked()

    entry = _parked_entry(project_root=tmp_path, monkeypatch=monkeypatch)

    assert _HUMAN_SENTENCE in entry["summary"]
    assert _CONSENSUS_SENTENCE not in entry["summary"]


def test_the_json_row_carries_a_configured_consensus_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reported disposition tracks the repository's committed setting."""
    _ = _module()
    _write_config(project_root=tmp_path, answer_disposition="consensus")
    _seed_parked()

    entry = _parked_entry(project_root=tmp_path, monkeypatch=monkeypatch)

    assert _CONSENSUS_SENTENCE in entry["summary"]


def test_a_ledger_answer_label_lowers_the_reported_disposition_below_the_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the tenant: the label the store carries beats the global.

    Run against a `consensus` global, so reading `human` is possible only if the
    label was actually read off the record and honored.
    """
    _ = _module()
    _write_config(project_root=tmp_path, answer_disposition="consensus")
    _seed_parked(answer_label="answer:human")

    entry = _parked_entry(project_root=tmp_path, monkeypatch=monkeypatch)

    assert _HUMAN_SENTENCE in entry["summary"]


def test_the_row_reports_the_disposition_without_advertising_an_answer_press(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The handoff stays the plain resolve-blocked action the lane always offered."""
    _ = _module()
    _write_config(project_root=tmp_path, answer_disposition=None)
    _seed_parked()

    entry = _parked_entry(project_root=tmp_path, monkeypatch=monkeypatch)

    assert entry["handoff"]["action_id"] == f"resolve-blocked:{_PARKED}:ready"
    assert "--answer" not in entry["summary"]


def test_an_unreadable_config_costs_the_read_and_reports_the_safe_default(
    tmp_path: Path,
) -> None:
    """Fail-soft, and soft in the restrictive direction rather than the permissive one."""
    module = _module()
    unreadable = tmp_path / "unreadable"
    unreadable.mkdir()
    _ = (unreadable / ".livespec.jsonc").write_text("{ not json", encoding="utf-8")

    summary = module.answer_disposition_summary(
        project_root=unreadable,
        item=_parked_item(),
        raw_labels=(),
        default_summary="Resolve human-needed block",
    )

    assert summary.startswith("Resolve human-needed block ")
    assert _HUMAN_SENTENCE in summary


def _parked_item() -> WorkItem:
    return WorkItem(
        id=_PARKED,
        type="task",
        status="blocked",
        title=f"{_PARKED} title",
        description="d",
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
        blocked_reason="needs-human",
    )
