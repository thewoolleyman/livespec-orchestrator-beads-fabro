"""`/livespec-impl-beads:list-memos` thin-transport command.

CLI surface per SPECIFICATION/contracts.md §"list-memos":

  list-memos [--filter <name>] [--json] [--memos-path <path>]

Filters:

- `--filter=untriaged` — state == "untriaged"
- `--filter=dispositioned` — state == "dispositioned"
- `--filter=all` (default)

Output:

- Default: one-line summary per memo.
- `--json`: an array of memo materialized views (latest record per id).
"""

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from livespec_impl_beads.commands._config import resolve_store_config
from livespec_impl_beads.errors import StoreFileMissingError
from livespec_impl_beads.store import materialize_memos, read_memos
from livespec_impl_beads.types import Memo

FilterChoice = Literal["all", "untriaged", "dispositioned"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="list-memos")
    _ = parser.add_argument(
        "--filter",
        dest="filter_name",
        default="all",
        choices=["all", "untriaged", "dispositioned"],
    )
    _ = parser.add_argument("--json", dest="as_json", action="store_true")
    _ = parser.add_argument("--memos-path", dest="memos_path", default=None)
    args = parser.parse_args(argv)
    config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None, memos_arg=args.memos_path)
    materialized = _load_memos(path=config.memos_path)
    filtered = _filter_memos(materialized=materialized, name=args.filter_name)
    if args.as_json:
        _write_json(memos=filtered)
    else:
        _write_human(memos=filtered)
    return 0


def _load_memos(*, path: Path) -> list[Memo]:
    try:
        return list(materialize_memos(read_memos(path=path)).values())
    except StoreFileMissingError:
        return []


def _filter_memos(*, materialized: list[Memo], name: str) -> list[Memo]:
    predicates: dict[str, Callable[[Memo], bool]] = {
        "all": lambda _: True,
        "untriaged": lambda memo: memo.state == "untriaged",
        "dispositioned": lambda memo: memo.state == "dispositioned",
    }
    predicate = predicates[name]
    return [memo for memo in materialized if predicate(memo)]


def _write_json(*, memos: list[Memo]) -> None:
    payload = [_memo_to_dict(memo=memo) for memo in memos]
    _ = sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_human(*, memos: list[Memo]) -> None:
    if not memos:
        _ = sys.stdout.write("(no memos)\n")
        return
    for memo in memos:
        suffix = f" → {memo.disposition}" if memo.disposition is not None else ""
        _ = sys.stdout.write(
            f"{memo.id}  [{memo.state}{suffix}]  {memo.captured_at}  {memo.text[:80]}\n"
        )


def _memo_to_dict(*, memo: Memo) -> dict[str, object]:
    return asdict(memo)
