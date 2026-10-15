"""Reading a dead run's changed files from its factory and publishing them."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    PreservedTree,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget

_BASE_COMMIT = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_RUN_ID = "01M4YJGC55V86C9V1X07QG3Y2H"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_COMMIT = "c0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm"

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = f"{_PACKAGE}._dispatcher_preserved_tree"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_preserved_tree.py"
)

# Two files the run wrote and one it deleted, as a factory run-files read
# reports them: content inline, base64-encoded, and a removal carrying none.
_RUN_FILES_PAYLOAD = {
    "data": [
        {"path": "a.py", "content": "Y2hhbmdlZAo=", "encoding": "base64"},
        {"path": "docs/b.md", "content": "notes\n"},
        {"path": "gone.py", "deleted": True},
    ]
}


@dataclass(kw_only=True)
class _PayloadTransport:
    """Answer the run-files route with `_RUN_FILES_PAYLOAD`, recording the url."""

    urls: list[str] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = method
        _ = headers
        _ = body
        _ = timeout_seconds
        self.urls.append(url)
        return FabroHttpResult(
            status=200,
            body=json.dumps(_RUN_FILES_PAYLOAD),
            error=None,
            payload=None,
            succeeded=True,
        )


@dataclass(kw_only=True)
class _ApiRunner:
    """Answer each `gh api` call with a canned object name, recording bodies."""

    argvs: list[list[str]] = field(default_factory=list)
    bodies: list[object] = field(default_factory=list)
    answers: list[str] = field(
        default_factory=lambda: ["basetree", "blob1", "blob2", "treesha", _COMMIT, ""]
    )

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd
        _ = timeout_seconds
        _ = env
        self.argvs.append(list(argv))
        if stdin is not None:
            self.bodies.append(json.loads(os.pread(stdin, 1_000_000, 0).decode("utf-8")))
        index = len(self.argvs) - 1
        answer = self.answers[index] if index < len(self.answers) else ""
        return CommandResult(exit_code=0, stdout=f"{answer}\n", stderr="")


def test_the_run_s_changed_files_are_published_as_one_commit_over_the_run_s_base_commit() -> None:
    # The module does not exist at Red, so this is a genuine assertion failure
    # rather than a collection error -- the decomposition pattern this repo's
    # new-module slices use.
    assert _MODULE_PATH.is_file(), _MODULE_PATH
    preserved_tree = importlib.import_module(_MODULE)
    transport = _PayloadTransport()
    runner = _ApiRunner()
    published = preserved_tree.publish_run_tree(
        port=FabroHttpPort(target=FabroTarget(server_url=_SERVER), transport=transport),
        runner=runner,
        repo=Path("/nonexistent"),
        work_item_id="bd-ib-na2xvm",
        run_id=_RUN_ID,
        base_commit=_BASE_COMMIT,
    )
    assert isinstance(published, PreservedTree), published
    # Read from the dispatch's RESOLVED factory, not from a local default.
    assert transport.urls == [f"{_SERVER}/api/v1/runs/{_RUN_ID}/files"]
    assert published.ref == f"refs/livespec/preserved-publish/bd-ib-na2xvm/{_COMMIT}"
    assert published.commit == _COMMIT
    assert published.file_count == 3
    # Every change the run made, removals included, over the base commit's tree.
    tree_body, commit_body = runner.bodies[2], runner.bodies[3]
    assert tree_body == {
        "base_tree": "basetree",
        "tree": [
            {"path": "a.py", "mode": "100644", "type": "blob", "sha": "blob1"},
            {"path": "docs/b.md", "mode": "100644", "type": "blob", "sha": "blob2"},
            {"path": "gone.py", "mode": "100644", "type": "blob", "sha": None},
        ],
    }
    assert isinstance(commit_body, dict)
    assert commit_body["parents"] == [_BASE_COMMIT]
    assert commit_body["tree"] == "treesha"
    # The two blob posts carry the run's own bytes, base64-encoded either way.
    assert runner.bodies[0] == {"content": "Y2hhbmdlZAo=", "encoding": "base64"}
    assert runner.bodies[1] == {"content": "bm90ZXMK", "encoding": "base64"}
