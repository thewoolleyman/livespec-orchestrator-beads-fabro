"""The stdlib-only record-file merger materialized into every factory sandbox.

The refresh stages run in a governed clone, not in this plugin's interpreter.
They therefore receive this source as a standalone program during preparation.
It reads the committed declaration and Git's three conflict-index stages, then
resolves only the two formats ratified for append-only shared records.
"""

from __future__ import annotations

import json

__all__: list[str] = [
    "RECORD_FILE_MERGE_PROGRAM_FILENAME",
    "record_file_merge_program_prepare_steps_block",
    "record_file_merge_program_source",
]

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

RECORD_FILE_MERGE_PROGRAM_FILENAME = "livespec-record-file-merge.py"

_PROGRAM = r'''"""Resolve declared shared record-file conflicts from Git's three-way index."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


_JSONC_TOKEN = re.compile(r'(?P<string>"(?:\\.|[^"\\])*")|(?P<comment>//[^\n]*)')


def _fail(detail: str) -> int:
    print(f"LIVESPEC_RECORD_FILE_MERGE_REFUSED: {detail}", file=sys.stderr)
    return 1


def _strip_comments(text: str) -> str:
    return _JSONC_TOKEN.sub(
        lambda match: match.group("string") if match.group("string") is not None else "", text
    )


def _declared_records() -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(_strip_comments(Path(".livespec.jsonc").read_text(encoding="utf-8")))
        plugin = raw["livespec-orchestrator-beads-fabro"]
        dispatcher = plugin["dispatcher"]
        entries = dispatcher.get("record_files", [])
    except (OSError, TypeError, ValueError, KeyError) as error:
        raise ValueError(f"record-file declaration is unreadable: {error}") from error
    if not isinstance(entries, list):
        raise ValueError("dispatcher.record_files is not a list")
    declared: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("dispatcher.record_files contains a non-object entry")
        path = entry.get("path")
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or ".." in Path(path).parts
        ):
            raise ValueError(f"record-file path is unsafe: {path!r}")
        if path in declared:
            raise ValueError(f"record-file declaration repeats {path}")
        declared[path] = entry
    return declared


def _stage(stage: int, path: str) -> str:
    shown = subprocess.run(
        ["git", "show", f":{stage}:{path}"], capture_output=True, text=True, check=False
    )
    if shown.returncode != 0:
        raise ValueError(f"could not read index stage {stage} for {path}: {shown.stderr.strip()}")
    return shown.stdout


def _key_of(item: object, fields: Sequence[object], path: str) -> str:
    if not isinstance(item, dict):
        raise ValueError(f"{path} contains a non-object JSON-array entry")
    names = [field for field in fields if isinstance(field, str) and field]
    if len(names) != len(fields):
        raise ValueError(f"{path} has an invalid json-array key declaration")
    if any(name not in item for name in names):
        raise ValueError(f"{path} has an entry missing a declared key field")
    return json.dumps([item[name] for name in names], sort_keys=True, separators=(",", ":"))


def _array(
    text: str, fields: Sequence[object], path: str
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not JSON: {error}") from error
    if not isinstance(value, list):
        raise ValueError(f"{path} is not a JSON array")
    items: list[dict[str, Any]] = []
    indexed: dict[str, dict[str, Any]] = {}
    for item in value:
        key = _key_of(item, fields, path)
        if key in indexed:
            raise ValueError(f"{path} has duplicate declared key {key}")
        assert isinstance(item, dict)
        indexed[key] = item
        items.append(item)
    return items, indexed


def _changed(base: dict[str, Any] | None, side: dict[str, Any] | None) -> bool:
    return base != side


def _json_array(
    base: str, default: str, run: str, entry: dict[str, Any], path: str
) -> tuple[str, int, int]:
    fields = entry.get("key")
    if not isinstance(fields, list) or not fields:
        raise ValueError(f"{path} declares json-array without a non-empty key")
    base_items, base_by_key = _array(base, fields, path)
    default_items, default_by_key = _array(default, fields, path)
    run_items, run_by_key = _array(run, fields, path)
    del base_items
    chosen: dict[str, tuple[dict[str, Any] | None, str]] = {}
    for key in set(base_by_key) | set(default_by_key) | set(run_by_key):
        before = base_by_key.get(key)
        default_value = default_by_key.get(key)
        run_value = run_by_key.get(key)
        default_changed = _changed(before, default_value)
        run_changed = _changed(before, run_value)
        if default_changed and run_changed and default_value != run_value:
            raise ValueError(f"{path} changes declared key {key} differently on both sides")
        if run_changed:
            chosen[key] = (run_value, "run")
        elif default_changed:
            chosen[key] = (default_value, "default")
        else:
            chosen[key] = (before, "default")
    ordered: list[dict[str, Any]] = []
    default_count = 0
    run_count = 0
    emitted: set[str] = set()
    for item in default_items:
        key = _key_of(item, fields, path)
        value, side = chosen[key]
        if value is not None:
            ordered.append(value)
            emitted.add(key)
            if side == "default":
                default_count += 1
            else:
                run_count += 1
    for item in run_items:
        key = _key_of(item, fields, path)
        if key in emitted or key in default_by_key:
            continue
        value, side = chosen[key]
        if value is not None:
            ordered.append(value)
            emitted.add(key)
            if side == "default":
                default_count += 1
            else:
                run_count += 1
    return json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", default_count, run_count


def _insertions(base: list[str], side: list[str], path: str) -> dict[int, list[str]]:
    import difflib

    inserted: dict[int, list[str]] = {}
    for tag, start, end, other_start, other_end in difflib.SequenceMatcher(
        a=base, b=side, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        if tag != "insert":
            raise ValueError(f"{path} changes or removes a merge-base line")
        assert start == end
        inserted.setdefault(start, []).extend(side[other_start:other_end])
    return inserted


def _markdown(base: str, default: str, run: str, path: str) -> tuple[str, int, int]:
    base_lines = base.splitlines(keepends=True)
    default_insertions = _insertions(base_lines, default.splitlines(keepends=True), path)
    run_insertions = _insertions(base_lines, run.splitlines(keepends=True), path)
    output: list[str] = []
    for position in range(len(base_lines) + 1):
        output.extend(default_insertions.get(position, []))
        output.extend(run_insertions.get(position, []))
        if position < len(base_lines):
            output.append(base_lines[position])
    return (
        "".join(output),
        sum(map(len, default_insertions.values())),
        sum(map(len, run_insertions.values())),
    )


def _merge(
    path: str, entry: dict[str, Any], default_stage: int, run_stage: int
) -> tuple[str, int, int]:
    base = _stage(1, path)
    default = _stage(default_stage, path)
    run = _stage(run_stage, path)
    format_name = entry.get("format")
    if format_name == "json-array":
        return _json_array(base, default, run, entry, path)
    if format_name == "markdown-insertions":
        return _markdown(base, default, run, path)
    raise ValueError(f"{path} has unsupported record-file format {format_name!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("rebase", "merge"), required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    try:
        declared = _declared_records()
        undeclared = [path for path in args.paths if path not in declared]
        if undeclared:
            return _fail(f"conflicted path is not declared: {', '.join(undeclared)}")
        default_stage, run_stage = (2, 3) if args.mode == "rebase" else (3, 2)
        for path in args.paths:
            merged, default_count, run_count = _merge(
                path, declared[path], default_stage, run_stage
            )
            Path(path).write_text(merged, encoding="utf-8")
            added = subprocess.run(["git", "add", "--", path], check=False)
            if added.returncode != 0:
                return _fail(f"could not stage merged record file {path}")
            print(
                "LIVESPEC_RECORD_FILE_MERGED: "
                f"path={path} format={declared[path]['format']} "
                f"default-count={default_count} run-count={run_count}",
                file=sys.stderr,
            )
    except ValueError as error:
        return _fail(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def record_file_merge_program_source() -> str:
    """Return the exact standalone program the refresh stages execute."""
    return _PROGRAM


def record_file_merge_program_prepare_steps_block() -> str:
    """Materialize the merger without evaluating its shell-looking source."""
    root = sandbox_plugins_root_expansion()
    script = (
        f"set -eu\nmkdir -p '{root}'\ncat > "
        f"'{root}/{RECORD_FILE_MERGE_PROGRAM_FILENAME}' <<'LIVESPEC_RECORD_FILE_MERGE_PROGRAM'\n"
        f"{record_file_merge_program_source()}"
        "LIVESPEC_RECORD_FILE_MERGE_PROGRAM"
    )
    return (
        "\n# --- Dispatcher-materialized declared record-file merge program ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )
