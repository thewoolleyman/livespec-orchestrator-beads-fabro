# Released baseline and replay probes

Measured on 2026-10-09 against the normal Codex installation of `v0.178.0`.
This note preserves the executable controls used to prepare the plan's eventual
Proof of Done. It records the faulty baseline; it does not discharge a plan
assertion or replace the independent replay and completeness review.

## Scope and recovery addendum

The complete ownership inventory in note 002 gains one prerequisite:
`bd-ib-nezrrh`, the failed-janitor output-retention repair, belongs to live plan
`failure-evidence-retention`, epic `bd-ib-4aebpa`. Its explicit parent-child edge
and that plan's anchor file agree. `bd-ib-ma3fvj` depends on it and reuses its
artifact format and retention mechanism. This dependency preserves the sibling
plan's ownership. The plan's five assertions and existing carrier map are
unchanged.

The shared no-backgrounding repair `bd-ib-k627ja` shipped in `v0.178.0`.
Following the maintainer's instruction to complete this plan autonomously, the
credential repair resumed through a fresh normal factory dispatch after its
old run was confirmed terminal and the forge showed no PR for its publish
branch. The original `llm-provider-manager` sandbox, cold copy and host worktree
remain preserved. The pending exception to publish that host candidate was
not granted. The already-merged watchdog still requires normal acceptance
reconciliation after credential isolation lands.

## What these probes exercise

Each probe takes the root of an explicitly selected, normally installed plugin
as its sole argument. The plugin's own bootstrap loads its distributed payload;
the service probes print the actual imported module path. Use a release that
contains all relevant merge commits for the final capture and replay, record
its tag and commit, and compare the installed artifact identity with that
release. A checkout invocation does not satisfy the released-build proof leg.

The probes exercise the installed reporting and reconciliation code on the host
with controlled inputs. The orphan probe uses an in-memory ledger and synthetic
engine transports; it never contacts a live factory. The terminal probe uses
synthetic engine, forge and provisioning transports. The janitor probe runs a
real child process that emits the failure output, while its checkout-provisioning
transport is simulated. The path probe executes the public CLI in fresh temporary
directories with the package's fake ledger enabled. These boundaries let a
reviewer reproduce the faults without cancelling a real run, publishing a PR,
changing credentials, or deliberately breaking a live repository.

They establish Dispatcher behavior under those controlled inputs. They do not
establish that the engine's canonical run-store defect has been repaired. That
engine-side question remains with `fabro-currency`, as note 002 records.

## Observed baseline and required replay observations

| Probe | Observation on v0.178.0 | Required observation on the delivered release |
| --- | --- | --- |
| Orphan race | The stale-snapshot case cancels `01NEW`. The known-older control cancels `01OLD`, preserves `01NEW` and `01FOREIGN`, and reads the export back before cancellation. | The stale-snapshot case preserves `01NEW`; the known-older control still cancels `01OLD`. Both preserve `01FOREIGN`, keep the item active, report no reconciliation errors, and read every export back before cancellation. |
| Terminal outcome | The ordinary successful dispatch reaches `green/done` with PR 1. The same successful checkpoint and matching PR accompanied by the worker-exit failure stop at `failed/fabro-run`. | The store-loss case reaches normal PR reconciliation and reports PR 1. The healthy control remains green. Missing checkpoint, missing PR, mismatched head, explicit cancellation, nonterminal checkpoint and unrelated-run controls remain non-green. |
| Janitor cause | The report and journal detail both name `check-passing-decoy.py`; neither names the two actual failed targets. | The report names both actual failed targets from stdout. It does not attribute failure to the passing stderr decoy. Read the retained artifact while the probe directory exists to confirm complete output, original exit code, digest and private permissions. |
| Repository argument | An absent path gets `--repo does not exist`; a regular file and a directory without config both get `ConnectionPrefixMissingError`. | Invalid path/file/config cases identify the submitted argument and the path or config requirement before any prefix diagnosis. A real config lacking its prefix retains the genuine prefix diagnostic. A valid config reaches normal item lookup. |

The path probe deliberately uses a nonexistent synthetic item. Its valid-config
control therefore expects the normal `work-item proof-path not found` refusal;
that is the positive observation that config resolution reached item lookup.
The probes print their observations, not an automatic proof verdict. A process
exit of zero is not sufficient: compare every required observation above, and
publish a non-reproduced verdict when one fails. The janitor artifact-read step
must be added to the probe when the retention interface is delivered; the
baseline build exposes no artifact to read.

The terminal fixture follows a fresh inspection of the original incident:
run `01M4EWVTGAH7MYP6XJH5DMHM7Z` exposes successful `verify_pr`,
`next_node_id=exit`, and checkpoint commit
`ba2ad49406c5f39199b7ea7df041b0e27eeede41`. PR 2683's head is the same commit
and its merge commit is `7748de7c5749f7953e32ff099571132a9a17841b`.
The conclusion still says the worker exited before emitting a terminal event,
with exit status 0. Requiring a fictitious completed `exit` checkpoint would
miss this incident. The fixture uses synthetic identifiers with that same
structure.

## Extract and run the probes

The code fences below are complete script bodies. Extract them from this note,
then run each under the project's normal credential wrapper. The wrapper's
credentials are never printed or incorporated into the fixtures.

```sh
python3 - <<'EXTRACT'
from pathlib import Path
import re
live = Path('plan/run-lifecycle-false-verdicts/research')
research = live if live.is_dir() else Path('plan/archive/run-lifecycle-false-verdicts/research')
note = research / '003-released-baseline-and-replay-probes.md'
out = Path('/tmp/run-lifecycle-proof-probes')
out.mkdir(mode=0o700, exist_ok=True)
for name, code in re.findall(r'```python file=(\S+)\n(.*?)\n```', note.read_text(), re.S):
    (out / name).write_text(code + '\n')
print(out)
EXTRACT
# Set installed_plugin to the normal installed release root being exercised.
with-livespec-env.sh -- python3 /tmp/run-lifecycle-proof-probes/orphan.py "$installed_plugin"
with-livespec-env.sh -- python3 /tmp/run-lifecycle-proof-probes/terminal.py "$installed_plugin"
with-livespec-env.sh -- python3 /tmp/run-lifecycle-proof-probes/janitor.py "$installed_plugin"
with-livespec-env.sh -- python3 /tmp/run-lifecycle-proof-probes/path.py "$installed_plugin"
```

The ownership assertion requires a separate live-ledger read through the package's
complete child-enumeration union, plus the sibling plan anchors named in notes
002 and 003. Re-read that inventory at final capture and replay. None of the
synthetic probes establishes ownership.

## orphan.py

```python file=orphan.py
"""Controlled host exercise of the installed reconciler; never contacts a factory."""
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

plugin = Path(sys.argv[1]).resolve()
os.environ['LIVESPEC_BEADS_FAKE'] = '1'
sys.path.insert(0, str(plugin / 'scripts/bin'))
from _bootstrap import bootstrap
bootstrap()
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs import reconcile_runs
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import read_journaled_runs
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import ReconcileInputs
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.commands._run_attribution import RunAttribution
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

ITEM = 'proof-race'
SERVER = 'https://proof.invalid:32276'

def exercise(stale):
    reset_fake_singleton()
    config = StoreConfig(tenant='proof', prefix='proof', server_user='proof', database='proof', bd_path='bd', fake=True)
    ledger = make_beads_client(config=config)
    append_work_item(path=config, item=WorkItem(id=ITEM, type='task', status='active', title='controlled race', description='synthetic host proof', origin='freeform', gap_id=None, rank='a0', assignee=None, depends_on=(), captured_at='2026-10-09T00:00:00Z', resolution=None, reason=None, audit=None, superseded_by=None))
    with tempfile.TemporaryDirectory(prefix='lifecycle-orphan-proof-') as directory:
        root = Path(directory)
        journal = JournalFile(path=root/'journal.jsonl')
        def stamp(rid):
            journal.append(record={'stage':'dispatch-run-stamp', 'work_item_id':ITEM, 'run_id':rid})
        stamp('01OLD')
        if not stale:
            stamp('01NEW')
        snapshot = read_journaled_runs(path=journal.path)
        calls = []
        readback_before_cancel = []
        class Engine:
            def run(self, *, argv, cwd, timeout_seconds, env=None, stdin=None):
                assert argv[argv.index('--server')+1] == SERVER
                if argv[1] == 'ps':
                    if stale:
                        stamp('01NEW')
                    inventory = [{'run_id':rid,'goal':f'Work-item: {ITEM}\nRepo: {root}','status':{'kind':'running'}} for rid in ('01OLD','01NEW','01FOREIGN')]
                    return CommandResult(exit_code=0, stdout=json.dumps(inventory), stderr='')
                if argv[1] == 'dump':
                    return CommandResult(exit_code=0, stdout='', stderr='')
                raise AssertionError('Unexpected engine command: '+argv[1])
        class Http:
            def send(self, *, method, url, headers, body, timeout_seconds):
                assert url.startswith(SERVER+'/api/v1/runs/')
                assert method == 'POST' and url.endswith('/cancel')
                rid = url.split('/')[-2]
                calls.append(rid)
                readback_before_cancel.append(any(rid in c.get('text','') for c in ledger.list_comments(issue_id=ITEM)))
                return FabroHttpResult(status=200,body='{}',error=None,payload=None,succeeded=True)
        result = reconcile_runs(inputs=ReconcileInputs(repo=root,fabro_bin='synthetic-fabro',id_prefix='proof',items=list(read_work_items(path=config)),journaled=snapshot,runner=Engine(),journal=journal,ledger=ledger,http=Http(),attribution=RunAttribution(metadata_run_ids={'01NEW':ITEM}),blocked_run_grace_seconds=0),factories=[FactoryTarget(name='proof',server=SERVER,dev_token='synthetic-token')])
        output = {'case':'stale-snapshot' if stale else 'known-older-control','cancelled':calls,'new_run_preserved':'01NEW' not in calls,'unrelated_run_preserved':'01FOREIGN' not in calls,'export_read_back_before_each_cancel':readback_before_cancel,'errors':[asdict(e) for e in result.errors],'item_status':list(read_work_items(path=config))[0].status}
        if not stale:
            output['older_run_cancelled'] = '01OLD' in calls
        return output

print(json.dumps({'installed_module':sys.modules[reconcile_runs.__module__].__file__}))
for stale in (True, False):
    print(json.dumps(exercise(stale)))
```

## terminal.py

```python file=terminal.py
"""Exercise installed dispatch routing with controlled engine/forge transports."""
import json
import os
import sys
import tempfile
from pathlib import Path

plugin = Path(sys.argv[1]).resolve()
os.environ['LIVESPEC_BEADS_FAKE'] = '1'
sys.path.insert(0, str(plugin/'scripts/bin'))
from _bootstrap import bootstrap
bootstrap()
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult, FabroRunResult, PollPolicy, run_dispatch
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan

RUN = '01PROOFTERMINAL'
HEAD = 'a'*40
MESSAGE = 'Worker exited before emitting a terminal run event: exit status: 0'
payload_root = Path(sys.modules[build_plan.__module__].__file__).parents[3]
workflow = payload_root/'.fabro/workflows/implement-work-item/workflow.toml'
assert workflow.is_file(), workflow

def exercise(case):
    reset_fake_singleton()
    with tempfile.TemporaryDirectory(prefix='lifecycle-terminal-proof-') as directory:
        root = Path(directory)
        repo = root/'repo'
        repo.mkdir()
        checkout = root/'janitor'
        checkout.mkdir()
        config = json.dumps({'livespec-orchestrator-beads-fabro':{'compat':{'pinned':'master'},'connection':{'tenant':'proof','prefix':'proof','database':'proof','server_user':'proof','fake':True}}})
        (repo/'.livespec.jsonc').write_text(config)
        plan = build_plan(repo=repo,work_item_id='proof-terminal',workflow_toml=workflow,goal_file=root/'goal.md',fabro_bin='synthetic-fabro',janitor=('mise','exec','--','just','check'),janitor_checkout=checkout,config_text=config,default_branch='master')
        journal = JournalFile(path=root/'journal.jsonl')
        nodes = ['start','dod_gate','implement','implementation_diff','janitor','publish_draft','proof_capture','review','proof_verify','pr','verify_pr']
        checkpoint = {'timestamp':'2026-10-09T03:15:20Z','current_node':'verify_pr','next_node_id':'exit','completed_nodes':nodes,'git_commit_sha':HEAD,'node_outcomes':{n:{'status':'succeeded'} for n in nodes}}
        message = 'Cancelled by operator' if case == 'cancelled' else MESSAGE
        inspected = {'run_id':RUN,'status':{'kind':'succeeded' if case=='healthy' else 'failed','reason':'terminated'},'conclusion':{'status':'succeeded' if case=='healthy' else 'failed','failure':{'reason':'terminated','detail':{'category':'deterministic','message':message}}},'checkpoint':checkpoint}
        if case=='no-checkpoint':
            inspected.pop('checkpoint')
        if case=='nonterminal-checkpoint':
            checkpoint['current_node'] = 'proof_verify'
            checkpoint['next_node_id'] = 'pr'
            checkpoint['completed_nodes'] = nodes[:-2]
            checkpoint['node_outcomes'] = {n:{'status':'succeeded'} for n in nodes[:-2]}
        if case=='wrong-run':
            inspected['run_id'] = '01UNRELATED'
        pr = {'number':1,'state':'MERGED','headRefName':plan.branch,'headRefOid':'b'*40 if case=='wrong-head' else HEAD,'mergeCommit':{'oid':'c'*40},'autoMergeRequest':None,'mergeStateStatus':'CLEAN','statusCheckRollup':[],'additions':1,'deletions':1}
        class Launcher:
            def launch(self, *, plan, runner, journal):
                return FabroRunResult(command=CommandResult(exit_code=0 if case=='healthy' else 1,stdout='',stderr='' if case=='healthy' else message),run_id=RUN)
        class Runner:
            def run(self, *, argv, cwd, timeout_seconds, env=None, stdin=None):
                assert Path(cwd).is_relative_to(root)
                if argv[0]=='synthetic-fabro':
                    assert argv[1]=='inspect', argv
                    return CommandResult(exit_code=0,stdout=json.dumps([inspected]),stderr='')
                if argv[0]=='gh':
                    if argv[1]=='api' and argv[-1].endswith('/pulls'):
                        return CommandResult(exit_code=0,stdout=json.dumps([{'number':1}]),stderr='')
                    assert argv[1]=='pr' and argv[2] in ('view','list'), argv
                    if case=='no-pr':
                        return CommandResult(exit_code=1,stdout='',stderr='no pull request found')
                    return CommandResult(exit_code=0,stdout=json.dumps([pr] if argv[2]=='list' else pr),stderr='')
                assert argv[0] in ('git','mise'), argv
                return CommandResult(exit_code=0,stdout='',stderr='')
        result = run_dispatch(plan=plan,runner=Runner(),journal=journal,sleep=lambda _:None,poll=PollPolicy(attempts=1,interval_seconds=0),fabro_launcher=Launcher())
        records = [json.loads(line) for line in journal.path.read_text().splitlines()]
        return {'case':case,'status':result.status,'stage':result.stage,'pr_number':result.pr_number,'run_id':result.fabro_run_id,'detail':result.detail,'journal_stages':[r['stage'] for r in records]}

print(json.dumps({'installed_module':sys.modules[run_dispatch.__module__].__file__}))
for case in ('healthy','store-loss','no-checkpoint','no-pr','wrong-head','cancelled','nonterminal-checkpoint','wrong-run'):
    print(json.dumps(exercise(case)))
```

## janitor.py

```python file=janitor.py
"""Exercise installed post-merge reporting with a real, synthetic failing check."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

plugin = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(plugin/'scripts/bin'))
from _bootstrap import bootstrap
bootstrap()
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult, DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_janitor import post_merge
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan, PrView

with tempfile.TemporaryDirectory(prefix='lifecycle-janitor-proof-') as directory:
    root = Path(directory)
    repo = root/'repo'
    repo.mkdir()
    checkout = root/'janitor'
    checkout.mkdir()
    config = '{"livespec-orchestrator-beads-fabro":{"compat":{"pinned":"master"}}}'
    (repo/'.livespec.jsonc').write_text(config)
    check = root/'synthetic_check.py'
    # The false cause is deliberately the last stderr line. The failure list
    # is on stdout, followed by enough output to defeat a tail-only reader.
    check.write_text("import sys\nprint('Failed targets (2):')\nprint('  - check-real-alpha')\nprint('  - check-real-beta')\nprint('\\n'.join('later ordinary output '+str(i) for i in range(300)))\nprint('python dev-tooling/check-passing-decoy.py', file=sys.stderr)\nsys.exit(7)\n")
    command = (sys.executable, str(check))
    plan = build_plan(repo=repo, work_item_id='proof-janitor', workflow_toml=root/'workflow.toml', goal_file=root/'goal.md', fabro_bin='synthetic-fabro', janitor=command, janitor_checkout=checkout, config_text=config, default_branch='master')
    journal = JournalFile(path=root/'journal.jsonl')
    class Runner:
        def run(self, *, argv, cwd, timeout_seconds, env=None, stdin=None):
            assert Path(cwd).is_relative_to(root)
            if tuple(argv) == command:
                p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout_seconds)
                return CommandResult(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
            # Only provisioning/refresh transport is simulated. The installed
            # reporting code and the failing check process run unchanged.
            assert argv[0] in ('git', 'mise'), argv[0]
            return CommandResult(exit_code=0, stdout='', stderr='')
    outcome = post_merge(outcome_type=DispatchOutcome,plan=plan,runner=Runner(),journal=journal,merged=PrView(number=1,state='MERGED',auto_merge_armed=False,merge_state_status='CLEAN',merge_sha='a'*40,terminal_required_check_failures=()))
    records = [json.loads(line) for line in journal.path.read_text().splitlines()]
    record = next(r for r in records if r.get('stage')=='janitor-post-merge')
    print(json.dumps({'installed_module':sys.modules[post_merge.__module__].__file__,'status':outcome.status,'stage':outcome.stage,'detail':outcome.detail,'journal_record':record}))
```

## path.py

```python file=path.py
"""Exercise the installed public reconcile-merged CLI in isolated directories."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

plugin = Path(sys.argv[1]).resolve()
cli = plugin/'scripts/bin/dispatcher.py'
assert cli.is_file(), cli
with tempfile.TemporaryDirectory(prefix='lifecycle-path-proof-') as directory:
    root = Path(directory)
    (root/'regular-file').write_text('not a directory')
    for name in ('missing-config','missing-prefix','valid-config'):
        (root/name).mkdir()
    connection = {'tenant':'proof','database':'proof','server_user':'proof','fake':True}
    (root/'missing-prefix/.livespec.jsonc').write_text(json.dumps({'livespec-orchestrator-beads-fabro':{'connection':connection}}))
    (root/'valid-config/.livespec.jsonc').write_text(json.dumps({'livespec-orchestrator-beads-fabro':{'connection':{**connection,'prefix':'proof'}}}))
    for name in ('absent-repository-name','regular-file','missing-config','missing-prefix','valid-config'):
        p = subprocess.run([sys.executable,str(cli),'reconcile-merged','--repo',name,'--item','proof-path','--json'],cwd=root,env={**os.environ,'LIVESPEC_BEADS_FAKE':'1'},text=True,capture_output=True,timeout=45)
        print(json.dumps({'case':name,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}),flush=True)
```

