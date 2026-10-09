"""Tests for dispatcher Fabro failure-detail parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_failure import (
    FabroFailureDetail,
    fabro_failure_outcome_detail,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget


@dataclass(kw_only=True)
class _Runner:
    stdout: str

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
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def test_fabro_port_inspect_extracts_nested_failure_block(tmp_path: Path) -> None:
    detail = _inspect_failure(
        tmp_path=tmp_path,
        stdout=(
            '{"events": [{"payload": {"failure": {'
            '"causes": [7, "script failed with exit 2"], '
            '"category": "deterministic", '
            '"signature": "fix|deterministic|script failed"}}}]}'
        ),
    )

    assert detail == FabroFailureDetail(
        cause="script failed with exit 2",
        category="deterministic",
        signature="fix|deterministic|script failed",
    )


def test_fabro_port_inspect_returns_none_for_unusable_payloads(tmp_path: Path) -> None:
    assert _inspect_failure(tmp_path=tmp_path, stdout="not json") is None
    assert _inspect_failure(tmp_path=tmp_path, stdout="[]") is None
    assert _inspect_failure(tmp_path=tmp_path, stdout='{"failure": {"causes": [7, "  "]}}') is None
    assert _inspect_failure(tmp_path=tmp_path, stdout='{"failure": "not an object"}') is None


def test_fabro_port_inspect_accepts_category_without_causes(tmp_path: Path) -> None:
    detail = _inspect_failure(
        tmp_path=tmp_path, stdout='{"failure": {"causes": "not a list", "category": "infra"}}'
    )

    assert detail == FabroFailureDetail(cause=None, category="infra", signature=None)


def test_fabro_port_inspect_reclassifies_codex_remote_compaction_404(tmp_path: Path) -> None:
    cause = (
        'Internal error: {"data": {"message": "Error running remote compact task: '
        'unexpected status 404 Not Found: {\\"detail\\":\\"Not Found\\"}, '
        "url: https://chatgpt.com/backend-api/codex/responses/compact, "
        'cf-ray: a2e713303af7ed35-SJC, request id: deb42542"}}'
    )

    detail = _inspect_failure(
        tmp_path=tmp_path,
        stdout=json.dumps(
            {
                "failure": {
                    "message": "ACP turn failed",
                    "causes": ["ACP protocol error", cause],
                    "category": "transient_infra",
                    "signature": "implement|transient_infra|acp turn failed",
                }
            }
        ),
    )

    # The cause is the provider's own sentence, lifted out of the embedded
    # payload -- not the raw text, which leads with a `spawned_at` path.
    assert detail == FabroFailureDetail(
        cause=(
            "Error running remote compact task: unexpected status 404 Not Found: "
            '{"detail":"Not Found"}, '
            "url: https://chatgpt.com/backend-api/codex/responses/compact, "
            "cf-ray: a2e713303af7ed35-SJC, request id: deb42542"
        ),
        category="deterministic",
        signature="implement|deterministic|acp turn failed",
    )


def test_fabro_port_inspect_does_not_reclassify_unrelated_404(tmp_path: Path) -> None:
    cause = (
        "Internal error: model lookup failed: unexpected status 404 Not Found, "
        "url: https://chatgpt.com/backend-api/codex/responses/not-compact"
    )

    detail = _inspect_failure(
        tmp_path=tmp_path,
        stdout=json.dumps(
            {
                "failure": {
                    "causes": ["ACP protocol error", cause],
                    "category": "transient_infra",
                }
            }
        ),
    )

    # The CONTROL is `category`: an unrelated 404 must stay transient_infra.
    # `cause` is now the innermost element rather than the "ACP protocol error"
    # transport wrapper -- that wrapper is a fixed string in every measured
    # chain, so asserting it was asserting the defect.
    assert detail == FabroFailureDetail(
        cause=cause,
        category="transient_infra",
        signature=None,
    )


def test_fabro_failure_outcome_detail_formats_available_fields() -> None:
    assert (
        fabro_failure_outcome_detail(
            failure=FabroFailureDetail(
                cause=None,
                category="deterministic",
                signature="fix|deterministic|script failed",
            ),
            fallback="ACP turn failed",
        )
        == "category=deterministic; signature=fix|deterministic|script failed"
    )
    assert (
        fabro_failure_outcome_detail(failure=None, fallback="ACP turn failed") == "ACP turn failed"
    )
    assert (
        fabro_failure_outcome_detail(
            failure=FabroFailureDetail(cause=None, category=None, signature=None),
            fallback="ACP turn failed",
        )
        == "ACP turn failed"
    )


def _inspect_failure(*, tmp_path: Path, stdout: str) -> FabroFailureDetail | None:
    return (
        FabroPort(
            fabro_bin="fabro",
            target=FabroTarget(),
            runner=_Runner(stdout=stdout),
            cwd=tmp_path,
        )
        .inspect(run_id="01RUN", timeout_seconds=1)
        .failure
    )


def test_provider_message_extraction_falls_back_on_unparseable_braces(
    tmp_path: Path,
) -> None:
    """Braces that are not JSON leave the raw cause intact rather than blanking it."""
    cause = "Internal error: {not json at all}"
    detail = _inspect_failure(
        tmp_path=tmp_path,
        stdout=json.dumps({"failure": {"causes": ["ACP protocol error", cause]}}),
    )

    assert detail is not None
    assert detail.cause == cause


def test_provider_message_extraction_falls_back_when_data_is_not_an_object(
    tmp_path: Path,
) -> None:
    """A payload whose `data` is not an object keeps the raw cause."""
    cause = 'Internal error: {"data": "a string, not an object"}'
    detail = _inspect_failure(
        tmp_path=tmp_path,
        stdout=json.dumps({"failure": {"causes": ["ACP protocol error", cause]}}),
    )

    assert detail is not None
    assert detail.cause == cause


def test_provider_message_extraction_falls_back_when_the_message_is_not_text(
    tmp_path: Path,
) -> None:
    """A `data.message` that is not a string keeps the raw cause.

    The lift REFUSES a non-text message rather than coercing one: a number
    rendered through `str()` would read as the provider's own sentence while
    being an artefact of this parser. Asserted here beside its two sibling
    fallbacks because `fabro_provider_message` is now the only reader of that
    field — before the permanent-failure split it shared a text helper with the
    records module, whose other callers exercised this arm incidentally.
    """
    cause = 'Internal error: {"data": {"message": 7}}'
    detail = _inspect_failure(
        tmp_path=tmp_path,
        stdout=json.dumps({"failure": {"causes": ["ACP protocol error", cause]}}),
    )

    assert detail is not None
    assert detail.cause == cause
