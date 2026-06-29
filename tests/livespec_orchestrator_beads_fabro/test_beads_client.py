"""Tests for the BeadsClient seam (`_beads_client`).

Covers, hermetically:

- `make_beads_client` factory selection (fake vs shell) + the process
  singleton + `reset_fake_singleton`.
- `FakeBeadsClient` — full CRUD surface incl. the not-present error branches.
- `ShellBeadsClient` PURE helpers — the connection-flags / argv builders, the
  `--json` parser, the `_coerce_record_list` envelope handling, and the
  `_raise_for_status` exit-code → typed-error mapping. The single
  `subprocess.run` call site is `# pragma: no cover` (no live dolt-server),
  so these tests never shell out.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_SUPERSEDES,
    FakeBeadsClient,
    IssueDraft,
    ShellBeadsClient,
    _build_create_argv,
    _build_update_argv,
    _coerce_record_list,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig


def _config(**overrides: object) -> StoreConfig:
    base: dict[str, object] = {
        "tenant": "t",
        "prefix": "t",
        "server_user": "t-user",
        "database": "t",
        "bd_path": "/managed/bd",
        "server_host": "127.0.0.1",
        "server_port": 3307,
        "socket": None,
        "fake": False,
    }
    base.update(overrides)
    return StoreConfig(**base)  # type: ignore[arg-type]


def _draft(**overrides: object) -> IssueDraft:
    base: dict[str, object] = {
        "issue_id": "li-a",
        "issue_type": "task",
        "title": "title",
        "description": "desc",
        "priority": 2,
        "assignee": None,
        "created_at": "2026-05-19T00:00:00Z",
    }
    base.update(overrides)
    return IssueDraft(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# make_beads_client / singleton / reset.
# --------------------------------------------------------------------------


def test_factory_returns_fake_when_config_fake() -> None:
    reset_fake_singleton()
    client = make_beads_client(config=_config(fake=True))
    assert isinstance(client, FakeBeadsClient)


def test_factory_returns_shell_when_config_not_fake() -> None:
    client = make_beads_client(config=_config(fake=False))
    assert isinstance(client, ShellBeadsClient)


def test_factory_fake_is_process_singleton() -> None:
    reset_fake_singleton()
    first = make_beads_client(config=_config(fake=True))
    second = make_beads_client(config=_config(fake=True))
    assert first is second


def test_reset_fake_singleton_drops_the_instance() -> None:
    reset_fake_singleton()
    first = make_beads_client(config=_config(fake=True))
    reset_fake_singleton()
    second = make_beads_client(config=_config(fake=True))
    assert first is not second


# --------------------------------------------------------------------------
# FakeBeadsClient — CRUD + not-present error branches.
# --------------------------------------------------------------------------


def test_fake_create_and_show() -> None:
    fake = FakeBeadsClient()
    returned = fake.create_issue(draft=_draft(issue_id="li-x"))
    assert returned == "li-x"
    record = fake.show_issue(issue_id="li-x")
    assert record["id"] == "li-x"
    assert record["status"] == "open"


def test_fake_list_returns_copies() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    records = fake.list_issues()
    records[0]["status"] = "mutated"
    assert fake.show_issue(issue_id="li-x")["status"] == "open"


def test_fake_exists() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    assert fake.exists(issue_id="li-x") is True
    assert fake.exists(issue_id="li-absent") is False


def test_fake_show_missing_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        _ = fake.show_issue(issue_id="li-absent")


def test_fake_update_missing_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.update_issue(issue_id="li-absent", status="closed")


def test_fake_close_missing_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.close_issue(issue_id="li-absent", reason="x")


def test_fake_add_dependency_missing_from_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.add_dependency(from_id="li-absent", to_id="li-y", edge_type=EDGE_BLOCKS)


def test_fake_add_comment_round_trips_via_list_comments() -> None:
    """`add_comment` is the net-new write verb (29f.4 comment-bump path).

    Unlike `seed_comment` (a fake-only hermetic seeding hook), `add_comment`
    is a real `BeadsClient` protocol verb, so the out-of-band reflector can
    append occurrence evidence to a recurring finding's existing item.
    """
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.add_comment(issue_id="li-x", body="recurrence x2 on wave w7")
    bodies = [comment["text"] for comment in fake.list_comments(issue_id="li-x")]
    assert bodies == ["recurrence x2 on wave w7"]


def test_fake_add_comment_missing_issue_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.add_comment(issue_id="li-absent", body="orphan comment")


def test_fake_update_applies_all_fields() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.update_issue(
        issue_id="li-x",
        status="closed",
        parent_id="li-epic",
        add_labels=["resolution:completed", "resolution:completed"],
        metadata={"k": "v"},
    )
    record = fake.show_issue(issue_id="li-x")
    assert record["status"] == "closed"
    assert record["parent_id"] == "li-epic"
    # Duplicate label added only once.
    assert record["labels"].count("resolution:completed") == 1
    assert record["metadata"] == {"k": "v"}


def test_fake_close_sets_status_and_reason() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.close_issue(issue_id="li-x", reason="shipped")
    record = fake.show_issue(issue_id="li-x")
    assert record["status"] == "closed"
    assert record["close_reason"] == "shipped"


def test_fake_add_dependency_dedupes() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.add_dependency(from_id="li-x", to_id="li-y", edge_type=EDGE_BLOCKS)
    fake.add_dependency(from_id="li-x", to_id="li-y", edge_type=EDGE_BLOCKS)
    record = fake.show_issue(issue_id="li-x")
    assert record["dependencies"] == [{"depends_on_id": "li-y", "type": EDGE_BLOCKS}]


def test_fake_children_filters_by_parent() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-child", parent_id="li-epic"))
    _ = fake.create_issue(draft=_draft(issue_id="li-other", parent_id=None))
    children = fake.children(parent_id="li-epic")
    assert [record["id"] for record in children] == ["li-child"]


# --------------------------------------------------------------------------
# ShellBeadsClient — pure argv builders (no subprocess).
# --------------------------------------------------------------------------


def test_per_command_argv_carries_no_connection_flags() -> None:
    """bd v1.0.5 accepts `--server*` only on `bd`'s `init` verb; every per-command
    verb (`create`/`list`/`show`/`update`/`dep`) gets its connection from
    `.beads/config.yaml` + `BEADS_DOLT_PASSWORD`, and REJECTS `--server*`
    as unknown flags. So the per-command argv must be exactly the bd path
    followed by the verb args — nothing appended.
    """
    client = ShellBeadsClient(config=_config())
    argv = client._build_argv(verb_args=["list", "--status", "all", "--json"])  # noqa: SLF001
    assert argv == ["/managed/bd", "list", "--status", "all", "--json"]
    for forbidden in (
        "--server",
        "--external",
        "--server-host",
        "--server-port",
        "--server-user",
        "--server-socket",
        "--database",
        "--prefix",
    ):
        assert forbidden not in argv


def test_per_command_argv_has_no_connection_flags_even_with_socket() -> None:
    """A configured socket does not leak onto per-command argv either —
    the socket is consumed by `bd`'s `init` verb / `.beads/config.yaml`, never by
    per-command verbs.
    """
    client = ShellBeadsClient(config=_config(socket="/tmp/dolt.sock"))
    argv = client._build_argv(verb_args=["show", "li-a", "--json"])  # noqa: SLF001
    assert argv == ["/managed/bd", "show", "li-a", "--json"]
    assert "--server-socket" not in argv
    assert "/tmp/dolt.sock" not in argv


def test_list_issues_passes_limit_zero_for_unbounded_enumeration() -> None:
    """`bd list` defaults to `--limit 50`, silently capping enumeration at
    50 records. `list_issues` MUST pass bd's `--limit 0` "unbounded"
    sentinel so the full tenant set is returned. We capture the `verb_args`
    that `list_issues` hands to `_run_json` (no subprocess) and assert the
    unbounded argv.
    """
    captured: dict[str, list[str]] = {}

    class _Recording(ShellBeadsClient):
        def _run_json(self, *, verb_args: list[str]) -> Any:
            captured["verb_args"] = verb_args
            return []

    client = _Recording(config=_config())
    _ = client.list_issues()
    assert captured["verb_args"] == ["list", "--status", "all", "--limit", "0", "--json"]


def test_register_custom_statuses_emits_config_set_argv() -> None:
    """The shell client registers the 5 custom statuses via the verified
    `bd config set status.custom` CSV form. Capture the `verb_args` handed
    to `_run_void` (no subprocess)."""
    captured: dict[str, list[str]] = {}

    class _Recording(ShellBeadsClient):
        def _run_void(self, *, verb_args: list[str]) -> None:
            captured["verb_args"] = verb_args

    client = _Recording(config=_config())
    client.register_custom_statuses()
    assert captured["verb_args"] == [
        "config",
        "set",
        "status.custom",
        "backlog,pending-approval,ready:active,active:wip,acceptance:wip",
    ]


def test_build_create_argv_full_field_set() -> None:
    draft = _draft(
        issue_id="li-a",
        assignee="alice",
        spec_id="topic-x",
        parent_id="li-epic",
        labels=["origin:freeform", "gap-id:G1"],
        metadata={"audit": {"merge_sha": "sha"}},
    )
    argv = _build_create_argv(draft=draft)
    assert argv[0] == "create"
    assert "--id" in argv
    assert "li-a" in argv
    assert "--type" in argv
    assert "--title" in argv
    assert "--description" in argv
    assert "--priority" in argv
    assert "2" in argv
    # bd v1.0.5 `bd create` has NO `--created-at` flag (timestamp
    # preservation is a `bd import`-only feature); it MUST NOT be emitted.
    assert "--created-at" not in argv
    assert "--assignee" in argv
    assert "alice" in argv
    assert "--spec-id" in argv
    assert "topic-x" in argv
    assert "--parent" in argv
    assert "li-epic" in argv
    assert argv.count("--label") == 2
    assert "origin:freeform" in argv
    assert "gap-id:G1" in argv
    # metadata is a single compact-JSON argument.
    meta_index = argv.index("--metadata")
    assert json.loads(argv[meta_index + 1]) == {"audit": {"merge_sha": "sha"}}


def test_build_create_argv_omits_optional_flags_when_absent() -> None:
    argv = _build_create_argv(draft=_draft(assignee=None, spec_id=None, parent_id=None))
    assert "--assignee" not in argv
    assert "--spec-id" not in argv
    assert "--parent" not in argv
    assert argv.count("--label") == 0


def test_build_update_argv_full() -> None:
    argv = _build_update_argv(
        issue_id="li-a",
        status="closed",
        parent_id="li-epic",
        add_labels=["resolution:completed"],
        metadata={"audit": {"merge_sha": "sha"}},
    )
    assert argv[:2] == ["update", "li-a"]
    assert "--status" in argv
    assert "closed" in argv
    assert "--parent" in argv
    assert "li-epic" in argv
    # bd v1.0.5 `bd update` has NO bare `--label`; label additions use
    # `--add-label` (one per repeated label).
    assert "--label" not in argv
    assert argv.count("--add-label") == 1
    add_index = argv.index("--add-label")
    assert argv[add_index + 1] == "resolution:completed"
    assert "--metadata" in argv


def test_build_update_argv_repeats_add_label_per_label() -> None:
    argv = _build_update_argv(
        issue_id="li-a",
        status=None,
        parent_id=None,
        add_labels=["origin:freeform", "gap-id:G1"],
        metadata=None,
    )
    assert "--label" not in argv
    assert argv.count("--add-label") == 2
    assert "origin:freeform" in argv
    assert "gap-id:G1" in argv


def test_build_update_argv_bare_is_noop_length() -> None:
    argv = _build_update_argv(
        issue_id="li-a",
        status=None,
        parent_id=None,
        add_labels=None,
        metadata=None,
    )
    assert argv == ["update", "li-a"]


def test_shell_update_skips_no_op_but_runs_when_flags_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare `update <id>` MUST NOT shell out; a flagged update MUST.

    One recorder spans both cases: the no-op `update_issue` records nothing
    (proving it never reached `_run_void`), and the flagged `update_issue`
    records exactly its argv — so `seen` holds the single flagged call.
    """
    client = ShellBeadsClient(config=_config())
    seen: list[list[str]] = []
    monkeypatch.setattr(
        client,
        "_run_void",
        lambda *, verb_args: seen.append(verb_args),
    )
    client.update_issue(issue_id="li-a")  # no-op: no mutating flags
    assert seen == []
    client.update_issue(issue_id="li-a", status="closed")  # flagged: shells out
    assert len(seen) == 1
    assert seen[0][:2] == ["update", "li-a"]


def test_shell_close_with_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    seen: list[list[str]] = []
    monkeypatch.setattr(
        client,
        "_run_void",
        lambda *, verb_args: seen.append(verb_args),
    )
    client.close_issue(issue_id="li-a", reason="done")
    assert seen[0] == ["close", "li-a", "--reason", "done"]


def test_shell_close_without_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    seen: list[list[str]] = []
    monkeypatch.setattr(
        client,
        "_run_void",
        lambda *, verb_args: seen.append(verb_args),
    )
    client.close_issue(issue_id="li-a", reason=None)
    assert seen[0] == ["close", "li-a"]


def test_shell_add_comment_builds_comment_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    seen: list[list[str]] = []
    monkeypatch.setattr(
        client,
        "_run_void",
        lambda *, verb_args: seen.append(verb_args),
    )
    client.add_comment(issue_id="li-a", body="recurrence note")
    assert seen[0] == ["comment", "li-a", "recurrence note"]


def test_shell_create_returns_id(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    monkeypatch.setattr(client, "_run_void", lambda *, verb_args: None)  # noqa: ARG005
    assert client.create_issue(draft=_draft(issue_id="li-z")) == "li-z"


def test_shell_add_dependency_builds_dep_add(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    seen: list[list[str]] = []
    monkeypatch.setattr(
        client,
        "_run_void",
        lambda *, verb_args: seen.append(verb_args),
    )
    client.add_dependency(from_id="li-a", to_id="li-b", edge_type=EDGE_SUPERSEDES)
    assert seen[0] == ["dep", "add", "li-a", "li-b", "--type", EDGE_SUPERSEDES]


# --------------------------------------------------------------------------
# _run_json / _run_void through the real path with a stubbed subprocess.run.
#
# The `subprocess.run` call site inside `_invoke` carries `# pragma: no
# cover`; patching it lets the pure `_run_json` / `_run_void` argv-build +
# parse bodies run hermetically (no live dolt-server).
# --------------------------------------------------------------------------


def test_run_json_builds_argv_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    seen: list[list[str]] = []

    def _fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout='[{"id": "li-a"}]', stderr=""
        )

    monkeypatch.setattr("livespec_orchestrator_beads_fabro._beads_client.subprocess.run", _fake_run)
    result = client.list_issues()
    assert result == [{"id": "li-a"}]
    # The argv is exactly the pinned bd path + the per-command verb args
    # (including `--limit 0` for unbounded enumeration); no `--server*`
    # connection flags are appended (they belong to `bd`'s `init` verb).
    assert seen[0] == ["/managed/bd", "list", "--status", "all", "--limit", "0", "--json"]
    assert "--server" not in seen[0]


def test_run_void_builds_argv_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    seen: list[list[str]] = []

    def _fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("livespec_orchestrator_beads_fabro._beads_client.subprocess.run", _fake_run)
    client.add_dependency(from_id="li-a", to_id="li-b", edge_type=EDGE_BLOCKS)
    assert seen[0][0] == "/managed/bd"
    assert "dep" in seen[0]
    assert "add" in seen[0]


# --------------------------------------------------------------------------
# ShellBeadsClient read verbs over a stubbed _run_json (no subprocess).
# --------------------------------------------------------------------------


def test_shell_list_issues_coerces_array(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    monkeypatch.setattr(
        client,
        "_run_json",
        lambda *, verb_args: [{"id": "li-a"}],  # noqa: ARG005
    )
    assert client.list_issues() == [{"id": "li-a"}]


def test_shell_show_issue_takes_first_element_of_array(monkeypatch: pytest.MonkeyPatch) -> None:
    """bd v1.0.5 `bd show <id> --json` returns a JSON ARRAY of one issue;
    `show_issue` must take the first element.
    """
    client = ShellBeadsClient(config=_config())
    monkeypatch.setattr(
        client,
        "_run_json",
        lambda *, verb_args: [{"id": "li-a", "status": "open"}],  # noqa: ARG005
    )
    assert client.show_issue(issue_id="li-a") == {"id": "li-a", "status": "open"}


def test_shell_show_issue_empty_array_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty array (no such issue) is a clean mapping error, not an
    IndexError.
    """
    client = ShellBeadsClient(config=_config())
    monkeypatch.setattr(client, "_run_json", lambda *, verb_args: [])  # noqa: ARG005
    with pytest.raises(BeadsMappingError):
        _ = client.show_issue(issue_id="li-a")


def test_shell_show_issue_non_array_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Anything that is not a JSON array of issue dicts is a bad-contract
    mapping error.
    """
    client = ShellBeadsClient(config=_config())
    monkeypatch.setattr(client, "_run_json", lambda *, verb_args: {"id": "li-a"})  # noqa: ARG005
    with pytest.raises(BeadsMappingError):
        _ = client.show_issue(issue_id="li-a")


def test_shell_show_issue_non_dict_first_element_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A JSON array whose first element is not an issue object is a
    bad-contract mapping error (not a downstream TypeError).
    """
    client = ShellBeadsClient(config=_config())
    monkeypatch.setattr(client, "_run_json", lambda *, verb_args: ["junk"])  # noqa: ARG005
    with pytest.raises(BeadsMappingError):
        _ = client.show_issue(issue_id="li-a")


def test_shell_children_coerces(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    monkeypatch.setattr(
        client,
        "_run_json",
        lambda *, verb_args: {"issues": [{"id": "li-c"}]},  # noqa: ARG005
    )
    assert client.children(parent_id="li-epic") == [{"id": "li-c"}]


def test_shell_exists_scans_list(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    monkeypatch.setattr(
        client,
        "_run_json",
        lambda *, verb_args: [{"id": "li-a"}, {"id": "li-b"}],  # noqa: ARG005
    )
    assert client.exists(issue_id="li-b") is True
    assert client.exists(issue_id="li-missing") is False


# --------------------------------------------------------------------------
# _coerce_record_list — envelope shapes.
# --------------------------------------------------------------------------


def test_coerce_record_list_bare_array_filters_non_dicts() -> None:
    out = _coerce_record_list(parsed=[{"id": "li-a"}, "junk", 7])
    assert out == [{"id": "li-a"}]


def test_coerce_record_list_envelope() -> None:
    out = _coerce_record_list(parsed={"issues": [{"id": "li-a"}, "junk"]})
    assert out == [{"id": "li-a"}]


def test_coerce_record_list_unknown_shape_raises() -> None:
    with pytest.raises(BeadsMappingError):
        _ = _coerce_record_list(parsed={"not_issues": []})


def test_coerce_record_list_scalar_raises() -> None:
    with pytest.raises(BeadsMappingError):
        _ = _coerce_record_list(parsed=42)


# --------------------------------------------------------------------------
# _parse_json — `--json` body parsing.
# --------------------------------------------------------------------------


def test_parse_json_empty_body_is_empty_list() -> None:
    client = ShellBeadsClient(config=_config())
    assert client._parse_json(stdout="   ", argv_repr="list") == []  # noqa: SLF001


def test_parse_json_valid_body() -> None:
    client = ShellBeadsClient(config=_config())
    assert client._parse_json(stdout='[{"id": "li-a"}]', argv_repr="list") == [  # noqa: SLF001
        {"id": "li-a"}
    ]


def test_parse_json_invalid_body_raises_command_error() -> None:
    client = ShellBeadsClient(config=_config())
    with pytest.raises(BeadsCommandError) as excinfo:
        _ = client._parse_json(stdout="not-json", argv_repr="list --json")  # noqa: SLF001
    assert "could not parse" in excinfo.value.stderr


# --------------------------------------------------------------------------
# _raise_for_status — exit-code → typed-error mapping (pure).
# --------------------------------------------------------------------------


def _completed(*, returncode: int, stderr: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["bd"], returncode=returncode, stdout="", stderr=stderr)


def test_raise_for_status_zero_is_noop() -> None:
    client = ShellBeadsClient(config=_config())
    client._raise_for_status(  # noqa: SLF001
        completed=_completed(returncode=0, stderr=""),
        argv=["bd", "list"],
    )


def test_raise_for_status_connection_refused() -> None:
    client = ShellBeadsClient(config=_config())
    with pytest.raises(BeadsConnectionError):
        client._raise_for_status(  # noqa: SLF001
            completed=_completed(returncode=1, stderr="dial tcp: connection refused"),
            argv=["bd", "list"],
        )


def test_raise_for_status_cant_connect() -> None:
    client = ShellBeadsClient(config=_config())
    with pytest.raises(BeadsConnectionError):
        client._raise_for_status(  # noqa: SLF001
            completed=_completed(returncode=1, stderr="ERROR: can't connect to server"),
            argv=["bd", "list"],
        )


def test_raise_for_status_unknown_database_is_tenant_missing() -> None:
    client = ShellBeadsClient(config=_config(database="my-tenant"))
    with pytest.raises(BeadsTenantMissingError) as excinfo:
        client._raise_for_status(  # noqa: SLF001
            completed=_completed(returncode=1, stderr="Unknown database 'my-tenant'"),
            argv=["bd", "list"],
        )
    assert excinfo.value.tenant == "my-tenant"


def test_raise_for_status_does_not_exist_is_tenant_missing() -> None:
    client = ShellBeadsClient(config=_config())
    with pytest.raises(BeadsTenantMissingError):
        client._raise_for_status(  # noqa: SLF001
            completed=_completed(returncode=1, stderr="database does not exist"),
            argv=["bd", "list"],
        )


def test_raise_for_status_other_nonzero_is_command_error() -> None:
    client = ShellBeadsClient(config=_config())
    with pytest.raises(BeadsCommandError) as excinfo:
        client._raise_for_status(  # noqa: SLF001
            completed=_completed(returncode=5, stderr="some other failure"),
            argv=["bd", "show", "li-a"],
        )
    assert excinfo.value.exit_code == 5
    assert excinfo.value.command == "bd show li-a"


# --------------------------------------------------------------------------
# Comments — fake seeding seam + shell `bd comments <id> --json` read.
# --------------------------------------------------------------------------


def test_fake_seed_and_list_comments_roundtrip() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.seed_comment(
        issue_id="li-x",
        text="first rider",
        author="operator",
        created_at="2026-06-12T00:00:00Z",
    )
    fake.seed_comment(issue_id="li-x", text="second rider")
    records = fake.list_comments(issue_id="li-x")
    assert [record["text"] for record in records] == ["first rider", "second rider"]
    assert records[0]["author"] == "operator"
    assert records[0]["created_at"] == "2026-06-12T00:00:00Z"
    assert records[1]["author"] is None
    assert records[1]["created_at"] is None


def test_fake_list_comments_returns_copies() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    fake.seed_comment(issue_id="li-x", text="original")
    records = fake.list_comments(issue_id="li-x")
    records[0]["text"] = "mutated"
    assert fake.list_comments(issue_id="li-x")[0]["text"] == "original"


def test_fake_list_comments_empty_for_uncommented_issue() -> None:
    fake = FakeBeadsClient()
    _ = fake.create_issue(draft=_draft(issue_id="li-x"))
    assert fake.list_comments(issue_id="li-x") == []


def test_fake_list_comments_missing_issue_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        _ = fake.list_comments(issue_id="li-absent")


def test_fake_seed_comment_missing_issue_raises() -> None:
    fake = FakeBeadsClient()
    with pytest.raises(BeadsMappingError):
        fake.seed_comment(issue_id="li-absent", text="orphan")


def test_shell_list_comments_builds_argv_and_filters_non_dicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`bd comments <id> --json` returns a JSON array of comment objects
    (`{id, issue_id, author, text, created_at}` in bd v1.0.5; empty array
    when uncommented); non-dict elements are dropped fail-soft."""
    client = ShellBeadsClient(config=_config())
    seen: list[list[str]] = []

    def _fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(
            args=argv,
            returncode=0,
            stdout='[{"issue_id": "li-a", "text": "a rider"}, 42]',
            stderr="",
        )

    monkeypatch.setattr("livespec_orchestrator_beads_fabro._beads_client.subprocess.run", _fake_run)
    result = client.list_comments(issue_id="li-a")
    assert result == [{"issue_id": "li-a", "text": "a rider"}]
    assert seen[0] == ["/managed/bd", "comments", "li-a", "--json"]


def test_shell_list_comments_non_array_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    monkeypatch.setattr(
        client,
        "_run_json",
        lambda *, verb_args: {"not": "an array"},  # noqa: ARG005
    )
    with pytest.raises(BeadsMappingError):
        _ = client.list_comments(issue_id="li-a")
