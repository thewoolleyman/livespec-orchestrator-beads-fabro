#!/usr/bin/env bash
# The REPOSITORY PREFLIGHT taking of the Definition-of-Done judgement.
#
# `contracts.md`'s one-rubric-one-subject clause names three HOST TAKINGS — this
# preflight, the Dispatcher's pre-admission judgement and its pre-dispatch
# judgement — and binds all three to ONE rubric and ONE subject: the `dod_gate`
# node's own prompt file, read from the plugin build that will execute the
# dispatch, over the item's effective criteria, the body of each heading its
# reference line names, and its operator riders. A taking other than the node may
# append ONLY an ending contract stating the verdict form it must return.
#
# So this script composes NOTHING. It resolves the registered build, asks the
# package for the prompt, and runs it on every candidate of the gate's chain.
# Everything it used to assemble itself — a `Goal:` preamble built out of the
# item's fields, a capability-source sentence, a paragraph about how to grade
# proof-mode feasibility — was prose the node has never read. Measured on this
# repository's own items between 2026-10-22 00:21Z and 08:13Z, four preflight
# PASSes were followed by an in-run refusal on unchanged Definition-of-Done
# bytes, and twice the same leg returned opposite verdicts on identical text.
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
# install registry rather than hard-coded, so a release moves the rubric with it.
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

# EVERY candidate of the in-run gate's chain. Measured 2026-10-20 over five
# PASS-then-refused items. A hard-coded `sonnet` here graded more leniently than
# the gate's `acp_nodes.dod_gate` route (References and deliverable-policy
# misses). And the admission session-headroom filter can skip the claude-acp
# primary at dispatch time, so the gate then runs a FALLBACK (bd-ib-h7iaai: the
# gate ran codex-acp gpt-5.6-terra while this script graded on claude-opus-5).
# Which candidate a dispatch will select is not knowable here, so the judgement
# runs on every candidate in the chain and passes only if all of them pass.
#
# IT NO LONGER REFUSES ON AN ABSENT `dispatcher.sandbox_capabilities` ARRAY. That
# refusal was this script grading the capability question itself, which is the
# rubric's to grade: the rubric resolves the set in its own order and reports
# `sandbox-capabilities: unpublished` where neither source answers, and the node
# grades by exactly that.
routes=$(python3 - "$install_root" "$repo_root" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, f"{sys.argv[1]}/scripts")
sys.path.insert(0, f"{sys.argv[1]}/scripts/_vendor")
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
block = dispatcher_block(cwd=Path(sys.argv[2]))
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

# THE WHOLE PROMPT, composed by the PACKAGE rather than assembled here:
# `judgement_prompt` over `judgement_rubric` and `judgement_subject`, which is
# the one assembly every host taking uses. A second copy here is a second set of
# rules, and the node reads neither of them.
judgement_input=$(mktemp)
trap 'rm -f "$judgement_input" "$judgement_input.last"' EXIT
python3 - "$install_root" "$repo_root" "$item" "$override" > "$judgement_input" <<'PROMPT_PY'
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, f"{sys.argv[1]}/scripts")
sys.path.insert(0, f"{sys.argv[1]}/scripts/_vendor")

from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    judgement_subject,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    judgement_prompt,
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items

install_root, repo_root, item_id, override = sys.argv[1:5]
repo = Path(repo_root)
config = store_config(repo=repo)
items = materialize_work_items(records=read_work_items(path=config))
if item_id not in items:
    sys.exit(f"dod-preflight: {item_id} is not a work-item of this repository's tenant")
item = items[item_id]
# The optional description file is substituted into the ITEM rather than into a
# rendered subject, so the same ratified parse reads the candidate edit.
if override:
    item = replace(item, description=Path(override).read_text(encoding="utf-8"))
comments = tuple(
    comment.text for comment in read_work_item_comments(path=config, work_item_id=item_id)
)
rubric = judgement_rubric(payload_root=Path(install_root))
if rubric is None:
    sys.exit(f"dod-preflight: the registered build ships no readable rubric under {install_root}")
sys.stdout.write(
    judgement_prompt(
        gate_prompt=rubric,
        subject=judgement_subject(item=item, cwd=repo, comments=comments),
    )
)
PROMPT_PY
[ -s "$judgement_input" ] || exit 2

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
  # READ by the package, for the same reason the prompt is COMPOSED by it: the
  # ending contract states one verdict form, and `parse_judgement_reply` is the
  # one reader of it. A second parse here is how this script came to accept a
  # bare `PASS` the contract never asked any judge to write.
  outcome=$(python3 - "$install_root" "$last" <<'VERDICT_PY'
import sys
sys.path.insert(0, f"{sys.argv[1]}/scripts")
sys.path.insert(0, f"{sys.argv[1]}/scripts/_vendor")
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    parse_judgement_reply,
)
print(parse_judgement_reply(reply=sys.argv[2]).outcome)
VERDICT_PY
) || exit 2
  case "$outcome" in
    admitted) ;;
    rests-at-needs-human) status=1 ;;
    *) echo "dod-preflight: $agent $model gave no verdict line; treat as not run" >&2; exit 2 ;;
  esac
done <<< "$routes"

[ "$status" -eq 0 ] && echo PASS
exit "$status"
