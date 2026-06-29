# Changelog

## [0.3.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.2.0...v0.3.0) (2026-06-29)


### Features

* **dispatcher:** admission valve + WIP cap + post-merge acceptance valves ([da61be6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/da61be6d05a2bdf36eec32a99516fe036ee55f99))
* **plan:** add the plan skill (Planning Lane realization) (livespec-zs22.5) ([bb4a20b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bb4a20bd3e9248ea893947186150dad6d704d5b5))
* **work-items:** adopt v0.5.0 rank/7-state model + beads store adapter ([dfbb21e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/dfbb21e80a22b698a9cc83e7d4a57d8a7c26c72f))
* **work-items:** doctor work-item-state invariants (rank/assignee/blocked-reason) ([8bb59d5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8bb59d570bc0baedb267eebaabca6d6da909d524))
* **work-items:** list-work-items emits lane/lane_reason + filter=blocked lane semantics ([da3c46c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/da3c46c3ec5319d9462201aab18ba19a305dc9ee))
* **work-items:** rebalance-ranks command + legacy-seed backfill primitive ([5d49d2b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5d49d2bc08f75c67686319dfd8c1f280c827bd74))


### Bug Fixes

* **dispatch:** anchor the run brief's repo line to the sandbox cwd ([e0baa28](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e0baa281337588d8c024b5cb46f9c4f5931e6d97))
* **dispatch:** size the Codex freshness gate to a realistic run budget ([7945c7e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7945c7e7d48cc0a648f6c47878f65037b4d3fe27))
* read fleet manifest 'fleet' key with legacy 'members' fallback ([e979d41](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e979d410566be9e8732e109efd30ecf52c4586e9))

## [0.2.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.1.0...v0.2.0) (2026-06-24)


### Features

* **acceptance:** live Beads/Fabro greeting assertion ([5113c09](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5113c09fb3f7ead53c9da5fa5b6e61b7383e3e7c))
* add beads acceptance harness ([ad6fd1c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ad6fd1c890f413369a5a422e2babaadd12052353))
* add BeadsClient.add_comment write verb for reflection comment-bumps ([311fc6f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/311fc6f3dd7d82315179cefbd3d0dac268f6a405))
* add Codex cross-runtime surface + structural check (P3a) ([6212a61](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6212a615e2e8aff73bba41d6413de6bc0136ef94))
* add fresh-clone real-work dispatch substrate (W7 pe9u) ([2431d4d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2431d4d0b648fa4871856413cce4c0ed84b2510e))
* add orchestrate operator surface ([3f795f7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3f795f79e6834a4362db1799341a081b836150d7))
* add the bin/dispatcher.py shebang wrapper for the Dispatcher CLI ([21855f2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/21855f277051b9d672aedc04082b2dff65cec350))
* add the bin/orchestrator.py shebang wrapper for the orchestrator contract CLI ([a9b50d0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a9b50d02ebc29880d8143cb57ead8ae6e0cb0f83))
* add the dispatcher CLI (ledger-check / dispatch / loop) realizing the Beads+Fabro orchestrator Dispatcher ([d49e763](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d49e763147507f72d8a6adf05bded0ea33265d18))
* add the orchestrator contract CLI (spec-reader / gap-capture / drift-capture) ([bd3fe96](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bd3fe96afcac4a1d8518c92f30d492c14e219d4e))
* **close-work-item:** atomic close + resolution:completed wrapper ([9b77c5c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9b77c5cea50bedbcdad4be9bf1cd78c7b4307b1f))
* coarse wall-clock stall watchdog for the fabro run (oyg) ([e8ce899](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e8ce899ed53d7c5541eb0e03c9ac0fc8bc927b08))
* containerized Beads/Dolt + Fabro orchestrator image (DinD) (livespec-impl-beads-8bc) ([f4e1c11](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f4e1c11321f0d562ee6278a997582f24afc37efb))
* convert dispatcher spend-COST gate into a report-only observability signal ([a9a3e6d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a9a3e6dd42e6df8fab6b00ba9eb9dbdb3dcd718f))
* **dev-tooling:** closed_item_integrity check rejects closed-but-unproven ([fc2c43b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fc2c43be694e430d8a604db2ffe98dd850904fc3))
* dispatcher arms the single shared live OTLP receiver at entry (29f.7 E1) ([50d144e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/50d144e5ff939fc1784fbd37ef7ee50873d4491b))
* Dispatcher bounces non-converging slice to needs-regroom (n5kina) ([1d8b049](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1d8b0495ccc0fc80ca57a577689651626da643d8))
* Dispatcher refuses human-gated item, surfaces for maintainer (cjey2z) ([12593e5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/12593e5e613e8c4ba9f9cf607e866b7a5bae8d78))
* dispatcher refuses to sandbox host-only self-machinery items (uvd) ([5870b56](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5870b566ebb7ba81817cd76b70f4a4eb59b84efa))
* **dispatcher:** comments read verb on the BeadsClient seam ([79165b1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/79165b16cf9f9ffadb7be3ed8f827ecb56737123))
* **dispatcher:** credential via fabro {{ env }} interpolation; fail-fast on missing CLAUDE_CODE_OAUTH_TOKEN ([322947b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/322947b4d4303f18bcc7fdef8f6fa5163035b419))
* **dispatcher:** fold ledger comments into the dispatch goal + sizing warnings + long-haul fabro budget ([692fadd](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/692fadded5af19b5fbe3b381a1dbcf8b4580a5b3))
* **dispatcher:** provision sandbox sibling clones + LIVESPEC_SIBLING_CLONES_ROOT ([e74b449](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e74b449bc7ed5fa632ad88b62ff3323c1643b848))
* **dispatcher:** rewire C-mode dispatch — sandbox-owned clone, credential overlay, blocked-aware engine ([b21c3eb](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b21c3ebba93fbc9daa31736e17f07f5a56541024))
* **dispatcher:** store-level work-item comments read ([a6d0a37](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a6d0a37ab3719ec2a90332a937a4ea7107ed1015))
* emit dispatcher calibration telemetry on the journal (yfsv4j) ([e2d7de2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e2d7de247f417aab46d9909cce4c9e0b680845b2))
* extract implement+groom to shared prose; thin Claude+Codex bindings ([da654cc](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/da654cc3af341f90882fc0cc1f578ec0a76dd3cd))
* extract three capture ops to shared prose; thin Claude+Codex bindings ([8668208](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8668208bbb77b771eef9662db7687ba9295b80cf))
* fail-closed cost-observability seam for the dispatcher (5v9) ([09a5114](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/09a51148651db5ceb4b57e308484e651d98fa539))
* fail-open ntfy alarm on terminal dispatcher failure (h1p) ([0ac7184](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0ac7184e0f592d86dbb8f8148aade801ce966ecc))
* freshness-gate the Codex subscription credential ([9e21ca6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9e21ca6417b1a724dd96984f666cae0cda9db268))
* groom front-end drafts read-only and files approved slices (6wksha) ([9976303](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/997630372d405643690dd75b9635406ce526683a))
* host-local OTLP enrich/scrub stage — 29f pipeline data plane (E1) ([31c0cd6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/31c0cd6bdf6363bfed2caa813acaa73bf4cb3440))
* in-sandbox CC OTel run-config overlay (29f.3) ([f4d3138](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f4d313888362401e16b5a2873a390447d8d4a7f0))
* intake Definition-of-Ready checklist tags captured items (v7p2sq) ([e0a15d8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e0a15d8ca40ba4e4c71bb296174b78141a60f2ff))
* live fail-closed dispatcher spend cap (per-run + per-session USD ceiling) ([11a5fd4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/11a5fd4ab416198252392412e2bf714793b215fd))
* live OTLP/HTTP RECEIVE plane + metrics heartbeat (29f.7 E1) ([7f5698a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7f5698aa3c4f1a9dced3599ecb34751b4201fe09))
* mechanical loop-exit reflection module (fail-open, &lt;=60s; 29f.2) ([09c9234](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/09c923480da694eb3bad2c6ad53045eb31284909))
* metrics-heartbeat LivenessProbe — oyg watchdog deferred-PRIMARY (29f.6) ([b4c6969](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b4c6969e7b0f48a6eb4dddd8e6ad15f822ba96cd))
* needs-regroom state machine (enter on DoR-fail/non-convergence; exit by filing ready slices) ([9a5593f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9a5593f21d9293060ab697f76d4e68c69601bf6c))
* orchestrate operator-surface defaults (Scenario 17) ([023c98f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/023c98ffaa703b8143a5e225fc8fab949f52867c))
* out-of-band LLM reflector — runtime, dedup filing, lessons-PR, verdict spans ([c6ce363](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c6ce363ebf32dabc129418749fe98683d77a08f3))
* per-dispatch CC-token cost sink (livespec-impl-beads-efj) ([d10f5e2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d10f5e22335d7d41bdef121e6c1b9257360d2cfe))
* periodic calibration analysis pass proposes advisory ceiling thresholds ([455d9ed](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/455d9ed3764264307e2fb08a13cd8b1eff0b9823))
* pin OOB reflector to hosted Honeycomb MCP via --strict-mcp-config ([7b4b2d8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7b4b2d8bcd2904d87e5b3784972dac991cab6806))
* project non-rotatable Codex credential snapshot ([e42c295](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e42c295b38920bd78554701010e0ab9dd34702c0))
* project the host Codex credential into the dispatch sandbox (Slice B) ([50bc862](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/50bc862728b9dccd5310ff4e95a04b3d3c25b693))
* pure CC-token cost pricing (livespec-impl-beads-efj) ([2e92b1d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2e92b1dd792f53b147f7c9a19bbd22e37d35ff66))
* re-home the three spec-context work-item invariants as the Dispatcher spec-check surface ([abfa881](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/abfa88191f32d47fb2fa69d551078891c7193169))
* re-home the three stale-cleanup doctor checks as the Dispatcher janitor-check surface ([7a69c30](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7a69c3052c697dec2affd2bb249c2dd33f7b852b))
* shared fail-closed _otel_scrub single source of truth (29f E1) ([54a38a6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/54a38a6fccd17da76f11eca96c04c20e6ce07a5a))
* single-source detector gap-id via shared livespec_spec_clauses ([55ae39e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/55ae39ee453b8016b95536296bef29bccf72648d))
* staged self-update + canary guards the dispatcher self-merge hazard (livespec-impl-beads-ddu) ([407a273](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/407a273659eebfb5451b8af03323633997a5a2b6))
* wire CC-token-derived cost into the spend cap (livespec-impl-beads-efj) ([95fd5f2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/95fd5f27db71f8fe4a2b8642b4fbd0e044664bd6))
* wire fail-open reflection stage into dispatcher loop/dispatch exit (29f.2) ([7676bc0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7676bc0c9f791b8e3ee1d974dca1f58fea209915))
* wire the fail-closed cost gate into the dispatch wave (5v9) ([b532df2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b532df264486157f99c55815141dc8c31104cb56))
* wire the out-of-band reflector as the 5th post-verdict stage ([c99756d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c99756d3222253b63d351454b5ede06394748053))


### Bug Fixes

* **acceptance:** assert greeting for positional or keyword-only greet ([e2ee88e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e2ee88ec0062625c4d84ddf0bfe9c2bec59ee6c5))
* align ShellBeadsClient per-command argv + show parsing with bd v1.0.5 ([c3954b7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c3954b710b649ab8d77db60aa80f732818baa3cb))
* avoid canceling finished fabro runs ([c54c092](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c54c09209e43eea12eb091ac374aa3eaa5891f5c))
* derive work-item origin from gap_id instead of raising on missing origin label ([d1094d2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d1094d2021f6830617fdcddbbdcf55478582a328))
* **dispatcher:** compose next ranking in drain order (i3jiny) ([de5fae1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/de5fae14ade4415a9ba8d31c88e6a61e0d8b2528))
* **dispatcher:** post-merge janitor runs in a fresh checkout of merged master ([ca6f7ed](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ca6f7ed89643c6ee586ba05c6293b628cbda8458))
* **dispatcher:** project credential via run-scoped overlay, not {{ env }} interpolation ([d1a9dac](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d1a9dac0fee621a87c48fc9efd2f26f8ad1fac75))
* drop brace token from implement-work-item preamble comment so the Fabro UI graph renders ([d52f69e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d52f69e025bd62652140fab58589e9efaa08eee3))
* escape MiniJinja delimiters in dispatcher goal text (livespec-impl-beads-ajv) ([10d61ca](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/10d61ca9b4869226d610b7bc2f9b760ba66dcbce))
* fetch renamed livespec fleet manifest ([cfdfb21](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cfdfb217e57ac3cf4c17d1867b02450248820436))
* install canonical hooks before post-merge janitor checks (bd-ib-f3p6vg) ([f14c093](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f14c0931d6966af30b5812e787675c8bc504f1ca))
* item-specific loop dispatch honors requested item in autonomous mode ([9a2377f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9a2377fc414f8da9c7613ad83ffce38b76d66ab8))
* let janitor install hooks without claude ([0ae52dd](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0ae52dd1f398221a6dff31e2982a89d9b4937df9))
* make groom honor repo_target for cross-repo factory slices ([2341e78](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2341e7886e5f5024427704b4131fdd99a509f352))
* make the out-of-band reflector operationally ready (29f.8) ([8c75890](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8c75890a0145c5a88221cfe33d35a92751bbe653))
* materialize depends_on as typed-dict local entries from blocks edges (v072 schema) ([d4bfa1d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d4bfa1d47efe1bce6b440aa28b60f5373945cb6c))
* mint work-item/memo ids from configured tenant prefix (bd v1.0.5) ([3f8beda](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3f8beda49e632f091432aac7fb5f142f820087dd))
* pass bd --limit 0 in list_issues so enumeration isn't capped at 50 (li-e7b9ba) ([08fe56a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/08fe56a3b0a46e0fa0a1e26f7205ece99a500797))
* persist non-local depends_on entries in the Beads store (bd-ib-v5fvqc) ([fe3737d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fe3737dec63904954887bebce986ca6ce70cd21d))
* point reflector Honeycomb MCP at /mcp endpoint (29f.8) ([f57d1ff](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f57d1ffc6cd74ddd24cfe90cec099632337f3930))
* regenerate beads metadata from clone config ([48a0f8e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/48a0f8e050ad9939014801a019cc40dd8c4b043a))
* reject wrong-tenant --item before container/FABRO work starts ([b4d9385](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b4d9385b4c87dddfde1d0970416dc522e5ff029e))
* relocate post-merge janitor checkout out of the /tmp coverage-omit venue ([151b7ac](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/151b7ac0acc3c90e554d2e002c344aa8ed42225c))
* require explicit connection.prefix in beads config loader (decoupled-prefix footgun) ([6f79bf3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6f79bf3a3bc0282ebd70c05cdbea1bba4483410f))
* resolve sibling_work_item dependencies when ranking readiness ([9a9958b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9a9958b8f8284c92a5f901bdc79c564fc8089b0f))
* **w7:** require github token projection ([d906b33](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d906b33a8ea23b7509cd45ab1c7a9b101f1e931f))


### Refactoring

* consume shared livespec_runtime.work_items surface (livespec-6a4n) ([e031e6d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e031e6d30abd866d73dab0e56cb33d0a29e6d8e6))
* rename impl-beads Beads tenant to livespec-orch-beads-fabro (S8) ([2e8858f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2e8858f02fd1fca039ba450925ed21c4858a7d50))
* rename impl-beads plugin identity + skill namespace to livespec-orchestrator-beads-fabro (S10 Part A) ([a375cda](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a375cda184166f9aa494c6096d8466a43edf255c))
* rename Python package livespec_impl_beads -&gt; livespec_orchestrator_beads_fabro ([c223fe2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c223fe20e776f65ae7773a425f2eaa62e724edd2))

## Changelog

All notable changes to this plugin are recorded here. This file is
auto-maintained by release-please; do not edit it by hand.
