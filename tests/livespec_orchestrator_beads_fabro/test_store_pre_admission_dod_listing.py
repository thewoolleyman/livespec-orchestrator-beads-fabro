"""Sparse raw metadata cannot invent a semantic admission hold."""

from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro import _store_pre_admission_dod as admission
from livespec_orchestrator_beads_fabro.types import StoreConfig


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"id": 42},
        {"id": "item"},
        {"id": "item", "metadata": []},
        {"id": "item", "metadata": {}},
        {"id": "item", "metadata": {"pre_admission_dod": "needs-human"}},
        {"id": "item", "metadata": {"pre_admission_dod": {"verdict": "passed"}}},
        {
            "id": "item",
            "metadata": {"pre_admission_dod": {"verdict": "needs-human"}},
        },
        *[
            {
                "id": "item",
                "metadata": {"pre_admission_dod": {"verdict": "needs-human", "remedies": remedies}},
            }
            for remedies in ["a remedy", [], [42], [""], ["  "]]
        ],
    ],
)
def test_sparse_or_malformed_metadata_does_not_report_a_hold(
    *, monkeypatch: pytest.MonkeyPatch, record: dict[str, object]
) -> None:
    # These malformed native records cannot be produced by the public fake
    # writer. Stub only the read boundary whose sparse tolerance is under test.
    client = Mock()
    client.list_issues.return_value = [record]
    monkeypatch.setattr(admission, "make_beads_client", Mock(return_value=client))
    config = StoreConfig(
        tenant="listing",
        prefix="listing",
        server_user="listing",
        database="listing",
        bd_path="bd",
        fake=True,
    )

    assert admission.read_pre_admission_holds(path=config) == {}

    client.list_issues.assert_called_once_with()
    client.update_issue.assert_not_called()
    client.add_comment.assert_not_called()
