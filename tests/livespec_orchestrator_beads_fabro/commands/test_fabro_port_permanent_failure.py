"""The permanent-failure classification is its own module, not the records module.

`_fabro_port_records.py` sat at 239 logical lines against the 250 hard ceiling,
and the Petri-era failure reader this plan needs (`bd-ib-227cbw`: a failure
block keyed `detail: {message, category}` with no `causes` and no `signature`)
does not fit beneath it. The seam cut here is a cohesion seam, not a line-count
cut: the module extracted answers "retrying cannot fix this, and THIS vendor
refused" — the provider usage-limit and remote-compaction classifiers plus the
provider's own sentence lifted out of an embedded payload — which is a
different question from "which run is this, what status does it carry, and what
is its failure block" that the records module keeps.

The measured chain below is the Codex form reproduced from run 01M0DN6CTWPF's
`fabro inspect --json` (the same fixture `test_fabro_provider_usage_limit.py`
carries), so the moved classifiers are exercised against real bytes rather than
an invented shape.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_fabro_port_permanent_failure.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._fabro_port_permanent_failure"
_RECORDS_NAME = "livespec_orchestrator_beads_fabro.commands._fabro_port_records"

_ACP_WRAPPER = "ACP protocol error"
_CODEX_USAGE_LIMIT = (
    'Internal error: {\n  "spawned_at": "/home/u/.cargo/registry/src/'
    'index.crates.io-1949cf8c/agent-client-protocol-0.11.1/src/session.rs:567:14",\n'
    '  "data": {\n    "message": "You\'ve hit your usage limit. Visit '
    "https://chatgpt.com/codex/settings/usage to purchase more credits or try again "
    'at Aug 20th, 2026 3:33 AM.",\n    "codex_error_info": "usage_limit_exceeded"\n'
    "  }\n}"
)


def _module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def test_permanent_failure_classification_lives_in_its_own_module() -> None:
    module = _module()
    records = importlib.import_module(_RECORDS_NAME)

    assert set(module.__all__) == {
        "fabro_permanent_cause",
        "fabro_provider_message",
        "fabro_usage_limit_provider",
    }
    # The moved privates are GONE from the records module rather than kept
    # beside a second copy: two classifiers over the same cause chain would
    # drift, and each would produce a well-formed answer while they did.
    assert not hasattr(records, "_permanent_cause")
    assert not hasattr(records, "_provider_usage_limit_provider")
    assert not hasattr(records, "_provider_message")
    assert not hasattr(records, "_usage_limit_provider")
    assert not hasattr(records, "_is_provider_usage_limit")
    assert not hasattr(records, "_is_remote_compaction_404")


def test_the_moved_classifiers_answer_for_a_measured_codex_usage_limit_chain() -> None:
    module = _module()
    causes = (_ACP_WRAPPER, _CODEX_USAGE_LIMIT)

    assert module.fabro_permanent_cause(causes=causes) == _CODEX_USAGE_LIMIT
    assert module.fabro_usage_limit_provider(causes=causes) == "codex"
    message = module.fabro_provider_message(text=_CODEX_USAGE_LIMIT)
    assert message is not None
    assert message.startswith("You've hit your usage limit.")
    assert "spawned_at" not in message


def test_a_chain_carrying_no_permanent_cause_reports_none_from_every_reader() -> None:
    module = _module()
    causes = (_ACP_WRAPPER, "connection reset by peer")

    assert module.fabro_permanent_cause(causes=causes) is None
    assert module.fabro_usage_limit_provider(causes=causes) is None
    assert module.fabro_provider_message(text="connection reset by peer") is None
