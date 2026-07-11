"""BeadsClient protocol, shell backend, and backend factory."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from livespec_orchestrator_beads_fabro._beads_client_argv import (
    build_create_argv,
    build_update_argv,
    coerce_comment_list,
    coerce_issue_record,
    coerce_record_list,
    parse_json_output,
)
from livespec_orchestrator_beads_fabro._beads_client_fake import (
    FakeBeadsClient,
    fake_singleton,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._beads_client_shell import (
    invoke,
    raise_for_status,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "BeadsClient",
    "BeadsRecord",
    "DependencyEdge",
    "FakeBeadsClient",
    "IssueDraft",
    "ShellBeadsClient",
    "make_beads_client",
    "reset_fake_singleton",
]

# A beads issue as it crosses the seam: the parsed `bd ... --json` object.
BeadsRecord = dict[str, Any]
# A dependency edge: `{"depends_on_id": <id>, "type": <blocks|supersedes|parent-child>}`.
DependencyEdge = dict[str, Any]


# The native beads `--priority` column value the bridge writes for a
# WorkItem-sourced create. `rank` (in `metadata.rank`) is the sole logical
# ordering authority now; the native int column is decorative (no longer
# read into the materialized record), so it defaults to a neutral mid value
# and is only set explicitly where a beads-native priority is meaningful
# (e.g. the reflector's severity → priority map).
_DEFAULT_NATIVE_PRIORITY = 2

# The five custom livespec statuses a tenant MUST register before any issue
# can carry one, in the `bd config set status.custom` CSV form (verified
# against the pinned beads source): `name[:category]`, where the absent
# category is `unspecified`. `ready` is the sole `active`-category status so
# native `bd ready` surfaces the admission-eligible set.
_STATUS_CUSTOM = "backlog,pending-approval,ready:active,active:wip,acceptance:wip"


@dataclass(frozen=True, kw_only=True)
class IssueDraft:
    """The full field set for a `bd create`."""

    issue_id: str
    issue_type: str
    title: str
    description: str
    assignee: str | None
    created_at: str
    priority: int = _DEFAULT_NATIVE_PRIORITY
    labels: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    spec_id: str | None = None
    parent_id: str | None = None


class BeadsClient(Protocol):
    """The backend verbs the store layer needs from `bd`."""

    def list_issues(self) -> list[BeadsRecord]:
        """Return every issue in the tenant (`bd list --status all --json`)."""
        ...

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        """Return one issue by id (`bd show <id> --json`)."""
        ...

    def list_comments(self, *, issue_id: str) -> list[BeadsRecord]:
        """Return an issue's comments (`bd comments <id> --json`).

        `bd show` does NOT carry comment bodies (only `comment_count`),
        so comment reads need this dedicated verb.
        """
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

    def update_issue(  # noqa: PLR0913 — kw-only partial-update verb; each field is an independent optional mutation.
        self,
        *,
        issue_id: str,
        status: str | None = None,
        assignee: str | None = None,
        parent_id: str | None = None,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mutate an existing issue's status / assignee / parent / labels / metadata.

        `assignee` maps onto `bd update --assignee` — the seam the admission
        valve uses to set the doer when it transitions a ready item to
        `active`. `remove_labels` maps onto `bd update --remove-label`
        (repeatable); it is the seam used by lifecycle routing to clear retired labels and
        policy labels when an item changes state. Removing a
        label the issue does not carry is a no-op (bd is idempotent here).
        """
        ...

    def close_issue(self, *, issue_id: str, reason: str | None) -> None:
        """Close an issue in place (`bd close <id> --reason`)."""
        ...

    def add_dependency(self, *, from_id: str, to_id: str, edge_type: str) -> None:
        """Add a dependency edge (`bd dep add <FROM> <TO> --type <edge_type>`)."""
        ...

    def add_comment(self, *, issue_id: str, body: str) -> None:
        """Append a comment to an issue (`bd comment <id> <body>`)."""
        ...

    def register_custom_statuses(self) -> None:
        """Register the five livespec custom statuses on the tenant.

        Per-tenant provisioning that MUST run before any issue can carry a
        custom status (`backlog`/`pending-approval`/`ready`/`active`/
        `acceptance`); the closure path reuses beads' built-in `closed`.
        Idempotent. A no-op against the in-memory fake (which stores
        whatever status string it is handed).
        """
        ...


# Dependency-edge type constants (the `--type` values `bd dep add` accepts).
EDGE_BLOCKS = "blocks"
EDGE_SUPERSEDES = "supersedes"
EDGE_PARENT_CHILD = "parent-child"

# `["update", <id>]` is the bare verb+id with no mutating flags; an argv of
# this length carries nothing to update, so the shell client skips the call.
_UPDATE_ARGV_NO_OP_LENGTH = 2


class ShellBeadsClient:
    """`BeadsClient` that shells out to the pinned `bd` binary."""

    def __init__(self, *, config: StoreConfig) -> None:
        self._config = config

    def _build_argv(self, *, verb_args: list[str]) -> list[str]:
        """Compose `<bd_path> <verb_args...>` with no connection flags."""
        return [self._config.bd_path, *verb_args]

    def _run_json(self, *, verb_args: list[str]) -> Any:
        """Run a read verb and parse its `--json` stdout into a Python value."""
        completed = self._invoke(argv=self._build_argv(verb_args=verb_args))
        return self._parse_json(stdout=completed.stdout, argv_repr=" ".join(verb_args))

    def _run_void(self, *, verb_args: list[str]) -> None:
        """Run a write verb whose stdout we do not parse."""
        _ = self._invoke(argv=self._build_argv(verb_args=verb_args))

    def _invoke(self, *, argv: list[str]) -> subprocess.CompletedProcess[str]:
        return invoke(config=self._config, argv=argv)

    def _raise_for_status(
        self,
        *,
        completed: subprocess.CompletedProcess[str],
        argv: list[str],
    ) -> None:
        """Map a nonzero `bd` exit onto the typed expected-error surface."""
        raise_for_status(completed=completed, argv=argv, tenant=self._config.database)

    def _parse_json(self, *, stdout: str, argv_repr: str) -> Any:
        """Parse `bd --json` stdout."""
        return parse_json_output(stdout=stdout, argv_repr=argv_repr)

    def list_issues(self) -> list[BeadsRecord]:
        parsed = self._run_json(verb_args=["list", "--status", "all", "--limit", "0", "--json"])
        return coerce_record_list(parsed=parsed)

    def show_issue(self, *, issue_id: str) -> BeadsRecord:
        parsed = self._run_json(verb_args=["show", issue_id, "--json"])
        return coerce_issue_record(parsed=parsed, issue_id=issue_id)

    def list_comments(self, *, issue_id: str) -> list[BeadsRecord]:
        """Return an issue's comments (`bd comments <id> --json`)."""
        parsed = self._run_json(verb_args=["comments", issue_id, "--json"])
        return coerce_comment_list(parsed=parsed, issue_id=issue_id)

    def children(self, *, parent_id: str) -> list[BeadsRecord]:
        parsed = self._run_json(verb_args=["children", parent_id, "--json"])
        return coerce_record_list(parsed=parsed)

    def exists(self, *, issue_id: str) -> bool:
        """Return True iff `issue_id` is present (scans the list-all read).

        Implemented over `list_issues` rather than `bd show` so a
        missing id is a clean boolean rather than a nonzero-exit error.
        """
        ids = {record.get("id") for record in self.list_issues()}
        return issue_id in ids

    def create_issue(self, *, draft: IssueDraft) -> str:
        self._run_void(verb_args=build_create_argv(draft=draft))
        return draft.issue_id

    def update_issue(  # noqa: PLR0913 — kw-only partial-update verb; each field is an independent optional mutation.
        self,
        *,
        issue_id: str,
        status: str | None = None,
        assignee: str | None = None,
        parent_id: str | None = None,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        verb_args = build_update_argv(
            issue_id=issue_id,
            status=status,
            assignee=assignee,
            parent_id=parent_id,
            add_labels=add_labels,
            remove_labels=remove_labels,
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

    def add_comment(self, *, issue_id: str, body: str) -> None:
        """Append a comment via `bd comment <id> <body>`."""
        self._run_void(verb_args=["comment", issue_id, body])

    def register_custom_statuses(self) -> None:
        """Register the five custom statuses via `bd config set status.custom`.

        Idempotent per-tenant provisioning. The `status.custom` value is the
        verified CSV form (`name[:category]`); `bd` upserts the configured
        set, so re-running is a safe no-op.
        """
        self._run_void(verb_args=["config", "set", "status.custom", _STATUS_CUSTOM])


def make_beads_client(*, config: StoreConfig) -> BeadsClient:
    """Select the backend from the connection descriptor's `fake` toggle."""
    if config.fake:
        return fake_singleton()
    return ShellBeadsClient(config=config)
