# Released foreground timeout policy: capture and independent replay

Measured 2026-10-09. This is evidence for the foreground-policy behavior in
opening research note 001, not a claim that the whole plan is done.

## What the released artifact did

The normally installed Codex plugin v0.178.0, commit
`cfc078d1d36ce6555de776a2a502912f0ebdc26b`, rendered the production run overlay
for a real Claude ACP stage on the hp Docker factory. A foreground `sleep 20`
with a Bash-tool timeout of 1000 ms terminated early. The next shell call and
a two-second call with a raised timeout both succeeded inside the same ACP
session. There was one uninterrupted agent turn and no backgrounded-tool
fault.

| Observation | Capture | Independent replay |
|---|---|---|
| Run | `01M4G4BGEW1FS58ZRWWRSM5F77` | `01M4G4TWWCK7AJZTJ91E20MG9E` |
| `sleep 20`, timeout 1000 | failed, 1757 ms | failed, 2811 ms |
| Next marker call | completed, 1152 ms | completed, 1173 ms |
| `sleep 2`, timeout 10000 | completed, 3151 ms | completed, 3102 ms |
| ACP session | `acp-7d65706b-1f58-4268-934e-19cf50e39f2b` | `acp-f1bfae26-61de-4fdc-80c8-20c1edb83d4b` |
| Stage outcome | succeeded | succeeded |

Durations are the engine's native `agent.tool.completed.properties.output.elapsed_ms`,
not guesses from the agent's response. Both failed calls returned
`<error>Exit code 143</error>`; there was no literal timeout wording. The
native timing distinguishes termination from a normally completed 20-second
sleep. Both next-call successes were measured after that termination, not
inferred merely from the absence of a background fault.

The runtime printed `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` and
`BASH_DEFAULT_TIMEOUT_MS=600000`. It printed `BASH_MAX_TIMEOUT_MS=1200000`
although the released renderer and recorded run environment carried `3600000`.
This establishes recoverable foreground timeouts, not a measured one-hour
maximum in the embedded runtime. The child assertion does not claim that
maximum; its separate factory assertion covers the rendered value.

## Durable proof records and identity

- [Capture on PR 2700](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2700#issuecomment-6079390002):
  Codex session `01a11fbb-60b0-75b3-883f-0d0c5eba1a51`.
- [Independent replay on PR 2700](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/pull/2700#issuecomment-6079519329):
  fresh Claude session `031f0b5e-9d67-46f9-bac2-03385f439077`.
- The replay used the installed `post-host-record` primitive, which drove
  acceptance and closed `bd-ib-k627ja` at `2026-10-09T10:58:49Z`.

The assertion's wording, numbered steps, build identity and verbatim proof are
in those append-only comments. Neither session modified a tracked file in the
probe sandbox. This minimal graph exercises the same production overlay,
Claude adapter and factory runtime; it is not an end-to-end publication test.

## Reproduction recipe

The following is the exact recipe carried by the capture and executed by the
independent replay. Run from this repository's clean, current primary checkout
under `/usr/local/bin/with-livespec-env.sh -- .venv/bin/python <recipe-file>`.
Create `/tmp/pr-stage-plan/` first if absent; the final line stores a nonsecret
output-directory pointer there.
The wrapper supplies credential variables and the installed token minter
supplies the run-scoped GitHub token. The recipe prints no secret values and
writes the overlay and raw launch output only into a private temporary directory.

```python
import os,sys,json,subprocess,tempfile
from pathlib import Path
root=Path('/home/ubuntu/.codex/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro/0.178.0')
assert (root/'plugin.json').exists()
for path in [root/'scripts',root/'scripts/_vendor']:sys.path.insert(0,str(path))
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import render_run_config_overlay
work=Path(tempfile.mkdtemp(prefix='pr-background-host-proof-'))
work.chmod(0o700)
prompt='''This is a READ-ONLY foreground-timeout behavior probe. Do not modify any tracked file or run git commit/push. Use the Bash tool (not shell timeout) to run command "sleep 20" with the Bash tool timeout field set to 1000 milliseconds. Keep run_in_background false. Observe its actual returned error. Next call Bash with command "printf 'FOREGROUND_RETRY_OK\\n'" and timeout 10000. Then call Bash with command "sleep 2; printf 'RAISED_TIMEOUT_OK\\n'" and timeout 10000. Also run one Bash call printing ONLY the three nonsecret variables CLAUDE_CODE_DISABLE_BACKGROUND_TASKS, BASH_DEFAULT_TIMEOUT_MS and BASH_MAX_TIMEOUT_MS. In your final response quote the actual three tool results and state whether the same agent turn continued after the timed-out first call. Do not interpret absence of a background fault as success unless the first call actually timed out. If the tool returns something else, report the mismatch and stop. Never print any token, other environment value, auth file or credentials.'''
graph='''digraph ForegroundTimeoutProof {
 graph [goal="Prove released foreground timeout behavior", default_max_retries=0, stall_timeout="600s"]
 start [shape=Mdiamond]
 implement [backend="acp", acp.command="ANTHROPIC_MODEL=claude-opus-5 CLAUDE_CODE_EFFORT_LEVEL=high npx -y @agentclientprotocol/claude-agent-acp", timeout="600s", prompt=%s]
 fail [shape=box, type="command", script="echo FOREGROUND_PROOF_FAILED >&2; exit 1"]
 done [shape=Msquare]
 start -> implement
 implement -> fail [condition="outcome=failed"]
 implement -> done
}
''' % json.dumps(prompt)
(work/'workflow.fabro').write_text(graph)
base='''_version = 1
[workflow]
graph = "workflow.fabro"
[run]
goal = "Released foreground timeout proof for bd-ib-k627ja and plan bd-ib-ctagnf"
[run.environment]
id = "livespec-ci"
[environments.livespec-ci]
provider = "docker"
[environments.livespec-ci.image]
docker = "ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.93.0"
[environments.livespec-ci.resources]
cpu = 2
memory = "4GB"
[run.clone]
enabled = true
[run.run_branch]
enabled = true
push = false
[run.meta_branch]
enabled = true
push = false
[run.checkpoint]
commit_timeout = "15m"
skip_git_hooks = false
[run.pull_request]
enabled = false
[[run.prepare.steps]]
script = "mise trust"
'''
r=subprocess.run([sys.executable,str(root/'scripts/bin/mint_app_token.py')],capture_output=True,text=True)
assert r.returncode==0,'App token mint failed; no token output disclosed'
token=r.stdout.strip();assert token
text=render_run_config_overlay(committed_text=base,workflow_dir=work,token=os.environ['CLAUDE_CODE_OAUTH_TOKEN'],github_token=token,siblings=None)
assert text
p=work/'overlay.toml';p.write_text(text);p.chmod(0o600)
r=subprocess.run(['/home/ubuntu/.fabro/bin/fabro','run',str(p),'--server','https://hp-xubuntu.perch-rudd.ts.net:32276','--detach','--json','--label','plan=pr-stage-backgrounded-push-fault'],capture_output=True,text=True)
# Keep raw tool output private, never print it.
for n,v in [('launch.stdout',r.stdout),('launch.stderr',r.stderr)]:
 f=work/n;f.write_text(v);f.chmod(0o600)
print(json.dumps({'exit_code':r.returncode,'artifact_directory':str(work),'build':'v'+json.loads((root/'plugin.json').read_text())['version'],'installed_root':str(root)}),flush=True)
if r.returncode==0:
 raw=json.loads(r.stdout)
 print('launch result type',type(raw).__name__)
 if isinstance(raw,dict):
  print(json.dumps({k:raw[k] for k in ['run_id','id','status'] if k in raw}))
Path('/tmp/pr-stage-plan/timeout-proof-dir').write_text(str(work))
raise SystemExit(r.returncode)
```

Wait for the printed run to terminate on the **hp** server, then export to a
new private directory with `fabro dump RUN --server
https://hp-xubuntu.perch-rudd.ts.net:32276 -o PRIVATE_DIRECTORY`. Read the
stage's `response.md` and `status.json`, and project only tool completion
status, duration and session identity from `events.jsonl`. Require the failed
short-timeout call, the successful next call in the same ACP turn, and a
successful stage. The run's settings/environment and raw exports can contain
credentials: do not print or commit them.

A verifier posts a new `host_verified` or `host_not_reproduced` record through
`post-host-record` from its own fresh session. Re-reading the first session's
output does not constitute replay.

## Invalid attempts retained in the account

- `01M4G3WDCN0XX1XXTHR0B7FHSN` failed before the probe because the cloned mise
  configuration was untrusted. It is not proof. The recipe gained the normal
  `mise trust` prepare step and an explicit failed-stage terminal edge.
- `01M4G40H6NRPCWNSM3A0P78AC8` succeeded with `sleep 3`; the stronger capture
  above uses `sleep 20` so elapsed time distinguishes early termination clearly.
- Replay attempt `01M4G4NQ73K2PF9WPFTDCPBBR1` failed before sandbox creation
  because the primary checkout was behind origin/master. The independent
  session fast-forwarded the clean checkout and reran the unchanged recipe.

None of these failed setup attempts was counted as a passing proof.
