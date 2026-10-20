#!/usr/bin/env bash
# STOPGAP pre-dispatch Definition-of-Done judgement (maintainer ruling 2026-10-20,
# stopgap 2 on plan epic bd-ib-7sjdzv). Retire it when bd-ib-7f66ar ships the
# ratified v132/v141 judgement inside the Dispatcher.
#
# Runs the factory's OWN `dod_gate` prompt on the host, over the item's title,
# description and ledger-comment riders, so a Definition of Done the gate would
# refuse is caught for one model call instead of a factory slot. It is not a
# second copy of the gate: the prompt is read from the orchestrator build the
# CURRENT repository has registered, so it changes whenever the gate does.
#
# Usage, from the governed repository's root, under its credential wrapper:
#   with-<project>-env.sh -- <orchestrator checkout>/dev-tooling/dod-preflight.sh <item-id> [<description-file>]
# The optional description file replaces the item's description, so a candidate
# edit can be checked before it is written to the ledger.
#
# Exit 0 and a last line of PASS: dispatch may proceed. Exit 1 and a last line of
# the gate's {"outcome": "failed", ...} JSON: do NOT dispatch; apply the remedies.
# Exit 2: the judgement could not run, which is a reason to fix the tool, not to
# skip the check.
set -euo pipefail

item="${1:?usage: dod-preflight.sh <item-id> [<description-file>]}"
override="${2:-}"
repo_root=$(git rev-parse --show-toplevel)

# The orchestrator build THIS repository has registered, read from Claude Code's
# install registry rather than hard-coded, so a release moves the prompt with it.
install_root=$(python3 - "$repo_root" <<'PY'
import json, os, sys
repo = os.path.realpath(sys.argv[1])
registry = os.path.expanduser("~/.claude/plugins/installed_plugins.json")
installs = json.load(open(registry, encoding="utf-8"))["plugins"].get(
    "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro", [])
paths = [i["installPath"] for i in installs if os.path.realpath(i.get("projectPath", "")) == repo]
if not paths:
    sys.exit(f"dod-preflight: no livespec-orchestrator-beads-fabro install registered for {repo}")
print(paths[0])
PY
) || exit 2
prompt_file="$install_root/.fabro/workflows/implement-work-item/prompts/dod-gate.md"
[ -r "$prompt_file" ] || { echo "dod-preflight: prompt not readable: $prompt_file" >&2; exit 2; }

# The in-run gate's own model and effort, and the capability set it can resolve.
# Measured 2026-10-20 over four PASS-then-refused items: a hard-coded `sonnet` here
# graded more leniently than the gate's `acp_nodes.dod_gate` route (References and
# deliverable-policy misses), and a governed repository with no committed
# `dispatcher.sandbox_capabilities` made this host call withhold check 5 while the
# sandbox, which publishes the file, ran it. So route like the gate does, and fail
# closed when the capability set cannot be resolved here.
read -r judge_model judge_effort < <(python3 - "$install_root" "$repo_root" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, f"{sys.argv[1]}/scripts")
sys.path.insert(0, f"{sys.argv[1]}/scripts/_vendor")
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
block = dispatcher_block(cwd=Path(sys.argv[2]))
if not block.get("sandbox_capabilities"):
    sys.exit("dod-preflight: the governed repository commits no dispatcher.sandbox_capabilities, "
             "so this host cannot run the gate's capability check (check 5); publish the mirror first")
# No entry means the workflow's built-in dod_gate default, its review_adapter.
entry = (block.get("acp_nodes") or {}).get("dod_gate") or {
    "agent": "claude-acp", "model": "claude-opus-4-8", "effort": "high"}
routes = [entry, *(entry.get("fallbacks") or [])]
claude = [r for r in routes if r.get("agent") == "claude-acp" and r.get("model")]
if not claude:
    sys.exit("dod-preflight: acp_nodes.dod_gate names no claude-acp route this host can run")
print(claude[0]["model"], claude[0].get("effort") or "high")
PY
) || exit 2
[ -n "${judge_model:-}" ] || exit 2

# The same three parts of the run goal the gate grades: title, description and riders.
goal=$(python3 - "$item" "$override" <<'PY'
import json, subprocess, sys
item, override = sys.argv[1], sys.argv[2]
record = json.loads(subprocess.check_output(["bd", "show", item, "--json"], text=True))[0]
comments = json.loads(subprocess.check_output(["bd", "comments", item, "--json"], text=True))
description = open(override, encoding="utf-8").read() if override else record.get("description") or ""
lines = [f"Work-item: {item}", f"Title: {record['title']}", "", "Description:", description, "",
         "Ledger comments (operator riders appended after filing; treat them as part of the brief):"]
lines += [f"[{n}] ({c.get('author')}, {c.get('created_at')}) {c.get('text', '')}"
          for n, c in enumerate(comments, 1)]
print("\n".join(lines))
PY
) || exit 2

verdict=$({
  printf 'Goal: %s\n\n\n' "$goal"
  cat "$prompt_file"
  printf '\n\nYou are running on the HOST as a pre-dispatch check, not inside a sandbox, so /etc/livespec/sandbox-capabilities is absent: use the committed mirror. Read files only. End with the JSON failure line on any finding, or with the single word PASS alone on the last line.\n'
} | claude -p --model "$judge_model" --effort "$judge_effort" --allowedTools "Read,Grep,Glob") || exit 2

printf '%s\n' "$verdict"
last=$(printf '%s\n' "$verdict" | awk 'NF { line = $0 } END { print line }')
case "$last" in
  PASS) exit 0 ;;
  *'"outcome"'*'"failed"'*) exit 1 ;;
  *) echo "dod-preflight: no verdict line; treat as not run" >&2; exit 2 ;;
esac
