"""The incident-authority per-verb lifecycle handlers live in their own cohesive module."""

from __future__ import annotations

import importlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _incident_authority_lifecycle as lifecycle

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_VERBS = (
    "record-merge",
    "enter-repayment",
    "advance-repayment",
    "bind-repayment-acceptance",
    "reopen-regression",
    "record-deferred-finding",
    "record-revert-receipt",
    "record-rollback-conflict",
    "resolve-rollback-conflict",
    "correct-attempt",
    "correct-unmerged-attempt",
    "complete-incident",
    "drill-close",
)


def test_per_verb_handlers_are_owned_by_their_own_module_and_left_the_lifecycle_module() -> None:
    module_path = Path(lifecycle.__file__).with_name("_incident_authority_lifecycle_handlers.py")
    assert module_path.is_file()
    handlers = importlib.import_module(f"{_PACKAGE}._incident_authority_lifecycle_handlers")
    assert set(handlers.LIFECYCLE_HANDLERS) == set(_VERBS)
    assert set(handlers.LIFECYCLE_PAYLOADS) == set(_VERBS)
    assert lifecycle.LIFECYCLE_PAYLOADS is handlers.LIFECYCLE_PAYLOADS
    for name in (
        "_record_merge",
        "_enter",
        "_advance",
        "_bind",
        "_reopen",
        "_defer",
        "_revert",
        "_rollback_conflict",
        "_resolve_rollback_conflict",
        "_correct",
        "_HANDLERS",
        "_PR_NUMBER",
        "_Handler",
    ):
        assert not hasattr(lifecycle, name)
