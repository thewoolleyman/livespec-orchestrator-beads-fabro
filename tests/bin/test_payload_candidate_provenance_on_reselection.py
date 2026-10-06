"""Re-selecting a source re-points the CANDIDATE, not just the executing code.

Cycle 11 made an explicitly selected installation win over an inherited
payload, so the right CODE runs. Cycle 12 gave `plugin_root()` a launcher
record to read when no harness exports `CLAUDE_PLUGIN_ROOT`, so the CANDIDATE
is the installation rather than the payload. This file is about what happens
when those two meet, which neither cycle's accepted Red covers.

`retain_payload` publishes the record with `environ.setdefault(...)`, and
`setdefault` is a NO-OP when the key is already present. An inherited
`INSTALLED_ROOT_ENV` therefore survives a re-selection. Worse for the checkout
case, which returns at the `harness_managed` test — BEFORE the publication line
— so it neither rebinds nor clears a stale inherited record.

Measured against the unmodified launcher on 2026-10-06, with install A at
release 7.1.0 provisioned first and its environment inherited:

| selected source      | executes | candidate resolves to |
| -------------------- | -------- | --------------------- |
| explicit newer B     | 9.9.9    | **A's install**       |
| this project's own checkout | 5.5.5 | **A's install**  |
| same-source helper A | 7.1.0    | A's install (correct) |

So the first two run one build while NAMING another as the installation
present. That is not cosmetic. `plugin_root()` is the candidate root for every
currency surface: a minimum-release refusal tells the operator to update the
installation it names, so it would point at A while B is what dispatched; the
self-update canary compares the running release against A's; and the
registered-install currency finding compares the registry against A. Each
reports a confident answer about the wrong installation.

The correct rule follows from what each path KNOWS, and the three cases are
genuinely different rather than one rule with exceptions:

- an ADOPTED inherited payload keeps the inherited record. The adoption arm
  returns before the publication line, so this already holds and must keep
  holding — the helper did not select an installation, it joined one, and its
  own `source_root` is the payload rather than any install;
- a FRESH provision selected the installation it copied, so that source IS the
  installation and the record must be re-pointed at it, overwriting whatever
  was inherited;
- a CHECKOUT is its own installation, so it must publish itself rather than
  leave a foreign install standing.

The third case below is the control that keeps the first bullet true. Without
it a fix could satisfy the two mismatches by publishing unconditionally, which
would make a helper record the PAYLOAD as the installation — re-opening
exactly the candidate/execution collapse cycle 12 closed.

Scope is candidate PROVENANCE within the work-item's second and fifth
assertions. No new policy about which source wins: that is cycle 11's, settled,
and this file asserts the same winners it does.
"""

import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_RELEASE_A = "7.1.0"
_RELEASE_B = "9.9.9"
_RELEASE_CHECKOUT = "5.5.5"
_CHECKOUT_PLUGIN_ROOT = ".claude-plugin"
_THIS_PROJECT = '[project]\nname = "livespec-orchestrator-beads-fabro"\n'


def _import_payload() -> Any:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    _ = sys.modules.pop("_payload", None)
    return importlib.import_module("_payload")


def _paths_module() -> Any:
    return importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_paths")


def _install(*, root: Path, release: str) -> Path:
    """A COMPLETE minimal installed plugin root carrying `release`."""
    for relative in (
        "scripts/bin",
        "scripts/livespec_orchestrator_beads_fabro/commands",
        "scripts/_vendor/livespec_runtime",
        ".fabro/workflows/implement-work-item",
    ):
        (root / relative).mkdir(parents=True)
    for relative in (
        "scripts/bin/_bootstrap.py",
        "scripts/bin/_payload.py",
        "scripts/livespec_orchestrator_beads_fabro/__init__.py",
        "scripts/livespec_orchestrator_beads_fabro/commands/__init__.py",
        "scripts/_vendor/livespec_runtime/__init__.py",
        ".fabro/workflows/implement-work-item/workflow.toml",
    ):
        _ = (root / relative).write_text("", encoding="utf-8")
    _ = (root / "plugin.json").write_text(json.dumps({"version": release}), encoding="utf-8")
    return root


def _private_tempdir(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    return temp_root


def _candidate(*, monkeypatch: pytest.MonkeyPatch, environ: dict[str, str]) -> Path:
    """What `plugin_root()` resolves under `environ`, with no harness export.

    `CLAUDE_PLUGIN_ROOT` is removed because it OUTRANKS the launcher record,
    so leaving it set would answer a different question than the one this file
    asks — and would answer it identically whether the record was re-pointed
    or not.
    """
    paths = _paths_module()
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    recorded = environ.get(paths.INSTALLED_ROOT_ENV)
    if recorded is None:
        monkeypatch.delenv(paths.INSTALLED_ROOT_ENV, raising=False)
    else:
        monkeypatch.setenv(paths.INSTALLED_ROOT_ENV, recorded)
    return paths.plugin_root()


def _release_of(*, payload: Any) -> str:
    manifest = json.loads((payload.root / "plugin.json").read_text(encoding="utf-8"))
    return str(manifest["version"])


def _provisioned_a(*, payload: Any, tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Install A, provisioned, with the environment it published."""
    source_a = _install(root=tmp_path / "cache" / "aaaaaaa1111", release=_RELEASE_A)
    environ: dict[str, str] = {}
    first = payload.retain_payload(source_root=source_a, environ=environ)
    assert _release_of(payload=first) == _RELEASE_A, "fixture: A did not provision as A"
    return source_a, environ


def test_an_explicitly_selected_newer_install_becomes_the_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """B's code runs, so B must also be the installation the candidate names."""
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_a, environ = _provisioned_a(payload=payload, tmp_path=tmp_path)
    source_b = _install(root=tmp_path / "cache" / "bbbbbbb2222", release=_RELEASE_B)

    inherited = dict(environ)
    selected = payload.retain_payload(source_root=source_b, environ=inherited)

    assert _release_of(payload=selected) == _RELEASE_B, "cycle 11's selection regressed"
    assert _candidate(monkeypatch=monkeypatch, environ=inherited) == source_b, (
        "the candidate still names install A while install B's release is what "
        "executes, so a minimum-release refusal would tell the operator to "
        "update the wrong installation and the canary would compare against it"
    )


def test_an_explicitly_selected_checkout_becomes_the_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A checkout is its own installation, inherited record or not.

    The checkout arm returns before the publication line, so a stale inherited
    record is neither rebound nor cleared.
    """
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_a, environ = _provisioned_a(payload=payload, tmp_path=tmp_path)
    checkout_parent = tmp_path / "checkout"
    checkout_parent.mkdir()
    _ = (checkout_parent / "pyproject.toml").write_text(_THIS_PROJECT, encoding="utf-8")
    checkout = _install(root=checkout_parent / _CHECKOUT_PLUGIN_ROOT, release=_RELEASE_CHECKOUT)

    inherited = dict(environ)
    selected = payload.retain_payload(source_root=checkout, environ=inherited)

    assert selected.root == checkout, "cycle 11's checkout selection regressed"
    assert _candidate(monkeypatch=monkeypatch, environ=inherited) == checkout, (
        "a developer running their own checkout has a foreign install left "
        "standing as the candidate, so every currency surface reports on an "
        "installation this invocation never touched"
    )


def test_an_adopted_inherited_payload_keeps_the_original_installs_candidacy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The control: a same-source helper joined A, it did not select anything.

    Its own `source_root` is the PAYLOAD, so publishing unconditionally would
    record the payload as the installation and collapse the candidate onto the
    execution path again — the regression cycle 12 closed. A fix for the two
    cases above must leave this answer alone.
    """
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_a, environ = _provisioned_a(payload=payload, tmp_path=tmp_path)

    inherited = dict(environ)
    helper = payload.retain_payload(source_root=source_a, environ=inherited)

    assert helper.holder is None, "a helper must not own the payload it inherited"
    assert _candidate(monkeypatch=monkeypatch, environ=inherited) == source_a, (
        "an adopted inherited payload lost its original installation's "
        "candidacy, so the helper reports on the wrong tree"
    )


def test_a_helper_launched_from_the_payload_keeps_the_installs_candidacy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The real helper shape, and the one a careless fix breaks.

    A `scripts/bin/` helper resolves its own plugin root to the tree it was
    loaded from, so it names the PAYLOAD as its source — the form
    `test_payload_lifetime_release.py` has spawned since cycle 4. The
    candidate must still be the installation the payload came from, never the
    payload itself.
    """
    payload = _import_payload()
    _ = _private_tempdir(monkeypatch=monkeypatch, tmp_path=tmp_path)
    source_a, environ = _provisioned_a(payload=payload, tmp_path=tmp_path)
    payload_root = Path(environ[payload.PAYLOAD_ROOT_ENV])

    inherited = dict(environ)
    helper = payload.retain_payload(source_root=payload_root, environ=inherited)

    assert helper.root == payload_root, "the payload-sourced helper did not reuse the payload"
    candidate = _candidate(monkeypatch=monkeypatch, environ=inherited)
    assert candidate == source_a, (
        f"the candidate followed the helper's own source instead of the "
        f"installation: {candidate}"
    )
    assert candidate != payload_root, (
        "the candidate collapsed onto the retained payload, which is the "
        "regression cycle 12 closed"
    )
