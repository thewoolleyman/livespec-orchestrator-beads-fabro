"""Exception types for the expected-error surface of livespec-orchestrator-beads-fabro.

Per SPECIFICATION/constraints.md (the
Result-vs-bugs split), these are the EXPECTED errors the substrate or
external input can produce. Each carries enough context for the calling
skill to surface a clear narration to the user.

Unexpected errors (caller bugs, contract violations within the plugin's
own code) raise built-in exceptions (`ValueError`, `RuntimeError`, etc.)
and propagate to the outermost supervisor.

These classes are plain Exception subclasses (not @dataclass) because
dataclass-frozen with Exception inheritance hits CPython's __setattr__
discipline on self.args during super().__init__().
"""

from pathlib import Path

__all__: list[str] = [
    "BeadsCommandError",
    "BeadsConnectionError",
    "BeadsCredentialMissingError",
    "BeadsMappingError",
    "BeadsTenantMissingError",
    "ClaimWriteRefusedError",
    "ConnectionPrefixMissingError",
    "GroomApprovalRequiredError",
    "GroomDraftError",
    "GroomExitRefusedError",
    "GroomTargetNotBacklogError",
    "IncidentClosureRefusedError",
    "LivespecConfigUnreadableError",
    "MalformedRecordLineError",
    "SchemaViolationError",
    "SpecVersionNotFoundError",
    "StoreFileMissingError",
    "WorkItemNotFoundError",
]


class StoreFileMissingError(Exception):
    """The configured JSONL store file did not exist on disk."""

    def __init__(self, *, path: Path) -> None:
        super().__init__(f"JSONL store file not found: {path}")
        self.path = path


class MalformedRecordLineError(Exception):
    """A line in the JSONL store could not be parsed as a JSON object."""

    def __init__(
        self,
        *,
        path: Path,
        line_number: int,
        raw_line: str,
        detail: str,
    ) -> None:
        super().__init__(f"Malformed JSONL record at {path}:{line_number}: {detail}")
        self.path = path
        self.line_number = line_number
        self.raw_line = raw_line
        self.detail = detail


class SchemaViolationError(Exception):
    """A parsed record's keys or values violated the schema contract."""

    def __init__(self, *, path: Path, line_number: int, detail: str) -> None:
        super().__init__(f"Schema violation at {path}:{line_number}: {detail}")
        self.path = path
        self.line_number = line_number
        self.detail = detail


class SpecVersionNotFoundError(Exception):
    """A requested vNNN/ directory did not exist under <spec-root>/history/."""

    def __init__(self, *, spec_root: Path, version: int) -> None:
        history_dir = spec_root / "history"
        super().__init__(
            f"Specification history version v{version:03d} not found under {history_dir}"
        )
        self.spec_root = spec_root
        self.version = version


class BeadsConnectionError(Exception):
    """The plugin could not reach the configured beads/Dolt tenant server."""

    def __init__(self, *, detail: str) -> None:
        super().__init__(f"Could not connect to the beads tenant server: {detail}")
        self.detail = detail


class BeadsCommandError(Exception):
    """An invoked `bd` CLI command exited non-zero or produced unparsable output."""

    def __init__(
        self,
        *,
        command: str,
        exit_code: int,
        stderr: str,
    ) -> None:
        super().__init__(f"beads command failed (exit {exit_code}): {command}\n{stderr}")
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr


class BeadsTenantMissingError(Exception):
    """The configured per-repo tenant database was not present on the server."""

    def __init__(self, *, tenant: str) -> None:
        super().__init__(f"beads tenant database not found: {tenant}")
        self.tenant = tenant


class BeadsMappingError(Exception):
    """A beads record could not be mapped onto the work-item schema."""

    def __init__(self, *, record_id: str, detail: str) -> None:
        super().__init__(f"Could not map beads record {record_id}: {detail}")
        self.record_id = record_id
        self.detail = detail


class WorkItemNotFoundError(Exception):
    """The referenced work-item id was not present in the tenant.

    EXPECTED: a regroom transition can be requested against an id that was
    never filed (a typo, or an item closed and pruned between read and
    write). The caller surfaces this rather than the transition proceeding
    against a phantom id.
    """

    def __init__(self, *, item_id: str) -> None:
        super().__init__(f"work-item not found in the tenant: {item_id}")
        self.item_id = item_id


class ClaimWriteRefusedError(Exception):
    """A close the claim-token protocol refused, so the item was not closed.

    EXPECTED: with `dispatcher.claim_tokens` true, every operation that closes
    a work item first wins the item's current claim token (`contracts.md`,
    "Claim tokens"), and a writer that does not win writes nothing. `outcome`
    is the protocol's own name for why: `claim-changed` when another writer won
    the token, or changed the item, first. A caller surfaces `detail`, which
    says who refused, the outcome and what was not written.
    """

    def __init__(self, *, item_id: str, outcome: str, detail: str) -> None:
        super().__init__(detail)
        self.item_id = item_id
        self.outcome = outcome
        self.detail = detail


class IncidentClosureRefusedError(Exception):
    """A close refused because the item is an incident whose final normal proof is owed.

    EXPECTED: `contracts.md`, "Expedited incident lifecycle" forbids any close
    path from discharging an incident from its expedited merge alone. The item
    closes only once its retained chain records `closed`. `outstanding` names
    every obligation still holding it open, and nothing was written.
    """

    def __init__(self, *, item_id: str, outstanding: tuple[str, ...], detail: str) -> None:
        super().__init__(detail)
        self.item_id = item_id
        self.outstanding = outstanding
        self.detail = detail


class GroomExitRefusedError(Exception):
    """A backlog groom exit was refused because no replacement slices were filed.

    EXPECTED: the groom contract is that a backlog decomposition target is
    disposed only after approved replacement slices are filed. An exit attempt
    that names no replacement slice is refused so the original backlog item is
    never silently dropped.
    """

    def __init__(self, *, item_id: str, detail: str) -> None:
        super().__init__(f"refusing to regroom-out backlog item {item_id}: {detail}")
        self.item_id = item_id
        self.detail = detail


class GroomTargetNotBacklogError(Exception):
    """The `groom` front-end was pointed at an item not in backlog.

    EXPECTED: grooming is the agent-drafts / human-approves surface for a
    backlog item needing decomposition. Pointing `groom` at a `ready`, closed,
    or already-groomed item is an expected misuse the front-end surfaces rather
    than drafting a decomposition for an item that does not need one.
    """

    def __init__(self, *, item_id: str) -> None:
        super().__init__(f"groom target is not in backlog: {item_id}")
        self.item_id = item_id


class GroomApprovalRequiredError(Exception):
    """An approved-slice filing arrived with no attributable approval record.

    EXPECTED: the filing seam performs a maintainer-tier mutation — it files
    replacement slices and closes the original — so the ratified groom-cut
    contract requires an approval record naming the approver identity and how
    the approval was obtained. A call carrying none is refused BEFORE anything
    is filed, rather than proceeding on the calling agent's say-so and leaving
    a ledger in which an unapproved cut is indistinguishable from an approved
    one.
    """

    def __init__(self, *, detail: str) -> None:
        super().__init__(f"refusing to file approved groom slices: {detail}")
        self.detail = detail


class GroomDraftError(Exception):
    """An approved groom draft was malformed and could not be filed.

    EXPECTED: the maintainer authors the cut, so an inconsistent draft
    (e.g. a slice that depends on a handle naming no earlier factory slice
    in the same draft) is an authoring error the front-end surfaces for a
    re-draft rather than filing a dangling dependency edge.
    """

    def __init__(self, *, detail: str) -> None:
        super().__init__(f"invalid groom draft: {detail}")
        self.detail = detail


_CONNECTION_PREFIX_MISSING_MESSAGE = (
    "connection.prefix is required: it is bd's server-stored issue-ID "
    "create-prefix (e.g. `bd-ib`) and may differ from the tenant DB name "
    "— set it explicitly in `.livespec.jsonc` `connection.prefix`."
)


class ConnectionPrefixMissingError(Exception):
    """The `.livespec.jsonc` connection block omitted the required `prefix`.

    EXPECTED: `connection.prefix` is bd's server-stored issue-ID
    create-prefix (e.g. `bd-ib`) and is DECOUPLED from the tenant DB name —
    it MAY differ from it. The loader therefore refuses to default it to the
    tenant: an unset/empty prefix would mint tenant-named ids the server
    rejects. The maintainer surfaces this and sets `connection.prefix`
    explicitly rather than the loader silently guessing.
    """

    def __init__(self) -> None:
        super().__init__(_CONNECTION_PREFIX_MISSING_MESSAGE)


_CONFIG_UNREADABLE_MESSAGE_TEMPLATE = (
    "`.livespec.jsonc` could not be read as a configuration object: {detail}. "
    "Fix the file; the loader will not fall back to defaults for a config that "
    "is present and wrong."
)


class LivespecConfigUnreadableError(Exception):
    """`.livespec.jsonc` EXISTS but does not parse, or its root is not an object.

    EXPECTED: the operator's configuration is wrong — a stray comma, a
    truncated write, a non-object root. It is DISTINCT from the file being
    ABSENT, which is an answer the loader serves from documented defaults.

    ⛔ IT EXISTS BECAUSE THE ABSENCE OF IT WAS A LIE. Every reader used to fold
    an unparseable file into an empty block, so `resolve_store_config` reached
    `_require_prefix` with nothing in hand and raised
    `ConnectionPrefixMissingError` — a true refusal naming the wrong cause,
    sending an operator to look at a `connection.prefix` that was sitting there
    correctly all along.
    """

    def __init__(self, *, detail: str) -> None:
        super().__init__(_CONFIG_UNREADABLE_MESSAGE_TEMPLATE.format(detail=detail))
        self.detail = detail


_CREDENTIAL_MISSING_MESSAGE_TEMPLATE = (
    "required secret env var {variable} is absent; run under your project's "
    "configured credential_wrapper (e.g. with-<project>-env.sh -- ...)."
)


class BeadsCredentialMissingError(Exception):
    """The tenant-password secret was absent when a real `bd` call was attempted.

    EXPECTED: an in-process library caller reached the beads seam WITHOUT the
    `BEADS_DOLT_PASSWORD` secret — i.e. the store was driven directly rather
    than through a `bin/` CLI, so the bin chokepoint's credential self-heal
    (which re-execs through the configured `credential_wrapper`) never ran. The
    caller surfaces this actionable message rather than letting `bd` fail with a
    raw tenant auth error that names neither the missing var nor the remedy.
    """

    def __init__(self, *, variable: str) -> None:
        super().__init__(_CREDENTIAL_MISSING_MESSAGE_TEMPLATE.format(variable=variable))
        self.variable = variable
