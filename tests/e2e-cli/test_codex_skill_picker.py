"""Live Codex TUI `/skills` picker acceptance for the orchestrator plugin."""

from __future__ import annotations

import fcntl
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import tempfile
import termios
import time
import tty
from collections.abc import Callable
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVESPEC_CODEX_SKILL_PICKER") != "1",
    reason="live Codex TUI picker acceptance runs only via just check-codex-skill-picker",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSI_RE = re.compile(r"(?:\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[78])")
_PICKER_QUERY = "orchestrate"
_EXPECTED_SKILL = "orchestrate"
_EXPECTED_PLUGIN = "livespec-orchestrator-beads-fabro"
_FOREGROUND_QUERY = "\x1b]10;?\x1b\\"
_BACKGROUND_QUERY = "\x1b]11;?\x1b\\"
_FOREGROUND_RESPONSE = "\x1b]10;rgb:ffff/ffff/ffff\x1b\\"
_BACKGROUND_RESPONSE = "\x1b]11;rgb:0000/0000/0000\x1b\\"
_TERMINAL_RESPONSES = _FOREGROUND_RESPONSE + _BACKGROUND_RESPONSE
_CODEX_STARTUP_TIMEOUT_SECONDS = 120
_CODEX_PROMPT_MARKER = chr(0x203A)
_GIT_HOOK_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)
_HOST_CODEX_HOME = Path.home() / ".codex"
_CODEX_TEST_CONFIG = f"""
model = "gpt-5.5"

[tui.model_availability_nux]
"gpt-5.5" = 4

[notice.model_migrations]
"gpt-5.4" = "gpt-5.5"

[projects."{_REPO_ROOT}"]
trust_level = "trusted"

[plugins."livespec@livespec"]
enabled = true

[plugins."livespec@livespec-driver-codex"]
enabled = true

[plugins."livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"]
enabled = true

[marketplaces.livespec]
source_type = "git"
source = "https://github.com/thewoolleyman/livespec.git"

[marketplaces.livespec-driver-codex]
source_type = "git"
source = "https://github.com/thewoolleyman/livespec-driver-codex.git"

[marketplaces.livespec-orchestrator-beads-fabro]
source_type = "git"
source = "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"
"""


def _plain(*, text: str) -> str:
    return _ANSI_RE.sub("", text).replace("\r", "\n")


def _squashed(*, text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _has_main_prompt(*, plain: str) -> bool:
    squashed = _squashed(text=plain)
    return (
        ("model:gpt-5.5" in squashed and "/modeltochange" in squashed)
        or (
            f"{_CODEX_PROMPT_MARKER}explainthiscodebase" in squashed
            and "gpt-5.5default" in squashed
        )
        or "tip:" in squashed
    )


def _has_trust_prompt(*, plain: str) -> bool:
    return "doyoutrust" in _squashed(text=plain)


def _prepare_pty(*, master_fd: int, slave_fd: int) -> None:
    tty.setraw(slave_fd)
    winsize = struct.pack("HHHH", 40, 120, 0, 0)
    termios.tcflush(slave_fd, termios.TCIOFLUSH)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)


def _read_until(
    *,
    fd: int,
    seen: str,
    predicate: Callable[[str], bool],
    timeout_seconds: float,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    current = seen
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        readable, _, _ = select.select([fd], [], [], min(0.25, remaining))
        if not readable:
            continue
        try:
            chunk = os.read(fd, 8192).decode("utf-8", errors="replace")
        except OSError as exc:
            tail = _plain(text=current)[-3000:]
            raise AssertionError(f"Codex TUI exited while waiting. Last output:\n{tail}") from exc
        current += chunk
        if _FOREGROUND_QUERY in chunk:
            _send(fd=fd, text=_FOREGROUND_RESPONSE)
        if _BACKGROUND_QUERY in chunk:
            _send(fd=fd, text=_BACKGROUND_RESPONSE)
        if predicate(_plain(text=current)):
            return current
    tail = _plain(text=current)[-3000:]
    raise AssertionError(f"Timed out waiting for Codex picker state. Last output:\n{tail}")


def _read_until_quiet(*, fd: int, seen: str, quiet_seconds: float, timeout_seconds: float) -> str:
    deadline = time.monotonic() + timeout_seconds
    quiet_deadline = time.monotonic() + quiet_seconds
    current = seen
    while time.monotonic() < deadline:
        remaining = max(0.05, min(deadline, quiet_deadline) - time.monotonic())
        readable, _, _ = select.select([fd], [], [], min(0.25, remaining))
        if not readable:
            if time.monotonic() >= quiet_deadline:
                return current
            continue
        try:
            chunk = os.read(fd, 8192).decode("utf-8", errors="replace")
        except OSError as exc:
            tail = _plain(text=current)[-3000:]
            raise AssertionError(f"Codex TUI exited while waiting. Last output:\n{tail}") from exc
        current += chunk
        if _FOREGROUND_QUERY in chunk:
            _send(fd=fd, text=_FOREGROUND_RESPONSE)
        if _BACKGROUND_QUERY in chunk:
            _send(fd=fd, text=_BACKGROUND_RESPONSE)
        quiet_deadline = time.monotonic() + quiet_seconds
    tail = _plain(text=current)[-3000:]
    raise AssertionError(f"Timed out waiting for Codex TUI to settle. Last output:\n{tail}")


def _send(*, fd: int, text: str) -> None:
    os.write(fd, text.encode("utf-8"))


def _prepare_codex_home(*, codex_home: Path) -> None:
    (codex_home / "config.toml").write_text(_CODEX_TEST_CONFIG, encoding="utf-8")
    os.symlink(_HOST_CODEX_HOME / "plugins", codex_home / "plugins")
    for filename in ("auth.json", ".credentials.json", "installation_id"):
        source = _HOST_CODEX_HOME / filename
        if source.exists():
            os.symlink(source, codex_home / filename)


def _await_codex_prompt(*, fd: int, transcript: str) -> str:
    current = _read_until(
        fd=fd,
        seen=transcript,
        predicate=lambda plain: _has_main_prompt(plain=plain) or _has_trust_prompt(plain=plain),
        timeout_seconds=_CODEX_STARTUP_TIMEOUT_SECONDS,
    )
    if not _has_trust_prompt(plain=_plain(text=current)):
        return _read_until_quiet(
            fd=fd,
            seen=current,
            quiet_seconds=6.0,
            timeout_seconds=_CODEX_STARTUP_TIMEOUT_SECONDS,
        )
    _send(fd=fd, text="\r")
    current = _read_until(
        fd=fd,
        seen=current,
        predicate=lambda plain: _has_main_prompt(plain=plain),
        timeout_seconds=_CODEX_STARTUP_TIMEOUT_SECONDS,
    )
    return _read_until_quiet(
        fd=fd,
        seen=current,
        quiet_seconds=6.0,
        timeout_seconds=_CODEX_STARTUP_TIMEOUT_SECONDS,
    )


def _open_skills_menu(*, fd: int, transcript: str) -> str:
    attempts = 3
    last_error: AssertionError | None = None
    current = transcript
    for attempt_index in range(attempts):
        if attempt_index > 0:
            _send(fd=fd, text="\x1b\x15")
            time.sleep(1)
        _send(fd=fd, text="\x15/skills\r")
        try:
            return _read_until(
                fd=fd,
                seen=current,
                predicate=lambda plain: "listskills" in _squashed(text=plain)
                and "enable/disableskills" in _squashed(text=plain),
                timeout_seconds=40,
            )
        except AssertionError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _stop_codex(*, proc: subprocess.Popen[bytes], fd: int) -> None:
    if proc.poll() is None:
        try:
            _send(fd=fd, text="\x03")
            _send(fd=fd, text="/quit\r")
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    os.close(fd)


def _exercise_skills_picker(*, master_fd: int) -> str:
    _send(fd=master_fd, text=_TERMINAL_RESPONSES)
    transcript = _await_codex_prompt(fd=master_fd, transcript="")
    transcript = _open_skills_menu(fd=master_fd, transcript=transcript)
    _send(fd=master_fd, text="\r")
    transcript = _read_until(
        fd=master_fd,
        seen=transcript,
        predicate=lambda plain: "Skills" in plain or "Search" in plain,
        timeout_seconds=15,
    )
    _send(fd=master_fd, text=_PICKER_QUERY)
    return _read_until(
        fd=master_fd,
        seen=transcript,
        predicate=lambda plain: all(
            expected in plain for expected in (_EXPECTED_SKILL, _EXPECTED_PLUGIN, "Skill")
        ),
        timeout_seconds=15,
    )


def test_skills_picker_finds_orchestrate_by_short_name() -> None:
    codex = shutil.which("codex")
    if codex is None:
        pytest.fail("codex CLI is required for the live /skills picker acceptance")

    master_fd, slave_fd = pty.openpty()
    _prepare_pty(master_fd=master_fd, slave_fd=slave_fd)
    env = os.environ.copy()
    env["TERM"] = env.get("TERM", "xterm-256color")
    env["COLUMNS"] = "120"
    env["LINES"] = "40"
    env["NO_COLOR"] = "1"
    for name in _GIT_HOOK_ENV_VARS:
        env.pop(name, None)
    with tempfile.TemporaryDirectory(
        prefix="livespec-codex-home-", dir=_HOST_CODEX_HOME / "tmp"
    ) as codex_home_raw:
        codex_home = Path(codex_home_raw)
        _prepare_codex_home(codex_home=codex_home)
        env["CODEX_HOME"] = str(codex_home)
        proc = subprocess.Popen(
            [codex, "--no-alt-screen", "--dangerously-bypass-hook-trust", "-C", str(_REPO_ROOT)],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            close_fds=True,
        )
        os.close(slave_fd)
        try:
            transcript = _exercise_skills_picker(master_fd=master_fd)
        finally:
            _stop_codex(proc=proc, fd=master_fd)

    plain = _plain(text=transcript)
    assert _EXPECTED_SKILL in plain
    assert _EXPECTED_PLUGIN in plain
    assert "Skill" in plain
