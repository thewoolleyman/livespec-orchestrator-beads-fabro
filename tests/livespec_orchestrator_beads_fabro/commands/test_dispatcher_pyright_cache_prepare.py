"""The sandbox prepares one complete pyright cache before agents can race it."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
from pathlib import Path
from types import ModuleType

import tomli

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_pyright_cache"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_pyright_cache.py"
)
_VERSION = "1.1.391"
_FAKE_TOKEN = "overlay-token-placeholder"
_FAKE_GITHUB_TOKEN = "overlay-github-placeholder"


def _module() -> ModuleType:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE)


def _write_fake_uv(*, bin_dir: Path) -> None:
    script = bin_dir / "uv"
    _ = script.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'if [ "$1" = sync ]; then exit 0; fi\n'
        "printf '%s\\n' '1.1.391'\n",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _write_fake_npm(*, bin_dir: Path) -> None:
    script = bin_dir / "npm"
    _ = script.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'if [ "$1" = pack ]; then\n'
        "  destination=\n"
        "  previous=\n"
        '  for argument in "$@"; do\n'
        '    if [ "$previous" = --pack-destination ]; then destination=$argument; fi\n'
        "    previous=$argument\n"
        "  done\n"
        "  python3 - \"$destination/pyright.tgz\" <<'PY'\n"
        "import io, json, sys, tarfile\n"
        "with tarfile.open(sys.argv[1], 'w:gz') as archive:\n"
        "    for name, text in {\n"
        "        'package/package.json': json.dumps({'version': '1.1.391'}),\n"
        "        'package/dist/typeshed-fallback/stdlib/typing.pyi': 'typing',\n"
        "        'package/dist/typeshed-fallback/stdlib/subprocess.pyi': 'subprocess',\n"
        "    }.items():\n"
        "        data = text.encode()\n"
        "        info = tarfile.TarInfo(name)\n"
        "        info.size = len(data)\n"
        "        archive.addfile(info, io.BytesIO(data))\n"
        "PY\n"
        "  exit 0\n"
        "fi\n"
        "prefix=\n"
        "archive=\n"
        "previous=\n"
        'for argument in "$@"; do\n'
        '  if [ "$previous" = --prefix ]; then prefix=$argument; fi\n'
        "  previous=$argument\n"
        "  archive=$argument\n"
        "done\n"
        'mkdir -p "$prefix/node_modules/pyright"\n'
        'tar -xzf "$archive" --strip-components=1 -C "$prefix/node_modules/pyright"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)


def test_prepare_step_replaces_a_partial_locked_cache_with_the_complete_archive(
    tmp_path: Path,
) -> None:
    """A matching package version alone never lets a partial typeshed escape."""
    module = _module()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_uv(bin_dir=bin_dir)
    _write_fake_npm(bin_dir=bin_dir)
    home = tmp_path / "home"
    partial = home / ".cache" / "pyright-python" / _VERSION / "node_modules" / "pyright"
    partial.mkdir(parents=True)
    _ = (partial / "package.json").write_text(json.dumps({"version": _VERSION}), encoding="utf-8")
    later_stub = partial / "dist/typeshed-fallback/stdlib/subprocess.pyi"
    later_stub.parent.mkdir(parents=True)
    _ = later_stub.write_text("subprocess", encoding="utf-8")

    rendered = tomli.loads(module.pyright_cache_prepare_steps_block())
    script = rendered["run"]["prepare"]["steps"][0]["script"]
    result = subprocess.run(
        ["sh", "-c", script],
        check=False,
        capture_output=True,
        env={**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        text=True,
    )

    assert result.returncode == 0, result.stderr
    installed = partial
    assert (installed / "dist/typeshed-fallback/stdlib/typing.pyi").is_file()
    assert (installed / "dist/typeshed-fallback/stdlib/subprocess.pyi").is_file()


def test_overlay_places_the_cache_preparation_after_a_resume_checkout(tmp_path: Path) -> None:
    """A resumed lock is re-synced and warmed before an agent or hook can run."""
    from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
        render_run_config_overlay,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
        ResumeCheckout,
    )

    assert _MODULE_PATH.is_file()
    rendered = render_run_config_overlay(
        committed_text='[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "sandbox"\n',
        workflow_dir=tmp_path,
        token=_FAKE_TOKEN,
        github_token=_FAKE_GITHUB_TOKEN,
        siblings=None,
        resume_checkout=ResumeCheckout(branch="feat/bd-ib-g5hp", head="a" * 40),
    )

    assert rendered is not None
    assert rendered.index("recovery checkout") < rendered.index("pyright cache provisioning")
    assert "npm pack" in rendered
    assert "typeshed-fallback/stdlib" in rendered
