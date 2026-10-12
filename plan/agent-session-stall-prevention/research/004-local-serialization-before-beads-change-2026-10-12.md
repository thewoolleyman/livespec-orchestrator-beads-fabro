# Local serialization alternatives before changing Beads

## Maintainer correction: the required topology includes independent hosts

This correction supersedes this note's host-domain recommendation, not its
measurements. The maintainer's ruling, relayed on 2026-10-12, is:

> The assumption that writes only occur from a single host is invalid. Beads is
> a server, and it's exposed as a DOLT server. There may be writes in the future
> from multiple hosts or multiple containers or cloud instances. There may not
> even be a shared state where places are writing to beads.

A host/kernel/filesystem fence therefore does not cover the required canonical
per-epic ownership topology. The passing finite controls below establish their
stated single-domain behavior only; the independent-domain negative already
shows the missing guarantee. Routing all writers through a presumed shared host
is not the accepted requirement. No universal or released recovery proof is
claimed from this experiment.

The local-first-plan-serialization proposal was generated in an unpublished
worktree and has been withdrawn without ratification or publication. The
worktree and local branch were removed; original proposal/journal bytes remain
private evidence. Beads PR 1 remains closed. Whether an existing server-side bd
primitive provides a satisfactory local integration, or a Beads change is
necessary, remains undecided. The relay owner owns that reassessment; this plan
will consume its result when it affects the recovery ownership fence and will
not launch parallel backend design. Pane-adapter work and all unrelated work
continue through their existing owners.


## Maintainer direction and finding

On 2026-10-12 the maintainer required modification or a fork of Beads only when a
local alternative cannot meet the requirement, or is substantially inferior or
complex. He explicitly directed closing the existing PR until that is proved.
[Beads PR 1](https://github.com/thewoolleyman/beads/pull/1) was read back CLOSED at
2026-10-12T06:23:43Z. Its branch `feat/relay-conditional-transition-v122` and head
`e82e0f4ed17cc837acdc49ea35cf26e68b52473a` remain preserved. No merge, installation,
schema change or backend release was performed by this investigation.

**Necessity of changing Beads has not been established.** A finite experiment
using the installed guarded Beads CLI demonstrated a small local serialization
mechanism with real separate processes, native ledger writes, crash recovery and
stale-request refusal on one declared host. It passed eleven controls. It also
measured a negative control showing why independent ownership scopes cannot be
advertised as equivalent. This is mechanism feasibility, not installed product,
released Codex/Herdr recovery, independent replay, or plan Proof of Done.

The current contract does NOT require metadata and comments to commit in one
physical transaction. `SPECIFICATION/contracts.md`, section "Required result,
budget and progress epoch", explicitly says: "A partial write MUST be diagnosable
and must not authorize a fresh dispatch until reconciled." Requiring a new atomic
metadata-plus-comment backend operation was a stronger implementation choice in
`bd-ib-vvf45c`; it is not proof that existing local mechanisms are inadequate.

## What was executed

The exact installed public entry was `/usr/local/bin/bd`, version
`1.2.2 (6c124203e)`, matching upstream source
`6c124203e771433a3550c348771a5b5e27fd3c21`. Calls ran from the target repository
under its configured `with-livespec-env.sh` wrapper. No private delegate,
credential bypass, raw SQL mutation, shared service change or binary replacement
was used. One read-only public `bd sql` query checked an existing foreign value;
it was not the transition implementation.

The experiment used owned disposable no-history records. Seven records in the
final positive run and one in the final negative control were deleted through
public `bd delete`; exact post-delete `bd show` outcomes were 1 (absent). Failed
preliminary runs also ran their exact owned-record cleanup. Original command
arguments, stdout, stderr and numeric outcomes remain in the private evidence
roots named below. No production obligation or real recovery command was issued.

The local mechanism:

1. Resolve one canonical host ownership root independently of caller `TMPDIR` and
   worktree; hold a per-epic kernel ownership descriptor without unlinking it.
2. Read current canonical state after obtaining ownership. Refuse a stale prior
   revision before mutation; inspect the original operation receipt before
   refusing a legitimate replay.
3. Preserve the original deadline and store the new authority plus stable
   operation receipt in ONE existing metadata update. Send only the owned
   top-level metadata key, preserving unrelated server-side fields.
4. Reconcile the native comment projection from that receipt. A crash between
   commands is observable; production readers must withhold dispatch until the
   canonical progress comment and pointer are reconciled.
5. Pass the ownership descriptor into any native write child. Parent death must
   not release ownership while a child can still commit. Takeover follows actual
   process/descriptor release, not a guessed lease expiry.

The sample operation advances one revision. Its receipts demonstrate logical
idempotency for that fixed operation; they do not assert exactly-once arbitrary
shell effects or implement the complete causal-recovery authorization grammar.

| Executed control | Outcome |
| --- | --- |
| independent processes distinct TMPDIR | Passed |
| duplicate delivery reuses original effect | Passed |
| stale generation after new owner | Passed |
| death before commit | Passed |
| death after metadata before comment | Passed |
| paused live owner is not stolen | Passed; 0.270 s |
| unrelated epic remains available | Passed |
| actual owner process death releases kernel ownership | Passed; 3.181 s |
| dead parent with live write child keeps ownership | Passed; 3.420 s |
| revision does not depend on timestamp precision | Passed |
| foreign server value preserved without resending | Passed |

The positive driver returned numeric **0**. It includes real child exits **17**
(before metadata), **19** (after metadata, before comment), **21** (parent death
while its descriptor-holding child remains live), and **-9** for the specifically
owned idle test holder. The experiment never killed a real hook, commit, pane or
factory actor. Native failed operations are preserved; no masked pipeline exit
is used to establish these outcomes.

## Discriminating negative control

Both independent processes read revision 0 while holding DIFFERENT ownership
roots. A committed first; B then submitted its stale payload in a fresh native
transaction. Both public metadata updates returned 0, but the final revision was
1 with only B's receipt. The negative driver returned 0 because it observed this
expected loss. This is an actual native-ledger failure of the unfenced design,
not a mock. Separate ownership roots on the SAME host simulate the absence of a
shared kernel fence; no two-host acceptance proof is claimed.

The first negative attempt issued both native transactions simultaneously. Dolt
correctly rejected one with Error 1213 / serialization failure, causing that
harness to return 1 because its expectation that both must commit was wrong.
That refusal is retained, not retried or counted as a positive result. Staggering
the writes after both callers read old state discriminates SQL transaction
serialization from serialization of the entire read/validate/write operation.

## Alternatives and actual limits

| Approach | Finding | Remaining limit |
| --- | --- | --- |
| Existing atomic claim | Public guarded `bd update --claim` returned 3 before any write: non-lifecycle; use status active. | Pinned claim requires native open/in_progress statuses and does not supply the complete transition or fenced release. Do not bypass the guard. |
| Append-only comments alone | Preserve observations but supply no exclusive execution ownership. | Concurrent readers can select actions before an ordering or winner is durable. An immutable log still needs a serialized executor for the protected effect. |
| Correctly scoped local ownership and native receipts | Eleven real-process/native-ledger controls passed. | All participating writers must use the same declared host/root and protocol. Independent kernels/roots are not protected. |
| Route writers through the existing overseer owner | Existing `overseer/_supervisor_lifecycle.py` already holds a per-store singleton for its lifetime. It is a candidate place to apply the measured ownership discipline. | Routing, authorization, native-child descriptor lifetime, coherent partial-write reads and startup reconciliation are NOT implemented or proven by this experiment. Existing singleton alone is not proof of these behaviors. |
| Public raw SQL wrapper | `bd sql` exists, but its own help says it bypasses the storage layer. | A mutation wrapper would conflict with the no-direct-plugin-SQL design and would couple the plugin to schema and backend transaction details. None was used. |
| Proposed Beads conditional operation | Can provide a backend transaction across distributed participating clients. | The closed candidate changes 24 files (1496 additions, 755 removals) and adds a compatible backend release/installation/maintenance obligation. Line counts alone do not prove relative complexity. |

The direct local-lock prototype conflicts with `SPECIFICATION/constraints.md`
"Process boundaries", which currently forbids plugin lockfiles/advisory locks.
The experiment is a research probe, not an authorized runtime exception. Adopting
that exact form requires a narrow spec amendment through the normal valve. An
alternative is to place serialization in the existing sibling service and route
all sanctioned writers through that owner; that requires source/design review
and sibling-owned integration, not a new daemon or a second canonical ledger.
No implementation restriction has been silently waived here.

The key choice is the actual supported topology. If all protected writers are
routed through one declared host owner, the measured local mechanism is a viable
candidate and no evidence currently establishes that its complexity or behavior
is substantially worse than maintaining the backend fork. If the requirement is
independent writers or automatic takeover on several hosts without such routing,
this local prototype does not satisfy it. That stronger topology must be
established from the real requirement and tested before claiming a backend
change necessary. Merely being able to run a CLI from another host is not itself
that requirement.

## Preliminary outcomes retained honestly

The first positive driver returned 1 at its final read-only check because it
queried `issues` for a record routed to `wisps`. Its core behavioral assertions
had run, but this run is not counted as the final pass. The second returned 1
when a large numeric-input control expected 9007199254740993; the existing create
path had already rounded the value to 9007199254740992. The final run compares the
foreign value before and after the local update instead. It proves preservation
of the value actually present and does NOT claim lossless numeric ingress or a
repair to Beads JSON formatting. These are separate limitations from conditional
transition necessity.

## Evidence and reproduction

- Positive source SHA256: `a3fbb663daf79828057bc05c33a7c60ade70275a884977313262aceaab0557c3`.
- Positive receipt SHA256: `01c8caecd11be3aa05de9a3f9253bb5ffc54f1becd99a013459d3818ff087c40`.
- Negative source SHA256: `0cf87b73bfad3074ce127d894c6cda914d9e35ffa61c3d25eae6127bd53c2d2b`.
- Negative receipt SHA256: `39afc59510b02fa25308850994e9885ae4f99df75ce5f22475c7037512019c02`.
- Positive evidence: `/tmp/stall-local-serialization-proof-20261012-v3/`.
- Negative evidence: `/tmp/stall-local-independent-roots-proof-20261012-v2/`.
- Preliminary originals: corresponding roots without `-v3` / with `-v2`, and
  `/tmp/stall-local-independent-roots-proof-20261012/`.
- Durable maintainer ruling and PR closure readback: `bd-ib-vvf45c` comment
  `01a12ec9-9573-7b4f-b965-026a195cd63f`.

For an independent finite reproduction, save the following two complete drivers
as Python files, select fresh private proof-root names, and update the negative
driver's source-module path to that positive driver. Root changes alter the
source digests and must be disclosed. Run each under the configured credential
wrapper from the target repo. The completed-root guard prevents an unnoticed
rerun against prior evidence. Both drivers clean up only their generated ids.
They create temporary ledger records; they are research probes, not production
installation procedures. Do not run without the target's normal store authority.

```python
"""Finite local-design experiment; no product installation or Beads changes."""
from pathlib import Path
import argparse, contextlib, fcntl, hashlib, json, os, subprocess, sys, time, uuid
ROOT=Path('/data/projects/livespec-orchestrator-beads-fabro')
BASE=Path('/tmp/stall-local-serialization-proof-20261012-v3')
BASE.mkdir(mode=0o700,exist_ok=True)
LOG=BASE/'calls'; LOG.mkdir(exist_ok=True)
KEY='stall_local_design_probe'
HELD_FD=None

def bd(*args):
    start=time.time_ns()
    r=subprocess.run(['/usr/local/bin/bd',*args],cwd=ROOT,capture_output=True,text=True,timeout=30,pass_fds=(() if HELD_FD is None else (HELD_FD,)))
    (LOG/f'{start}-{os.getpid()}.json').write_text(json.dumps({'args':args,'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))
    if r.returncode:raise RuntimeError(f'public bd exit {r.returncode}: {r.stderr[:600]}')
    return json.loads(r.stdout) if r.stdout.strip().startswith(('[','{')) else r.stdout

def state(item):
    row=bd('show',item,'--json'); row=row[0] if isinstance(row,list) else row
    return row.get('metadata',{}).get(KEY)

@contextlib.contextmanager
def owner(item,budget=8):
    global HELD_FD
    # Every participating checkout/TMPDIR resolves the SAME declared host root.
    path=BASE/(hashlib.sha256(item.encode()).hexdigest()+'.lock')
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    until=time.monotonic()+budget
    try:
        while True:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=until:raise TimeoutError('live owner retained; no steal or unlink')
                time.sleep(.02)
        HELD_FD=fd
        yield fd
    finally:
        HELD_FD=None
        os.close(fd) # NEVER unlink a lockfile while any writer could hold it.

def reconcile_comment(item,op):
    marker=json.dumps({'local_probe_commit':op},sort_keys=True)
    rows=bd('comments',item,'--json')
    hits=[x for x in rows if x.get('text')==marker]
    if not hits:bd('comments','add',item,marker,'--json')

def transition(item,op,expected,crash=None):
    with owner(item):
        old=state(item)
        receipts=old['receipts']
        if op in receipts:
            # Receipt precedes stale-prior checking: retry returns the original effect.
            reconcile_comment(item,op)
            return {'verdict':'replay','effect':receipts[op],'generation':old['generation']}
        if old['revision']!=expected:return {'verdict':'stale','revision':old['revision']}
        if crash=='before':os._exit(17)
        new=dict(old);new['revision']=expected+1;new['generation']=str(uuid.uuid4())
        effect={'revision':new['revision'],'original_deadline':old['original_deadline']}
        new['receipts']={**receipts,op:effect}
        bd('update',item,'--metadata',json.dumps({KEY:new}),'--json')
        if crash=='after':os._exit(19)
        reconcile_comment(item,op)
        return {'verdict':'committed','effect':effect,'generation':new['generation']}

def worker(item,op,expected,crash=None):
    return subprocess.Popen([sys.executable,__file__,'worker',item,op,str(expected),crash or 'none'],env={**os.environ,'TMPDIR':str(BASE/f'tmp-{uuid.uuid4().hex}')},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)

def finish(p):
    out,err=p.communicate(timeout=35)
    return {'exit':p.returncode,'result':json.loads(out) if out.strip().startswith('{') else out,'stderr':err}

def create(item):
    bd('create','--id',item,'--type','task','--title','Disposable local serialization design proof','--description','Owned finite mechanism experiment, not a product obligation or acceptance record.','--no-history','--metadata',json.dumps({KEY:{'revision':0,'generation':'initial','original_deadline':'2026-10-12T00:00:00Z','receipts':{}},'foreign_probe':{'large':9007199254740993}}),'--json')

def main():
    if (BASE/'receipt.json').exists():raise RuntimeError('completed experiment will not silently rerun')
    items=[];results=[];foreign_initial={}
    def fresh():
        item='bd-ib-local-probe-'+uuid.uuid4().hex[:12];items.append(item);create(item);row=bd('show',item,'--json');foreign_initial[item]=(row[0] if isinstance(row,list) else row)['metadata']['foreign_probe'];return item
    def record(name,**kw):
        results.append({'case':name,**kw});(BASE/'partial-results.json').write_text(json.dumps(results,indent=2))
    try:
        item=fresh()
        pair=[worker(item,'race-A',0),worker(item,'race-B',0)]
        observed=[finish(p) for p in pair]
        assert all(x['exit']==0 for x in observed),observed
        assert sorted(x['result']['verdict'] for x in observed)==['committed','stale'],observed
        s=state(item);assert s['revision']==1 and len(s['receipts'])==1
        record('independent_processes_distinct_TMPDIR',observed=observed,final=s)
        prior=s
        duplicate=list(prior['receipts'])[0]
        observed=[finish(worker(item,duplicate,0)) for _ in range(2)]
        assert all(x['result']['verdict']=='replay' for x in observed)
        assert state(item)==prior
        record('duplicate_delivery_reuses_original_effect',observed=observed)
        observed=finish(worker(item,'stale-owner',0));assert observed['result']['verdict']=='stale';assert state(item)==prior
        record('stale_generation_after_new_owner',observed=observed,unchanged=True)
        item=fresh();r=finish(worker(item,'crash-before',0,'before'));assert r['exit']==17
        assert state(item)['revision']==0
        recovery=finish(worker(item,'crash-before',0));assert recovery['result']['verdict']=='committed'
        record('death_before_commit',original=r,recovery=recovery)
        item=fresh();r=finish(worker(item,'crash-after',0,'after'));assert r['exit']==19
        assert state(item)['revision']==1 and len(bd('comments',item,'--json'))==0
        recovery=finish(worker(item,'crash-after',0));assert recovery['result']['verdict']=='replay'
        comments=bd('comments',item,'--json');assert len(comments)==1
        assert state(item)['revision']==1
        record('death_after_metadata_before_comment',original=r,recovery=recovery,comment_count=len(comments))
        item=fresh();ready=BASE/'holder-ready';ready.unlink(missing_ok=True)
        holder=subprocess.Popen([sys.executable,__file__,'hold',item,str(ready)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        until=time.monotonic()+10
        while not ready.exists() and time.monotonic()<until:time.sleep(.02)
        assert ready.exists(),'holder readiness missing'
        start=time.monotonic()
        try:
            with owner(item,budget=.25):raise AssertionError('stole live owner')
        except TimeoutError:pass
        record('paused_live_owner_is_not_stolen',elapsed=time.monotonic()-start)
        other=fresh();observed=finish(worker(other,'unrelated',0));assert observed['result']['verdict']=='committed'
        record('unrelated_epic_remains_available',observed=observed)
        holder.kill();holder.communicate(timeout=10);assert holder.returncode==-9
        start=time.monotonic();recovery=finish(worker(item,'dead-owner',0));assert recovery['result']['verdict']=='committed'
        record('actual_owner_process_death_releases_kernel_ownership',original_exit=holder.returncode,recovery=recovery,elapsed=time.monotonic()-start)
        item=fresh();ready=BASE/'orphan-ready'
        parent=subprocess.Popen([sys.executable,__file__,'orphan-parent',item,str(ready)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        until=time.monotonic()+10
        while not ready.exists() and time.monotonic()<until:time.sleep(.01)
        assert ready.exists(),'in-flight child readiness absent'
        assert parent.wait(timeout=10)==21
        started=time.monotonic();r=finish(worker(item,'successor-after-orphan',0));elapsed=time.monotonic()-started
        assert r['exit']==0 and r['result']['verdict']=='stale',r
        assert elapsed>=.6, 'successor entered while old native write could still occur'
        assert state(item)['revision']==1
        record('dead_parent_with_live_write_child_keeps_ownership',parent_exit=21,observed=r,elapsed=elapsed,child_pid=int(ready.read_text()))
        item=fresh();r=finish(worker(item,'same-second-A',0));r2=finish(worker(item,'same-second-B',1))
        assert r['result']['verdict']==r2['result']['verdict']=='committed'
        assert r['result']['generation']!=r2['result']['generation'] and state(item)['revision']==2
        record('revision_does_not_depend_on_timestamp_precision',observed=[r,r2])
        # Exact large numeric foreign field stays server-side: only our top-level key is sent.
        value=bd('sql',f"SELECT JSON_EXTRACT(metadata, '$.foreign_probe.large') AS large FROM issues WHERE id='{item}' UNION ALL SELECT JSON_EXTRACT(metadata, '$.foreign_probe.large') AS large FROM wisps WHERE id='{item}'",'--json')
        assert len(value)==1, 'positive control: exactly one retained regular-or-wisp row required'
        assert str(value[0]['large'])==str(foreign_initial[item]['large']),value
        record('foreign_server_value_preserved_without_resending',initial=foreign_initial[item],observed=value,numeric_ingress_limitation='Existing create path rounded the supplied large number before local transitions; no precision repair claimed.')
        receipt={'kind':'local finite design feasibility only; not installed recovery, released host proof, or cross-host fencing','public_bd':'/usr/local/bin/bd','script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'results':results,'cleanup':[]}
    finally:
        cleanup=[]
        for item in items:
            bd('delete',item,'--dry-run');bd('delete',item,'--force')
            r=subprocess.run(['/usr/local/bin/bd','show',item,'--json'],cwd=ROOT,capture_output=True,text=True,timeout=30)
            assert r.returncode!=0,'owned probe still present'
            cleanup.append({'id':item,'absent_exit':r.returncode})
        if 'receipt' in locals():
            receipt['cleanup']=cleanup;(BASE/'receipt.json').write_text(json.dumps(receipt,indent=2))
            print(json.dumps({'cases':len(results),'receipt':str(BASE/'receipt.json'),'owned_records_deleted':len(cleanup)}))
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='orphan-parent':
        with owner(sys.argv[2]) as fd:
            subprocess.Popen([sys.executable,__file__,'orphan-child',sys.argv[2],str(fd),sys.argv[3]],pass_fds=(fd,),stdout=(BASE/'orphan-child.stdout').open('w'),stderr=(BASE/'orphan-child.stderr').open('w'))
            os._exit(21)
    elif len(sys.argv)>1 and sys.argv[1]=='orphan-child':
        HELD_FD=int(sys.argv[3]);Path(sys.argv[4]).write_text(str(os.getpid()));time.sleep(1.2)
        old=state(sys.argv[2]);old['revision']=1;old['generation']='orphan-write';old['receipts']={'orphan-write':{'revision':1,'original_deadline':old['original_deadline']}}
        bd('update',sys.argv[2],'--metadata',json.dumps({KEY:old}),'--json');os.close(HELD_FD)
    elif len(sys.argv)>1 and sys.argv[1]=='worker':
        print(json.dumps(transition(sys.argv[2],sys.argv[3],int(sys.argv[4]),None if sys.argv[5]=='none' else sys.argv[5])))
    elif len(sys.argv)>1 and sys.argv[1]=='hold':
        with owner(sys.argv[2]):Path(sys.argv[3]).write_text(str(os.getpid()));time.sleep(120)
    else:main()
```

```python
from pathlib import Path
import subprocess,json,sys,time,uuid,os,importlib.util
spec=importlib.util.spec_from_file_location('p','/tmp/stall-local-serialization-probe-v3.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
base=Path('/tmp/stall-local-independent-roots-proof-20261012-v2');base.mkdir(mode=0o700,exist_ok=True)
if len(sys.argv)>1:
 item,who=sys.argv[1:3];p.BASE=base/who;p.BASE.mkdir(exist_ok=True)
 with p.owner(item):
  old=p.state(item);(base/(who+'-ready')).write_text('ready')
  until=time.monotonic()+10
  while not (base/'go').exists() and time.monotonic()<until:time.sleep(.01)
  assert (base/'go').exists()
  new=dict(old);new['revision']+=1;new['generation']=who;new['receipts']={who:{'revision':new['revision'],'original_deadline':old['original_deadline']}}
  if who=='B':
   until=time.monotonic()+10
   while not (base/'A-complete').exists() and time.monotonic()<until:time.sleep(.01)
   assert (base/'A-complete').exists()
  p.bd('update',item,'--metadata',json.dumps({p.KEY:new}),'--json')
  if who=='A':(base/'A-complete').write_text('native mutation finished')
  print(json.dumps({'prior':old['revision'],'verdict':'committed','writer':who}))
else:
 assert not (base/'receipt.json').exists()
 item='bd-ib-local-probe-'+uuid.uuid4().hex[:12];workers=[]
 try:
  p.create(item)
  workers=[subprocess.Popen([sys.executable,__file__,item,who],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for who in ['A','B']]
  until=time.monotonic()+15
  while not all((base/(w+'-ready')).exists() for w in ['A','B']) and time.monotonic()<until:time.sleep(.01)
  assert all((base/(w+'-ready')).exists() for w in ['A','B'])
  (base/'go').write_text('go');rs=[p.finish(w) for w in workers];final=p.state(item)
  assert all(r['exit']==0 and r['result']['prior']==0 for r in rs),rs
  assert final['revision']==1 and len(final['receipts'])==1,final
  receipt={'kind':'negative control: separate ownership roots simulate absent shared kernel fencing; same real host/public tenant, not a cross-host recovery proof','observed':rs,'final':final}
 finally:
  for w in workers:
   if w.poll() is None:w.kill();w.wait(timeout=10)
  p.bd('delete',item,'--dry-run');p.bd('delete',item,'--force')
  r=subprocess.run(['/usr/local/bin/bd','show',item,'--json'],cwd=p.ROOT,capture_output=True,text=True,timeout=30);assert r.returncode!=0
  if 'receipt' in locals():receipt['cleanup_absent_exit']=r.returncode;(base/'receipt.json').write_text(json.dumps(receipt,indent=2));print(json.dumps({'expected_loss_observed':True,'receipt':str(base/'receipt.json')}))
```

## Required follow-through

Keep Beads PR 1 closed. Review a local design with explicit ownership topology,
coherent partial-write behavior, bounded receipts, conflicting-operation identity
refusal and existing canonical result/epoch fields. Preserve the 60-second
released Codex/Herdr requirement, legitimate HOLD/open-Red controls, native
producer outcomes and OTel/Honeycomb publication. The finite storage experiment
satisfies none of those released plan assertions by itself. Any required spec
change precedes runtime implementation; relay integration and sibling service
work remain with their existing owners. Revisit a Beads change only if the local
candidate fails a required control or its measured operational cost is
substantially worse. No such necessity has yet been proved.
