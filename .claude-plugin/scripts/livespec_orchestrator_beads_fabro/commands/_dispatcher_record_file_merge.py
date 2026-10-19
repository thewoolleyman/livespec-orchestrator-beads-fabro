"""The declared-record-file merger the Dispatcher materializes into every sandbox.

`SPECIFICATION/contracts.md` section "Declared record files merge without a
repair round" (v162) gives `publish_draft` and `pr_refresh` an arm to take
BEFORE the refresh-repair route: when every conflicted path is a record file the
repository DECLARES as shared and append-only, the stage merges each one entry
by entry, continues the rebase or merge, and proceeds exactly as after a refresh
that did not conflict.

WHY A MATERIALIZED PROGRAM RATHER THAN SHELL IN THE NODE. The merge reads a
JSONC declaration, three Git index stages per file, and then either a keyed JSON
array or a line-level insertion diff. None of that is expressible in a node
`script`, and the half that is -- the declaration read -- is the half
`_dispatcher_publication_head` measured a hand-rolled shell reader getting wrong
on 100% of real records. The two refusals the paragraph turns on (an object both
sides changed differently, a merged array repeating a key) are comparisons, not
greps.

WHY IT IS STDLIB-ONLY AND CARRIES NO LIVESPEC IMPORT. The sandbox clone is the
GOVERNED repository and has no copy of this package, exactly as the plugin-cache
gate, the publication-head reader and the carry-forward decision record. It is
also why the program opens `.livespec.jsonc` itself rather than being handed a
resolved declaration: the conflict happens mid-rebase in the clone, and the
authority on what that clone declares is the clone's own committed file.

ONE DELIBERATE NARROWING, recorded because it decides which conflicts cost a
repair round. For `markdown-insertions` the paragraph makes the merge resolvable
"only when each conflicting region consists of lines that each side inserted at
the same position, with no line of the merge base changed or removed by both
sides". This program requires both sides to be PURE INSERTIONS relative to the
merge base over the whole file, which is stricter: a side that also rewrote an
untouched base line elsewhere is handed back rather than merged. The paragraph
states a necessary condition, so refusing more is conforming, and the direction
is the safe one -- a file refused here takes the route it took before v162,
while a file merged here is rewritten with no human in the loop.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "RECORD_FILE_MERGE_PROGRAM_FILENAME",
    "record_file_merge_program_path_expansion",
    "record_file_merge_program_prepare_steps_block",
    "record_file_merge_program_source",
]

# The program's filename below the sandbox plugins root.
#
# Fail-closed is the node's own existence test rather than a `${VAR:?}` guard,
# for the reason the carry-forward program gives: a sandbox the prepare step did
# not reach carries no program, and a refresh that silently skipped the merge arm
# would read as a repository whose record files were never declared.
RECORD_FILE_MERGE_PROGRAM_FILENAME = "livespec-record-file-merge.py"

_PROGRAM = r'''"""Resolve declared shared record-file conflicts from Git's three-way index.

Materialized by the Dispatcher from `_dispatcher_record_file_merge`. Do not edit
this file in a sandbox: it is rewritten from that module on every dispatch.
"""

import argparse
import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

MERGED_PREFIX = "LIVESPEC_RECORD_FILE_MERGED"
REFUSED_PREFIX = "LIVESPEC_RECORD_FILE_MERGE_REFUSED"

# The one configuration file the governed clone is the authority on, and the
# table the declaration lives under.
DECLARATION_FILENAME = ".livespec.jsonc"
_PLUGIN_KEY = "livespec-orchestrator-beads-fabro"

# `//` line comments outside string literals, which `.livespec.jsonc` carries and
# `json.loads` rejects. The string alternative is FIRST and is preserved
# verbatim, so a `//` inside a declared path is not mistaken for a comment.
_JSONC_TOKEN = re.compile(r'(?P<string>"(?:\\.|[^"\\])*")|(?P<comment>//[^\n]*)')


class RecordFileMergeUnresolvable(Exception):
    """An input this merge must hand back to the refresh-repair route."""


def _strip_jsonc_comments(text):
    return _JSONC_TOKEN.sub(lambda match: match.group("string") or "", text)


def declared_record_files(*, text):
    """Index the committed declaration by path.

    An absent key declares no record files, which is what makes the program safe
    to materialize into every sandbox: a repository that never opted in resolves
    nothing and every conflict takes the route it always took.
    """
    try:
        document = json.loads(_strip_jsonc_comments(text))
    except ValueError as error:
        raise RecordFileMergeUnresolvable(f"the declaration does not parse: {error}") from error
    table = document.get(_PLUGIN_KEY, {}) if isinstance(document, dict) else None
    dispatcher = table.get("dispatcher", {}) if isinstance(table, dict) else None
    entries = dispatcher.get("record_files", []) if isinstance(dispatcher, dict) else None
    if entries is None:
        raise RecordFileMergeUnresolvable("the declaration is not shaped as a configuration object")
    if not isinstance(entries, list):
        raise RecordFileMergeUnresolvable("dispatcher.record_files is not a list")
    declared = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise RecordFileMergeUnresolvable("a dispatcher.record_files entry is not an object")
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            raise RecordFileMergeUnresolvable(f"a record-file entry names no path: {entry!r}")
        if path.startswith("/") or ".." in path.split("/"):
            raise RecordFileMergeUnresolvable(
                f"record-file path is not repository-relative: {path}"
            )
        if path in declared:
            raise RecordFileMergeUnresolvable(f"record-file path {path} is declared twice")
        declared[path] = entry
    return declared


def _key_of(*, record, fields, path):
    if not isinstance(record, dict):
        raise RecordFileMergeUnresolvable(f"{path} holds a JSON-array entry that is not an object")
    missing = [name for name in fields if name not in record]
    if missing:
        raise RecordFileMergeUnresolvable(f"{path} holds an entry missing {missing}")
    return json.dumps([record[name] for name in fields], sort_keys=True)


def _indexed(*, text, fields, path):
    try:
        value = json.loads(text)
    except ValueError as error:
        raise RecordFileMergeUnresolvable(f"{path} does not parse as JSON: {error}") from error
    if not isinstance(value, list):
        raise RecordFileMergeUnresolvable(f"{path} is not a JSON array")
    order = []
    index = {}
    for record in value:
        key = _key_of(record=record, fields=fields, path=path)
        if key in index:
            raise RecordFileMergeUnresolvable(f"{path} already holds an entry keyed {key}")
        index[key] = record
        order.append(key)
    return order, index


def _merged_json_array(*, entry, base, default, run):
    path = entry.get("path")
    fields = entry.get("key")
    if not isinstance(fields, list) or not fields:
        raise RecordFileMergeUnresolvable(f"{path} declares json-array with no key fields")
    if any(not isinstance(name, str) or not name for name in fields):
        raise RecordFileMergeUnresolvable(f"{path} declares a json-array key that is not a field")
    _, at_base = _indexed(text=base, fields=fields, path=path)
    default_order, at_default = _indexed(text=default, fields=fields, path=path)
    run_order, at_run = _indexed(text=run, fields=fields, path=path)
    resolved = {}
    for key in set(at_base) | set(at_default) | set(at_run):
        before = at_base.get(key)
        on_default = at_default.get(key)
        on_run = at_run.get(key)
        if on_default != before and on_run != before and on_default != on_run:
            raise RecordFileMergeUnresolvable(
                f"{path} has the entry keyed {key} changed differently by "
                "the default branch and by the run"
            )
        if on_run != before:
            resolved[key] = (on_run, "run")
        else:
            resolved[key] = (on_default, "default")
    merged = []
    taken = {"default": 0, "run": 0}
    appended = [key for key in run_order if key not in at_default]
    for key in [*default_order, *appended]:
        record, side = resolved[key]
        if record is None:
            continue
        merged.append(record)
        taken[side] += 1
    # Serialize in the encoding the record's OWN sides carry, because an object
    # neither side changed has to stay as it is ON DISK and not only in the
    # parse. `ensure_ascii=True` can emit nothing but ASCII, so a side holding a
    # raw non-ASCII character PROVES that side was not written that way; where
    # all three sides are pure ASCII, escaping is the only encoding that
    # reproduces their bytes. A fixed choice re-encodes every untouched entry of
    # whichever convention it is wrong for -- and no gate catches it, since every
    # reader of these records parses rather than compares bytes.
    raw_non_ascii = any(not side.isascii() for side in (base, default, run))
    return (
        json.dumps(merged, indent=2, ensure_ascii=not raw_non_ascii) + "\n",
        taken["default"],
        taken["run"],
    )


def _insertions(*, base_lines, side_lines, path):
    inserted = {}
    matcher = SequenceMatcher(a=base_lines, b=side_lines, autojunk=False)
    for tag, base_start, _base_end, side_start, side_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag != "insert":
            raise RecordFileMergeUnresolvable(
                f"{path} has a merge-base line one side changed or removed, "
                "so this side is not an insertion"
            )
        inserted.setdefault(base_start, []).extend(side_lines[side_start:side_end])
    return inserted


def _merged_markdown_insertions(*, entry, base, default, run):
    path = entry.get("path")
    base_lines = base.splitlines(keepends=True)
    from_default = _insertions(
        base_lines=base_lines, side_lines=default.splitlines(keepends=True), path=path
    )
    from_run = _insertions(
        base_lines=base_lines, side_lines=run.splitlines(keepends=True), path=path
    )
    merged = []
    for position in range(len(base_lines) + 1):
        merged.extend(from_default.get(position, []))
        merged.extend(from_run.get(position, []))
        if position < len(base_lines):
            merged.append(base_lines[position])
    return (
        "".join(merged),
        sum(len(lines) for lines in from_default.values()),
        sum(len(lines) for lines in from_run.values()),
    )


def merged_record(*, entry, base, default, run):
    """Merge one declared record file's three sides, or refuse.

    Returns the merged text and the number of entries or lines taken from the
    default-branch side and from the run's side, which is what the stage records
    in its own output.
    """
    record_format = entry.get("format")
    if record_format == "json-array":
        return _merged_json_array(entry=entry, base=base, default=default, run=run)
    if record_format == "markdown-insertions":
        return _merged_markdown_insertions(entry=entry, base=base, default=default, run=run)
    raise RecordFileMergeUnresolvable(
        f"{entry.get('path')} declares unsupported record-file format {record_format!r}"
    )


def _index_stage(*, stage, path):
    shown = subprocess.run(
        ["git", "show", f":{stage}:{path}"], capture_output=True, text=True, check=False
    )
    if shown.returncode != 0:
        raise RecordFileMergeUnresolvable(
            f"index stage {stage} of {path} is unreadable: {shown.stderr.strip()}"
        )
    return shown.stdout


def _refuse(detail):
    print(f"{REFUSED_PREFIX}: {detail}", file=sys.stderr)
    return 1


def _merge_one(*, path, entry, default_stage, run_stage):
    merged, from_default, from_run = merged_record(
        entry=entry,
        base=_index_stage(stage=1, path=path),
        default=_index_stage(stage=default_stage, path=path),
        run=_index_stage(stage=run_stage, path=path),
    )
    Path(path).write_text(merged, encoding="utf-8")
    staged = subprocess.run(["git", "add", "--", path], check=False)
    if staged.returncode != 0:
        raise RecordFileMergeUnresolvable(f"the merged {path} could not be staged")
    print(
        f"{MERGED_PREFIX}: path={path} format={entry.get('format')} "
        f"default-count={from_default} run-count={from_run}",
        file=sys.stderr,
    )


def main():
    """Merge every named conflicted path, or refuse without touching any of them."""
    parser = argparse.ArgumentParser(description="Merge declared record-file conflicts.")
    _ = parser.add_argument("--mode", choices=("rebase", "merge"), required=True)
    _ = parser.add_argument("paths", nargs="+")
    arguments = parser.parse_args()
    # During a rebase the upstream being replayed ONTO is stage 2 ("ours") and
    # the run's own commit is stage 3 ("theirs"); a merge reverses them. Getting
    # this backwards produces a well-formed merge with the two sides' order and
    # per-side counts swapped, which nothing downstream would report.
    default_stage, run_stage = (2, 3) if arguments.mode == "rebase" else (3, 2)
    try:
        declaration = Path(DECLARATION_FILENAME).read_text(encoding="utf-8")
    except OSError as error:
        return _refuse(f"{DECLARATION_FILENAME} is unreadable: {error}")
    try:
        declared = declared_record_files(text=declaration)
    except RecordFileMergeUnresolvable as refusal:
        return _refuse(str(refusal))
    undeclared = [path for path in arguments.paths if path not in declared]
    if undeclared:
        return _refuse(f"conflicted path is not a declared record file: {' '.join(undeclared)}")
    for path in arguments.paths:
        try:
            _merge_one(
                path=path,
                entry=declared[path],
                default_stage=default_stage,
                run_stage=run_stage,
            )
        except (RecordFileMergeUnresolvable, OSError) as refusal:
            return _refuse(str(refusal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def record_file_merge_program_source() -> str:
    """The materialized program's exact bytes."""
    return _PROGRAM


def record_file_merge_program_path_expansion() -> str:
    """The shell expansion the refresh stages resolve the program through.

    PUBLIC and spelled once, for the reason the carry-forward program's own
    expansion records: a node resolving a DIFFERENT root than the prepare pass
    would find no program at all, and every record-file conflict would then take
    the repair route while the stage reported the merger absent.
    """
    return f"{sandbox_plugins_root_expansion()}/{RECORD_FILE_MERGE_PROGRAM_FILENAME}"


def record_file_merge_program_prepare_steps_block() -> str:
    """The prepare step that lands the program below the sandbox plugins root.

    Written through a heredoc with a QUOTED delimiter, so the shell expands
    nothing inside the program: the merger carries dollar-bearing,
    shell-looking text of its own -- a backslash-bearing regular expression, a
    `$` inside one -- and an unquoted heredoc would substitute into it.
    """
    root = sandbox_plugins_root_expansion()
    script = (
        f'set -eu\nmkdir -p "{root}"\n'
        f'cat > "{root}/{RECORD_FILE_MERGE_PROGRAM_FILENAME}" '
        f"<<'LIVESPEC_RECORD_FILE_MERGE_PROGRAM'\n"
        f"{record_file_merge_program_source()}"
        "LIVESPEC_RECORD_FILE_MERGE_PROGRAM"
    )
    return (
        "\n# --- Dispatcher-materialized declared record-file merger: the arm a\n"
        "# --- refresh takes before refresh repair when every conflicted path is\n"
        "# --- a declared shared record (v162, bd-ib-davaxq) ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {json.dumps(script)}\n"
    )
