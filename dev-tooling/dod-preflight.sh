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

# Tenant credential wrappers deliberately replace PATH.  Both host-judge CLIs
# are operator-installed user tools, so restore their conventional directory
# before the package resolves the configured candidate chain.
PATH="$HOME/.local/bin:$PATH"
export PATH

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

# THE WHOLE PROMPT, composed by the PACKAGE rather than assembled here:
# `judgement_prompt` over `judgement_rubric` and `judgement_subject`, which is
# the one assembly every host taking uses. A second copy here is a second set of
# rules, and the node reads neither of them.
#
# THE SPEC-STATED JUDGEMENT IS TAKEN HERE TOO, through the gate's own reader. The
# pre-dispatch gate composes it into its verdict twice: its governing-heading
# verdict rides in the subject the rubric grades, and `governing_heading_findings`
# holds an item whose References line omits a heading it returned (check 6).
# Without it this preflight PASSED items the gate then refused at exit 5 — three
# measured on 2026-10-24, each costing a launch slot for the whole pre-launch
# (bd-ib-tka3wb). The verdict and any check 6 findings go to a side file, because
# stdout here is the prompt.
judgement_input=$(mktemp)
trap 'rm -f "$judgement_input" "$judgement_input.last" "$judgement_input.judge" "$judgement_input.stderr" "$judgement_input.governing" "$judgement_input.findings" "$judgement_input.section_findings" "$judgement_input.record" "$judgement_input.reused"' EXIT
python3 - "$install_root" "$repo_root" "$item" "$override" "$judgement_input" > "$judgement_input" <<'PROMPT_PY'
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, f"{sys.argv[1]}/scripts")
sys.path.insert(0, f"{sys.argv[1]}/scripts/_vendor")

from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_findings import (
    definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    judgement_subject,
    judgement_subject_digest,
    rubric_digest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_markers import (
    is_receipt_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    reusable_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    spec_identity_for_governing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    judgement_prompt,
    judgement_rubric,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.store import materialize_work_items, read_work_items

# The reading is the package's own seam: a recorded verdict the component's reuse
# rule still allows decides and starts no judge candidate, as at the gate. The
# registered build may predate the seam, and this script (shipped by v0.244.0)
# must hold on any build it can meet, so such a build takes the judgement every
# run, which is what this script did before the seam existed.
try:
    from livespec_orchestrator_beads_fabro.commands._dod_preflight_governing_reading import (
        preflight_governing_heading_reading,
    )
except ImportError:
    from types import SimpleNamespace

    from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
        governing_heading_findings,
    )
    from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
        host_governing_heading_reader,
    )

    def preflight_governing_heading_reading(*, item, repo, comments, runner):
        del comments
        governing = host_governing_heading_reader(runner=runner)(item=item, repo=repo)
        report = (
            ["governing-heading-kind: unobserved"]
            if governing is None
            else [f"governing-heading-kind: {governing.kind}"]
            + [f"governing-heading: {heading}" for heading in governing.stated_by]
        )
        findings = governing_heading_findings(
            item=item, section=definition_of_done(description=item.description), verdict=governing
        )
        holds = (
            governing is not None
            and bool(findings)
            and len(findings) == len(set(governing.stated_by))
        )
        return SimpleNamespace(
            verdict=governing, report=report, findings=findings, holds=holds
        )


install_root, repo_root, item_id, override, side = sys.argv[1:6]
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
# The Dispatcher refuses malformed section structure before it asks either
# judgement.  Take that same pure reading before even the governing-heading
# host taking, so a malformed candidate spends no model legs here either.
section_findings = definition_of_done_findings(item=item, cwd=repo)
if section_findings:
    Path(f"{side}.section_findings").write_text(
        "".join(f"{finding}\n" for finding in section_findings), encoding="utf-8"
    )
    raise SystemExit(0)
Path(f"{side}.section_findings").write_text("", encoding="utf-8")
comments = tuple(
    comment.text for comment in read_work_item_comments(path=config, work_item_id=item_id)
)
rubric = judgement_rubric(payload_root=Path(install_root))
if rubric is None:
    sys.exit(f"dod-preflight: the registered build ships no readable rubric under {install_root}")
# `None` as the verdict means the judgement could not be taken, and it fails open
# exactly as it does at the gate: no finding is raised on an outage no edit could
# clear. The reading sees the candidate edit above, so a changed governing-heading
# subject finds no record and is taken afresh.
reading = preflight_governing_heading_reading(
    item=item, repo=repo, comments=comments, runner=ShellCommandRunner()
)
governing = reading.verdict
Path(f"{side}.governing").write_text("\n".join(reading.report) + "\n", encoding="utf-8")
# The omission HOLDS only when the reference line names none of the headings the
# verdict returns. Otherwise each finding is advisory: printed with its remedy,
# holding nothing.
Path(f"{side}.findings").write_text(
    "".join(f"finding: {finding}\n" for finding in reading.findings) if reading.holds else "",
    encoding="utf-8",
)
if not reading.holds:
    with Path(f"{side}.governing").open("a", encoding="utf-8") as advisory:
        advisory.writelines(f"advisory: {finding}\n" for finding in reading.findings)
subject = judgement_subject(item=item, cwd=repo, comments=comments, governing=governing)
identity = spec_identity_for_governing(item=item, cwd=repo, governing=governing)
Path(f"{side}.record").write_text(
    json.dumps(
        {
            "item_id": item.id,
            "subject_digest": judgement_subject_digest(
                item=item, cwd=repo, comments=comments, spec_identity=identity.value
            ),
            "rubric_digest": rubric_digest(rubric=rubric),
            "spec_identity_form": identity.form,
            "spec_identity": identity.value,
            "subject_characters": len(subject),
            "carried_rider_count": sum(
                not is_receipt_comment(body=comment) for comment in comments
            ),
        }
    ),
    encoding="utf-8",
)
reused = reusable_verdict(
    comments=comments,
    digest=judgement_subject_digest(
        item=item, cwd=repo, comments=comments, spec_identity=identity.value
    ),
    rubric_digest=rubric_digest(rubric=rubric),
)
if reused is not None:
    Path(f"{side}.reused").write_text(reused.outcome, encoding="utf-8")
    print(f"REUSED {reused.outcome}")
    raise SystemExit(0)
Path(f"{side}.reused").write_text("", encoding="utf-8")
sys.stdout.write(judgement_prompt(gate_prompt=rubric, subject=subject))
PROMPT_PY
if [ -s "$judgement_input.section_findings" ]; then
  cat "$judgement_input.section_findings"
  exit 1
fi
[ -s "$judgement_input" ] || exit 2
[ -f "$judgement_input.governing" ] || exit 2
cat "$judgement_input.governing"
if [ -s "$judgement_input.reused" ]; then
  cat "$judgement_input"
  case "$(cat "$judgement_input.reused")" in
    admitted) exit 0 ;;
    *) exit 1 ;;
  esac
fi
# A check 6 finding that HOLDS — the References line names no governing heading —
# holds the item at the gate whatever the rubric says, so the candidate legs
# would spend two model calls to change nothing. An advisory one was printed with
# the verdict above and holds nothing.
if [ -s "$judgement_input.findings" ]; then
  cat "$judgement_input.findings"
  echo "dod-preflight: FAILED — the References line names none of the governing headings the spec-stated judgement returned; add them verbatim and re-run"
  exit 1
fi

# Run through the host's shared candidate chain rather than invoking bare CLIs
# here.  Besides preserving the configured Codex-first order, this keeps the
# governing-heading, Definition-of-Done and reflector model bindings in one
# resolver.  The legacy string form predates candidate metadata, so bridge its
# recognisable Claude adapter into that resolver until the configuration is
# migrated.
set +e
python3 - "$install_root" "$repo_root" "$judgement_input" "$judgement_input.record" <<'JUDGE_PY'
import json
import sys
from pathlib import Path

sys.path.insert(0, f"{sys.argv[1]}/scripts")
sys.path.insert(0, f"{sys.argv[1]}/scripts/_vendor")

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import parse_adapter_string
from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_gate_candidates import (
    dod_gate_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    parse_judgement_reply,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_candidates import (
    run_candidate_chain,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    did_not_run_comment,
    verdict_comment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import SpecIdentity
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment

repo = Path(sys.argv[2])
prompt = Path(sys.argv[3]).read_text(encoding="utf-8")
record = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))


def candidates(*, cwd: Path) -> tuple[AcpCandidate, ...] | None:
    resolved = dod_gate_candidates(cwd=cwd)
    if resolved is not None:
        return resolved
    entry = (dispatcher_block(cwd=cwd).get("acp_nodes") or {}).get("dod_gate")
    if not isinstance(entry, str):
        return None
    adapter = parse_adapter_string(text=entry)
    if "claude-agent-acp" in adapter.command:
        return (AcpCandidate(adapter=adapter, agent_id="claude-acp"),)
    return None


def is_verdict(*, text: str) -> bool:
    return parse_judgement_reply(reply=text).outcome in {"admitted", "rests-at-needs-human"}


chain = run_candidate_chain(
    prompt=prompt,
    cwd=repo,
    runner=ShellCommandRunner(),
    is_verdict=lambda text: is_verdict(text=text),
    candidate_resolver=candidates,
    bound_input=True,
    caller="dod_preflight",
    journal_spend=True,
)
if chain.reply is None:
    append_work_item_comment(
        path=store_config(repo=repo),
        work_item_id=record["item_id"],
        body=did_not_run_comment(
            item_id=record["item_id"],
            stage="repository-preflight",
            digest=record["subject_digest"],
            rubric_digest=record["rubric_digest"],
            cause=chain.cause,
            subject_characters=record["subject_characters"],
            carried_rider_count=record["carried_rider_count"],
            bound_ended_candidates=chain.bound_ended_candidates,
            attempts=chain.attempts,
        ),
    )
    print(f"DID-NOT-RUN {chain.cause}")
    raise SystemExit(2)
print(chain.reply)
judgement = parse_judgement_reply(reply=chain.reply)
append_work_item_comment(
    path=store_config(repo=repo),
    work_item_id=record["item_id"],
    body=verdict_comment(
        item_id=record["item_id"],
        stage="repository-preflight",
        digest=record["subject_digest"],
        rubric_digest=record["rubric_digest"],
        judgement=judgement,
        spec_identity=SpecIdentity(
            form=record["spec_identity_form"], value=record["spec_identity"]
        ),
    ),
)
outcome = judgement.outcome
raise SystemExit(0 if outcome == "admitted" else 1)
JUDGE_PY
status=$?
set -e

case "$status" in
  0) echo PASS ;;
  1) exit 1 ;;
  *) exit 2 ;;
esac
