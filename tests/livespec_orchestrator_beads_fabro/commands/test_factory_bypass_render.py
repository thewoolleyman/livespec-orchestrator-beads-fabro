"""The audit renders incident exceptions, declared exceptions and unverifiable items apart."""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths import (
    ProductPathPolicy,
)
from livespec_orchestrator_beads_fabro.commands._factory_bypass_render import (
    render_json,
    render_report,
)
from livespec_orchestrator_beads_fabro.commands.factory_bypass_audit import (
    AuditPolicy,
    AuditReport,
    BypassFinding,
    RecordedException,
)

_PRODUCT = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/foo.py"
_POLICY = AuditPolicy(
    factory_app_login="app/thewoolleyman-factory-bot",
    allow_authors=frozenset(),
    allow_labels=frozenset(),
    product_paths=ProductPathPolicy(prefixes=(".claude-plugin/scripts/",), origin="declared"),
)


def _report() -> AuditReport:
    return AuditReport(
        scanned=4,
        findings=(
            BypassFinding(
                number=81, title="marker", author_login="thewoolleyman", product_paths=(_PRODUCT,)
            ),
        ),
        exceptions=(
            RecordedException(
                number=73,
                title="repair",
                author_login="thewoolleyman",
                kind="incident-receipt",
                item_id="incident-1",
                repayment_outstanding=True,
            ),
            RecordedException(
                number=74,
                title="revert",
                author_login="thewoolleyman",
                kind="incident-receipt",
                item_id="incident-2",
                repayment_outstanding=False,
            ),
            RecordedException(number=75, title="declared", author_login="thewoolleyman"),
        ),
        incident_refusals=(
            "incident item incident-3 could not be verified against its retained authority "
            "chain: incident-authority-missing (incident-3)",
        ),
    )


def test_the_report_states_each_exception_kind_and_what_it_still_owes() -> None:
    text = render_report(report=_report(), policy=_POLICY)
    assert "Recorded 3 factory exception(s):" in text
    assert (
        "- PR #73 by @thewoolleyman — repair (incident incident-1, deferred verification, "
        "normal repayment outstanding)"
    ) in text
    assert (
        "- PR #74 by @thewoolleyman — revert (incident incident-2, deferred verification, " in text
    )
    assert "normal repayment recorded as repaid)" in text
    assert "- PR #75 by @thewoolleyman — declared (Factory-Override trailer, unverified)" in text


def test_the_report_keeps_an_unverifiable_incident_beside_its_still_flagged_carriers() -> None:
    text = render_report(report=_report(), policy=_POLICY)
    assert "Flagged 1 product-code PR(s)" in text
    assert "1 incident item(s) could not be verified:" in text
    assert "- incident item incident-3 could not be verified" in text
    assert "an unreadable receipt excepts nothing" in text


def test_the_json_carries_kind_item_repayment_and_refusals() -> None:
    payload = json.loads(render_json(report=_report(), policy=_POLICY))
    assert payload["exception_count"] == 3
    assert [recorded["kind"] for recorded in payload["exceptions"]] == [
        "incident-receipt",
        "incident-receipt",
        "factory-override",
    ]
    assert payload["exceptions"][0]["item_id"] == "incident-1"
    assert payload["exceptions"][0]["repayment_outstanding"] is True
    assert payload["exceptions"][1]["repayment_outstanding"] is False
    assert payload["exceptions"][2] == {
        "author": "thewoolleyman",
        "item_id": "",
        "kind": "factory-override",
        "number": 75,
        "repayment_outstanding": False,
        "title": "declared",
    }
    assert payload["incident_refusals"] == list(_report().incident_refusals)


def test_a_clean_report_renders_neither_block() -> None:
    report = AuditReport(scanned=1, findings=(), exceptions=())
    text = render_report(report=report, policy=_POLICY)
    assert "No factory bypasses found." in text
    assert "exception(s)" not in text
    assert "could not be verified" not in text
    assert json.loads(render_json(report=report, policy=_POLICY))["incident_refusals"] == []
