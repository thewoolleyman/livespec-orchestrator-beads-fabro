"""Paired coverage for shell-backed beads client effects."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import ShellBeadsClient
from livespec_orchestrator_beads_fabro.effects import _beads_client_shell as shell
from livespec_orchestrator_beads_fabro.errors import BeadsConnectionError
from livespec_orchestrator_beads_fabro.types import StoreConfig


def test_raise_for_status_maps_connection_refused() -> None:
    completed = subprocess.CompletedProcess(
        args=["bd", "list"],
        returncode=1,
        stdout="",
        stderr="connection refused",
    )

    with pytest.raises(BeadsConnectionError):
        shell.raise_for_status(completed=completed, argv=["bd", "list"], tenant="tenant")


def test_raise_for_status_surfaces_zero_exit_stderr(caplog: pytest.LogCaptureFixture) -> None:
    completed = subprocess.CompletedProcess(
        args=["bd", "comment"],
        returncode=0,
        stdout="ok\n",
        stderr="synthetic warning on stderr\n",
    )

    with caplog.at_level(logging.WARNING):
        shell.raise_for_status(completed=completed, argv=["bd", "comment"], tenant="tenant")

    assert caplog.messages == ["bd exited zero with stderr"]
    assert caplog.records[0].bd_argv == ["bd", "comment"]
    assert caplog.records[0].bd_tenant == "tenant"
    assert caplog.records[0].bd_stderr == "synthetic warning on stderr"


def test_raise_for_status_zero_exit_empty_stderr_is_quiet(
    caplog: pytest.LogCaptureFixture,
) -> None:
    completed = subprocess.CompletedProcess(
        args=["bd", "list"],
        returncode=0,
        stdout="[]\n",
        stderr="",
    )

    with caplog.at_level(logging.WARNING):
        shell.raise_for_status(completed=completed, argv=["bd", "list"], tenant="tenant")

    assert caplog.messages == []


def test_raise_for_status_nonzero_keeps_typed_error_without_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    completed = subprocess.CompletedProcess(
        args=["bd", "list"],
        returncode=1,
        stdout="",
        stderr="connection refused",
    )

    with caplog.at_level(logging.WARNING), pytest.raises(BeadsConnectionError):
        shell.raise_for_status(completed=completed, argv=["bd", "list"], tenant="tenant")

    assert caplog.messages == []


def _tenant_config(
    *, repo_root: Path, tenant: str = "tenant-db", credential_wrapper: tuple[str, ...] = ()
) -> StoreConfig:
    return StoreConfig(
        tenant=tenant,
        prefix="td",
        server_user=tenant,
        database=tenant,
        bd_path="/nonexistent/bd",
        repo_root=repo_root,
        credential_wrapper=credential_wrapper,
    )


def _fake_bd_config_get(counter: list[str]) -> object:
    """A subprocess.run stand-in answering `bd config get <key>` correctly."""

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        counter.append(argv[-1])
        value = "tenant-db"
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout=value + "\n", stderr="")

    return run


def _server_mode_repo(*, tmp_path: Path) -> tuple[Path, Path]:
    """A repo root whose `.beads/config.yaml` declares server mode."""
    repo_root = tmp_path / "repo"
    config_path = repo_root / ".beads" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    _ = config_path.write_text("dolt:\n  mode: server\n", encoding="utf-8")
    return repo_root, config_path


def _embedded_repo(*, tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    config_path = repo_root / ".beads" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    _ = config_path.write_text("dolt.mode: embedded\n", encoding="utf-8")
    return repo_root


def test_run_json_surfaces_zero_exit_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo_root = _embedded_repo(tmp_path=tmp_path)

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout="[]\n",
            stderr="synthetic json-path warning\n",
        )

    monkeypatch.setattr(shell.subprocess, "run", run)
    client = ShellBeadsClient(config=_tenant_config(repo_root=repo_root))

    with caplog.at_level(logging.WARNING):
        assert client._run_json(verb_args=["list", "--json"]) == []  # noqa: SLF001

    assert caplog.messages == ["bd exited zero with stderr"]
    assert caplog.records[0].bd_argv == ["/nonexistent/bd", "list", "--json"]
    assert caplog.records[0].bd_tenant == "tenant-db"
    assert caplog.records[0].bd_stderr == "synthetic json-path warning"


def test_run_void_surfaces_zero_exit_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo_root = _embedded_repo(tmp_path=tmp_path)

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout="ok\n",
            stderr="synthetic void-path warning\n",
        )

    monkeypatch.setattr(shell.subprocess, "run", run)
    client = ShellBeadsClient(config=_tenant_config(repo_root=repo_root))

    with caplog.at_level(logging.WARNING):
        client._run_void(verb_args=["comment", "li-a", "body"])  # noqa: SLF001

    assert caplog.messages == ["bd exited zero with stderr"]
    assert caplog.records[0].bd_argv == ["/nonexistent/bd", "comment", "li-a", "body"]
    assert caplog.records[0].bd_tenant == "tenant-db"
    assert caplog.records[0].bd_stderr == "synthetic void-path warning"


def test_shell_uses_the_target_wrapper_for_preflight_and_bd_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, _ = _server_mode_repo(tmp_path=tmp_path)
    _ = (repo_root / ".beads" / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    wrapper = tmp_path / "with-target-tenant-env.sh"
    client = ShellBeadsClient(
        config=_tenant_config(
            repo_root=repo_root,
            credential_wrapper=(str(wrapper), "--"),
        )
    )
    calls: list[tuple[list[str], Path]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cwd = kwargs["cwd"]
        assert isinstance(cwd, Path)
        calls.append((argv, cwd))
        if argv[-3:-1] == ["config", "get"]:
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="tenant-db\n", stderr=""
            )
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="[]\n", stderr="")

    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)
    _ = _tmp_xdg_cache_dir(tmp_path=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setattr(shell.subprocess, "run", run)
    shell.reset_tenant_verification_memo()

    assert client._run_json(verb_args=["list", "--json"]) == []  # noqa: SLF001

    assert calls == [
        ([str(wrapper), "--", "/nonexistent/bd", "config", "get", "dolt.server-user"], repo_root),
        ([str(wrapper), "--", "/nonexistent/bd", "config", "get", "dolt.database"], repo_root),
        ([str(wrapper), "--", "/nonexistent/bd", "list", "--json"], repo_root),
    ]


def _tmp_xdg_cache_dir(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect XDG_CACHE_HOME into tmp_path; return the cache's own directory."""
    xdg_home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_home))
    return xdg_home / "livespec-orchestrator-beads-fabro" / "tenant-verification"


def _cache_files(*, cache_dir: Path) -> list[Path]:
    return sorted(cache_dir.glob("*.json"))


def _legacy_cache_path(*, repo_root: Path) -> Path:
    return repo_root / ".beads" / "tenant-verification-cache.json"


def test_fresh_process_reuses_the_file_cached_tenant_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A one-shot CLI process must not re-spawn `bd config get`.

    Clearing the in-process memo stands in for a brand-new wrapper process
    (scripts/bin/list_work_items.py and friends spawn, make one or two bd calls,
    and exit). The tier-2 file cache must satisfy the verification with zero new
    subprocess spawns, from a file OUTSIDE the governed repo.
    """
    repo_root, _ = _server_mode_repo(tmp_path=tmp_path)
    cache_dir = _tmp_xdg_cache_dir(tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = _tenant_config(repo_root=repo_root)
    calls: list[str] = []
    monkeypatch.setattr(shell.subprocess, "run", _fake_bd_config_get(calls))
    shell.reset_tenant_verification_memo()

    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)
    assert len(calls) == 2

    shell.reset_tenant_verification_memo()
    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    assert len(calls) == 2
    assert len(_cache_files(cache_dir=cache_dir)) == 1
    assert not _legacy_cache_path(repo_root=repo_root).exists()
    assert list((repo_root / ".beads").iterdir()) == [repo_root / ".beads" / "config.yaml"]


def test_cache_falls_back_to_home_cache_without_xdg_cache_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, _ = _server_mode_repo(tmp_path=tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(home))
    config = _tenant_config(repo_root=repo_root)
    calls: list[str] = []
    monkeypatch.setattr(shell.subprocess, "run", _fake_bd_config_get(calls))
    shell.reset_tenant_verification_memo()

    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    cache_dir = home / ".cache" / "livespec-orchestrator-beads-fabro" / "tenant-verification"
    assert len(_cache_files(cache_dir=cache_dir)) == 1


def test_legacy_in_repo_cache_is_ignored_and_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old `.beads/` cache file must never be read, and must be swept away.

    It predates the XDG relocation and `.beads/.gitignore` never covered it, so
    every repo the orchestrator touched grew a permanently untracked file.
    """
    repo_root, config_path = _server_mode_repo(tmp_path=tmp_path)
    cache_dir = _tmp_xdg_cache_dir(tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = _tenant_config(repo_root=repo_root)
    legacy_path = _legacy_cache_path(repo_root=repo_root)
    stat = config_path.stat()
    live_key = "|".join(
        (str(repo_root), "tenant-db", "tenant-db", f"{stat.st_mtime_ns}:{stat.st_size}")
    )
    _ = legacy_path.write_text(json.dumps({live_key: time.time()}), encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(shell.subprocess, "run", _fake_bd_config_get(calls))
    shell.reset_tenant_verification_memo()

    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    assert len(calls) == 2
    assert not legacy_path.exists()
    assert len(_cache_files(cache_dir=cache_dir)) == 1


def test_config_file_change_invalidates_the_file_cached_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, config_path = _server_mode_repo(tmp_path=tmp_path)
    _ = _tmp_xdg_cache_dir(tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = _tenant_config(repo_root=repo_root)
    calls: list[str] = []
    monkeypatch.setattr(shell.subprocess, "run", _fake_bd_config_get(calls))
    shell.reset_tenant_verification_memo()
    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    shell.reset_tenant_verification_memo()
    stat = config_path.stat()
    os.utime(config_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    assert len(calls) == 4


def test_expired_file_cache_entries_are_reverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The TTL bounds a positive whose config identity never changed."""
    repo_root, _ = _server_mode_repo(tmp_path=tmp_path)
    cache_dir = _tmp_xdg_cache_dir(tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = _tenant_config(repo_root=repo_root)
    calls: list[str] = []
    monkeypatch.setattr(shell.subprocess, "run", _fake_bd_config_get(calls))
    shell.reset_tenant_verification_memo()
    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    cache_path = _cache_files(cache_dir=cache_dir)[0]
    cached: dict[str, float] = json.loads(cache_path.read_text(encoding="utf-8"))
    _ = cache_path.write_text(json.dumps({key: 0.0 for key in cached}), encoding="utf-8")
    shell.reset_tenant_verification_memo()
    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    assert len(calls) == 4


def test_corrupt_file_cache_is_treated_as_a_miss_and_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, _ = _server_mode_repo(tmp_path=tmp_path)
    cache_dir = _tmp_xdg_cache_dir(tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = _tenant_config(repo_root=repo_root)
    calls: list[str] = []
    monkeypatch.setattr(shell.subprocess, "run", _fake_bd_config_get(calls))
    shell.reset_tenant_verification_memo()
    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    cache_path = _cache_files(cache_dir=cache_dir)[0]
    _ = cache_path.write_text("{ not json at all", encoding="utf-8")
    shell.reset_tenant_verification_memo()
    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)
    assert len(calls) == 4

    shell.reset_tenant_verification_memo()
    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    assert len(calls) == 4
    rewritten: dict[str, float] = json.loads(cache_path.read_text(encoding="utf-8"))
    assert len(rewritten) == 1


def test_tenant_mismatch_without_a_config_file_is_never_file_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only POSITIVE verifications are cached; a mismatch keeps raising."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    cache_dir = _tmp_xdg_cache_dir(tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = _tenant_config(repo_root=repo_root)

    def run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="other-tenant\n", stderr=""
        )

    monkeypatch.setattr(shell.subprocess, "run", run)
    shell.reset_tenant_verification_memo()

    with pytest.raises(BeadsConnectionError):
        shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)

    assert not cache_dir.exists()


def test_repeat_tenant_verification_reuses_memo_for_process_lifetime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A re-verify of the same repo tenant must not re-spawn `bd config get`.

    First verification runs the two config reads; a second verification of the
    SAME repo root and tenant identity reuses the memoized positive result
    (zero new subprocess spawns) for process lifetime.
    """
    repo_root = tmp_path / "repo"
    config_path = repo_root / ".beads" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    _ = config_path.write_text("dolt:\n  mode: server\n", encoding="utf-8")
    _ = _tmp_xdg_cache_dir(tmp_path=tmp_path, monkeypatch=monkeypatch)
    config = _tenant_config(repo_root=repo_root)
    calls: list[str] = []
    monkeypatch.setattr(shell.subprocess, "run", _fake_bd_config_get(calls))
    shell.reset_tenant_verification_memo()

    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)
    assert len(calls) == 2

    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)
    assert len(calls) == 2

    stat = config_path.stat()
    os.utime(config_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    shell.assert_repo_root_matches_config(config=config, repo_root=repo_root)
    assert len(calls) == 2


def test_invoke_memoizes_tenant_validation_per_process_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    config_a_path = repo_a / ".beads" / "config.yaml"
    config_b_path = repo_b / ".beads" / "config.yaml"
    config_a_path.parent.mkdir(parents=True)
    config_b_path.parent.mkdir(parents=True)
    _ = config_a_path.write_text("dolt.mode: server\n", encoding="utf-8")
    _ = config_b_path.write_text("dolt.mode: server\n", encoding="utf-8")
    config_a = _tenant_config(repo_root=repo_a, tenant="tenant-a")
    config_b = _tenant_config(repo_root=repo_b, tenant="tenant-b")
    tenant_by_repo = {
        repo_a: "tenant-a",
        repo_b: "tenant-b",
    }
    config_get_calls: list[tuple[Path, str]] = []

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        cwd = kwargs["cwd"]
        assert isinstance(cwd, Path)
        if argv[1:3] == ["config", "get"]:
            key = argv[3]
            config_get_calls.append((cwd, key))
            value = tenant_by_repo[cwd]
            return subprocess.CompletedProcess(
                args=argv,
                returncode=0,
                stdout=value + "\n",
                stderr="",
            )
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="[]\n", stderr="")

    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "present")
    _ = _tmp_xdg_cache_dir(tmp_path=tmp_path, monkeypatch=monkeypatch)
    monkeypatch.setattr(shell.subprocess, "run", run)
    shell.reset_tenant_verification_memo()

    for _ in range(3):
        shell.invoke(config=config_a, argv=[config_a.bd_path, "list"])
    for _ in range(2):
        shell.invoke(config=config_b, argv=[config_b.bd_path, "list"])

    stat = config_a_path.stat()
    os.utime(config_a_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    shell.invoke(config=config_a, argv=[config_a.bd_path, "show", "bd-ib-demo"])

    assert config_get_calls == [
        (repo_a, "dolt.server-user"),
        (repo_a, "dolt.database"),
        (repo_b, "dolt.server-user"),
        (repo_b, "dolt.database"),
    ]
