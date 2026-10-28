"""The pull requests an item's dispatch records name, projected into the sandbox.

`publish_draft` finishes a publication that already landed only when the merged
pull request is attributable to a dispatch of THIS item. A branch name alone does
not establish that: a name an earlier, unrelated item reused still finds a merged
pull request on the forge, and reading it as this item's would end the run as a
finished publication for work this item never published.

The journal is the Dispatcher's own record of which pull request each dispatch of
an item opened, so the numbers are read from it on the host and handed to the
node. A number sits at the top level of some records and inside the `outcome`
payload of others, depending on which build dispatched, so both shapes are read.

An item with no recorded pull request projects an EMPTY value, never an absent
one: the node reads empty as "nothing attributable", which keeps its existing
behaviour, while an absent variable would read the same way only by accident.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)

__all__: list[str] = [
    "DISPATCH_PULL_REQUESTS_ENV_VAR",
    "dispatch_pull_requests_env_line",
    "journaled_pull_request_numbers",
]

DISPATCH_PULL_REQUESTS_ENV_VAR = "LIVESPEC_DISPATCH_PULL_REQUESTS"


def journaled_pull_request_numbers(*, journal_path: Path, work_item_id: str) -> tuple[int, ...]:
    """Every pull request number the journal names for one item, ascending, once each."""
    found: set[int] = set()
    for record in read_journal_records(journal_path=journal_path):
        for payload in _payloads(record=record):
            number = payload.get("pr_number")
            if (
                payload.get("work_item_id") == work_item_id
                and isinstance(number, int)
                and not isinstance(number, bool)
            ):
                found.add(number)
    return tuple(sorted(found))


def dispatch_pull_requests_env_line(*, journal_path: Path, work_item_id: str) -> str:
    """The env-table line carrying the item's recorded pull request numbers."""
    numbers = journaled_pull_request_numbers(journal_path=journal_path, work_item_id=work_item_id)
    return f'{DISPATCH_PULL_REQUESTS_ENV_VAR} = "{" ".join(str(number) for number in numbers)}"\n'


def _payloads(*, record: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    nested = record.get("outcome")
    if isinstance(nested, dict):
        return (record, cast("Mapping[str, object]", nested))
    return (record,)
