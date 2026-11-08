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
        case "$input" in
          *bad*) exit 1 ;;
          *) exit 0 ;;
        esac
        """,
    )
    _write_executable(
        path=bin_dir / "curl",
        body="""\
        #!/usr/bin/env bash
        printf '%s\\n' "$*" >> "$CURL_LOG"
        exit 97
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
