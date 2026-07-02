"""`mint-app-token` CLI over the vendored fleet GitHub App-token primitive.

FAIL-CLOSED per the github-app-auth design record (Pillar 2 —
tenant-scoped resolution): the credential env (GITHUB_APP_ID +
GITHUB_PRIVATE_KEY, optional GITHUB_APP_INSTALLATION_ID /
GITHUB_API_URL) is injected ONLY by the calling tenant's
credential_wrapper, and the retired fleet PAT
(LIVESPEC_FAMILY_GITHUB_TOKEN) is NEVER read — not even as a fallback.
The signing / mint / provider logic lives in the vendored
`livespec_runtime.github_auth` (tested upstream in livespec-runtime);
these tests cover ONLY this repo's CLI wiring: the env → config →
provider → stdout railway and the expected-failure exit mapping.
"""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands import mint_app_token as cli
from livespec_runtime.github_auth.config import GithubAppConfig
from livespec_runtime.github_auth.errors import GithubAppAuthError

_GITHUB_ENV_VARS = (
    "GITHUB_APP_ID",
    "GITHUB_PRIVATE_KEY",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_API_URL",
    "LIVESPEC_FAMILY_GITHUB_TOKEN",
)


@pytest.fixture(autouse=True)
def _scrub_github_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from a credential-free environment (hermetic)."""
    for name in _GITHUB_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


class _StubProvider:
    """Provider stand-in: captures the config, never touches the network."""

    built_with: GithubAppConfig | None = None

    def __init__(self, *, config: GithubAppConfig) -> None:
        type(self).built_with = config

    def token(self) -> str:
        return "ghs_stub-installation-token"


class _MintFailingProvider:
    """Provider stand-in whose mint raises the expected domain error."""

    def __init__(self, *, config: GithubAppConfig) -> None:
        _ = config

    def token(self) -> str:
        raise GithubAppAuthError(detail="the App API rejected the JWT")


def test_main_mints_via_the_vendored_provider_and_prints_only_the_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", " 42 ")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    monkeypatch.setattr(cli, "InstallationTokenProvider", _StubProvider)
    assert cli.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == "ghs_stub-installation-token"
    assert "github-token source: github-app-installation-token" in captured.err
    built = _StubProvider.built_with
    assert built is not None
    assert built.app_id == "42"
    assert built.installation_id is None


def test_main_threads_the_optional_installation_pin_and_api_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "131208965")
    monkeypatch.setenv("GITHUB_API_URL", "https://ghe.example/api/v3")
    monkeypatch.setattr(cli, "InstallationTokenProvider", _StubProvider)
    assert cli.main() == 0
    _ = capsys.readouterr()
    built = _StubProvider.built_with
    assert built is not None
    assert built.installation_id == "131208965"
    assert built.api_url == "https://ghe.example/api/v3"


def test_main_never_falls_back_to_the_retired_fleet_pat(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A present fleet PAT with no App env is a REFUSAL, never a credential.

    The pre-github-app-auth CLI silently downgraded to the
    LIVESPEC_FAMILY_GITHUB_TOKEN PAT when no App was configured — the
    exact fleet fallback Pillar 2 forbids. The PAT must never reach
    stdout, and the diagnostic must route the operator to the calling
    tenant's credential_wrapper.
    """
    monkeypatch.setenv("LIVESPEC_FAMILY_GITHUB_TOKEN", "github_pat_retired")
    assert cli.main([]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "credential_wrapper" in captured.err
    assert "github_pat_retired" not in captured.err


def test_main_maps_missing_app_env_to_exit_3_with_actionable_detail(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main([]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "GITHUB_APP_ID" in captured.err


def test_main_maps_a_mint_failure_to_exit_3(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "stub-pem")
    monkeypatch.setattr(cli, "InstallationTokenProvider", _MintFailingProvider)
    assert cli.main([]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "the App API rejected the JWT" in captured.err
