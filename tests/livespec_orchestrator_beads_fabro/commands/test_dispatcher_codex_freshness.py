"""Hermetic tests for the Codex credential freshness gate.

`assess_codex_credential_freshness` decodes the ChatGPT-subscription access
token's `exp` claim and refuses dispatch unless the credential outlives the
run budget plus a safety margin (scenarios.md Scenario 19).
"""

from __future__ import annotations

import base64
import json

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    CODEX_FRESHNESS_MARGIN_SECONDS,
    assess_codex_credential_freshness,
)

_NOW = 1_000_000
_BUDGET = 54_000


def _auth_json_with_exp(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    access_token = f"header.{payload}.sig"
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": access_token,
                "refresh_token": "x",
                "id_token": "y",
                "account_id": "z",
            },
        }
    )


def test_fresh_when_token_outlives_budget_plus_margin() -> None:
    exp = _NOW + _BUDGET + CODEX_FRESHNESS_MARGIN_SECONDS + 60
    verdict = assess_codex_credential_freshness(
        source_auth_json=_auth_json_with_exp(exp=exp), now_epoch=_NOW, run_budget_seconds=_BUDGET
    )
    assert verdict.fresh_enough is True
    assert verdict.renewal_message is None
    assert verdict.access_token_expires_at_epoch == exp


def test_not_fresh_when_token_expires_within_budget() -> None:
    exp = _NOW + _BUDGET
    verdict = assess_codex_credential_freshness(
        source_auth_json=_auth_json_with_exp(exp=exp), now_epoch=_NOW, run_budget_seconds=_BUDGET
    )
    assert verdict.fresh_enough is False
    assert verdict.renewal_message is not None
    assert "codex login" in verdict.renewal_message


def test_raises_when_access_token_missing() -> None:
    source = json.dumps({"auth_mode": "chatgpt", "tokens": {"refresh_token": "x"}})
    with pytest.raises(ValueError, match="access_token is missing"):
        assess_codex_credential_freshness(
            source_auth_json=source, now_epoch=_NOW, run_budget_seconds=_BUDGET
        )


def test_raises_when_access_token_is_not_a_jwt() -> None:
    source = json.dumps({"tokens": {"access_token": "not-a-jwt"}})
    with pytest.raises(ValueError, match="not a JWT"):
        assess_codex_credential_freshness(
            source_auth_json=source, now_epoch=_NOW, run_budget_seconds=_BUDGET
        )


def test_raises_when_exp_claim_is_not_an_integer() -> None:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": "soon"}).encode()).decode().rstrip("=")
    source = json.dumps({"tokens": {"access_token": f"header.{payload}.sig"}})
    with pytest.raises(ValueError, match="no integer exp claim"):
        assess_codex_credential_freshness(
            source_auth_json=source, now_epoch=_NOW, run_budget_seconds=_BUDGET
        )
