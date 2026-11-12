"""The host-judgement spend journal records complete Claude responses."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _host_judge_spend_journal
from livespec_orchestrator_beads_fabro.commands._host_judge_spend_journal import (
    append_assistant_event,
    start_spend_journal,
)


def _records(*, path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_journal_declares_final_usage_and_keeps_an_unclosed_assistant_as_its_last_line(
    tmp_path: Path,
) -> None:
    journal = start_spend_journal(
        home=tmp_path,
        name="purpose:drift_run@repo",
        cwd=tmp_path / "repo",
        first_prompt="judge this",
    )

    append_assistant_event(
        journal=journal,
        line=(
            '{"type":"assistant","message":{"id":"msg_assistant",'
            '"model":"claude","usage":{"output_tokens":5}}}'
        ),
    )

    records = _records(path=journal.path)
    assert records[0]["final_usage_line"] is True
    assert records[-1]["type"] == "assistant"


def test_journal_ends_with_the_result_usage_and_its_assistant_message_ids(
    tmp_path: Path,
) -> None:
    journal = start_spend_journal(
        home=tmp_path,
        name="purpose:drift_run@repo",
        cwd=tmp_path / "repo",
        first_prompt="judge this",
    )
    for message_id in ("msg_first", "msg_last"):
        append_assistant_event(
            journal=journal,
            line=json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "id": message_id,
                        "model": "claude",
                        "usage": {"output_tokens": 5},
                    },
                }
            ),
        )
    final_usage = {"input_tokens": 31, "output_tokens": 1148, "cache": {"read": 7}}

    _host_judge_spend_journal.append_result_event(
        journal=journal,
        line=json.dumps({"type": "result", "usage": final_usage}),
    )

    result = _records(path=journal.path)[-1]
    assert result["type"] == "result"
    assert result["usage"] == final_usage
    assert result["message_ids"] == ["msg_first", "msg_last"]
    assert result["ts"].endswith("Z")
    assert "started_at" not in result
