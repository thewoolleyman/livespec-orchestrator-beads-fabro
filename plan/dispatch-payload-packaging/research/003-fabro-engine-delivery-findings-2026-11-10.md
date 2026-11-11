# 003 — Fabro engine delivery findings (2026-11-10)

Read-only research by a helper agent of this session against /data/projects/fabro and /data/projects/petri. The packager reference-scan claim was re-verified by the session on carrier-v0.408.0-nightly.0-20261108 (fabro-dot/src/lib.rs:252-259). Other citations are the helper's, unverified line by line.


## Refs and lineage (what each name means)

- **C408** = `origin/carrier-v0.408.0-nightly.0-20261108` (tip `85071c828`). It contains upstream `b452f498f`, so `run.prepare` is gone. Its Petri engine is pinned to `thewoolleyman/petri` branch `fabro-integration-f30a12df-20261108` at `ac0b9fb3` (C408 `Cargo.toml:212-220` `[patch]`, and `Cargo.lock`). Petri is read from `/data/projects/petri` at that commit and cited below as **P408**.
- **SERVING** = `bbe693847`, on `origin/carrier-candidate-registered-20261023` (also on `origin/probe|test/authored-run-prepare-nodes`). It does NOT contain `b452f498f`, so `run.prepare` still exists there (`lib/foundation/fabro-config/src/layers/run.rs:35,292-307`). Its Petri is `c6bfd5e3` (**P-SERVING**).
- `origin/factory-integration` (tip `8b82e99bb`) contains neither `b452` nor the C408 tip. It still has `run.prepare`.
- `upstream/main` was not consulted. `b452f498f` was read directly.

## 1. What the packager collects, and the caps

**Collection follows references. It is not a directory walk.** `collect_workflow_versions` → `WorkflowBundler::collect_versions` (C408 `fabro-manifest/src/workflow_version_collector.rs:109-148,174-191`). The bundler collects only these:

- the entrypoint graph and its sibling `workflow.toml` (`workflow_bundler.rs:106-128`). The config must be exactly `<graph dir>/workflow.toml` (`:109-120`);
- from `workflow.toml`: the `[run.goal] file` and an `[environments.*.image] dockerfile = { path }` (`workflow_bundler.rs:413-493`);
- from the graph: the graph `goal="@file"`, a node's `prompt="@file"` / `output_schema="@file"`, `import=`, and `stack.child_workflow=`. Child workflows become separate dependency versions. (`fabro-dot/src/lib.rs:201-287`, esp. `:252-259`; walk at `workflow_bundler.rs:240-324`);
- minijinja `{% include %}` targets reached from prompt, goal and inline-prompt text (`workflow_bundler.rs:257-269,329-373`).
- **`script=` is never scanned**, whether as `@file` or for includes (`fabro-dot/src/lib.rs:252-259` names only `import`, `stack.child_workflow`, `prompt`, `output_schema`).
- An unreferenced file in the workflow directory is silently left out. The test `ignores_symlinks_the_selected_workflow_never_reads` (`workflow_version_collector.rs:506-520`) shows this.
- Files are read with `read_to_string` (`workflow_bundler.rs:553`), and a version holds files as `BTreeMap<WorkflowPath, String>` (`fabro-types/src/workflow_version.rs:57`). So package files must be valid UTF-8; raw gzip bytes cannot be a file.
- For `fabro run <path>`, the CLI calls `resolve_local_workflow_package` (`fabro-cli/src/commands/run/resolution.rs:42`). Its source root is the containing Git worktree, else the user root, else the file's own directory (`fabro-manifest/src/local_workflow_package.rs:71-107`). For `$TMPDIR/fabro-workflow-<hex>/` that is the directory itself.

**Caps** (C408 `fabro-types/src/workflow_version.rs:14-17`; identical on SERVING and factory-integration):

- `MAX_WORKFLOW_VERSION_FILES = 512`
- `MAX_WORKFLOW_VERSION_FILE_BYTES = 512*1024`. Checked as raw `content.len()` for **every** file, including `workflow.fabro` and `workflow.toml` (`:146-164`).
- `MAX_WORKFLOW_VERSION_BYTES = 2 MiB`, measured on the canonical **JSON** serialization (`:112-121`). JSON escaping of newlines and quotes counts against it; base64 does not inflate under JSON.
- `MAX_WORKFLOW_VERSION_DEPENDENCIES = 512`
- These apply per version. Each child workflow is its own version with its own caps (`workflow_version_collector.rs:277-326`).
- **Consequence for today's option C:** all ~400-500 KB sits in one `workflow.toml`, which is near its own 512 KiB per-file cap.

## 2. Are package files materialized into the sandbox?

**No; not found.** Scope searched:

- C408 `lib/components/fabro-petri/src`, `fabro-workflow/src` and `fabro-server/src`, for `write_file` and bundle/version file consumers. The only consumer, `run_intent.rs:376-410`, feeds files to Petri lowering. Nothing writes them to the sandbox.
- P408 `crates/**`, every `.write_file(` call outside tests: checkout tarball, hook context, pebble, process/docker outputs, GitHub Actions. None writes workflow-package files.

The only native "files into sandbox" path is the repository checkout (`[run.clone]`). It is delivered as a tarball of the run's repository (P408 `crates/attractor/steps/src/checkout.rs:1-20,120`), not of the package.

None of the other candidate mechanisms exists:

- **`@file` in `script`:** not supported. `render_script` only substitutes `{{ inputs.* }}`, `{{ vars.* }}` and `{{ goal }}`, with no includes (P408 `crates/attractor/frontend/src/template.rs:303-330`). The packager would not collect such a file anyway (§1).
- **Asset or attachment config key:** none exists. The `[environments.*]` fields are `provider, cwd, image, resources, network, lifecycle, labels, env` (C408 `fabro-config/src/layers/environment.rs:11-28`).
- **Command-node attributes** are only `script`, `language`, `stdin_source` and `output_schema` (P408 `lower/lints.rs:31-46`).
- `prompt="@file"` or `{% include %}` would inline a file's text, but only into an LLM prompt. That makes it model-visible and gives no file in the sandbox.

**Option A therefore has no native delivery path on C408.** It could only work if a helper were made a referenced file (it would still never reach the sandbox) or if the engine were extended.

## 3. Command nodes: per-node `env`, and rendering under `compact`

**Per-node literal `env`: no.**

- Authored command-node config gets `env` only from the workflow environment's **secret** references (P408 `lower/nodes.rs:555-568,618-621`).
- Literal env values go to the scope instead (`lower/mod.rs:482-506`).
- No DOT `env` attribute exists (`lints.rs:31-46`).
- `CommandConfig.env` does exist in the IR (P408 `crates/attractor/steps/src/command.rs:60-84`). On SERVING it was filled per step only by the `run.prepare` lowering (P-SERVING `lower/settings.rs:189-219`, `envs.insert(id, step.env)`).

**How the script runs:** `bash -c "exec 2>&1\n<script>"`, or `python3 -c <script>` (P408 `steps/src/command.rs:243-246`). The whole script is **one argv string**.

- This is general Linux kernel behavior, not something in the repository: one argv or env string is capped at `MAX_ARG_STRLEN` = 128 KiB, so a larger script fails with E2BIG.
- On a timeout, the full script is copied into the failure reason (`command.rs:334-338`).

**Rendering into agent requests (default fidelity is `compact`):** P408 `crates/attractor/frontend/src/fidelity.rs:15-27,82` sets the default.

- Every agent or prompt node's config gets `stages`, a copy of **every DOT node's raw `script`** (P408 `lower/nodes.rs:396`; `lower/threads.rs:301-324`). The lowered graph therefore holds each script once per LLM node, plus `config.script` and `meta.script` (`nodes.rs:603-609`).
- `Preamble::compact` emits `- Script: \`<script>\`` for **every completed command stage, untruncated** (P408 `crates/attractor/steps/src/fidelity.rs:241-249,459-477`). Only output is clipped, to 25 lines (`:27`). The 8 KiB `INLINE_VALUE_MAX` applies to context values, not scripts.
- `summary:*` modes include the script too (`:485-493`). Only `full` and `truncate` omit it (`:186-194`).
- ACP agents get the same prompt (P408 `steps/src/agent.rs:1-11,242-265`).
- **Yes: helper bytes placed in a command-node script would be sent in the session prompt of every agent or prompt node that starts after that command node.** That covers every node and every retry, and the bytes then stay in that session's context for all its turns.
- On SERVING, the run.prepare payload lived in the per-node `env`, which is not part of `stages`, so it was not model-visible. Only the small decoder `script` was.

## 4. What re-runs on sandbox re-acquire / resume

**Prepare re-run on C408** (`fabro-petri/src/prepare.rs:1-24,41-57,95-129,176-232`; `hooks.rs:574-633`):

- **Which nodes count:** root-graph command nodes named `run_prepare_<N>`, N numeric, sorted by N. `PREPARE_NODE_PREFIX` is now Fabro's own constant (`prepare.rs:46`).
- **What triggers it:** a **resumed** run that acquires that scope with no marker at `/tmp/fabro-run-prepared/<run_key>`.
- **What happens:** it re-runs those nodes' stored `CommandConfig`s in order, before the first node of the resume, then writes the marker. A fresh run only writes the marker.
- **Environment on re-run:** the node's `config.env`, which on C408 is secret references only, plus whatever env the scope supplies. The re-run spawns through the acquired `ExecEnv` (`checkpoint.rs:917-949`), and `SandboxEnv::spawn` adds the scope env (P408 `crates/core/executor-sandbox/src/env.rs:346-353`). So helpers delivered through `[environments.<id>.env]` are present on re-run.

**`run.prepare` itself:**

- C408 rejects it at parse time (`fabro-config/src/parse.rs:34,49-50,101`; test `load.rs:77-102`).
- On SERVING, `run.prepare` lowers to the same `run_prepare_N` nodes (P-SERVING `lower/settings.rs:172-219`), with the same marker logic (SERVING `fabro-petri/src/prepare.rs`).

**Package-file materialization:** not applicable. Nothing materializes package files (§2).

## 5. Where the 512 KiB cap is enforced; can it be raised?

**It is enforced on both client and server:**

- **Client:** collection builds `WorkflowVersion::new` → `validate_workflow_files` (`workflow_version.rs:62-75,146-164`; called at `workflow_version_collector.rs:305`), inside the CLI's `resolve_local_workflow_package` (`resolution.rs:42`). It fails before any upload.
- **Server:** `Deserialize for WorkflowVersion` calls `Self::new` (`workflow_version.rs:231-245`). `POST /workflow-versions` also carries `DefaultBodyLimit::max(MAX_WORKFLOW_VERSION_BYTES)` (`fabro-server/src/server/handler/workflow_versions.rs:22-26`). The MCP tool checks the total again (`fabro-tool/src/workflow_version.rs:45`).

**No configuration raises it.** The caps are `pub const` values. A grep of C408 `fabro-config`, `fabro-server/src` and `fabro-cli/src` for max/limit settings or environment variables found no override. Raising the cap means a fork code change on **both** client and server.

## 6. Scope and visibility of `[environments.<id>.env]` (orchestrator draft PR #4844, migration item dpsiwz)

**How it is lowered:**

- `workflow.toml` may have a top-level `environments` (C408 `fabro-config/src/parse.rs:7-16`). `env` is a `StickyMap<InterpString>` (`layers/environment.rs:27,46`).
- In Petri, a value that is exactly `{{ secrets.NAME }}` becomes `Secret`; anything else is `Literal` (P408 `crates/fabro/frontend/src/workflow_toml.rs:623-645`).
- Literals go into the IR **scope** `env` (P408 `lower/mod.rs:482-506`). Secret references go into each command's config `env` (`lower/nodes.rs:555-568,618-621`).

**Scope: every process in the sandbox, not only command nodes.** Each item has its evidence:

- At acquire, `env_overrides = scope.env` becomes `SandboxEnv.env` (P408 `crates/core/executor-sandbox/src/lib.rs:325-342`).
- `SandboxEnv::spawn` attaches all of it to **every** exec, with step env winning (`env.rs:346-353`). That covers command nodes, Fabro's own internal execs (checkpoint and prepare markers), and **ACP agent processes**, which launch through `ExecEnv::spawn`: Fabro's `TelemetryEnv::spawn` observes the ACP launches (C408 `fabro-petri/src/run_turn.rs:640-660`).
- For container scopes it is also set as container env at create time (`executor-sandbox/src/lib.rs:615-619`), so even processes not started by Petri see it.
- Agent tool subprocesses inherit it from the agent process. That last step is ordinary OS inheritance; no repository code is involved.
- The scope env is also bound as `env` in every firing's expression statics (P408 `crates/core/engine/src/context.rs:47-71`).
- **Cost (kernel facts, not from the repository):** every exec then carries ~400 KB of environment. That counts toward ARG_MAX, which argv and environment share (about 2 MiB at the default 8 MiB stack). Each `KEY=VALUE` string must also stay under 128 KiB (`MAX_ARG_STRLEN`).

**Model visibility: no.**

- The preamble is built only from goal, run id, `stages`, `nodes` and `kv` (P408 `steps/src/fidelity.rs:143-153`). Scope env is not in any of these.
- Agent prompt assembly (`agent.rs:242-265`) does not read env.
- Scope searched: P408 `crates/attractor/steps/src/{fidelity,agent,prompt}.rs` and `crates/core/engine/src/context.rs`. Within that scope, no path renders `env` into a request.

**Persisted: yes, twice per run.**

- **In the run spec:** `RunSpec.settings` (`WorkflowSettings` → `run.environment`; C408 `fabro-types/src/settings/run.rs:37`, `run.rs:63-98`) travels in the `run.created` platform record, which "carries the run spec" (`fabro-store/src/platform_records.rs:154-163`). It is also kept as an unredacted `spec_blob` (`run.rs:86-90`).
- **In the graph blob:** the lowered Petri graph serializes `Scope.env` (P408 `crates/core/ir/src/graph.rs:887-890`), and that graph is stored as the admission blob (`fabro-types/src/engine.rs:21-28`; `RunSpec.admission`, `run.rs:95-97`).
- Per-event emission of env was not found. Scope searched: Petri core engine `context.rs`. No full event-schema audit was done.

## Bottom line

1. **Option A has no native support.** The packager collects only referenced goal, prompt, schema, import, child-workflow, Dockerfile and include files, all UTF-8. Nothing ever writes package files into the sandbox, and no configuration raises the client-plus-server 512 KiB, 2 MiB and 512-file caps.
2. **Option B works but is the worst choice.** Command nodes take no literal per-node env. The script runs as one `bash -c` argument, which the Linux kernel caps at 128 KiB per argument. Under the default `compact` fidelity, every completed command script is pasted untruncated into each later agent or prompt node's prompt, and it is copied into every LLM node's stored config.
3. **Option C is the only native carrier for opaque bytes on C408.** It works through literal `[environments.<id>.env]`, which reaches every sandbox process, ACP agents included, and is present when `run_prepare_<N>` nodes re-run on resume. It stays out of model prompts but is persisted in `run.created` and the graph blob. It is bounded by the 512 KiB `workflow.toml` cap and by the kernel's 128 KiB per-variable and shared ARG_MAX limits on every exec.
4. **Option D has no engine feature.** It would be an ordinary command node fetching from a pinned URL, which needs network egress allowed in `[environments.*.network]`. The only built-in file delivery is the `[run.clone]` repository checkout.
5. **Recommendation:** keep C (gzip+base64 in scope env, with small `run_prepare_N` decoder nodes) as the near-term choice on C408. Move to D, a pinned released artifact or a pinned repository checkout, to lift the 512 KiB ceiling. Avoid B because its bytes become model-visible.
