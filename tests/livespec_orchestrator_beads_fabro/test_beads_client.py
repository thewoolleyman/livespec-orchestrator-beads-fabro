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

import subprocess
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_SUPERSEDES,
    FakeBeadsClient,
    IssueDraft,
    ShellBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
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


@pytest.fixture(autouse=True)
def _tenant_password_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default the tenant secret present for the whole module, modelling a
    normally-wrapped environment, so every ShellBeadsClient test that reaches
    `_invoke` clears its credential guard. The guard's own test deletes it.
    """
    monkeypatch.setenv("BEADS_DOLT_PASSWORD", "test-secret")


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
# ShellBeadsClient — pure argv wiring (no subprocess).
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

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro._beads_client_shell.subprocess.run", _fake_run
    )
    result = client.list_issues()
    assert result == [{"id": "li-a"}]
    # The argv is exactly the pinned bd path + the per-command verb args
    # (including `--limit 0` for unbounded enumeration); no `--server*`
    # connection flags are appended (they belong to `bd`'s `init` verb).
    assert seen[0] == ["/managed/bd", "list", "--status", "all", "--limit", "0", "--json"]
    assert "--server" not in seen[0]


def test_run_json_invokes_bd_from_config_repo_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ShellBeadsClient(config=_config(repo_root=tmp_path))
    seen: list[tuple[list[str], Path | None]] = []

    def _fake_run(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        cwd = kw.get("cwd")
        seen.append((argv, cwd if isinstance(cwd, Path) else None))
        if argv == ["/managed/bd", "config", "get", "dolt.server-user"]:
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="t-user\n", stderr=""
            )
        if argv == ["/managed/bd", "config", "get", "dolt.database"]:
            return subprocess.CompletedProcess(args=argv, returncode=0, stdout="t\n", stderr="")
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="[]", stderr="")

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro._beads_client_shell.subprocess.run", _fake_run
    )
    _ = client.list_issues()
    assert seen == [
        (["/managed/bd", "config", "get", "dolt.server-user"], tmp_path),
        (["/managed/bd", "config", "get", "dolt.database"], tmp_path),
        (["/managed/bd", "list", "--status", "all", "--limit", "0", "--json"], tmp_path),
    ]


def test_run_json_rejects_repo_root_with_mismatched_beads_tenant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ShellBeadsClient(config=_config(repo_root=tmp_path))

    def _fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        values = {
            ("/managed/bd", "config", "get", "dolt.server-user"): "other-user\n",
            ("/managed/bd", "config", "get", "dolt.database"): "other-db\n",
        }
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout=values[tuple(argv)], stderr=""
        )

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro._beads_client_shell.subprocess.run", _fake_run
    )
    with pytest.raises(BeadsConnectionError) as excinfo:
        _ = client.list_issues()
    message = str(excinfo.value)
    assert "does not match resolved StoreConfig" in message
    assert "dolt.database=other-db" in message


def test_run_void_builds_argv_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    client = ShellBeadsClient(config=_config())
    seen: list[list[str]] = []

    def _fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro._beads_client_shell.subprocess.run", _fake_run
    )
    client.add_dependency(from_id="li-a", to_id="li-b", edge_type=EDGE_BLOCKS)
    assert seen[0][0] == "/managed/bd"
    assert "dep" in seen[0]
    assert "add" in seen[0]


def test_invoke_raises_credential_error_when_password_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_invoke`'s secondary guard: an in-process caller that reached the beads
    seam without `BEADS_DOLT_PASSWORD` gets an actionable typed error naming the
    missing var — never a raw backend auth failure — and never shells out.
    """
    monkeypatch.delenv("BEADS_DOLT_PASSWORD", raising=False)
    client = ShellBeadsClient(config=_config())
    with pytest.raises(BeadsCredentialMissingError) as excinfo:
        client.list_issues()
    assert excinfo.value.variable == "BEADS_DOLT_PASSWORD"
    assert "credential_wrapper" in str(excinfo.value)


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
# Comments — shell `bd comments <id> --json` read.
# --------------------------------------------------------------------------


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

    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro._beads_client_shell.subprocess.run", _fake_run
    )
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
