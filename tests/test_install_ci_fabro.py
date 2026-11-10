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
ARCHITECTURES = {
    "x86_64": (
        "27ff7a930950a322fcd5debdba7e35f63e999179169ccbaadbe502090094d7b0",
        "438318077",
    ),
    "aarch64": (
        "1c3e7f25410f14d2407782b1effebc450138a65e3b5e844937c5edb6474c8731",
        "438318044",
    ),
}


def _pinned_sha256(*, environment: dict[str, str]) -> str:
    return ARCHITECTURES[environment["FAKE_UNAME_M"]][0]


def _asset_id(*, environment: dict[str, str]) -> str:
    return ARCHITECTURES[environment["FAKE_UNAME_M"]][1]


def _asset_name(*, environment: dict[str, str]) -> str:
    return f"fabro-{environment['FAKE_UNAME_M']}-unknown-linux-musl.tar.gz"


def _warm_asset(*, environment: dict[str, str]) -> Path:
    return Path(environment["INSTALL_CI_FABRO_WARM_DIR"]) / _pinned_sha256(environment=environment)


def _write_executable(*, path: Path, body: str) -> None:
    path.write_text(textwrap.dedent(body))
    path.chmod(0o755)


@pytest.fixture(params=list(ARCHITECTURES))
def installer_environment(
    *, request: pytest.FixtureRequest, tmp_path: Path
) -> tuple[dict[str, str], Path, Path]:
    """Provide command stubs and a valid archive without network access."""
    architecture: str = request.param
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fixture_root = tmp_path / "fixture" / f"fabro-{architecture}-unknown-linux-musl"
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
        [[ "${input%%  *}" == "$EXPECT_SHA256" ]] || exit 1
        if [[ "$(head -c 3 "$path")" == bad ]]; then
          exit 1
        fi
        """,
    )
    _write_executable(
        path=bin_dir / "uname",
        body="""\
        #!/usr/bin/env bash
        [[ "$*" == -m ]] || exit 98
        printf '%s\\n' "$FAKE_UNAME_M"
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
          api-bad)
            [[ "$url" == *api.github.com* ]] || exit 97
            printf bad > "$output"
            ;;
          *) exit 97 ;;
        esac
        """,
    )
    environment = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "INSTALL_CI_FABRO_WARM_DIR": str(tmp_path / "warm"),
        "FAKE_UNAME_M": architecture,
        "EXPECT_SHA256": ARCHITECTURES[architecture][0],
    }
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
    warm_asset = _warm_asset(environment=environment)
    warm_asset.parent.mkdir(parents=True)
    shutil.copyfile(fixture_asset, warm_asset)

    result = _run_installer(environment=environment, target=tmp_path / "fabro")

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
    if seed_is_wrong:
        warm_asset = _warm_asset(environment=environment)
        warm_asset.parent.mkdir(parents=True)
        warm_asset.write_text("bad warm seed")

    result = _run_installer(environment=environment, target=tmp_path / "fabro")

    assert result.returncode == 0, result.stderr
    curl_arguments = curl_log.read_text()
    asset_id = _asset_id(environment=environment)
    assert (
        f"https://api.github.com/repos/fabro-sh/fabro/releases/assets/{asset_id}" in curl_arguments
    )
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

    result = _run_installer(environment=environment, target=tmp_path / "fabro")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "fabro").is_file()
    curl_arguments = curl_log.read_text()
    asset_id = _asset_id(environment=environment)
    asset_name = _asset_name(environment=environment)
    assert (
        f"https://api.github.com/repos/fabro-sh/fabro/releases/assets/{asset_id}" in curl_arguments
    )
    assert (
        f"https://github.com/fabro-sh/fabro/releases/download/v0.254.0/{asset_name}"
        in curl_arguments
    )


def test_rejects_a_downloaded_asset_with_the_wrong_sha256(
    *, installer_environment: tuple[dict[str, str], Path, Path], tmp_path: Path
) -> None:
    """A bad downloaded archive never installs a Fabro binary."""
    environment, _fixture_asset, curl_log = installer_environment
    environment.update({"CURL_LOG": str(curl_log), "CURL_MODE": "api-bad"})
    target = tmp_path / "fabro"

    result = _run_installer(environment=environment, target=target)

    assert result.returncode != 0
    assert not target.exists()
    assert "sha256 mismatch for GitHub releases API asset" in result.stderr


def test_reports_each_failed_source_when_no_asset_can_be_fetched(
    *, installer_environment: tuple[dict[str, str], Path, Path], tmp_path: Path
) -> None:
    """The terminal failure says which source in the ordered chain failed."""
    environment, _fixture_asset, curl_log = installer_environment
    environment.update({"CURL_LOG": str(curl_log), "CURL_MODE": "all-fail"})

    result = _run_installer(environment=environment, target=tmp_path / "fabro")

    assert result.returncode != 0
    assert "warm seed" in result.stderr
    assert "GitHub releases API asset route failed" in result.stderr
    assert "GitHub release download URL failed" in result.stderr


def test_unsupported_architecture_exits_naming_it_and_installs_nothing(
    *, installer_environment: tuple[dict[str, str], Path, Path], tmp_path: Path
) -> None:
    """An architecture without a pinned asset fails closed before any fetch."""
    environment, _fixture_asset, curl_log = installer_environment
    environment.update({"CURL_LOG": str(curl_log), "FAKE_UNAME_M": "riscv64"})
    target = tmp_path / "fabro"

    result = _run_installer(environment=environment, target=target)

    assert result.returncode != 0
    assert "riscv64" in result.stderr
    assert not target.exists()
    assert not curl_log.exists()
