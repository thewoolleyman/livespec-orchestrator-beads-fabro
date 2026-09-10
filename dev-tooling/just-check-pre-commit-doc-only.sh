#!/usr/bin/env bash
# Deliberately omit errexit so the doc-only subset reports every failing target.
set -uo pipefail

targets=(
    check-heading-coverage
    check-agents-ai-references-resolve
    check-claude-md-coverage
    check-handoff-dispatch-routing
    check-plan-anchor-declared
    check-vendor-manifest
    check-no-direct-tool-invocation
    check-check-tools
    # The integration-contract gates over the workflow payload (workflow.toml,
    # workflow.fabro, prompts/*.md): a payload-only push has zero .py changes
    # and therefore takes THIS path, so the gates must be here to run at all.
    check-no-fleet-toolchain-literals
    check-seam-equivalence
    check-ci-wires-repo-local-gates
    # The factory-graph validity gate is here for the same reason, and it is the
    # one whose absence has twice taken the factory down: a `workflow.fabro` edit
    # is a zero-.py changeset, so this is the only pre-commit path it takes.
    check-fabro-graph-validity
)
authored_unowned_heading_coverage_todo() {
    uv run python - <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def git_show(*, revision: str) -> str | None:
    result = subprocess.run(
        ["git", "show", revision],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def parse_entries(*, text: str | None) -> list[dict[str, Any]]:
    if text is None:
        return []
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        return []
    return [entry for entry in parsed if isinstance(entry, dict)]


def entry_key(*, entry: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (entry.get("spec_root"), entry.get("spec_file"), entry.get("heading"))


def is_unowned_todo(*, entry: dict[str, Any]) -> bool:
    work_item = entry.get("work_item")
    return entry.get("test") == "TODO" and not (
        isinstance(work_item, str) and bool(work_item.strip())
    )


head_entries = {
    entry_key(entry=entry): entry
    for entry in parse_entries(text=git_show(revision="HEAD:tests/heading-coverage.json"))
}
staged_entries = parse_entries(text=git_show(revision=":tests/heading-coverage.json"))
for entry in staged_entries:
    if not is_unowned_todo(entry=entry):
        continue
    previous = head_entries.get(entry_key(entry=entry))
    if previous != entry:
        sys.exit(0)
sys.exit(1)
PY
}
failed=()
for target in "${targets[@]}"; do
    printf '\n::: just %s\n' "$target"
    if ! just "$target"; then
        failed+=("$target")
    fi
done
# check-no-todo-registry (work-item livespec-dev-tooling-yilyxr.10): the
# per-commit tier is warn-only everywhere; the release tier is armed only
# for the commit that itself edits tests/heading-coverage.json, because
# authoring an UNOWNED TODO entry is never valid per the check's contract.
printf '\n::: just check-no-todo-registry\n'
if git diff --cached --name-only | grep -qx 'tests/heading-coverage.json'; then
    echo ":: staged changeset edits tests/heading-coverage.json — checking authored TODO ownership"
    if authored_unowned_heading_coverage_todo; then
        echo ":: staged changeset authors an unowned heading-coverage TODO — arming the TODO-ownership release tier"
        if ! LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST=true just check-no-todo-registry; then
            failed+=(check-no-todo-registry)
        fi
    elif ! just check-no-todo-registry; then
        failed+=(check-no-todo-registry)
    fi
elif ! just check-no-todo-registry; then
    failed+=(check-no-todo-registry)
fi
if [[ ${#failed[@]} -gt 0 ]]; then
    printf '\nFailed targets (%d):\n' "${#failed[@]}"
    printf '  - %s\n' "${failed[@]}"
    exit 1
fi
printf '\nAll doc-only targets passed.\n' 
