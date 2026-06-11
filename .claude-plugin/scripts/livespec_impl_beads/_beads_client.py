"""BeadsClient seam — the backend abstraction the store layer talks to.

The store layer (`store.py`) never shells out to `bd` directly. Instead it
talks to a `BeadsClient` — a small protocol whose verbs cover exactly the
beads operations the store needs (list-all, show-one, children, create,
update, close, dep-add). Two implementations satisfy the protocol:

- `ShellBeadsClient` — shells out to the pinned `bd` binary (by absolute
  path, NEVER the mise shim) over the server-mode FLAGS connection and
  parses the `--json` stdout. The real-binary call sites carry
  `# pragma: no cover` (they cannot run hermetically without a live
  `dolt-server`), but ALL parsing / argv-construction logic lives OUTSIDE
  the pragma so the hermetic test tier covers it.

- `FakeBeadsClient` — a pure in-memory implementation (a dict of issue
  records keyed by id) with the SAME interface. It is PRODUCT code, not
  test scaffolding: it is the runtime backend when no live connection is
  configured (`StoreConfig.fake is True`) AND the backend the hermetic CI
  tier runs against. It is fully coverable.

Selection mechanism (documented in CLAUDE.md): `make_beads_client(*, config)`
picks the implementation from `StoreConfig.fake` — a boolean carried on the
connection descriptor. The descriptor's `fake` is itself resolved from the
`.livespec.jsonc` connection block overlaid by the `LIVESPEC_BEADS_FAKE`
environment variable (see `commands/_config.py`). When `fake` is True the
factory returns a process-singleton `FakeBeadsClient` so repeated
`read`/`append` calls within one wrapper invocation share the same
in-memory tenant; when False it returns a `ShellBeadsClient`.

All beads records cross this seam as plain `dict[str, object]` shaped like
the `bd ... --json` issue object: `id`, `title`, `description`, `status`,
`priority`, `issue_type`, `assignee`, `created_at`, `close_reason`,
`spec_id`, `labels` (list[str]), `metadata` (a JSON object), and
`dependencies` (a list of `{depends_on_id, type}` edge records). The store
layer owns the field map from this dict onto `WorkItem` / `Memo`.

Per SPECIFICATION/constraints.md §"Inherited from livespec" (the
Result-vs-bugs split), EXPECTED backend failures raise the typed
`Beads*Error` classes from `errors.py`; genuine bugs propagate as raised
built-in exceptions.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, cast

from livespec_impl_beads.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from livespec_impl_beads.types import StoreConfig

__all__: list[str] = [
    "BeadsClient",
    "BeadsRecord",
    "DependencyEdge",
    "FakeBeadsClient",
    "IssueDraft",
    "ShellBeadsClient",
    "make_beads_client",
]

# A beads issue as it crosses the seam: the parsed `bd ... --json` object.
BeadsRecord = dict[str, Any]
# A dependency edge: `{"depends_on_id": <id>, "type": <blocks|supersedes|parent-child>}`.
DependencyEdge = dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class IssueDraft:
    """The full field set for a `bd create` — bundled so the create verb
    takes one keyword argument instead of eleven (the family `max-args`
    rule caps a `def` at six). Every field maps onto a `bd create` flag
    per the FIELD MAP (see `_build_create_argv`).
    """

    issue_id: str
    issue_type: str
    title: str
    description: str
    priority: int
    assignee: str | None
    created_at: str
    labels: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    spec_id: str | None = None
    parent_id: str | None = None


class BeadsClient(Protocol):
    """The backend verbs the store layer needs from `bd`.

    Reads return parsed records (issue dicts). Writes mutate the tenant
    and return nothing (or, for `create`, the created id). Every method
    is keyword-only to match the family's keyword-only-args rule.
    """

    def list_issues(self) -> list[BeadsRecord]:
        """Return every issue in the tenant (`bd list --status all --json`)."""
        ...

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        """Return one issue by id (`bd show <id> --json`)."""
        ...

    def children(self, *, parent_id: str) -> list[BeadsRecord]:
        """Return the parent-child children of an issue (`bd children <id>`)."""
        ...

    def exists(self, *, issue_id: str) -> bool:
        """Return True iff an issue with this id is present in the tenant."""
        ...

    def create_issue(self, *, draft: IssueDraft) -> str:
        """Create an issue with an operator-supplied id; return the id."""
        ...

    def update_issue(
        self,
        *,
        issue_id: str,
        status: str | None = None,
        parent_id: str | None = None,
        add_labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mutate an existing issue's status / parent / labels / metadata."""
        ...

    def close_issue(self, *, issue_id: str, reason: str | None) -> None:
        """Close an issue in place (`bd close <id> --reason`)."""
        ...

    def add_dependency(self, *, from_id: str, to_id: str, edge_type: str) -> None:
        """Add a dependency edge (`bd dep add <FROM> <TO> --type <edge_type>`)."""
        ...


# Dependency-edge type constants (the `--type` values `bd dep add` accepts).
EDGE_BLOCKS = "blocks"
EDGE_SUPERSEDES = "supersedes"
EDGE_PARENT_CHILD = "parent-child"

# `["update", <id>]` is the bare verb+id with no mutating flags; an argv of
# this length carries nothing to update, so the shell client skips the call.
_UPDATE_ARGV_NO_OP_LENGTH = 2


class FakeBeadsClient:
    """Pure in-memory `BeadsClient` — runtime fallback + hermetic test backend.

    Holds a dict of issue records keyed by id. Each record is the same
    shape a parsed `bd ... --json` issue object has, so the store layer's
    field map works identically against the fake and the shell backend.
    Writes mutate the in-memory dict; reads return copies so callers
    cannot accidentally mutate the backing store.
    """

    def __init__(self) -> None:
        self._issues: dict[str, BeadsRecord] = {}

    def list_issues(self) -> list[BeadsRecord]:
        return [dict(record) for record in self._issues.values()]

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        record = self._issues.get(issue_id)
        if record is None:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="issue not present in the in-memory tenant",
            )
        return dict(record)

    def children(self, *, parent_id: str) -> list[BeadsRecord]:
        return [
            dict(record) for record in self._issues.values() if record.get("parent_id") == parent_id
        ]

    def exists(self, *, issue_id: str) -> bool:
        return issue_id in self._issues

    def create_issue(self, *, draft: IssueDraft) -> str:
        record: BeadsRecord = {
            "id": draft.issue_id,
            "issue_type": draft.issue_type,
            "title": draft.title,
            "description": draft.description,
            "priority": draft.priority,
            "assignee": draft.assignee,
            "created_at": draft.created_at,
            "status": "open",
            "close_reason": None,
            "labels": list(draft.labels),
            "metadata": dict(draft.metadata),
            "spec_id": draft.spec_id,
            "parent_id": draft.parent_id,
            "dependencies": [],
        }
        self._issues[draft.issue_id] = record
        return draft.issue_id

    def update_issue(
        self,
        *,
        issue_id: str,
        status: str | None = None,
        parent_id: str | None = None,
        add_labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record = self._issues.get(issue_id)
        if record is None:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="cannot update an issue that is not present in the tenant",
            )
        if status is not None:
            record["status"] = status
        if parent_id is not None:
            record["parent_id"] = parent_id
        if add_labels is not None:
            existing = cast("list[str]", record.get("labels", []))
            merged = list(existing)
            for label in add_labels:
                if label not in merged:
                    merged.append(label)
            record["labels"] = merged
        if metadata is not None:
            record["metadata"] = dict(metadata)

    def close_issue(self, *, issue_id: str, reason: str | None) -> None:
        record = self._issues.get(issue_id)
        if record is None:
            raise BeadsMappingError(
                record_id=issue_id,
                detail="cannot close an issue that is not present in the tenant",
            )
        record["status"] = "closed"
        record["close_reason"] = reason

    def add_dependency(self, *, from_id: str, to_id: str, edge_type: str) -> None:
        record = self._issues.get(from_id)
        if record is None:
            raise BeadsMappingError(
                record_id=from_id,
                detail="cannot add a dependency from an issue not present in the tenant",
            )
        edges = cast("list[DependencyEdge]", record.setdefault("dependencies", []))
        edge: DependencyEdge = {"depends_on_id": to_id, "type": edge_type}
        if edge not in edges:
            edges.append(edge)


class ShellBeadsClient:
    """`BeadsClient` that shells out to the pinned `bd` binary in server mode.

    The connection surface (host / port / socket / user / database / prefix)
    and the binary path come from `StoreConfig`; the tenant password comes
    from the `BEADS_DOLT_PASSWORD` environment variable at call time and is
    never stored on the descriptor (see `commands/_config.py`).

    Argv construction and `--json` parsing are pure and fully covered; the
    single `subprocess.run` call site carries `# pragma: no cover` because
    it cannot execute hermetically without a live `dolt-server`.
    """

    def __init__(self, *, config: StoreConfig) -> None:
        self._config = config

    def _build_argv(self, *, verb_args: list[str]) -> list[str]:
        """Compose the full per-command `bd` argv: `<bd_path> <verb_args...>`.

        Per the verified v1.0.5 connection model (beads-schema-mapping.md
        §2.1), only `bd`'s `init` verb accepts the `--server*` connection flags.
        Every per-command verb (`create`/`list`/`show`/`update`/`dep`)
        takes its connection from `.beads/config.yaml` (written by
        `bd`'s `init` verb) plus the tenant password in the `BEADS_DOLT_PASSWORD`
        environment variable, and REJECTS `--server*` as unknown flags.
        So per-command argv carries NO connection flags — just the pinned
        bd path and the verb args.
        """
        return [self._config.bd_path, *verb_args]

    def _run_json(self, *, verb_args: list[str]) -> Any:
        """Run a read verb and parse its `--json` stdout into a Python value."""
        completed = self._invoke(argv=self._build_argv(verb_args=verb_args))
        return self._parse_json(stdout=completed.stdout, argv_repr=" ".join(verb_args))

    def _run_void(self, *, verb_args: list[str]) -> None:
        """Run a write verb whose stdout we do not parse."""
        _ = self._invoke(argv=self._build_argv(verb_args=verb_args))

    def _invoke(self, *, argv: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            # argv[0] is the pinned bd binary's absolute path from config;
            # the verb/flag args are bridge-constructed (never raw user
            # input). Shelling out to bd is the documented store backend.
            completed = subprocess.run(  # noqa: S603  # pragma: no cover
                argv,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:  # pragma: no cover
            raise BeadsConnectionError(
                detail=f"bd binary not found at {self._config.bd_path}"
            ) from exc
        self._raise_for_status(completed=completed, argv=argv)  # pragma: no cover
        return completed  # pragma: no cover

    def _raise_for_status(
        self,
        *,
        completed: subprocess.CompletedProcess[str],
        argv: list[str],
    ) -> None:
        """Map a nonzero `bd` exit onto the typed expected-error surface.

        Pure (takes the completed process), so it is covered by the
        hermetic tier even though `_invoke`'s subprocess call is not.
        """
        if completed.returncode == 0:
            return
        stderr = completed.stderr or ""
        command = " ".join(argv)
        lowered = stderr.lower()
        if "connection refused" in lowered or "can't connect" in lowered:
            raise BeadsConnectionError(detail=stderr.strip())
        if "unknown database" in lowered or "does not exist" in lowered:
            raise BeadsTenantMissingError(tenant=self._config.database)
        raise BeadsCommandError(
            command=command,
            exit_code=completed.returncode,
            stderr=stderr,
        )

    def _parse_json(self, *, stdout: str, argv_repr: str) -> Any:
        """Parse `bd --json` stdout; an unparsable body is an EXPECTED error."""
        text = stdout.strip()
        if text == "":
            return []
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise BeadsCommandError(
                command=argv_repr,
                exit_code=0,
                stderr=f"could not parse bd --json output: {exc}",
            ) from exc

    def list_issues(self) -> list[BeadsRecord]:
        parsed = self._run_json(verb_args=["list", "--status", "all", "--limit", "0", "--json"])
        return _coerce_record_list(parsed=parsed)

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        parsed = self._run_json(verb_args=["show", issue_id, "--json"])
        # bd v1.0.5 `bd show <id> --json` returns a JSON ARRAY containing
        # the single matched issue (not a bare object); take the first
        # element. An empty array means no such issue.
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

    def children(self, *, parent_id: str) -> list[BeadsRecord]:
        parsed = self._run_json(verb_args=["children", parent_id, "--json"])
        return _coerce_record_list(parsed=parsed)

    def exists(self, *, issue_id: str) -> bool:
        """Return True iff `issue_id` is present (scans the list-all read).

        Implemented over `list_issues` rather than `bd show` so a
        missing id is a clean boolean rather than a nonzero-exit error.
        """
        ids = {record.get("id") for record in self.list_issues()}
        return issue_id in ids

    def create_issue(self, *, draft: IssueDraft) -> str:
        self._run_void(verb_args=_build_create_argv(draft=draft))
        return draft.issue_id

    def update_issue(
        self,
        *,
        issue_id: str,
        status: str | None = None,
        parent_id: str | None = None,
        add_labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        verb_args = _build_update_argv(
            issue_id=issue_id,
            status=status,
            parent_id=parent_id,
            add_labels=add_labels,
            metadata=metadata,
        )
        if len(verb_args) <= _UPDATE_ARGV_NO_OP_LENGTH:
            return
        self._run_void(verb_args=verb_args)

    def close_issue(self, *, issue_id: str, reason: str | None) -> None:
        verb_args: list[str] = ["close", issue_id]
        if reason is not None:
            verb_args.extend(["--reason", reason])
        self._run_void(verb_args=verb_args)

    def add_dependency(self, *, from_id: str, to_id: str, edge_type: str) -> None:
        self._run_void(
            verb_args=["dep", "add", from_id, to_id, "--type", edge_type],
        )


def _coerce_record_list(*, parsed: Any) -> list[BeadsRecord]:
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


def _build_create_argv(*, draft: IssueDraft) -> list[str]:
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


def _build_update_argv(
    *,
    issue_id: str,
    status: str | None,
    parent_id: str | None,
    add_labels: list[str] | None,
    metadata: dict[str, Any] | None,
) -> list[str]:
    """Build the `bd update <id> ...` verb argv (pure; fully covered).

    bd v1.0.5 `bd update` has no bare `--label`; label ADDITIONS use the
    repeatable `--add-label` flag (the in-place close path only ever adds
    labels, e.g. `resolution:completed`), so each label is emitted as a
    `--add-label <label>` pair.
    """
    argv: list[str] = ["update", issue_id]
    if status is not None:
        argv.extend(["--status", status])
    if parent_id is not None:
        argv.extend(["--parent", parent_id])
    if add_labels is not None:
        for label in add_labels:
            argv.extend(["--add-label", label])
    if metadata is not None:
        argv.extend(["--metadata", json.dumps(metadata, separators=(",", ":"), sort_keys=True)])
    return argv


# Process-scoped holder for the fake tenant. A single-element list rather
# than a bare module global so the factory can rebind the contained value
# without a `global` statement (PLW0603).
_FAKE_HOLDER: list[FakeBeadsClient] = []


def make_beads_client(*, config: StoreConfig) -> BeadsClient:
    """Select the backend from the connection descriptor's `fake` toggle.

    When `config.fake` is True, return a PROCESS-SINGLETON
    `FakeBeadsClient` so that repeated store calls within one wrapper
    invocation (e.g. an `append_work_item` followed by a
    `read_work_items`) observe the same in-memory tenant. When False,
    return a fresh `ShellBeadsClient` bound to the connection descriptor.

    The singleton is intentionally process-scoped: each CLI wrapper
    invocation is a fresh process, so the fake tenant is empty at the
    start of every real command and only accumulates within that one
    invocation. Tests that need isolation call `reset_fake_singleton`.
    """
    if config.fake:
        if not _FAKE_HOLDER:
            _FAKE_HOLDER.append(FakeBeadsClient())
        return _FAKE_HOLDER[0]
    return ShellBeadsClient(config=config)


def reset_fake_singleton() -> None:
    """Drop the process-singleton fake tenant (test-isolation hook)."""
    _FAKE_HOLDER.clear()
