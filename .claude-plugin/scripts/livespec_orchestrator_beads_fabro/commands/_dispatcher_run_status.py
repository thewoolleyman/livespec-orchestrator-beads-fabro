"""Run and pull-request status parsers for the Dispatcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_pr_open_diff import pr_diff_size_of
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "PrView",
    "parse_pr_view",
]


@dataclass(frozen=True, kw_only=True)
class PrView:
    """The slice of `gh pr view --json` the engine routes on.

    `diff_size` is the branch-versus-base churn (plan slice S4, `bd-ib-tbgxm4`).
    It is NOT routed on; it rides here because the engine already takes this
    view at the moment it confirms the pull request, which is the moment the
    repaired size proxy has to be recorded. A separate probe would be a second
    forge round trip whose answer could differ from the view beside it, for the
    same pull request, with nothing in the record saying which was read.

    `None` means the forge reported neither field or only one of them — absent,
    deliberately distinct from a pull request whose churn is genuinely zero.
    """

    number: int
    state: str
    auto_merge_armed: bool
    merge_state_status: str
    merge_sha: str | None
    terminal_required_check_failures: tuple[str, ...]
    diff_size: int | None = None
    head_ref_name: str | None = None
    head_ref_oid: str | None = None
    head_repository: str | None = None

    def matches_publication(self, *, branch: str, head: str, repository: str) -> bool:
        """Whether this is a live or merged publication of the checkpoint head."""
        return (
            self.state in {"OPEN", "MERGED"}
            and self.head_ref_name == branch
            and self.head_ref_oid == head
            and self.head_repository == repository
        )


_TERMINAL_CHECK_CONCLUSIONS = frozenset(
    {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
    }
)


def parse_pr_view(*, stdout: str) -> PrView | None:
    """Parse `gh pr view --json` output; None when the shape is unusable."""
    parsed_raw = parse_json(text=stdout)
    if isinstance(parsed_raw, JsonParseFailure):
        return None
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, Any]", parsed_raw)
    number_raw: object = parsed.get("number")
    if not isinstance(number_raw, int):
        return None
    terminal_failures = tuple(
        name
        for item in _status_check_rollup_items(rollup_raw=parsed.get("statusCheckRollup"))
        if isinstance(item, dict)
        for name in [_terminal_required_check_failure_name(item=cast("dict[str, Any]", item))]
        if name is not None
    )
    state_raw: object = parsed.get("state")
    merge_state_raw: object = parsed.get("mergeStateStatus")
    return PrView(
        number=number_raw,
        state=state_raw if isinstance(state_raw, str) else "UNKNOWN",
        auto_merge_armed=parsed.get("autoMergeRequest") is not None,
        merge_state_status=merge_state_raw if isinstance(merge_state_raw, str) else "UNKNOWN",
        merge_sha=_merge_sha_of(parsed=parsed),
        terminal_required_check_failures=terminal_failures,
        diff_size=pr_diff_size_of(payload=parsed),
        head_ref_name=_optional_string(value=parsed.get("headRefName")),
        head_ref_oid=_optional_string(value=parsed.get("headRefOid")),
        head_repository=_head_repository_of(parsed=parsed),
    )


def _optional_string(*, value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _head_repository_of(*, parsed: dict[str, Any]) -> str | None:
    repository_raw: object = parsed.get("headRepository")
    if not isinstance(repository_raw, dict):
        return None
    return _optional_string(value=cast("dict[str, Any]", repository_raw).get("nameWithOwner"))


def _status_check_rollup_items(*, rollup_raw: object) -> list[object]:
    if isinstance(rollup_raw, list):
        return cast("list[object]", rollup_raw)
    if not isinstance(rollup_raw, dict):
        return []
    rollup = cast("dict[str, Any]", rollup_raw)
    nodes_raw: object = rollup.get("nodes")
    if isinstance(nodes_raw, list):
        return cast("list[object]", nodes_raw)
    contexts_raw: object = rollup.get("contexts")
    if not isinstance(contexts_raw, dict):  # pragma: no cover - defensive malformed gh JSON
        return []
    context_nodes_raw: object = cast("dict[str, Any]", contexts_raw).get("nodes")
    if isinstance(context_nodes_raw, list):
        return cast("list[object]", context_nodes_raw)
    return []  # pragma: no cover - defensive malformed gh JSON


def _terminal_required_check_failure_name(*, item: dict[str, Any]) -> str | None:
    if item.get("required") is not True and item.get("isRequired") is not True:
        return None
    conclusion_raw: object = item.get("conclusion")
    if not isinstance(conclusion_raw, str):
        return None
    if conclusion_raw.lower() not in _TERMINAL_CHECK_CONCLUSIONS:
        return None
    name_raw: object = item.get("name", item.get("context"))
    return name_raw if isinstance(name_raw, str) and name_raw else "unknown"


def _merge_sha_of(*, parsed: dict[str, Any]) -> str | None:
    commit_raw: object = parsed.get("mergeCommit")
    if not isinstance(commit_raw, dict):
        return None
    commit = cast("dict[str, Any]", commit_raw)
    oid_raw: object = commit.get("oid")
    if isinstance(oid_raw, str) and oid_raw:
        return oid_raw
    return None
