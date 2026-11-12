"""Regression coverage for the Codex picker cleanup fallback."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType

import pytest


def _picker_module() -> ModuleType:
    """Load the picker acceptance helpers without relying on a package import."""
    path = Path(__file__).with_name("test_codex_skill_picker.py")
    specification = importlib.util.spec_from_file_location("codex_skill_picker", path)
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_picker_cleanup_uses_writer_exit_event_without_pidfds(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    picker = _picker_module()
    release = tmp_path / "release-writer"
    child_pid_file = tmp_path / "writer-pid"
    os.mkfifo(release)
    exit_read_fd, exit_write_fd = os.pipe()
    proc = subprocess.Popen(
        [
            "sh",
            "-c",
            'read < "$1" & ' 'printf "%s\\n" "$!" > "$2"',
            "--",
            str(release),
            str(child_pid_file),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        pass_fds=(exit_write_fd,),
        start_new_session=True,
    )
    os.close(exit_write_fd)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        assert proc.wait(timeout=5) == 0
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        os.kill(child_pid, 0)
        monkeypatch.delattr(picker.os, "pidfd_open", raising=False)
        stopped = False
        try:
            picker.stop_codex(
                proc=proc,
                fd=devnull_fd,
                group_exit_fd=exit_read_fd,
            )
        except (AttributeError, TypeError):
            pass
        else:
            stopped = True
        assert stopped
    finally:
        with suppress(OSError):
            os.close(devnull_fd)
        with suppress(OSError):
            os.close(exit_read_fd)
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, 9)
        proc.wait(timeout=5)
