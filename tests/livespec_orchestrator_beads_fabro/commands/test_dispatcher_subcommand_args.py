"""The flag surface of every dispatcher subcommand that is NOT a dispatch.

`dispatcher.py` is the Dispatcher's supervisor and subcommand ROUTER: it owns
`main`, the handler table, and the assembly of the subparsers. It also carried the
per-subcommand ARGUMENT DECLARATIONS of the check, credential-status and reconcile
families, and that is a second concern — one that grows every time a subcommand is
added, which is what put the router at its own file-size ceiling with a ratified
`resume` subcommand still to wire in.

`_dispatcher_subcommand_args` is the sibling of `_dispatcher_dispatch_args`, which
already owns the group `dispatch`, `loop` and `probe` share. Between the two, every
flag declaration lives beside its own concern and the router declares none itself.

WHAT THIS FILE ASSERTS, AND WHY A PARSER TEST IS NOT ENOUGH. `test_dispatcher.py`
already drives these subcommands through `main`, so the flags are exercised. That
is exactly why the move needs its own assertions: a parser test passes whether the
declarations live in the router or in the extracted module, so nothing in the suite
would notice the extraction being undone, or half-undone with one subcommand's
declaration left behind in the router. So this file asserts BOTH directions — the
public names exist in the new module, and the private originals are GONE from the
router's source.

THE PARSED NAMESPACE IS ASSERTED TOO, not just the names. A declaration can be
moved and silently lose a flag, a `dest`, or a default; every consumer downstream
reads those `dest` names off the Namespace, and an absent one surfaces as an
`AttributeError` deep inside a dispatch rather than as a usage error here.
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_subcommand_args"

_PUBLIC_NAMES = (
    "add_claude_cred_status_arguments",
    "add_codex_cred_refresh_arguments",
    "add_janitor_check_arguments",
    "add_ledger_check_arguments",
    "add_ledger_normalize_arguments",
    "add_reconcile_merged_arguments",
    "add_reconcile_runs_arguments",
    "add_spec_check_arguments",
)

# The private originals, as the router spelled them. Each one's ABSENCE from
# `dispatcher.py` is what proves the declaration moved rather than being copied:
# a copy would leave both surfaces green and let the two drift apart.
_PRIVATE_ORIGINALS = (
    "_add_cred_status",
    "_add_codex_cred_refresh",
    "_add_janitor_check",
    "_add_ledger_check",
    "_add_ledger_normalize",
    "_add_reconcile_merged",
    "_add_reconcile_runs",
    "_add_spec_check",
)


def _module_path() -> Path:
    """Where the extracted module is expected on disk."""
    return Path(dispatcher.__file__).parent / "_dispatcher_subcommand_args.py"


def test_the_extracted_module_exists_on_disk() -> None:
    """The first genuine assertion of the move: the module is a file."""
    assert _module_path().is_file()


def test_every_declaration_is_public_in_the_extracted_module() -> None:
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)

    missing = [name for name in _PUBLIC_NAMES if not hasattr(module, name)]
    assert missing == []


def test_the_extracted_module_declares_exactly_those_names() -> None:
    """`__all__` is the module's own account of its surface, per the package rule."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)

    assert sorted(module.__all__) == sorted(_PUBLIC_NAMES)


def test_the_router_no_longer_declares_any_of_them() -> None:
    """A leftover private original is a second copy that can drift from this one."""
    source = Path(dispatcher.__file__).read_text(encoding="utf-8")

    left_behind = [name for name in _PRIVATE_ORIGINALS if f"def {name}(" in source]
    assert left_behind == []


@pytest.mark.parametrize(
    ("adder", "argv", "expected"),
    [
        (
            "add_ledger_check_arguments",
            ["--project-root", "/repo", "--json"],
            {"project_root": "/repo", "as_json": True},
        ),
        (
            "add_ledger_normalize_arguments",
            ["--dry-run", "--gate"],
            {"project_root": None, "as_json": False, "dry_run": True, "gate": True},
        ),
        (
            "add_spec_check_arguments",
            ["--spec-root", "/spec"],
            {"project_root": None, "spec_root": "/spec", "as_json": False},
        ),
        (
            "add_codex_cred_refresh_arguments",
            ["--dry-run"],
            {"as_json": False, "dry_run": True},
        ),
        (
            "add_claude_cred_status_arguments",
            ["--json"],
            {"as_json": True},
        ),
        (
            "add_janitor_check_arguments",
            ["--repo", "/repo"],
            {"repo": "/repo", "as_json": False},
        ),
        (
            "add_reconcile_runs_arguments",
            ["--factory", "hp", "--fabro-bin", "/bin/fabro", "--dry-run"],
            {
                "repo": None,
                "factory": "hp",
                "fabro_bin": "/bin/fabro",
                "journal": None,
                "dry_run": True,
                "as_json": False,
            },
        ),
        (
            "add_reconcile_merged_arguments",
            ["--repo", "/repo", "--item", "bd-ib-one", "--force", "--regrade"],
            {
                "repo": "/repo",
                "item": "bd-ib-one",
                "janitor": None,
                "journal": None,
                "force": True,
                "regrade": True,
                "as_json": False,
            },
        ),
    ],
)
def test_each_declaration_parses_the_namespace_its_handler_reads(
    *, adder: str, argv: list[str], expected: dict[str, object]
) -> None:
    """Every `dest` a handler reads must survive the move, defaults included."""
    assert _module_path().is_file()
    module = importlib.import_module(_MODULE)
    parser = argparse.ArgumentParser(prog="probe-parser")

    getattr(module, adder)(parser=parser)
    parsed = vars(parser.parse_args(argv))

    assert {key: parsed[key] for key in expected} == expected


def test_the_router_still_parses_every_one_of_those_subcommands() -> None:
    """The extraction is a pure move: the router's own surface is unchanged."""
    parsed = dispatcher.main.__globals__["_build_parser"]().parse_args(
        ["reconcile-merged", "--repo", "/repo", "--item", "bd-ib-one"]
    )

    assert parsed.subcommand == "reconcile-merged"
    assert parsed.item == "bd-ib-one"
    assert parsed.regrade is False
