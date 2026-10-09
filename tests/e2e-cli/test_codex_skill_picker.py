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
from dataclasses import dataclass
from pathlib import Path

import pyte
import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COLUMNS = 240
_FRAME_END = b"\x1b[?2026l"
_PICKER_QUERY = "drive"
_NO_MATCH_SUFFIX = "zzzz4gkfaanomatch"
_EXPECTED_SKILL = "drive"
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
model = "gpt-5.6-sol"

[tui.model_availability_nux]
"gpt-5.6-sol" = 4

[notice.model_migrations]
"gpt-5.5" = "gpt-5.6-sol"

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


@dataclass(kw_only=True)
class _Terminal:
    fd: int
    screen: pyte.Screen
    stream: pyte.ByteStream
    pending: bytes = b""

    def text(self) -> str:
        return "\n".join(line.rstrip() for line in self.screen.display)


def _squashed(*, text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _has_main_prompt(*, plain: str) -> bool:
    return (
        re.search(rf"^\s*{_CODEX_PROMPT_MARKER} .+", plain, re.MULTILINE) is not None
        and "GPT-" in plain
        and "Tip:" in plain
    )


def _has_trust_prompt(*, plain: str) -> bool:
    return "doyoutrust" in _squashed(text=plain)


def _prepare_pty(*, master_fd: int, slave_fd: int) -> None:
    tty.setraw(slave_fd)
    winsize = struct.pack("HHHH", 40, _COLUMNS, 0, 0)
    termios.tcflush(slave_fd, termios.TCIOFLUSH)
    fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)


def _read_until(
    *, terminal: _Terminal, predicate: Callable[[str], bool], timeout_seconds: float
) -> str:
    """Judge a new complete screen, never concatenated terminal history.

    Codex writes cursor-addressed deltas inside synchronized-output frames.
    Stripping ANSI loses unchanged cells and retains erased text. ByteStream
    handles split UTF-8/escape sequences; pending retains partial frames across
    actions. A previously matching screen cannot pass without new output.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        readable, _, _ = select.select([terminal.fd], [], [], min(0.25, remaining))
        if not readable:
            continue
        try:
            chunk = os.read(terminal.fd, 8192)
        except OSError as exc:
            raise AssertionError(f"Codex TUI exited while waiting:\n{terminal.text()}") from exc
        if not chunk:
            raise AssertionError(f"Codex TUI closed while waiting:\n{terminal.text()}")
        terminal.pending += chunk
        for query, response in (
            (_FOREGROUND_QUERY, _FOREGROUND_RESPONSE),
            (_BACKGROUND_QUERY, _BACKGROUND_RESPONSE),
        ):
            if query.encode() in terminal.pending:
                _send(fd=terminal.fd, text=response)
                terminal.pending = terminal.pending.replace(query.encode(), b"")
        if _FRAME_END not in terminal.pending:
            continue
        frame, _, terminal.pending = terminal.pending.rpartition(_FRAME_END)
        terminal.stream.feed(frame + _FRAME_END)
        current = terminal.text()
        if predicate(current):
            return current
    raise AssertionError(f"Timed out waiting for Codex picker state:\n{terminal.text()}")


def _send(*, fd: int, text: str) -> None:
    os.write(fd, text.encode("utf-8"))


def _prepare_codex_home(*, codex_home: Path) -> None:
    (codex_home / "config.toml").write_text(_CODEX_TEST_CONFIG, encoding="utf-8")
    os.symlink(_HOST_CODEX_HOME / "plugins", codex_home / "plugins")
    for filename in ("auth.json", ".credentials.json", "installation_id"):
        source = _HOST_CODEX_HOME / filename
        if source.exists():
            os.symlink(source, codex_home / filename)


def _await_codex_prompt(*, terminal: _Terminal) -> None:
    current = _read_until(
        terminal=terminal,
        predicate=lambda plain: _has_main_prompt(plain=plain) or _has_trust_prompt(plain=plain),
        timeout_seconds=_CODEX_STARTUP_TIMEOUT_SECONDS,
    )
    if _has_trust_prompt(plain=current):
        _send(fd=terminal.fd, text="\r")
        _read_until(
            terminal=terminal,
            predicate=lambda plain: _has_main_prompt(plain=plain),
            timeout_seconds=_CODEX_STARTUP_TIMEOUT_SECONDS,
        )


def _paste(*, fd: int, text: str) -> None:
    # A single paste event, not a burst of printable keys plus Enter. The old
    # burst left a multiline composer, and retries appended /skillss. Submit
    # separately, only after the actual command suggestion has been rendered.
    _send(fd=fd, text=f"\x1b[200~{text}\x1b[201~")


def _open_skills_menu(*, terminal: _Terminal) -> None:
    _paste(fd=terminal.fd, text="/skills")
    _read_until(
        terminal=terminal,
        predicate=lambda plain: "/skills" in plain and "use skills to improve" in plain,
        timeout_seconds=15,
    )
    _send(fd=terminal.fd, text="\r")
    _read_until(
        terminal=terminal,
        predicate=lambda plain: "listskills" in _squashed(text=plain)
        and "enable/disableskills" in _squashed(text=plain),
        timeout_seconds=15,
    )


def _has_skill_row(*, plain: str) -> bool:
    # Codex truncates the fixed-width name column. The wider viewport exposes
    # the full plugin identifier in this SAME row's description. A cwd banner,
    # another row's kind, or a composer echo must never satisfy this assertion.
    return any(
        re.match(rf"^\s*{_CODEX_PROMPT_MARKER} {_EXPECTED_SKILL} \(", line) is not None
        and _EXPECTED_PLUGIN in line
        and "[Skill]" in line
        for line in plain.splitlines()
    )


def _has_result(*, plain: str) -> bool:
    return (
        _has_skill_row(plain=plain)
        and f"{_CODEX_PROMPT_MARKER} ${_PICKER_QUERY}" in plain.splitlines()
        and "enterinsert·escclose" in _squashed(text=plain)
    )


@pytest.mark.parametrize(
    "screen",
    [
        # The unchanged native fixture passed this composer-only screen by
        # joining its cwd, a discarded Skills menu, and the echoed query.
        f"{_EXPECTED_PLUGIN}\nSkills\n{_CODEX_PROMPT_MARKER} skills$drive",
        f"{_CODEX_PROMPT_MARKER} drive (other-plugin) [Skill]\n{_EXPECTED_PLUGIN}",
        f"{_CODEX_PROMPT_MARKER} drive ({_EXPECTED_PLUGIN}) [App]",
        f"{_CODEX_PROMPT_MARKER} drive ({_EXPECTED_PLUGIN})\n[Skill]",
    ],
)
def test_picker_oracle_rejects_unrelated_or_split_tokens(*, screen: str) -> None:
    assert not _has_skill_row(plain=screen)


def test_picker_wait_refuses_an_inactive_previously_matching_screen() -> None:
    read_fd, write_fd = os.pipe()
    screen = pyte.Screen(_COLUMNS, 40)
    terminal = _Terminal(fd=read_fd, screen=screen, stream=pyte.ByteStream(screen))
    terminal.stream.feed(
        (
            f"{_CODEX_PROMPT_MARKER} drive ({_EXPECTED_PLUGIN}) [Skill]\r\n"
            f"enter insert · esc close\r\n{_CODEX_PROMPT_MARKER} $drive"
        ).encode()
    )
    assert _has_result(plain=terminal.text())
    try:
        # No producer writes a fresh frame. Existing screen content is not an
        # acknowledgement of an input action, even when every token matches.
        with pytest.raises(AssertionError, match="Timed out"):
            _read_until(
                terminal=terminal, predicate=lambda p: _has_result(plain=p), timeout_seconds=0.01
            )
    finally:
        os.close(read_fd)
        os.close(write_fd)


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
    screen = pyte.Screen(_COLUMNS, 40)
    terminal = _Terminal(fd=master_fd, screen=screen, stream=pyte.ByteStream(screen))
    _send(fd=master_fd, text=_TERMINAL_RESPONSES)
    _await_codex_prompt(terminal=terminal)
    _open_skills_menu(terminal=terminal)
    _send(fd=master_fd, text="\r")
    _read_until(
        terminal=terminal,
        predicate=lambda plain: "enterinsert·escclose" in _squashed(text=plain)
        and "[Skill]" in plain
        and f"{_CODEX_PROMPT_MARKER} $" in plain.splitlines(),
        timeout_seconds=15,
    )
    _paste(fd=master_fd, text=_PICKER_QUERY)
    _read_until(terminal=terminal, predicate=lambda p: _has_result(plain=p), timeout_seconds=15)
    # Native negative control: stale rows/history cannot pass a changed query.
    _paste(fd=master_fd, text=_NO_MATCH_SUFFIX)
    _read_until(
        terminal=terminal,
        predicate=lambda plain: "no matches" in plain
        and f"{_CODEX_PROMPT_MARKER} ${_PICKER_QUERY}{_NO_MATCH_SUFFIX}" in plain.splitlines()
        and not _has_skill_row(plain=plain),
        timeout_seconds=15,
    )
    _send(fd=master_fd, text="\x7f" * len(_NO_MATCH_SUFFIX))
    return _read_until(
        terminal=terminal, predicate=lambda p: _has_result(plain=p), timeout_seconds=15
    )


@pytest.mark.skipif(
    os.environ.get("LIVESPEC_CODEX_SKILL_PICKER") != "1",
    reason="live Codex TUI picker acceptance runs only via just check-codex-skill-picker",
)
def test_skills_picker_finds_drive_by_short_name() -> None:
    codex = shutil.which("codex")
    if codex is None:
        pytest.fail("codex CLI is required for the live /skills picker acceptance")

    master_fd, slave_fd = pty.openpty()
    _prepare_pty(master_fd=master_fd, slave_fd=slave_fd)
    env = os.environ.copy()
    inherited_term = env.get("TERM", "").strip()
    env["TERM"] = (
        inherited_term if inherited_term and inherited_term != "dumb" else "xterm-256color"
    )
    env["COLUMNS"] = str(_COLUMNS)
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

    assert _has_result(plain=transcript), transcript
