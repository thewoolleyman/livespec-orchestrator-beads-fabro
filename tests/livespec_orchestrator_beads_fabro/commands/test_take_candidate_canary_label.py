"""Every canary the recipe files is marked, on the record, as a fixture dispatch.

Assertion under test: *each canary work-item the recipe files carries a canary
label that identifies it as a fixture dispatch*.

The label is what makes a canary legible to everything that reads the ledger
rather than the brief. A fixture dispatch is indistinguishable from real work by
its fields — it is a plain `task`, freeform, auto-admitted, factory-safe — so a
ledger survey, a stranded-claim sweep or a backlog census that does not know it
is instrumentation counts it as work somebody wanted. The label is the one place
that fact can be read without parsing the description.

Read through the client's RAW record rather than the materialized `WorkItem`,
because the bridge projects only the label prefixes it models onto fields and a
marker label has no field to land in: a projection-level assertion would be
blind to exactly the thing being asserted.

The label is spelled as a literal here and the module's published constant is
asserted EQUAL to it, rather than being read from the module and compared with
itself. The second form passes on any value the module happens to hold,
including one that says nothing about what the item is.
"""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import take_candidate_canary as canary
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.unsafe import unsafe_perform_io

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE_RELPATH = "orchestrator-image/candidate-canary-work-item-template.md"
_MARKER_RELPATH = "orchestrator-image/candidate-canary-log.md"
_TENANT = "livespec-canary-label"
_FACTORY = "hp"
_CANARY_LABEL = "canary:fixture"


def _config(*, repo_root: Path) -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_TENANT,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _governed_repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "governed"
    (repo / "orchestrator-image").mkdir(parents=True)
    (repo / "SPECIFICATION").mkdir()
    for relpath in (_TEMPLATE_RELPATH, _MARKER_RELPATH):
        (repo / relpath).write_text(
            (_REPO_ROOT / relpath).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (repo / "SPECIFICATION" / "constraints.md").write_text(
        "## Fabro runtime constraints\n\nThe engine is external.\n", encoding="utf-8"
    )
    (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": _TENANT,
                        "prefix": _TENANT,
                        "server_user": _TENANT,
                        "database": _TENANT,
                        "bd_path": "bd",
                        "fake": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _raw_labels(*, config: StoreConfig, item_id: str) -> list[str]:
    record = make_beads_client(config=config).show_issue(issue_id=item_id)
    labels = record["labels"]
    assert isinstance(labels, list)
    return [str(label) for label in labels]


def _file_one(*, config: StoreConfig, repo: Path, now_iso: str) -> str:
    filed = canary.file_candidate_canary(
        path=config, repo_root=repo, factory=_FACTORY, now_iso=now_iso
    )
    return unsafe_perform_io(filed.unwrap()).item_id


def test_a_filed_canary_carries_the_canary_label(tmp_path: Path) -> None:
    reset_fake_singleton()
    repo = _governed_repo(tmp_path=tmp_path)
    config = _config(repo_root=repo)

    item_id = _file_one(config=config, repo=repo, now_iso="2026-10-13T00:00:00Z")

    assert _CANARY_LABEL in _raw_labels(config=config, item_id=item_id)


def test_every_canary_carries_it_not_only_the_first(tmp_path: Path) -> None:
    reset_fake_singleton()
    repo = _governed_repo(tmp_path=tmp_path)
    config = _config(repo_root=repo)

    first = _file_one(config=config, repo=repo, now_iso="2026-10-13T00:00:00Z")
    second = _file_one(config=config, repo=repo, now_iso="2026-10-13T00:00:01Z")

    assert first != second
    for item_id in (first, second):
        assert _CANARY_LABEL in _raw_labels(config=config, item_id=item_id)


def test_the_published_label_constant_is_the_one_that_lands(tmp_path: Path) -> None:
    reset_fake_singleton()
    repo = _governed_repo(tmp_path=tmp_path)
    config = _config(repo_root=repo)

    item_id = _file_one(config=config, repo=repo, now_iso="2026-10-13T00:00:00Z")

    assert _CANARY_LABEL in _raw_labels(config=config, item_id=item_id)
    # Self-describing, per the repository rule that a marker value names what it
    # IS rather than carrying an opaque code — and published, so a ledger survey
    # can filter on it without re-spelling the string.
    assert canary.CANARY_FIXTURE_LABEL == _CANARY_LABEL
    assert "CANARY_FIXTURE_LABEL" in canary.__all__
