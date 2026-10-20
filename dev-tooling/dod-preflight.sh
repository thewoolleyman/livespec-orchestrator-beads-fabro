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
# Exit 0 and a last line of PASS: every candidate of the gate's chain passed, so
# dispatch may proceed. Exit 1 and a failure JSON line from any candidate: do NOT
# dispatch; apply the remedies. Exit 2: the judgement could not run, which is a
# reason to fix the tool, not to skip the check.
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

# EVERY candidate of the in-run gate's chain, and the capability set it can resolve.
# Measured 2026-10-20 over five PASS-then-refused items. A hard-coded `sonnet` here
# graded more leniently than the gate's `acp_nodes.dod_gate` route (References and
# deliverable-policy misses). A governed repository with no committed
# `dispatcher.sandbox_capabilities` made this host call withhold check 5 while the
# sandbox, which publishes the file, ran it. And the admission session-headroom filter
# can skip the claude-acp primary at dispatch time, so the gate then runs a FALLBACK
# (bd-ib-h7iaai: the gate ran codex-acp gpt-5.6-terra while this script graded on
# claude-opus-5). Which candidate a dispatch will select is not knowable here, so the
# judgement runs on every candidate in the chain and passes only if all of them pass.
# It fails closed when the capability set cannot be resolved.
routes=$(python3 - "$install_root" "$repo_root" <<'PY'
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
for route in [entry, *(entry.get("fallbacks") or [])]:
    if route.get("agent") not in ("claude-acp", "codex-acp") or not route.get("model"):
        sys.exit(f"dod-preflight: acp_nodes.dod_gate candidate {route!r} is not one this host can run")
    print(route["agent"], route["model"], route.get("effort") or "high")
PY
) || exit 2
[ -n "$routes" ] || exit 2

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

judgement_input=$(mktemp)
trap 'rm -f "$judgement_input" "$judgement_input.last"' EXIT
{
  printf 'Goal: %s\n\n\n' "$goal"
  cat "$prompt_file"
  printf '\n\nYou are running on the HOST as a pre-dispatch check, not inside a sandbox, so /etc/livespec/sandbox-capabilities is absent: use the committed mirror. Read files only. End with the JSON failure line on any finding, or with the single word PASS alone on the last line.\n'
} > "$judgement_input"

# The claude leg authenticates as the account a dispatch would, through the
# Dispatcher's own selector, not as whatever bare CLAUDE_CODE_OAUTH_TOKEN the
# wrapper injected. Measured 2026-10-20: the bare token was the account at its
# weekly limit while caam had selected another, so every claude leg exited 2
# for a factory that was not exhausted (coordinator R324).
claude_credential_env=$(python3 - "$install_root" <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, f"{sys.argv[1]}/scripts")
sys.path.insert(0, f"{sys.argv[1]}/scripts/_vendor")
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
choice = select_factory_credential(
    environ=os.environ, home=Path.home(), warn=lambda line: print(f"dod-preflight: {line}", file=sys.stderr)
)
print(choice.env_name)
PY
) || exit 2

status=0
while read -r agent model effort; do
  echo "=== dod-preflight candidate: $agent $model $effort"
  if [ "$agent" = claude-acp ]; then
    echo "dod-preflight: claude leg credential: $claude_credential_env"
    [ -n "${!claude_credential_env:-}" ] || { echo "dod-preflight: $claude_credential_env is not set" >&2; exit 2; }
    verdict=$(CLAUDE_CODE_OAUTH_TOKEN="${!claude_credential_env}" \
      claude -p --model "$model" --effort "$effort" --allowedTools "Read,Grep,Glob" < "$judgement_input") || exit 2
  else
    # Session hooks are disabled because this is a one-shot judgement, not a
    # supervised session, and a Stop hook that blocks makes the model keep going
    # past its verdict, so `-o` captures whatever it said last. Measured
    # 2026-10-20 on livespec-dev-tooling-r6kagr: the candidate printed PASS, then
    # livespec-driver-codex's supervisor completion gate blocked the stop on that
    # repository's legacy non-JSON tmp/overseer markers, and the last message was
    # a question, so the leg reported "no verdict" (coordinator R342 follow-up).
    codex exec -m "$model" -c "model_reasoning_effort=$effort" -s read-only --skip-git-repo-check \
      --disable hooks \
      -o "$judgement_input.last" < "$judgement_input" > /dev/null 2>&1 || exit 2
    verdict=$(cat "$judgement_input.last")
  fi
  printf '%s\n' "$verdict"
  # The verdict line is the last non-empty line that is not a Markdown code
  # fence, trimmed. Measured 2026-10-20 (coordinator R339): a candidate wrapped
  # its failed JSON in a fenced block, so the last line was the closing fence and
  # a real finding was reported as "not run" (exit 2) instead of failed.
  last=$(printf '%s\n' "$verdict" | awk '
    { sub(/\r$/, ""); sub(/^[ \t]+/, ""); sub(/[ \t]+$/, "") }
    NF && !/^(```|~~~)/ { line = $0 }
    END { print line }')
  case "$last" in
    PASS) ;;
    *'"outcome"'*'"failed"'*) status=1 ;;
    *) echo "dod-preflight: $agent $model gave no verdict line; treat as not run" >&2; exit 2 ;;
  esac
done <<< "$routes"

[ "$status" -eq 0 ] && echo PASS
exit "$status"
