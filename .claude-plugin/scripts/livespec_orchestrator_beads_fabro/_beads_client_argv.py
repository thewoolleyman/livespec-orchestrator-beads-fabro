"""Pure argv and record builders for the beads client."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError, BeadsMappingError

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord, IssueDraft

__all__: list[str] = [
    "build_create_argv",
    "build_update_argv",
    "coerce_comment_list",
    "coerce_issue_record",
    "coerce_record_list",
    "parse_json_output",
]


def parse_json_output(*, stdout: str, argv_repr: str) -> Any:
    """Parse `bd --json` stdout; an unparsable body is an expected error."""
    text = stdout.strip()
    if text == "":
        return []
    parsed = parse_json(text=text)
    if isinstance(parsed, JsonParseFailure):
        exc = parsed.error
        raise BeadsCommandError(
            command=argv_repr,
            exit_code=0,
            stderr=f"could not parse bd --json output: {exc}",
        ) from exc
    return parsed


def coerce_issue_record(*, parsed: Any, issue_id: str) -> BeadsRecord:
    """Coerce `bd show <id> --json` output into one issue record."""
    if not isinstance(parsed, list):
        raise BeadsMappingError(
            record_id=issue_id,
            detail="bd show --json did not return a JSON array",
        )
    records = cast("list[Any]", parsed)
    if not records:
        raise BeadsMappingError(
            record_id=issue_id,
            detail="bd show --json returned an empty array (no such issue)",
        )
    first = records[0]
    if not isinstance(first, dict):
        raise BeadsMappingError(
            record_id=issue_id,
            detail="bd show --json array element was not a JSON object",
        )
    return cast("BeadsRecord", first)


def coerce_comment_list(*, parsed: Any, issue_id: str) -> list[BeadsRecord]:
    """Coerce `bd comments <id> --json` output into comment records."""
    if not isinstance(parsed, list):
        raise BeadsMappingError(
            record_id=issue_id,
            detail="bd comments --json did not return a JSON array",
        )
    records = cast("list[Any]", parsed)
    return [cast("BeadsRecord", record) for record in records if isinstance(record, dict)]


def coerce_record_list(*, parsed: Any) -> list[BeadsRecord]:
    """Coerce a parsed `bd --json` body into a list of issue dicts.

    `bd list --json` may return a bare array, or an envelope object with
    an `issues` key. Both shapes are accepted; anything else is a bug in
    the assumed bd contract and raises.
    """
    if isinstance(parsed, list):
        records = cast("list[Any]", parsed)
        return [cast("BeadsRecord", record) for record in records if isinstance(record, dict)]
    if isinstance(parsed, dict):
        envelope = cast("dict[str, Any]", parsed)
        issues_raw = envelope.get("issues")
        if isinstance(issues_raw, list):
            issues = cast("list[Any]", issues_raw)
            return [cast("BeadsRecord", record) for record in issues if isinstance(record, dict)]
    raise BeadsMappingError(
        record_id="<list>",
        detail="bd list --json returned neither an array nor an {issues:[...]} envelope",
    )


def build_create_argv(*, draft: IssueDraft) -> list[str]:
    """Build the `bd create ...` verb argv (pure; fully covered).

    Per the FIELD MAP: operator-supplied `--id`, native `--type` /
    `--title` / `--description` / `--priority` / `--assignee` /
    `--spec-id` / `--parent`, every label as a repeated `--label`, and
    the metadata JSON object as a single `--metadata` argument carrying
    compact JSON.

    `bd create` in v1.0.5 has NO `--created-at` flag — server-assigned
    creation timestamps are authoritative and timestamp preservation is
    a `bd import`-only feature — so `draft.created_at` is not emitted
    here (it is still carried on the draft for the FakeBeadsClient and
    the import path).
    """
    argv: list[str] = [
        "create",
        "--id",
        draft.issue_id,
        "--type",
        draft.issue_type,
        "--title",
        draft.title,
        "--description",
        draft.description,
        "--priority",
        str(draft.priority),
    ]
    if draft.assignee is not None:
        argv.extend(["--assignee", draft.assignee])
    if draft.spec_id is not None:
        argv.extend(["--spec-id", draft.spec_id])
    if draft.parent_id is not None:
        argv.extend(["--parent", draft.parent_id])
    for label in draft.labels:
        argv.extend(["--label", label])
    argv.extend(["--metadata", json.dumps(draft.metadata, separators=(",", ":"), sort_keys=True)])
    return argv


def build_update_argv(  # noqa: PLR0913 — kw-only argv builder mirroring update_issue's optional fields.
    *,
    issue_id: str,
    status: str | None,
    parent_id: str | None,
    add_labels: list[str] | None,
    metadata: dict[str, Any] | None,
    remove_labels: list[str] | None = None,
    assignee: str | None = None,
) -> list[str]:
    """Build the `bd update <id> ...` verb argv (pure; fully covered).

    bd v1.0.5 `bd update` has no bare `--label`; label ADDITIONS use the
    repeatable `--add-label` flag (the in-place close path only ever adds
    labels, e.g. `resolution:completed`), so each label is emitted as a
    `--add-label <label>` pair. Label REMOVALS use the symmetric repeatable
    `--remove-label` flag (the lifecycle router clears retired labels this way).
    `--assignee` sets the doer (the admission valve's `ready -> active`
    transition).
    """
    argv: list[str] = ["update", issue_id]
    if status is not None:
        argv.extend(["--status", status])
    if assignee is not None:
        argv.extend(["--assignee", assignee])
    if parent_id is not None:
        argv.extend(["--parent", parent_id])
    if add_labels is not None:
        for label in add_labels:
            argv.extend(["--add-label", label])
    if remove_labels is not None:
        for label in remove_labels:
            argv.extend(["--remove-label", label])
    if metadata is not None:
        argv.extend(["--metadata", json.dumps(metadata, separators=(",", ":"), sort_keys=True)])
    return argv
