"""`FabroPort.events` carries the token evidence it parsed off the stream.

The reader itself is covered in `test_fabro_port_run_evidence`; this file
asserts the PORT exposes it, which is what makes the evidence reach a consumer
rather than sit in a function nobody calls. The token counts ride on
`FabroEventsResult` so the reflection and audit paths read ONE parse of the
stream — two consumers each re-parsing could disagree, and nothing in either
answer would say which had.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget


@dataclass(kw_only=True)
class _Runner:
    results: list[CommandResult]

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return self.results.pop(0)


def _port(*, stdout: str) -> FabroPort:
    return FabroPort(
        fabro_bin="/usr/local/bin/fabro",
        target=FabroTarget(server_url="https://example.invalid:32278"),
        runner=_Runner(results=[CommandResult(exit_code=0, stdout=stdout, stderr="")]),
        cwd=Path("/workspace"),
    )


def _token_envelope(*, seq: int, input_tokens: int, output_tokens: int) -> dict[str, object]:
    return {
        "run_id": "01M4DCQPCX6Z",
        "stream_seq": seq,
        "kind": "token.emitted",
        "id": f"e{seq}",
        "recorded_at": 1_760_000_000_000 + seq,
        "item": {
            "seq": seq,
            "recorded_at": 1_760_000_000_000 + seq,
            "record": {
                "kind": "token.emitted",
                "body": {
                    "event": "token.emitted",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            },
        },
    }


def test_events_result_carries_the_summed_token_usage() -> None:
    stdout = json.dumps(
        [
            _token_envelope(seq=1, input_tokens=900, output_tokens=120),
            _token_envelope(seq=2, input_tokens=100, output_tokens=80),
        ]
    )

    events = _port(stdout=stdout).events(run_id="01M4DCQPCX6Z", timeout_seconds=5.0)

    assert events.token_usage is not None
    assert events.token_usage.input_tokens == 1_000
    assert events.token_usage.output_tokens == 200
    assert events.token_usage.total_tokens == 1_200


def test_a_legacy_stream_leaves_the_token_usage_absent() -> None:
    """On 0.254 no token event exists, so the port reports no token evidence."""
    stdout = json.dumps([{"timestamp": "2026-08-20T03:21:37Z", "event": "run.completed"}])

    events = _port(stdout=stdout).events(run_id="01M0ABC", timeout_seconds=5.0)

    assert events.token_usage is None


def test_the_events_wrapper_form_is_read_as_well_as_a_bare_array() -> None:
    """`fabro events --json` has shipped both a bare array and an `events` wrapper."""
    stdout = json.dumps({"events": [_token_envelope(seq=1, input_tokens=5, output_tokens=7)]})

    events = _port(stdout=stdout).events(run_id="01M4DCQPCX6Z", timeout_seconds=5.0)

    assert events.token_usage is not None
    assert events.token_usage.total_tokens == 12


def test_a_malformed_envelope_contributes_nothing_rather_than_raising() -> None:
    """Every level of the envelope nest is optional, and a gap at any of them
    means the body was not reached — which is "no evidence read", not an error
    and not a zero. The stream is fabro's shape to change, so a reader that
    raised here would turn a payload revision into a dispatch failure.
    """
    malformed: list[object] = [
        "not-a-mapping",
        {"kind": "token.emitted"},
        {"kind": "token.emitted", "item": "not-a-mapping"},
        {"kind": "token.emitted", "item": {"record": "not-a-mapping"}},
        {"kind": "token.emitted", "item": {"record": {"body": "not-a-mapping"}}},
    ]

    events = _port(stdout=json.dumps(malformed)).events(run_id="01M4DCQPCX6Z", timeout_seconds=5.0)

    assert events.token_usage is None


def test_one_direction_alone_is_still_evidence() -> None:
    """A body naming only one direction counts; the other reads as zero.

    This is the one place a zero is legitimate: the body WAS parsed and that
    direction genuinely carried nothing, which is different from a body whose
    field names were unrecognizable.
    """
    stdout = json.dumps(
        [
            {
                "kind": "token.emitted",
                "item": {
                    "record": {
                        "kind": "token.emitted",
                        "body": {"event": "token.emitted", "prompt_tokens": 42},
                    }
                },
            }
        ]
    )

    events = _port(stdout=stdout).events(run_id="01M4DCQPCX6Z", timeout_seconds=5.0)

    assert events.token_usage is not None
    assert events.token_usage.input_tokens == 42
    assert events.token_usage.output_tokens == 0
