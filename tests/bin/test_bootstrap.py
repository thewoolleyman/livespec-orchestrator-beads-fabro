"""Tests for .claude-plugin/scripts/bin/_bootstrap.py.

Covers both branches of `sys.version_info < (3, 10)` via
`monkeypatch.setattr`, the "path already in sys.path" branch, the
`_read_credential_wrapper` config-read (every fail-open branch + the happy
path), and the `_self_heal_credentials` performer's three decision arms
(Proceed returns, Fail exits 3, Reexec supervises the wrapped subprocess).

The pure `decide_credentials` brain is exhaustively tested in
livespec-runtime; here we only test the thin bin-side performer, so each
decision arm is driven by monkeypatching `decide_credentials` to return the
chosen variant and `subprocess.run` so a test never really re-execs.
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from livespec_runtime.credentials import (
    CREDENTIAL_REEXEC_SENTINEL,
    Fail,
    Proceed,
    Reexec,
)

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_BUNDLE_SCRIPTS = _BIN_DIR.parent
_BUNDLE_VENDOR = _BUNDLE_SCRIPTS / "_vendor"
_EXIT_CODE_VERSION_MISMATCH = 127
_EXIT_CODE_CREDENTIAL_FAIL = 3


def _import_bootstrap() -> object:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    sys.modules.pop("_bootstrap", None)
    return importlib.import_module("_bootstrap")


def test_bootstrap_exits_on_old_python(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap_module = _import_bootstrap()
    monkeypatch.setattr(sys, "version_info", (3, 9, 0, "final", 0))
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module.bootstrap()  # type: ignore[attr-defined]
    assert excinfo.value.code == _EXIT_CODE_VERSION_MISMATCH


def test_bootstrap_inserts_paths_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap_module = _import_bootstrap()
    # Neutralize the credential self-heal so this test isolates the sys.path
    # behavior (raising=False so the same file passes at the Red commit, when
    # the performer attribute does not yet exist on the master module).
    monkeypatch.setattr(
        bootstrap_module, "_self_heal_credentials", lambda **_kwargs: None, raising=False
    )
    fresh_path: list[str] = ["/usr/lib/python3.10"]
    monkeypatch.setattr(sys, "path", fresh_path)
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))
    bootstrap_module.bootstrap()  # type: ignore[attr-defined]
    assert str(_BUNDLE_SCRIPTS) in sys.path
    assert str(_BUNDLE_VENDOR) in sys.path


def test_bootstrap_skips_paths_already_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bootstrap_module = _import_bootstrap()
    monkeypatch.setattr(
        bootstrap_module, "_self_heal_credentials", lambda **_kwargs: None, raising=False
    )
    seeded_path: list[str] = [str(_BUNDLE_SCRIPTS), str(_BUNDLE_VENDOR), "/usr/lib/python3.10"]
    monkeypatch.setattr(sys, "path", seeded_path)
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))
    bootstrap_module.bootstrap()  # type: ignore[attr-defined]
    assert sys.path.count(str(_BUNDLE_SCRIPTS)) == 1
    assert sys.path.count(str(_BUNDLE_VENDOR)) == 1


# --------------------------------------------------------------------------
# _read_credential_wrapper — fail-open config read of the top-level
# `credential_wrapper` argv-prefix from <cwd>/.livespec.jsonc.
# --------------------------------------------------------------------------


def test_read_credential_wrapper_missing_file_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    bootstrap_module = _import_bootstrap()
    assert bootstrap_module._read_credential_wrapper() == []  # type: ignore[attr-defined]  # noqa: SLF001


def test_read_credential_wrapper_malformed_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text("{ not valid json", encoding="utf-8")
    bootstrap_module = _import_bootstrap()
    assert bootstrap_module._read_credential_wrapper() == []  # type: ignore[attr-defined]  # noqa: SLF001


def test_read_credential_wrapper_non_object_root_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text("[1, 2, 3]", encoding="utf-8")
    bootstrap_module = _import_bootstrap()
    assert bootstrap_module._read_credential_wrapper() == []  # type: ignore[attr-defined]  # noqa: SLF001


def test_read_credential_wrapper_non_list_value_returns_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"credential_wrapper": "not-a-list"}', encoding="utf-8"
    )
    bootstrap_module = _import_bootstrap()
    assert bootstrap_module._read_credential_wrapper() == []  # type: ignore[attr-defined]  # noqa: SLF001


def test_read_credential_wrapper_returns_configured_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '// leading comment\n{"credential_wrapper": ["/usr/local/bin/with-livespec-env.sh", "--"]}',
        encoding="utf-8",
    )
    bootstrap_module = _import_bootstrap()
    assert bootstrap_module._read_credential_wrapper() == [  # type: ignore[attr-defined]  # noqa: SLF001
        "/usr/local/bin/with-livespec-env.sh",
        "--",
    ]


# --------------------------------------------------------------------------
# _self_heal_credentials — the thin bin-side performer over the three
# CredentialDecision variants. The decision is monkeypatched; `subprocess.run`
# is stubbed so a test never really re-execs the process.
# --------------------------------------------------------------------------


def test_self_heal_proceeds_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "livespec_runtime.credentials.decide_credentials",
        lambda **_kwargs: Proceed(),
    )
    bootstrap_module = _import_bootstrap()
    assert bootstrap_module._self_heal_credentials() is None  # type: ignore[attr-defined]  # noqa: SLF001


def test_self_heal_fails_exits_three_and_writes_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "livespec_runtime.credentials.decide_credentials",
        lambda **_kwargs: Fail(message="secret absent and no wrapper"),
    )
    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module._self_heal_credentials()  # type: ignore[attr-defined]  # noqa: SLF001
    assert excinfo.value.code == _EXIT_CODE_CREDENTIAL_FAIL
    assert "secret absent and no wrapper" in capsys.readouterr().err


def test_self_heal_reexec_supervises_subprocess_and_propagates_output_and_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    reexec_argv = ("/usr/local/bin/with-livespec-env.sh", "--", "/usr/bin/python3", "next.py")
    monkeypatch.setattr(
        "livespec_runtime.credentials.decide_credentials",
        lambda **_kwargs: Reexec(argv=reexec_argv),
    )
    recorded: dict[str, object] = {}

    def _fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        recorded["args"] = args
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=args,
            returncode=17,
            stdout=b'{"ok": false}\n',
            stderr=b"wrapped cli stderr\n",
        )

    monkeypatch.setattr(
        os, "execvp", Mock(side_effect=AssertionError("blind execvp must not be used"))
    )
    monkeypatch.setattr(subprocess, "run", _fake_run)
    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module._self_heal_credentials()  # type: ignore[attr-defined]  # noqa: SLF001
    assert os.environ[CREDENTIAL_REEXEC_SENTINEL] == "1"
    assert recorded["args"] == list(reexec_argv)
    assert recorded["kwargs"] == {"capture_output": True, "check": False}
    assert excinfo.value.code == 17
    captured = capsys.readouterr()
    assert captured.out == '{"ok": false}\n'
    assert "wrapped cli stderr" in captured.err
    assert "credential_wrapper could not run" not in captured.err


def test_self_heal_reexec_structural_wrapper_failure_prints_clean_fail_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    reexec_argv = ("/usr/local/bin/with-livespec-env.sh", "--", "/usr/bin/python3", "next.py")
    _ = (tmp_path / ".livespec.jsonc").write_text(
        '{"credential_wrapper": ["/usr/local/bin/with-livespec-env.sh", "--"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "livespec_runtime.credentials.decide_credentials",
        lambda **_kwargs: Reexec(argv=reexec_argv),
    )

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            args=args,
            returncode=1,
            stdout=b"",
            stderr=b"sudo: The 'no new privileges' flag is set\n",
        )

    monkeypatch.setattr(
        os, "execvp", Mock(side_effect=AssertionError("blind execvp must not be used"))
    )
    monkeypatch.setattr(subprocess, "run", _fake_run)
    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module._self_heal_credentials()  # type: ignore[attr-defined]  # noqa: SLF001
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "credential_wrapper could not run in this environment" in captured.err
    assert "sudo:" not in captured.err


def test_self_heal_reexec_zero_exit_with_empty_output_exits_zero_without_hint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    reexec_argv = ("/usr/local/bin/with-livespec-env.sh", "--", "/usr/bin/python3", "next.py")
    monkeypatch.setattr(
        "livespec_runtime.credentials.decide_credentials",
        lambda **_kwargs: Reexec(argv=reexec_argv),
    )

    def _fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(
        os, "execvp", Mock(side_effect=AssertionError("blind execvp must not be used"))
    )
    monkeypatch.setattr(subprocess, "run", _fake_run)
    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module._self_heal_credentials()  # type: ignore[attr-defined]  # noqa: SLF001
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "credential_wrapper could not run" not in captured.err


def test_self_heal_threads_the_required_override_into_the_decision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`required` names the calling wrapper's OWN secret set (the Dispatcher
    adds the GitHub App env to the tenant secret; the mint CLI needs the App
    env ALONE — all riding the SAME credential_wrapper self-heal, per
    github-app-auth Pillar 2)."""
    monkeypatch.chdir(tmp_path)
    seen: dict[str, object] = {}

    def _record(**kwargs: object) -> Proceed:
        seen.update(kwargs)
        return Proceed()

    monkeypatch.setattr("livespec_runtime.credentials.decide_credentials", _record)
    bootstrap_module = _import_bootstrap()
    bootstrap_module._self_heal_credentials(  # type: ignore[attr-defined]  # noqa: SLF001
        required=("GITHUB_APP_ID", "GITHUB_PRIVATE_KEY")
    )
    assert seen["required"] == ("GITHUB_APP_ID", "GITHUB_PRIVATE_KEY")


def test_bootstrap_required_override_drops_the_tenant_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A wrapper that never touches the ledger (the mint-app-token CLI) MUST
    proceed on its own secret set alone: with the App env present and the
    tenant secret ABSENT, bootstrap(required=<app env>) returns instead of
    exiting — the entrypoint's github provisioning must not demand the Dolt
    password."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    bootstrap_module = _import_bootstrap()
    bootstrap_module.bootstrap(  # type: ignore[attr-defined]
        required=("GITHUB_APP_ID", "GITHUB_PRIVATE_KEY")
    )


def test_bootstrap_fails_when_secret_and_wrapper_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Integration: real bootstrap() reaches the self-heal Fail arm when the
    tenant secret is absent and no credential_wrapper is configured.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module.bootstrap()  # type: ignore[attr-defined]
    assert excinfo.value.code == _EXIT_CODE_CREDENTIAL_FAIL


def test_bootstrap_fails_when_a_required_override_secret_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Integration: a present tenant secret does NOT satisfy a wrapper whose
    required set names the GitHub App env — absent members still fail closed
    (exit 3) when no credential_wrapper is configured to re-exec through.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "test-not-a-real-secret")
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_PRIVATE_KEY", raising=False)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module.bootstrap(  # type: ignore[attr-defined]
            required=("BEADS_DOLT_PASSWORD", "GITHUB_APP_ID", "GITHUB_PRIVATE_KEY")
        )
    assert excinfo.value.code == _EXIT_CODE_CREDENTIAL_FAIL


# --------------------------------------------------------------------------
# _tenant_secret_required — derive whether the family tenant secret
# (BEADS_DOLT_PASSWORD) is needed from the cwd beads ledger MODE. A server-mode
# tenant (`.beads/config.yaml` declaring `dolt.mode: server`) needs it, and an
# absent/unreadable config fails CLOSED (require). An EMBEDDED, self-contained
# Dolt ledger (`bd init` with no `--server`, e.g. the disposable livespec-e2e
# golden-master target) needs NONE. Regression: the embedded e2e dispatch path
# was demanding the family password the embedded store never uses.
# --------------------------------------------------------------------------


def _write_beads_config(*, cwd: Path, body: str) -> None:
    beads_dir = cwd / ".beads"
    beads_dir.mkdir(parents=True, exist_ok=True)
    _ = (beads_dir / "config.yaml").write_text(body, encoding="utf-8")


def test_tenant_secret_required_when_beads_config_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    bootstrap_module = _import_bootstrap()
    assert bootstrap_module._tenant_secret_required(cwd=tmp_path) is True  # type: ignore[attr-defined]  # noqa: SLF001


def test_tenant_secret_required_for_server_mode_tenant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_beads_config(
        cwd=tmp_path,
        body="# server-mode tenant on the shared dolt-server\ndolt.mode: server\ndolt.server-host: 127.0.0.1\n",
    )
    bootstrap_module = _import_bootstrap()
    assert bootstrap_module._tenant_secret_required(cwd=tmp_path) is True  # type: ignore[attr-defined]  # noqa: SLF001


def test_tenant_secret_not_required_for_embedded_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_beads_config(
        cwd=tmp_path,
        body="# Embedded (no --server) self-contained Dolt; no family password.\ndolt.auto-start: true\n",
    )
    bootstrap_module = _import_bootstrap()
    assert bootstrap_module._tenant_secret_required(cwd=tmp_path) is False  # type: ignore[attr-defined]  # noqa: SLF001


def test_bootstrap_embedded_ledger_proceeds_without_tenant_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The disposable livespec-e2e golden-master dispatches against an EMBEDDED
    beads ledger (cwd `.beads/config.yaml` with no `dolt.mode: server`), whose
    self-contained Dolt store needs no family BEADS_DOLT_PASSWORD. bootstrap()
    must PROCEED there with the App env present and the tenant secret absent —
    not fail closed at exit 3 as it did before, which broke the e2e substrate.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    _write_beads_config(
        cwd=tmp_path,
        body="# Embedded (no --server) self-contained Dolt; no family password.\ndolt.auto-start: true\n",
    )
    bootstrap_module = _import_bootstrap()
    assert (
        bootstrap_module.bootstrap(  # type: ignore[attr-defined]
            required=("BEADS_DOLT_PASSWORD", "GITHUB_APP_ID", "GITHUB_PRIVATE_KEY")
        )
        is None
    )
