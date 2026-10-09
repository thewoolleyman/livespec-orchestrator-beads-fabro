# Provider failure and source recovery

This is a historical recovery receipt measured on 2026-10-09. It does not
claim that the plan or the interrupted implementations have passed their
Definition of Done. The five plan assertions and their carrier map are
unchanged.

## The watchdog repair completed through ordinary reconciliation

The credential-pool isolation foundation was already shipped in commit
`f7eeea555e4460ee4a60280ca69ee5a82c443c37`, under `bd-ib-vvs645`, in
`v0.178.0`. The new `bd-ib-656k7i` work supplies the missing regression
control; it was not necessary to wait for that regression to recover the
already-merged watchdog item.

The ordinary `reconcile-merged` command for `bd-ib-n44n4e` completed in gate
`20261009T122808Z-355414`. The post-merge janitor passed, the disposable
checkout was removed, acceptance passed, and the ledger closed the item at
12:44:45 UTC. PR 2684 merged as
`ebafdbc8723afc08378761e592d77c74fa08a888`; its verified factory proof is
[comment 6073103047](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2684#issuecomment-6073103047).
This was normal reconciliation, with no forced close or changed proof grade.

## Four interrupted runs retained their work

Between 12:59 and 13:01 UTC, four previously launched Claude-routed runs
failed after the provider reported its session limit. Their implementation
or review stage reported `ACP turn failed`, with a `transient_infra`
category. The subsequent `needs_human` script reported that no run id had
arrived on stdin, so its own preservation branch was not pushed. This
absence was not treated as evidence that the source was lost.

| Work item | Factory run | Publication when interrupted |
| --- | --- | --- |
| `bd-ib-gh5xwq` | `01M4G37NYW2JRP0N9M7EX02WM7` | Draft PR 2714; capture completed; review interrupted. |
| `bd-ib-656k7i` | `01M4G4ZRJRXMBS95KR06AS91QK` | Draft PR 2713; capture completed; review interrupted. |
| `bd-ib-emzxlx` | `01M4G6AXXXYK5KWYWY87C08MZW` | No PR; implementation commits retained. |
| `bd-ib-nezrrh` | `01M4G3ENZ3R1QMF1YSSDWMK48A` | No PR; two Green commits and a final test-only Red retained. |

PR 2714's capture is
[comment 6081350932](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2714#issuecomment-6081350932).
PR 2713's capture is
[comment 6081318574](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2713#issuecomment-6081318574).
A capture is not an independent verification.

Every run was exported with `fabro dump` against its actual server,
`https://hp-xubuntu.perch-rudd.ts.net:32276`. Each stopped sandbox's complete
`.git` directory was copied read-only, including the original objects
referenced by `TDD-Green-Parent-Reflog`. The raw exports remain private under
`/tmp/run-lifecycle-recovery-20261009T1305`; they are not published as proof
artifacts. The directory has mode 0700 and its receipt has mode 0600.

The following archive checksums identify those private copies. SHA256 is the
content digest of the complete tar file.

- `bd-ib-gh5xwq`: 21838848 bytes; SHA256
  `dd84e3b340286a63ccdcc5840e95aaefaa060f48bb33bbdbb750484e23f8f62a`; original HEAD
  `87268add8de3ebe7618bf7255a8d4e3a7b6436d3`.
- `bd-ib-656k7i`: 21698048 bytes; SHA256
  `efabe813ba050933094e31d553a56df1377625ed3cf3489dbb3f5815d291599d`; original HEAD
  `bf5c948845bcb41c60d7b8bfe8d226f15b3d7d33`.
- `bd-ib-emzxlx`: 21921280 bytes; SHA256
  `8d9a0767192f0b4836e1c6e290d9f95942071ba9ffff90cf9f361c336b1caad3`; original HEAD
  `b7de1db2caa1a33d28a2944dac7dbf1a722da1e4`.
- `bd-ib-nezrrh`: 21759488 bytes; SHA256
  `40c82669c14688d06014681c7829ba1ec77c30bc0b98bd0597087f8c3901e315`; original HEAD
  `24fe583f706c60103bfcf3a92e1cd8bca73216ef`.

The two unpublished runs' exported implementation patches were byte-for-byte
identical to the changes committed between their recorded `origin/master`
and their original HEAD. No uncommitted implementation was omitted.

The original heads and all referenced Red objects are now independently
fetchable from origin under:

```text
refs/livespec/preserved-run/<work-item-id>/<full-object-sha>
```

All twelve refs were pushed through normal `mise exec -- git push` hooks in
an isolated worktree, gate `20261009T131206Z-1116750`, and then verified with
`git ls-remote` against each expected full SHA. These immutable preservation
refs are not publish branches. The temporary preservation worktree and its
local branch were removed afterward. A passing preservation push is not a
claim that the interrupted implementations passed validation.

In particular, retention HEAD
`24fe583f706c60103bfcf3a92e1cd8bca73216ef` is the test-only Red for the
retention-write-failure assertion. It carries no Green receipt. The next
ordinary factory implementation must adopt the source, finish that cycle
through the normal hooks, and obtain its own validation and proof. Original
producer attribution must remain intact.

The published repairs use Dispatcher `resume` to continue their existing
PRs. The unpublished repairs use an ordinary new factory dispatch whose
ledger brief names these exact preservation refs and instructs source
adoption. Rebuilding the published repairs through plain `impl` would
discard the useful resume boundary.

## Renderer prerequisite and ownership

The ordinary admission wait for `bd-ib-l55d7e`, gate
`20261009T112513Z-3287842`, ended with the quote/backslash workflow-rendering
refusal. It created no run and released its claim to `ready`. That waiter
was no longer active after the refusal.

Committed routing `989ea469` requires Codex ACP nodes. The existing renderer
item `bd-ib-4gkfaa` owns the failure to render those adapter commands. It
remains a child of the live `fabro-currency` plan, epic `bd-ib-6tcjfx`;
this plan neither duplicates that item nor changes the routing policy to
avoid it. At this receipt's observation, its preserved producer source was
being adopted in native Codex session
`01a120b0-ad13-7801-8f2b-76fa8727107e`. Its first adoption validation stopped
on the live skill-picker fixture, with no PR or push; a serial continuation
was subsequently launched as gate `20261009T132138Z-1220251`. This history
is not evidence that the renderer has shipped.

The live skill-picker target passed unchanged on the clean primary at
`59b747df` in diagnostic gate `20261009T131720Z-1181275`. This established
that the target could pass on the host; it did not establish a passing
result for the adoption worktree. Its owner retains the repair and release
obligation.

The other cross-plan ownership remains as recorded in research 002 and 003:
`bd-ib-k627ja` belongs to `pr-stage-backgrounded-push-fault`, epic
`bd-ib-ctagnf`; `bd-ib-nezrrh` belongs to `failure-evidence-retention`, epic
`bd-ib-4aebpa`. Engine storage repair and candidate cutover remain explicitly
with `fabro-currency`. Dispatcher terminal-evidence reconciliation does not
claim to repair the engine's storage.

## Reproducible ownership enumeration

The following read-only probe enumerates children through the package's
union of dotted ids and explicit parent-child edges. Its preparation run
used the checkout package and verified seven children for this plan and
all three named cross-plan carriers. The final plan capture must run it
against the normally installed release and record that module path.
Save the block as `ownership_probe.py`, then invoke it under the configured
credential wrapper with the installed plugin root and repository root as
its two arguments.

```python
import json
import sys
from pathlib import Path

plugin = Path(sys.argv[1]).resolve()
repo = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(plugin / 'scripts' / 'bin'))
from _bootstrap import bootstrap
bootstrap()
from livespec_orchestrator_beads_fabro import _beads_client
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config

client = _beads_client.make_beads_client(
    config=resolve_store_config(cwd=repo, work_items_arg=None).work_items_path
)
expected = {
    'run-lifecycle-false-verdicts': ('bd-ib-qen6rr', {
        'bd-ib-gh5xwq', 'bd-ib-l55d7e', 'bd-ib-ma3fvj', 'bd-ib-emzxlx',
        'bd-ib-656k7i', 'bd-ib-n44n4e', 'bd-ib-4ouajy',
    }),
    'pr-stage-backgrounded-push-fault': ('bd-ib-ctagnf', {'bd-ib-k627ja'}),
    'failure-evidence-retention': ('bd-ib-4aebpa', {'bd-ib-nezrrh'}),
    'fabro-currency': ('bd-ib-6tcjfx', {'bd-ib-4gkfaa'}),
}
results = []
for slug, (epic_id, expected_ids) in expected.items():
    anchor = repo / 'plan' / slug / 'associated_work_item_id'
    assert anchor.is_file(), f'Expected a live plan anchor: {anchor}'
    assert anchor.read_text().strip() == epic_id, f'Wrong epic at {anchor}'
    children = client.children(parent_id=epic_id)
    ids = {record['id'] for record in children}
    assert expected_ids <= ids, f'Missing ownership: {sorted(expected_ids - ids)}'
    if slug == 'run-lifecycle-false-verdicts':
        assert ids == expected_ids, f'Unreviewed additional children: {sorted(ids - expected_ids)}'
    results.append({
        'plan': slug, 'epic': epic_id, 'anchor': str(anchor),
        'complete_child_count': len(children),
        'collected_follow_ups': [
            {key: record.get(key) for key in ('id', 'status', 'title')}
            for record in sorted(children, key=lambda record: record['id'])
            if record['id'] in expected_ids
        ],
    })
print(json.dumps({'module': _beads_client.__file__, 'ownership': results}, indent=2))
```

The final archive still requires actual closure of every plan child, the
released-artifact behavior probes, independent replay of all five plan
assertions, and a fresh independent completeness review after child
closure. This receipt supplies recovery provenance, not any of those
outstanding verdicts.
