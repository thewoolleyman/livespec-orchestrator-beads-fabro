"""Run attribution from a publication record, and the passed-over needs-human field."""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    PreservedWorkUnobservable,
    verified_preserved_seed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_records import (
    recovery_route_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_SEEDED,
    RecoverySeed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_run_age import (
    published_head_relation,
)

from tests.livespec_orchestrator_beads_fabro.commands._recovery_tip_reads import tip_read_answer

_HEAD = "b" * 40
_TERMINAL = "a" * 40


class _Origin:
    def __init__(self, *, extra: dict[str, str] | None = None) -> None:
        self.refs = {"refs/heads/needs-human/older": _TERMINAL, "refs/heads/feat/item": _HEAD}
        self.refs.update(extra or {})
        self.calls: list[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if (tip := tip_read_answer(argv=argv)) is not None:
            return tip
        wanted = argv[-1]
        listing = "".join(
            f"{commit}\t{ref}\n"
            for ref, commit in self.refs.items()
            if wanted == ref or (wanted.endswith("/*") and ref.startswith(wanted[:-1]))
        )
        return CommandResult(exit_code=0, stdout=listing, stderr="")


def _seed(
    *,
    origin: _Origin,
    records: tuple[dict[str, object], ...],
    publications: tuple[tuple[str, str], ...] = (),
) -> object:
    return verified_preserved_seed(
        runner=origin,
        repo=Path("/repo"),
        work_item_id="item",
        earlier_run_ids=("older",),
        journal_records=records,
        publications=publications,
    )


def test_a_publication_record_by_the_refs_own_run_leaves_the_ref_standing() -> None:
    seed = _seed(
        origin=_Origin(),
        records=({"work_item_id": "item", "run_id": "older"},),
        publications=((_HEAD, "older"),),
    )
    assert isinstance(seed, RecoverySeed)
    assert seed.commit_sha == _TERMINAL


def test_a_publication_record_by_a_later_journaled_run_outranks_the_earlier_ref() -> None:
    seed = _seed(
        origin=_Origin(),
        records=(
            {"work_item_id": "item", "run_id": "older"},
            {"work_item_id": "item", "run_id": "newer"},
        ),
        publications=((_HEAD, "newer"),),
    )
    assert isinstance(seed, RecoverySeed)
    assert seed.commit_sha == _HEAD


def test_a_publication_record_by_an_unjournaled_run_is_held() -> None:
    held = _seed(
        origin=_Origin(),
        records=({"work_item_id": "item", "run_id": "older"},),
        publications=((_HEAD, "newer"),),
    )
    assert isinstance(held, PreservedWorkUnobservable)
    assert "publishing-run-unobservable" in held.detail


def test_a_publication_record_for_another_head_attributes_nothing() -> None:
    assert (
        published_head_relation(
            records=({"run_id": "older"},),
            preserved_run_id="older",
            published_head=_HEAD,
            publications=(("c" * 40, "older"),),
        )
        is None
    )


def test_a_ref_named_under_another_items_run_does_not_hold_this_item() -> None:
    origin = _Origin(extra={"refs/heads/needs-human/foreign": "d" * 40})
    origin.refs.pop("refs/heads/needs-human/older")
    origin.refs.pop("refs/heads/feat/item")
    seed = _seed(
        origin=origin,
        records=(
            {"work_item_id": "other", "run_id": "foreign"},
            {"work_item_id": "other", "dispatch_id": "foreign-dispatch"},
            {"work_item_id": "item", "run_id": "older"},
        ),
    )
    assert not isinstance(seed, RecoverySeed)
    assert not any(call[1] == "show" for call in origin.calls)


def test_a_route_row_lists_each_passed_over_needs_human_ref_with_its_commit() -> None:
    seed = RecoverySeed(
        source_run_id="run",
        remote="origin",
        commit_sha=_TERMINAL,
        preservation_ref="refs/heads/needs-human/run",
        passed_over_needs_human=(("refs/heads/needs-human/old", _HEAD),),
    )
    row = recovery_route_record(work_item_id="item", route=ROUTE_SEEDED, seed=seed)
    assert row["passed_over_needs_human"] == [
        {"ref": "refs/heads/needs-human/old", "commit": _HEAD, "reason": "not-taken"}
    ]


def test_a_route_row_carries_an_empty_passed_over_list_when_nothing_was_taken() -> None:
    row = recovery_route_record(work_item_id="item", route=ROUTE_FRESH)
    assert row["passed_over_needs_human"] == []
