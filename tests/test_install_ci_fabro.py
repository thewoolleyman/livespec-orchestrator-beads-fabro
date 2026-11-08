"""Behaviour tests for the pinned Fabro installer."""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[1]
INSTALLER = REPOSITORY_ROOT / "dev-tooling/install-ci-fabro.sh"
PINNED_SHA256 = "27ff7a930950a322fcd5debdba7e35f63e999179169ccbaadbe502090094d7b0"
WARM_ASSET = Path("/__w/_warm/release-assets") / PINNED_SHA256


def _write_executable(*, path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body))
    path.chmod(0o755)


@pytest.fixture
def installer_environment(*, tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    """Provide command stubs and a valid archive without network access."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixture_root = tmp_path / "fixture" / "fabro-x86_64-unknown-linux-musl"
    fixture_root.mkdir(parents=True)
    _write_executable(
        path=fixture_root / "fabro",
        body="""\
        #!/usr/bin/env bash
        printf 'fabro fixture\\n'
        """,
    )
    fixture_asset = tmp_path / "fixture.tar.gz"
    subprocess.run(
        ["tar", "-czf", str(fixture_asset), "-C", str(fixture_root.parent), fixture_root.name],
        check=True,
    )
    _write_executable(
        path=bin_dir / "sha256sum",
        body="""\
        #!/usr/bin/env bash
        input="$(cat)"
        path="${input##*  }"
        if [[ "$path" == /__w/_warm/release-assets/* ]] && [[ "$(head -c 3 "$path")" == bad ]]; then
          exit 1
        fi
        """,
    )
    _write_executable(
        path=bin_dir / "curl",
        body="""\
        #!/usr/bin/env bash
        printf '%s\\n' "$*" >> "$CURL_LOG"
        url="${!#}"
        output=""
        while (($#)); do
          if [[ "$1" == --output ]]; then
            output="$2"
            shift 2
            continue
          fi
          shift
        done
        case "${CURL_MODE:-fail}" in
          api-success)
            [[ "$url" == *api.github.com* ]] || exit 97
            cp "$CURL_FIXTURE" "$output"
            ;;
          api-fail-fallback-success)
            [[ "$url" == *api.github.com* ]] && exit 97
            [[ "$url" == *github.com/fabro-sh/fabro/releases/download* ]] || exit 97
            cp "$CURL_FIXTURE" "$output"
            ;;
          *) exit 97 ;;
        esac
        """,
    )
    environment = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return environment, fixture_asset, tmp_path / "curl.log"


def _run_installer(
    *, environment: dict[str, str], target: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALLER), str(target)],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )


def test_uses_verified_warm_seed_without_calling_curl(
    *, installer_environment: tuple[dict[str, str], Path, Path], tmp_path: Path
) -> None:
    """A verified warm asset is installed locally without a network attempt."""
    environment, fixture_asset, curl_log = installer_environment
    environment["CURL_LOG"] = str(curl_log)
    WARM_ASSET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture_asset, WARM_ASSET)

    try:
        result = _run_installer(environment=environment, target=tmp_path / "fabro")
    finally:
        WARM_ASSET.unlink(missing_ok=True)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "fabro").is_file()
    assert not curl_log.exists()


@pytest.mark.parametrize("seed_is_wrong", [False, True], ids=["absent", "checksum-mismatch"])
def test_uses_api_asset_when_warm_seed_is_unavailable(
    *,
    installer_environment: tuple[dict[str, str], Path, Path],
    seed_is_wrong: bool,
    tmp_path: Path,
) -> None:
    """A missing or invalid warm asset moves to the authenticated API route."""
    environment, fixture_asset, curl_log = installer_environment
    environment.update(
        {
            "CURL_LOG": str(curl_log),
            "CURL_MODE": "api-success",
            "CURL_FIXTURE": str(fixture_asset),
            "GITHUB_TOKEN": "test-token",
        }
    )
    WARM_ASSET.unlink(missing_ok=True)
    if seed_is_wrong:
        WARM_ASSET.parent.mkdir(parents=True, exist_ok=True)
        WARM_ASSET.write_text("bad warm seed")

    try:
        result = _run_installer(environment=environment, target=tmp_path / "fabro")
    finally:
        WARM_ASSET.unlink(missing_ok=True)

    assert result.returncode == 0, result.stderr
    curl_arguments = curl_log.read_text()
    assert "https://api.github.com/repos/fabro-sh/fabro/releases/assets/438318077" in curl_arguments
    assert "Accept: application/octet-stream" in curl_arguments
    assert "Authorization: Bearer test-token" in curl_arguments
    assert "https://github.com/fabro-sh/fabro/releases/download/" not in curl_arguments


def test_falls_back_to_release_download_after_api_asset_failure(
    *, installer_environment: tuple[dict[str, str], Path, Path], tmp_path: Path
) -> None:
    """An API error tries the direct release URL next."""
    environment, fixture_asset, curl_log = installer_environment
    environment.update(
        {
            "CURL_LOG": str(curl_log),
            "CURL_MODE": "api-fail-fallback-success",
            "CURL_FIXTURE": str(fixture_asset),
        }
    )
    WARM_ASSET.unlink(missing_ok=True)

    result = _run_installer(environment=environment, target=tmp_path / "fabro")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "fabro").is_file()
    curl_arguments = curl_log.read_text()
    assert "https://api.github.com/repos/fabro-sh/fabro/releases/assets/438318077" in curl_arguments
    assert "https://github.com/fabro-sh/fabro/releases/download/v0.254.0/" in curl_arguments
