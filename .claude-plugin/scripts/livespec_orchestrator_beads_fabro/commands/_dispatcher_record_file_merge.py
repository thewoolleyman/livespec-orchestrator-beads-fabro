"""Materialize the safe entry-wise merge used for declared refresh records."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "RECORD_FILE_MERGE_PROGRAM_FILENAME",
    "record_file_merge_program_path_expansion",
    "record_file_merge_program_prepare_steps_block",
    "record_file_merge_program_source",
]

RECORD_FILE_MERGE_PROGRAM_FILENAME = "livespec-record-file-merge.py"

_PROGRAM = r'''"""Resolve declared shared record-file conflicts from Git's index."""

import argparse
import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

MERGED_PREFIX = "LIVESPEC_RECORD_FILE_MERGED"
REFUSED_PREFIX = "LIVESPEC_RECORD_FILE_MERGE_REFUSED"
_JSONC = re.compile(r'("(?:\\.|[^"\\])*")|(//[^\n]*)')


class RecordFileMergeUnresolvable(Exception):
    """A conflict that must follow the ordinary refresh-repair route."""


def _refuse(detail):
    print(f"{REFUSED_PREFIX}: {detail}", file=sys.stderr)
    return 1


def _declaration():
    try:
        text = Path(".livespec.jsonc").read_text(encoding="utf-8")
        document = json.loads(_JSONC.sub(lambda match: match.group(1) or "", text))
        dispatcher = document["livespec-orchestrator-beads-fabro"]["dispatcher"]
        entries = dispatcher.get("record_files", [])
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise RecordFileMergeUnresolvable(f"record-file declaration is unreadable: {error}")
    if not isinstance(entries, list):
        raise RecordFileMergeUnresolvable("dispatcher.record_files is not an array")
    declared = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RecordFileMergeUnresolvable("record-file entry is not an object")
        path = entry.get("path")
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
            raise RecordFileMergeUnresolvable(f"record-file path is unsafe: {path!r}")
        if path in declared:
            raise RecordFileMergeUnresolvable(f"record-file path is declared twice: {path}")
        if entry.get("generator") is not None:
            raise RecordFileMergeUnresolvable(
                f"{path} is generated and must be resolved from its generator"
            )
        declared[path] = entry
    return declared


def _indexed(text, fields, path):
    try:
        values = json.loads(text)
    except ValueError as error:
        raise RecordFileMergeUnresolvable(f"{path} is not JSON: {error}")
    if not isinstance(values, list):
        raise RecordFileMergeUnresolvable(f"{path} is not a JSON array")
    order, indexed = [], {}
    for value in values:
        if not isinstance(value, dict) or any(field not in value for field in fields):
            raise RecordFileMergeUnresolvable(f"{path} has an entry without its declared key")
        key = json.dumps([value[field] for field in fields], sort_keys=True)
        if key in indexed:
            raise RecordFileMergeUnresolvable(f"{path} repeats key {key}")
        order.append(key)
        indexed[key] = value
    return order, indexed


def _merge_json(entry, base, default, run):
    path, fields = entry.get("path"), entry.get("key")
    if (
        not isinstance(fields, list)
        or not fields
        or not all(isinstance(field, str) and field for field in fields)
    ):
        raise RecordFileMergeUnresolvable(f"{path} declares no usable json-array key")
    _, base_by_key = _indexed(base, fields, path)
    default_order, default_by_key = _indexed(default, fields, path)
    run_order, run_by_key = _indexed(run, fields, path)
    resolved, sources = {}, {}
    for key in set(base_by_key) | set(default_by_key) | set(run_by_key):
        before = base_by_key.get(key)
        default_value = default_by_key.get(key)
        run_value = run_by_key.get(key)
        if default_value != before and run_value != before and default_value != run_value:
            raise RecordFileMergeUnresolvable(f"{path} changes key {key} differently on both sides")
        resolved[key] = run_value if run_value != before else default_value
        sources[key] = "run" if run_value != before else "default"
    keys = [*default_order, *(key for key in run_order if key not in default_by_key)]
    values = [resolved[key] for key in keys if resolved[key] is not None]
    default_count = sum(sources[key] == "default" for key in keys if resolved[key] is not None)
    run_count = len(values) - default_count
    ascii_only = all(side.isascii() for side in (base, default, run))
    return json.dumps(values, indent=2, ensure_ascii=ascii_only) + "\n", default_count, run_count


def _insertions(base_lines, side_lines, path):
    inserted = {}
    matcher = SequenceMatcher(a=base_lines, b=side_lines, autojunk=False)
    for tag, start, _end, side_start, side_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag != "insert":
            raise RecordFileMergeUnresolvable(f"{path} changes or removes a merge-base line")
        inserted.setdefault(start, []).extend(side_lines[side_start:side_end])
    return inserted


def _merge_markdown(entry, base, default, run):
    path, base_lines = entry.get("path"), base.splitlines(keepends=True)
    default_insertions = _insertions(base_lines, default.splitlines(keepends=True), path)
    run_insertions = _insertions(base_lines, run.splitlines(keepends=True), path)
    merged = []
    for position in range(len(base_lines) + 1):
        merged.extend(default_insertions.get(position, []))
        merged.extend(run_insertions.get(position, []))
        if position < len(base_lines):
            merged.append(base_lines[position])
    return (
        "".join(merged),
        sum(map(len, default_insertions.values())),
        sum(map(len, run_insertions.values())),
    )


def merged_record(*, entry, base, default, run):
    """Return merged text and default/run counts for one declared record."""
    if entry.get("format") == "json-array":
        return _merge_json(entry, base, default, run)
    if entry.get("format") == "markdown-insertions":
        return _merge_markdown(entry, base, default, run)
    raise RecordFileMergeUnresolvable(f"unsupported record-file format: {entry.get('format')!r}")


def _stage(stage, path):
    result = subprocess.run(
        ["git", "show", f":{stage}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RecordFileMergeUnresolvable(f"index stage {stage} of {path} is unreadable")
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("rebase", "merge"), required=True)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    try:
        declared = _declaration()
        if any(path not in declared for path in args.paths):
            raise RecordFileMergeUnresolvable("a conflicted path is not a declared record file")
        default_stage, run_stage = (2, 3) if args.mode == "rebase" else (3, 2)
        for path in args.paths:
            merged, default_count, run_count = merged_record(
                entry=declared[path], base=_stage(1, path),
                default=_stage(default_stage, path), run=_stage(run_stage, path),
            )
            Path(path).write_text(merged, encoding="utf-8")
            if subprocess.run(["git", "add", "--", path], check=False).returncode:
                raise RecordFileMergeUnresolvable(f"{path} could not be staged")
            print(
                f"{MERGED_PREFIX}: path={path} format={declared[path].get('format')} "
                f"default-count={default_count} run-count={run_count}",
                file=sys.stderr,
            )
    except RecordFileMergeUnresolvable as error:
        return _refuse(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def record_file_merge_program_source() -> str:
    """The exact stdlib-only program the prepare step materializes."""
    return _PROGRAM


def record_file_merge_program_path_expansion() -> str:
    """The program path both refresh stages resolve."""
    return f"{sandbox_plugins_root_expansion()}/{RECORD_FILE_MERGE_PROGRAM_FILENAME}"


def record_file_merge_program_prepare_steps_block() -> str:
    """Render the prepare step that writes the resolver into the sandbox."""
    root = sandbox_plugins_root_expansion()
    script = (
        f'set -eu\nmkdir -p "{root}"\n'
        f'cat > "{root}/{RECORD_FILE_MERGE_PROGRAM_FILENAME}" '
        "<<'LIVESPEC_RECORD_FILE_MERGE_PROGRAM'\n"
        f"{_PROGRAM}LIVESPEC_RECORD_FILE_MERGE_PROGRAM"
    )
    return "\n[[run.prepare.steps]]\nscript = '''\n" + script + "\n'''\n"
