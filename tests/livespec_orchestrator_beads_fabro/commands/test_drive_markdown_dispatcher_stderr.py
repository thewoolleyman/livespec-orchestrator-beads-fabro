"""The flagless drive Markdown summary carries the Dispatcher's refusal reason.

A Dispatcher precondition refusal (exit 3) writes its reason to stderr only. The
detached launcher captures drive's Markdown summary, so a summary that omits the
Dispatcher's stderr leaves the refusal invisible unless `--json` was passed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import drive
from livespec_orchestrator_beads_fabro.commands.drive import CommandRun

_STALE_REASON = "ERROR: executing plugin build 31d5fb5d69a9 is stale; newer release ee124fa9dcfe"


class _Runner:
    def __init__(self, *, result: CommandRun) -> None:
        self.result = result

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        _ = argv, cwd
        return self.result


def _refusal(*, stderr: str) -> CommandRun:
    return CommandRun(argv=("cmd",), returncode=3, stdout="", stderr=stderr)


def _drive_markdown(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str], stderr: str, as_json: bool = False
) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    argv = ["--repo", str(repo), "--action", "impl:bd-ib-123"]
    if as_json:
        argv.append("--json")
    _ = drive.main(argv=argv, runner=_Runner(result=_refusal(stderr=stderr)))
    return capsys.readouterr().out


def test_markdown_summary_includes_dispatcher_refusal_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _drive_markdown(tmp_path=tmp_path, capsys=capsys, stderr=_STALE_REASON + "\n")

    assert "dispatcher exit code: 3" in out
    assert _STALE_REASON in out


def test_markdown_summary_carries_only_the_final_lines_of_long_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stderr = "".join(f"noise-{index:03d}\n" for index in range(1, 101))

    out = _drive_markdown(tmp_path=tmp_path, capsys=capsys, stderr=stderr)

    assert "noise-100" in out
    assert "noise-001" not in out


def test_markdown_summary_omits_stderr_block_when_stderr_is_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _drive_markdown(tmp_path=tmp_path, capsys=capsys, stderr="")

    assert out.splitlines() == [
        "# drive — impl:bd-ib-123",
        "",
        "- status: **failed**",
        "- dispatcher exit code: 3",
        "- Dispatcher did not report green for bd-ib-123.",
    ]


def test_json_payload_still_carries_full_dispatcher_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stderr = "".join(f"noise-{index:03d}\n" for index in range(1, 101))

    out = _drive_markdown(tmp_path=tmp_path, capsys=capsys, stderr=stderr, as_json=True)

    assert json.loads(out)["dispatcher"]["stderr"] == stderr
