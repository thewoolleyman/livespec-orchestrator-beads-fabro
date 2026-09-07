# Changelog

## [0.140.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.140.0...v0.140.1) (2026-09-07)


### Bug Fixes

* **groom:** read the answer disposition before treating it as consent (bd-ib-it2df2) ([578fdab](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/578fdab58944c3d1ca768e39ac3c9907fd063def))

## [0.140.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.139.0...v0.140.0) (2026-09-07)


### Features

* **dispatcher:** make the pre-dispatch criteria wall variant-aware (bd-ib-5k27yw) ([d20db47](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d20db472288a9ad1d52ef309658058980d6b2fad))

## [0.139.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.138.3...v0.139.0) (2026-09-07)


### Features

* **needs-attention:** surface each attention item's effective answer disposition (bd-ib-br6nmo) ([beee503](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/beee5039a544765b79c68677d6307c47cf3bad62))

## [0.138.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.138.2...v0.138.3) (2026-09-07)


### Bug Fixes

* **dispatcher:** read the needs-human sentinel from output, not script source ([067693d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/067693db609aafcdf8a907476ed80a298892cda8))

## [0.138.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.138.1...v0.138.2) (2026-09-07)


### Bug Fixes

* **dispatcher:** let the groom door's own claim reach the launch leg ([bbb4e3f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bbb4e3f252d545724aeb71ef6c2d2bea1046d805))

## [0.138.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.138.0...v0.138.1) (2026-09-07)


### Bug Fixes

* **bootstrap:** forward LIVESPEC_PLAN_UNATTENDED through the credential re-exec ([a8e3dc4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a8e3dc4cd22efe16d98409415c894f526f9b006b))

## [0.138.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.137.0...v0.138.0) (2026-09-07)


### Features

* **groom:** register a two-phase groom workflow variant under .fabro/workflows/ ([e740ab2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e740ab2591a6918801738171ed1bac20c0b7a04b))


### Bug Fixes

* **otel-receiver:** allowlist the sccache and registry cache attributes ([f183676](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f183676789171448e69a6f769f2e5ebe480f9597))

## [0.137.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.136.0...v0.137.0) (2026-09-06)


### Features

* **merge-hold:** render and honor merge_hold across the workflow, both seams, and three input families ([080eded](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/080eded670bd47a1e33141c0d84b8e5c10fe91c0))


### Bug Fixes

* **dispatcher:** a merge-held run terminates green at the pr stage ([a066168](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a066168ef6c32e8600e1e8f0aa35433ddc6c2317))
* **dispatcher:** pair loop-selection import cleanup with module surface test ([638667d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/638667dd4499535704a6212f2356be2093ff2c90))

## [0.136.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.135.0...v0.136.0) (2026-09-06)


### Features

* **groom:** open the groom door from backlog to active under a claim and a pin ([c017389](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c017389aa147f4d91ac7ab524ecc10a3cfd6d4ce))
* **groom:** read a workflow variant's kind from its own run config ([aa104a9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/aa104a96dda79c13bc0156e5ca1c6be2e0002954))
* **groom:** record a groom run's draft on the ledger when it needs a human ([8cd9d51](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8cd9d51354e2520ca1c68d06502c7df665af9472))
* **groom:** refuse an apply dispatch that does not resolve to a groom variant ([f318aa4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f318aa4f35ca5940fc4e47fdb7f88da26fdfebe6))

## [0.135.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.134.0...v0.135.0) (2026-09-06)


### Features

* **needs-attention:** the held-item lifecycle — reclaimed, unreconciled, discriminated, and surfaced once ([3d794a5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3d794a540d7fe3ce4e906e0df138853f4c756dbf))

## [0.134.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.133.2...v0.134.0) (2026-09-06)


### Features

* **drive:** add the set-merge-hold valve, its forge arm/disarm, and a merge_hold projection field ([f8bcfd1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f8bcfd117d40487fa671604b91d39bf8779711df))
* parse the two v100 groom-cut policy settings as inert configuration ([0fb0a0f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0fb0a0f2f925e16861babddfeb85cb178e9be197))


### Bug Fixes

* **groom:** gate approved-slice filing on a recorded approval (bd-ib-ouoq) ([1064ffe](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1064ffe5a7a836b6cadc66d1f480f762dfcf610f))

## [0.133.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.133.1...v0.133.2) (2026-09-06)


### Bug Fixes

* **otel:** bind the OTLP receiver on the tailnet for a remote-factory dispatch ([c7710ae](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c7710ae3fa62d182b01f247e00d04e19d2003a57))

## [0.133.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.133.0...v0.133.1) (2026-09-06)


### Bug Fixes

* **plan:** refuse a plan archive while code outside plan/ reads it by path ([bdc37b1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bdc37b1ee6237b849042d3322bf080cd8abd8b94))

## [0.133.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.132.0...v0.133.0) (2026-09-06)


### Features

* **dev-tooling:** hold every registered workflow variant to the bundle's seam parity ([43c76e7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/43c76e75f72b8317f5c704b38e54e91814273441))
* **dispatcher:** pin the resolved workflow variant to the work-item ledger ([5f9e3a3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5f9e3a3a40fcd3910b53abab12c28e8eda407efd))

## [0.132.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.131.1...v0.132.0) (2026-09-06)


### Features

* **dispatcher:** resolve named workflow variants from a dispatcher.workflows registry ([f0a170b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f0a170b4f8efec6ec74bf6fd68efa7dcbd9d0a25))

## [0.131.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.131.0...v0.131.1) (2026-09-06)


### Bug Fixes

* **dispatcher:** journal a registered-install lag warning when a stale session executes an older plugin build (bd-ib-h3mm) ([54da25d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/54da25d9aeba885cec26f1680136d53a27c8e798))

## [0.131.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.130.1...v0.131.0) (2026-09-06)


### Features

* **drive:** resolve-blocked carries the human answer as a ledger comment so the re-dispatch brief flows it (bd-ib-uuohty) ([f3f7f63](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f3f7f6346e74e00ebf0cb8d5392abfb94cf022db))

## [0.130.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.130.0...v0.130.1) (2026-09-06)


### Bug Fixes

* **dispatcher:** key the heartbeat liveness probe on the dispatch id ([9636a96](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9636a969f8e218c48394fdb67c015bb16c03f9d3))
* **plan:** tag a metadata-less epic instead of raising KeyError ([6c9e7dd](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6c9e7ddebd332f6d5cbf82e5b9d4f8dbf1cb4f91))

## [0.130.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.129.1...v0.130.0) (2026-09-06)


### Features

* **needs-attention:** carry the needs-human run's own account on the valve ([79192c6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/79192c6a9a20d8051e8131fc1709a0b910728003))

## [0.129.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.129.0...v0.129.1) (2026-09-05)


### Bug Fixes

* **dispatcher:** janitor venue provisions the janitor checkout itself (bd-ib-ttmeb2) ([0e74c1f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0e74c1facd4896ffbf97eccbe379140ac5b08e32))

## [0.129.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.128.0...v0.129.0) (2026-09-05)


### Features

* **discuss-work-item:** interactive stand-by skill over the context loader (bd-ib-kr334k) ([e9e4d4c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e9e4d4c598f4e2e78760f4dd75b61c3c6f18d318))

## [0.128.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.127.0...v0.128.0) (2026-09-05)


### Features

* **context:** item-context read primitive and `context --json` (bd-ib-g4lj2w) ([1b221da](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1b221dacfc03e3f5c2f6e1689216b107ea338c0f))

## [0.127.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.126.0...v0.127.0) (2026-09-04)


### Features

* **plan:** one-shot idempotent plan-record migration (bd-ib-bmxumc) ([eea591f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/eea591facf56a82793dca5e530a32f30922b02a5))

## [0.126.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.125.0...v0.126.0) (2026-09-04)


### Features

* **plan:** typed next_action metadata is the resume authority (bd-ib-yq2tx6) ([30ff89d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/30ff89d4045bb1f52488f03aa626a42cacddb7c3))

## [0.125.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.124.3...v0.125.0) (2026-09-04)


### Features

* **plan:** write the plan-identity anchor and plan_slug on every epic route (bd-ib-cwhos6) ([3779e93](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3779e93ddcfaa40a34f9dc27b5154d709a404f63))

## [0.124.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.124.2...v0.124.3) (2026-09-04)


### Bug Fixes

* **dispatcher:** substitute the resolved contract's inputs into the overlay's prepare commands (bd-ib-8atx) ([79066c7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/79066c796fa1507e3789f959fe9893a8b2750a44))

## [0.124.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.124.1...v0.124.2) (2026-09-02)


### Bug Fixes

* **otel-receiver:** allowlist the factory build-telemetry scheme attributes ([44ca04f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/44ca04f5d8bb755f53b51c19ffbd7ef859f67879))

## [0.124.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.124.0...v0.124.1) (2026-08-31)


### Bug Fixes

* **checks:** the doc-only target parse ignores comments (bd-ib-vblnq2.8) ([acaf0ed](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/acaf0ed2bd954d7ca95d329dee78dc3ea8f92c9e))

## [0.124.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.123.0...v0.124.0) (2026-08-31)


### Features

* **checks:** guard that the integration gates are wired into CI and the doc-only pre-push path (bd-ib-vblnq2.6) ([4217d29](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4217d291db0dd102770278dec29288e05ff0db9a))

## [0.123.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.122.0...v0.123.0) (2026-08-31)


### Features

* **contract:** retire MEASURED_EXEMPTIONS by converting its six sites (bd-ib-vblnq2.2) ([0eb564d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0eb564d009b544b35993050937c155f186487753))

## [0.122.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.121.0...v0.122.0) (2026-08-31)


### Features

* **payload:** template the implement-work-item payload from the resolved integration contract (bd-ib-b7xpzl) ([39526e5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/39526e5c4840da7f7fabc64b71144f11bf67bb5f))

## [0.121.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.120.0...v0.121.0) (2026-08-31)


### Features

* **dispatcher:** conformance-premise contract fields with a closed mode enumeration ([69bd21a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/69bd21a07d5949c6aee7c835bf358b7cacc2892b))

## [0.120.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.119.0...v0.120.0) (2026-08-30)


### Features

* **dispatcher:** validate the declaration against the build's schema version before dispatch (bd-ib-6nbduv) ([b80532a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b80532a65afd319210a82163f6990fc698fcfebe))

## [0.119.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.118.1...v0.119.0) (2026-08-30)


### Features

* **dispatcher:** retire the stale-run-sweep alias of reconcile-runs (bd-ib-az73w3) ([ba050ea](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ba050ea3849ef0a7c184e90c073cc71ae2b0e24e))

## [0.118.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.118.0...v0.118.1) (2026-08-30)


### Bug Fixes

* **dispatcher:** journal a reconcile-runs-pass record from the standalone command (bd-ib-gjfcor) ([dd73e4e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/dd73e4ea2dade13e2102e94ef79a1ddb1f0f2a77))

## [0.118.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.117.0...v0.118.0) (2026-08-30)


### Features

* **dispatcher:** resolve the integration contract once at plan build and project it to every seam (bd-ib-t5ierm) ([d9c53a3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d9c53a3e8f015f3ada874f668549a1d17177d706))

## [0.117.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.116.0...v0.117.0) (2026-08-30)


### Features

* **dev-tooling:** check-no-fleet-toolchain-literals gate over the dispatcher package (bd-ib-u2d62p) ([095217d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/095217db4992ab87783fe32d7f9b0fe7eb9e33a8))

## [0.116.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.115.0...v0.116.0) (2026-08-30)


### Features

* bound the slot hold for a parked run whose work-item is still live ([93dc544](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/93dc544b9a89eb3d8317efb8b8775724f28f1437))

## [0.115.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.114.0...v0.115.0) (2026-08-30)


### Features

* **dispatcher:** retire the eight per-key resolver modules onto the generic integration-contract resolver (bd-ib-oahwsi) ([a85a944](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a85a944bb105c52405a877487f22e6ca4c5a5633))
* **dispatcher:** typed RepoIntegrationContract schema and generic Declared|FleetDefault|Defective resolver (bd-ib-oahwsi) ([741b102](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/741b102d7db6c6d2fba53b97a33dc035f59a0e06))

## [0.114.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.113.0...v0.114.0) (2026-08-30)


### Features

* **dispatcher:** reconcile every factory automatically on the dispatch path ([6d6e32e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6d6e32e2c6d6c3256fdbcdaa2b25342abfb77794))
* **dispatcher:** route the reconciler's orphan join through RunAttribution ([09027d4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/09027d4b99966456738bba04ffce30ccde3ad134))
* **needs-attention:** surface orphaned factory runs from the reconciler's dry run ([5203641](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5203641909f61c23f3234d2954f74f143849adb6))

## [0.113.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.112.1...v0.113.0) (2026-08-30)


### Features

* **dispatcher:** couple lifecycle writes to run reconciliation and add the orphaned-factory-run invariant (bd-ib-nby2xp) ([c5405e5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c5405e53418dfc76ed43d7b209c9a796e81c73f3))

## [0.112.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.112.0...v0.112.1) (2026-08-30)


### Bug Fixes

* **reconcile:** reach the real Fabro server over its own API (bd-ib-gzoayo) ([91053da](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/91053daf4bdacee15a5149b25cd10820d9cb6867))

## [0.112.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.111.0...v0.112.0) (2026-08-30)


### Features

* **workflow:** retire the in-loop human gate — needs-human terminates at a needs_human node and routes to the ledger (bd-ib-dgu3qg) ([b4e140b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b4e140b45ced7d3e6c71a0a2fe152c14400aeafb))

## [0.111.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.110.0...v0.111.0) (2026-08-30)


### Features

* **dispatcher:** reconcile-runs over every factory's run inventory (bd-ib-iqyekp) ([60e15bc](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/60e15bc7f6f125927cbd6e69b9d27bde4bf4a568))

## [0.110.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.109.0...v0.110.0) (2026-08-30)


### Features

* **dispatcher:** shared run-to-item attribution helper (bd-ib-qvy7sv) ([35ecad1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/35ecad162d21e17836daaa54cada25789109a3af))
* **dispatcher:** stamp the Fabro run id and factory onto the work-item (bd-ib-qvy7sv) ([fc535ee](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fc535eec978b23e2ce8a4c9bf262ce4d9a53485c))


### Bug Fixes

* **dispatcher:** name the resolved factory in every blocked-run recovery command (bd-ib-qvy7sv) ([dd3d8a3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/dd3d8a35f420f36d48807b6c14ea0936ab8aa14c))

## [0.109.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.108.0...v0.109.0) (2026-08-30)


### Features

* **dispatcher:** operator clearance for a provider-exhaustion record (bd-ib-yhbsd4.4) ([e3d1f15](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e3d1f150f8c4f84f475e8f6371bd5d754ff6ad3a))

## [0.108.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.107.0...v0.108.0) (2026-08-30)


### Features

* **dispatcher:** declared janitor-core provisioning (bd-ib-qx4wmo) ([f246498](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f246498c93aa8913d73943450231ca78bc330f6a))

## [0.107.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.106.0...v0.107.0) (2026-08-30)


### Features

* **telemetry:** surface stall-watchdog cancellations as OTLP spans (bd-ib-o3cpko) ([ab930a4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ab930a41c1500105b2b683ee5f2e318801a0c0ad))

## [0.106.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.105.0...v0.106.0) (2026-08-30)


### Features

* **watchdog:** journal a per-poll run-discovery record (bd-ib-n6cobe) ([e0abdaf](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e0abdaf7be17f9c66bd2619c83a40d99714fd53c))

## [0.105.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.104.0...v0.105.0) (2026-08-30)


### Features

* **needs-attention:** name the empty-diff leg on a zero-change acceptance park (bd-ib-fkpkmv) ([1d2b6e7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1d2b6e7f493d7c4a7bafb0858e8241afe3f7e9f9))

## [0.104.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.103.0...v0.104.0) (2026-08-30)


### Features

* resolve the default branch in the factory workflow-drift guard ([afd86c2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/afd86c214d08a51f6c7a592f2876a073b0017d4d))


### Bug Fixes

* restore default branch resolver export ([447ee3c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/447ee3cc45e908099b823704e0a5e616d972cc25))

## [0.103.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.102.0...v0.103.0) (2026-08-30)


### Features

* **acceptance:** refuse an empty merged diff for a change-implying item (bd-ib-jzikwb) ([897af44](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/897af44db3b3a9d7d8c36d0c717b372fc31a196e))

## [0.102.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.101.0...v0.102.0) (2026-08-30)


### Features

* **dispatcher:** janitor venue is the merged default-branch tip (bd-ib-f3uuqm) ([9dc92e6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9dc92e65617adf8c94ed4c7b55b0ace89bfb1817))

## [0.101.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.100.0...v0.101.0) (2026-08-30)


### Features

* a file-scoped check matching zero files reports vacuous-match ([d00ae84](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d00ae844177650bb9b1b14951680eae03c6bbd98))

## [0.100.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.99.0...v0.100.0) (2026-08-30)


### Features

* **acceptance:** classify gradeable criteria change-implying by default (bd-ib-e3lr6p) ([5344115](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5344115214fb9721510a750e8da35122efd30a71))

## [0.99.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.98.1...v0.99.0) (2026-08-30)


### Features

* **dispatcher:** resolve the post-merge janitor check-suite from a committed declaration ([a6ebaaf](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a6ebaafba2c17f3b169de7085509525ea0faa4d7))

## [0.98.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.98.0...v0.98.1) (2026-08-30)


### Bug Fixes

* **beads112-rehearsal:** secret scan must see the leaked VALUE, not only the variable name ([cb9662b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cb9662b0afe41fcfac9a4d727361b0388c66d0f3))

## [0.98.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.97.2...v0.98.0) (2026-08-29)


### Features

* surface dispatcher-currency staleness as a non-blocking fact ([32ece3f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/32ece3f3fc18813e02b50e810615c2e6ee186e9c))

## [0.97.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.97.1...v0.97.2) (2026-08-29)


### Bug Fixes

* re-base dispatch-admission currency gate onto a deliberate release floor ([9db824f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9db824fd09f827df270f1664c6a8fd5c97de0aee))

## [0.97.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.97.0...v0.97.1) (2026-08-29)


### Bug Fixes

* remove the never-emitted updated_at watchdog liveness fallback ([f1b6144](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f1b6144e31160f72693eb6735ffaf88d35278cec))

## [0.97.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.96.1...v0.97.0) (2026-08-29)


### Features

* cover fabro preflight port contract ([031cef0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/031cef084853347dfa191b26592074b2126a08af))


### Bug Fixes

* align tier-1 EUTs with measured fabro 0.254 run semantics ([a50bdb7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a50bdb730b1c4457d448d524aa2d7207a313f8fc))
* track per-node acp.command adapters in tier-0 EUT ([bd624cc](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bd624ccbe2c16261135e8209cee4350ce83d9874))

## [0.96.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.96.0...v0.96.1) (2026-08-29)


### Bug Fixes

* **acceptance:** narrow the telemetry arm to genuine verification assertions ([4b1f376](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4b1f37638bf1e6edff776001d427534f489a2354))

## [0.96.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.95.3...v0.96.0) (2026-08-29)


### Features

* **dispatcher:** resolve the janitor-bootstrap recipe the repository declares ([08a5482](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/08a5482b6200aa935b4a29a514cded524f82e342))


### Bug Fixes

* degrade the post-merge janitor on a defective bootstrap recipe ([8c84ffb](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8c84ffb783d924e59cd7e75deda99b4e2f4a2760))

## [0.95.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.95.2...v0.95.3) (2026-08-29)


### Bug Fixes

* **dispatcher:** let a reader other than the writer check a preserved pointer for danglingness ([86816e6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/86816e6ef9074de8ff3967104d4b43e8baa0fb03))
* **dispatcher:** make a digest-less preserved pointer say why, and print a runnable retrieval command ([7fa5cd7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7fa5cd75174519b0519ac8c95256b40f3aeaa538))
* **dispatcher:** record the PR that carries the item's merge sha ([27e5c28](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/27e5c28c296cab6ba4b4b998c68f959111d34e23))

## [0.95.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.95.1...v0.95.2) (2026-08-29)


### Bug Fixes

* **dispatcher:** count wip_cap claims across every checkout of the tenant ([fe10bf3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fe10bf36ccb9f511739061505da50aece2ef8453))

## [0.95.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.95.0...v0.95.1) (2026-08-29)


### Bug Fixes

* **dispatcher:** derive the exhaustion record's provider from the observed failure ([4385cb8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4385cb8a1c423371d2dac02405fe084ef8c6879a))

## [0.95.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.94.2...v0.95.0) (2026-08-28)


### Features

* **dispatcher:** journal a dead-implementer truncation with its governing condition ([61e39f3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/61e39f3f0906c65f22574522de0e84a3acdcb22e))

## [0.94.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.94.1...v0.94.2) (2026-08-28)


### Bug Fixes

* **dispatcher:** split criteria at a sentence-ending initialism ([dcf13d5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/dcf13d51cada6ce4dc46f6ef8986bdd489f594b5))

## [0.94.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.94.0...v0.94.1) (2026-08-28)


### Bug Fixes

* **store:** clear blocked_reason on every exit from blocked ([9fba720](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9fba720264824b369219db82dbfe73fddccd5fbc))

## [0.94.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.93.0...v0.94.0) (2026-08-28)


### Features

* **detection:** record detection coverage and surface staleness ([a1a69b1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a1a69b1f3e6cbfb947b022b9a3c8594d09b0e604))

## [0.93.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.92.0...v0.93.0) (2026-08-28)


### Features

* **dispatcher:** execute the rework-pending re-dispatch ([7ccf6f6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7ccf6f64d6bc8d54f4486c30e3c4c506fcd227eb))

## [0.92.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.91.0...v0.92.0) (2026-08-28)


### Features

* **dispatcher:** stamp and materialize the rework:pending marker ([74a97bf](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/74a97bf975d8bf50c9f2402150af6f87d90f3b3d))

## [0.91.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.90.0...v0.91.0) (2026-08-28)


### Features

* **dispatcher:** add the take-never-file loop probe subcommand ([5a01ce8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5a01ce8730c399f67bec6716fdb63964bec138c7))

## [0.90.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.89.0...v0.90.0) (2026-08-28)


### Features

* **dispatcher:** route every criteria gate through one primitive ([32b25ed](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/32b25ed5c3ffa109c434895792b20289fe1a10d3))

## [0.89.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.88.2...v0.89.0) (2026-08-28)


### Features

* **dispatcher:** close the preflight and post-merge step discipline ([83d26f3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/83d26f3cd6fa161eb77474e90d5353aaafe73fbd))

## [0.88.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.88.1...v0.88.2) (2026-08-28)


### Bug Fixes

* **dispatcher:** fold flush-left wrapped continuations in the acceptance criteria parser ([e4db2e5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e4db2e5ddbc11732c4b34323a27ef88f2910cb46))

## [0.88.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.88.0...v0.88.1) (2026-08-28)


### Bug Fixes

* **dispatcher:** route a failed AI acceptance pass to ready with a named recovery ([03da32d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/03da32d354fd99da9424b40e3878f755badee7df))

## [0.88.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.87.0...v0.88.0) (2026-08-28)


### Features

* **dispatcher:** resolve the declared master-CI pipeline and retire the fail-open cases ([f391378](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f3913780e2be6056724b962f84a1534694300dd7))


### Bug Fixes

* **dispatcher:** refuse a present-but-unusable master-CI declaration ([1da118c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1da118cff6d4eb408a2ee543deb937a4b96b61d1))

## [0.87.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.86.0...v0.87.0) (2026-08-28)


### Features

* **dispatcher:** widen acceptance verdicts to the ratified evidence rule ([b68358b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b68358be0e97b97417dfaa47fcb689cc11734d9b))

## [0.86.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.85.0...v0.86.0) (2026-08-27)


### Features

* **dev-tooling:** guard the overloaded spec id field against presence tests ([2c618e8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2c618e8ecaff514af49cc125d81313a1706c042f))


### Bug Fixes

* **dev-tooling:** catch annotated aliases and walrus reads of the spec id field ([84dcdd2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/84dcdd2c2fd16ad04e78f722e825c0c922b71711))

## [0.85.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.84.4...v0.85.0) (2026-08-27)


### Features

* report which adopters have resolved the current release ([6e8ba62](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6e8ba62cadd5b7b631f80df6ac547ce38c23962e))


### Bug Fixes

* key release adoption on this plugin's name, not the governed project's ([86c985a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/86c985aa70309e6e7ce57ad473186faf8c928cb8))

## [0.84.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.84.3...v0.84.4) (2026-08-27)


### Bug Fixes

* **dispatcher:** render an engine-escalated run as an escalation, not a gate ([7424e26](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7424e26a0824ccef2ae4d2e5e28cbe188844b67a))

## [0.84.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.84.2...v0.84.3) (2026-08-27)


### Bug Fixes

* **dispatcher:** shell-quote ACP adapter env values so they survive tokenization ([28947b0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/28947b0b00580b29fbfe307b44618c17cad0c3e3))

## [0.84.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.84.1...v0.84.2) (2026-08-27)


### Bug Fixes

* **dispatcher:** stop injecting the plan anchor into the dispatched agent's brief ([02bb61c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/02bb61ca7157c97355c1529b1fd43d79561f7982))

## [0.84.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.84.0...v0.84.1) (2026-08-27)


### Bug Fixes

* **plan:** discriminate the plan anchor marker from a spec commitment ([35712fa](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/35712fabf35c31bb4039fb8c0fb1fecb3c180c27))

## [0.84.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.83.0...v0.84.0) (2026-08-26)


### Features

* **dispatcher:** stamp journal invoker attribution at the append chokepoint ([d4371ad](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d4371adcc2fc0d8e4682ecf6e1c9f6605f9ace2b))

## [0.83.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.82.0...v0.83.0) (2026-08-26)


### Features

* **needs-attention:** surface envelope validation failures instead of dropping candidates ([cad326d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cad326da20574672b96dc42b87703cb9b8e3a75e))

## [0.82.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.81.0...v0.82.0) (2026-08-26)


### Features

* **dispatcher:** render the Codex ACP adapter at its baked path via CODEX_CONFIG ([1d08013](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1d080136abc8e95afc79adc63c29b0bfaf27e6fb))

## [0.81.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.80.1...v0.81.0) (2026-08-26)


### Features

* **dispatcher:** resolve every ACP node's adapter from three configuration layers ([8cb6023](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8cb6023644737102016f4f2373e7c8b9ceecee35))

## [0.80.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.80.0...v0.80.1) (2026-08-26)


### Bug Fixes

* **dispatcher:** report loop --dry-run picks instead of an empty outcome list ([115b3e4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/115b3e4b6fbc68a6bf9c1a14808a396ce703bf67))

## [0.80.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.79.1...v0.80.0) (2026-08-26)


### Features

* **dispatcher:** make the Codex compaction token limit configurable ([116526a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/116526a6c74ff8d12bb14ff55654bf5bd07e89e3))
* **dispatcher:** resolve every node timeout from configuration ([702d5a5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/702d5a596b875ae33bc774b51a5715c153e84fd1))

## [0.79.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.79.0...v0.79.1) (2026-08-26)


### Bug Fixes

* bind explicit implementer tables to Codex ([2149839](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2149839c13c0303d5b0963e4498396cc7ce0d681))

## [0.79.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.78.1...v0.79.0) (2026-08-26)


### Documentation

* **plan:** record the model commission and classify item A as a minor release ([6355423](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6355423f7595c6f98046f91c2cbfedcd29d9b389))

## [0.78.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.78.0...v0.78.1) (2026-08-26)


### Bug Fixes

* switch implementer default adapter ([4db2ec4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4db2ec47c7621ca620928de120d3d67fd401b7ef))

## [0.78.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.77.0...v0.78.0) (2026-08-26)


### Features

* specify ready-work aging attention ([5c87205](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5c87205deea87b66915b4a70dcbfb0837df365cf))


### Bug Fixes

* batch ready-aging watchable run lookup ([097a748](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/097a7485af603c2b1c0f66d7274a79abbb88d104))

## [0.77.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.76.0...v0.77.0) (2026-08-26)


### Features

* declare ready aging threshold config ([541ab9a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/541ab9ad7ef7e933f04673b11765600d0826a64d))

## [0.76.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.75.1...v0.76.0) (2026-08-26)


### Features

* cover complete wait composition ([b33e5d7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b33e5d7c06f9be8726b20fff30977709d9f4eca6))


### Bug Fixes

* guard needs-attention ownership boundary ([cd6c361](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cd6c361f0d9d85046158f46e56facad978b4e359))

## [0.75.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.75.0...v0.75.1) (2026-08-26)


### Bug Fixes

* allow leased publish retry after rebase ([1a30cdc](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1a30cdc8e19405f79be41cab674728183351c3c6))

## [0.75.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.74.0...v0.75.0) (2026-08-25)


### Features

* cover capacity needs-attention residue ([9763d7c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9763d7c93db1abc06c5bac60e0144e942488d0e7))


### Bug Fixes

* honor capacity accounting verdict ([4e9082e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4e9082e9daed9f21e87524f9de06cd7e135b2f26))

## [0.74.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.73.0...v0.74.0) (2026-08-25)


### Features

* require durable ready dwell instants ([b104177](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b104177bde21a52b477ef0778e603fcf3941ee7b))

## [0.73.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.10...v0.73.0) (2026-08-25)


### Features

* specify read-only claim accounting projection ([c6ef34d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c6ef34dde10e6d27f378e75b5885fd0bfd322e28))

## [0.72.10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.9...v0.72.10) (2026-08-25)


### Bug Fixes

* **spec:** ratify the orchestrator-owned attention facts (v079) ([7c54eb3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7c54eb390a4910bfeea3b9ec0c5d60fbd58e1a11))

## [0.72.9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.8...v0.72.9) (2026-08-25)


### Bug Fixes

* **spec:** ratify detection coverage records and staleness facts (v078) ([4dcd6ae](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4dcd6ae1f27b55eba3f4276ea2e36f2d7965fada))

## [0.72.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.7...v0.72.8) (2026-08-25)


### Bug Fixes

* **spec:** ratify the needs-attention machine envelope (v077) ([3ec5872](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3ec587218891a54c253e8e241b7aad50ab613df8))

## [0.72.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.6...v0.72.7) (2026-08-25)


### Bug Fixes

* **spec:** ratify the take-never-file loop probe (v076) ([79191c4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/79191c45e4d5810631f3b8e0e2296105075585c1))

## [0.72.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.5...v0.72.6) (2026-08-25)


### Bug Fixes

* **spec:** ratify the owned-restore-item rule for temporary settings (v075) ([ccbedb9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ccbedb97b9351f477b784672969fe021f951439c))

## [0.72.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.4...v0.72.5) (2026-08-25)


### Bug Fixes

* **spec:** ratify the step discipline and preflight persistence (v074) ([aac849d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/aac849d51ffd1a72867e97184b68f305662b76a0))

## [0.72.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.3...v0.72.4) (2026-08-25)


### Bug Fixes

* **spec:** ratify journal invoker attribution (v073) ([6def7aa](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6def7aa0615051727bb263ec137043d6f7394915))

## [0.72.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.2...v0.72.3) (2026-08-25)


### Bug Fixes

* **spec:** ratify the four-verdict evidence rule and criteria walls (v072) ([89e0345](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/89e0345f0f0ac2479210fe718860e06e2a13f847))

## [0.72.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.1...v0.72.2) (2026-08-25)


### Bug Fixes

* **spec:** ratify the executable rework-pending re-dispatch contract (v071) ([e293349](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e293349f5b027706753e4671ea1b570b265a9f92))

## [0.72.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.72.0...v0.72.1) (2026-08-24)


### Bug Fixes

* **spec:** ratify check-path-anchored gap-tied closure (Gate 3) ([c620f51](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c620f51090246fafec22bf9254286760beed8756))

## [0.72.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.71.8...v0.72.0) (2026-08-24)


### Features

* add check-path-anchored gap-tied closure decision ([637f5d5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/637f5d5e11146ad2f347ccbc28fa273c07dfec05))

## [0.71.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.71.7...v0.71.8) (2026-08-23)


### Bug Fixes

* recognize Codex cost span model metadata ([630503f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/630503fa1efbbd2663935a3e6abc1c291a19b085))

## [0.71.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.71.6...v0.71.7) (2026-08-23)


### Bug Fixes

* guard acceptance diff provenance ([4c28a92](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4c28a92d3741769d919658bdafa477a97d944dc7))

## [0.71.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.71.5...v0.71.6) (2026-08-23)


### Bug Fixes

* grade acceptance against pull request diff ([d5849ed](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d5849edd5389fa5c458823386e38a8c572eae4c5))

## [0.71.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.71.4...v0.71.5) (2026-08-23)


### Bug Fixes

* harden preserve reference failure paths ([3749739](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/374973930a859a8366817d1ac34061b9ae1e3f6a))

## [0.71.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.71.3...v0.71.4) (2026-08-23)


### Bug Fixes

* make dead implementer route fail closed ([cd03106](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cd0310650534e67ed7c21b1393fc3e351fa054e5))
* require dead implementer workflow breaker ([e2216db](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e2216dbfbff1f6194c778ed7bc186642a7eb52b0))

## [0.71.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.71.2...v0.71.3) (2026-08-23)


### Bug Fixes

* preserve all fabro patch references ([c279cf8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c279cf81ef0bf743c937d6988f164342bc8fca35))

## [0.71.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.71.1...v0.71.2) (2026-08-23)


### Bug Fixes

* **config:** stop an unreadable config from silently disabling the pre-push ledger gate ([f605992](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f605992e548909afffc6adf469cbadfefa846357))

## [0.71.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.71.0...v0.71.1) (2026-08-23)


### Bug Fixes

* **config:** stop blaming the connection prefix for a config that will not parse ([c6c4512](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c6c4512f45108424959ad2954a4a862a204ca4ea))

## [0.71.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.70.0...v0.71.0) (2026-08-23)


### Features

* preserve failed fabro work by reference ([5a68bfc](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5a68bfc28ed14cd7e67315e878a73ac8db5e7f13))

## [0.70.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.69.0...v0.70.0) (2026-08-23)


### Features

* report codex token spend ([f4cf86c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f4cf86c42e7274c893a1573c39ee7a2ee30279e3))

## [0.69.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.68.5...v0.69.0) (2026-08-23)


### Features

* gate dispatch on provider exhaustion ([918c94c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/918c94c06e43b2153f9e53e1844d491cb5bfa1a1))

## [0.68.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.68.4...v0.68.5) (2026-08-22)


### Bug Fixes

* harden ai acceptance matching ([05f02f9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/05f02f9f2ea56875c4397a597dc7e8ddd831563f))
* preserve one-line acceptance criteria ([8cc2d2d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8cc2d2dd4850d820f9be65d2254323c2df72f6a3))
* relax acceptance diff evidence threshold ([73be6d4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/73be6d4d9cbe38399f6404ba939d63f4658048aa))

## [0.68.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.68.3...v0.68.4) (2026-08-22)


### Bug Fixes

* model no-change dispatch closure ([0030a7c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0030a7c01e8c8b8c8d342486211a028dc6e50712))
* reject net-zero dispatch completion ([2e11405](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2e114059c9ebe3320e0193238e565a314539bfcb))

## [0.68.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.68.2...v0.68.3) (2026-08-22)


### Bug Fixes

* fail ai acceptance without criteria ([3132ace](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3132aceedee9b1a971eddd2d5e289bd8dd9ba533))

## [0.68.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.68.1...v0.68.2) (2026-08-22)


### Bug Fixes

* surface bd stderr on zero exit ([45f6761](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/45f67615b46f5a410b2895a5d9471a28ed1c3ff8))

## [0.68.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.68.0...v0.68.1) (2026-08-22)


### Bug Fixes

* keep parsed fabro failure on failed outcomes ([36026f9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/36026f97eee381671839bf1d3f7c8b2a5822d818))
* re-inspect when the fabro failure block lands after the terminal inspect ([ac7ebb0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ac7ebb0f8e5ddd73aff24e001bd6e40634773c84))
* surface fabro failure and calibration telemetry ([89997f9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/89997f93d91b936b9721ab72391a20a81a0843dd))

## [0.68.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.67.2...v0.68.0) (2026-08-22)


### Features

* flag ledger MiniJinja opener contamination ([2dc9f1c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2dc9f1cd05e6357289801740dcb8d565127dd6eb))

## [0.67.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.67.1...v0.67.2) (2026-08-22)


### Bug Fixes

* release pre-run dispatch claims ([52d826f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/52d826fca841a86b717584a312fda5f6ee886540))

## [0.67.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.67.0...v0.67.1) (2026-08-22)


### Bug Fixes

* parse inventory sql table output ([3b371e4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3b371e430905bbc542e3ccef45d80258d7296780))
* prove inventory capture uses real bd surface ([e982ca5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e982ca5e90bbeeb6c58fecc2889ec6c339aaf36c))

## [0.67.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.66.1...v0.67.0) (2026-08-22)


### Features

* refuse templated dispatcher goals ([c44f13d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c44f13dd3ffc904e1d5b081101dd9c0db6aa24cd))

## [0.66.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.66.0...v0.66.1) (2026-08-22)


### Bug Fixes

* surface cap override on drive deferral ([c279c10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c279c108154162e682db667e5676399e46c45803))

## [0.66.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.65.3...v0.66.0) (2026-08-22)


### Features

* compare Fabro enemy unit test pairs ([b97af6e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b97af6efee28e85664b1f82b74db4b8f0375ca62))


### Bug Fixes

* preserve Fabro EUT identity defaults ([ef6b4c0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ef6b4c0fe61850656f7d9e1e9495c082c2ca5abb))

## [0.65.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.65.2...v0.65.3) (2026-08-22)


### Bug Fixes

* request pr write permissions for app tokens ([b6a85cd](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b6a85cd8a0c922b126572c0a0d06fa8af10ff4ef))

## [0.65.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.65.1...v0.65.2) (2026-08-22)


### Bug Fixes

* pin shell-aware beads guard matching ([3377f7d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3377f7d4758eb2b204ad2b0751b2c7ea454546eb))
* unwrap tenant command prefixes ([6c77644](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6c77644134e91d79dfee472bee58bbb88810b699))

## [0.65.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.65.0...v0.65.1) (2026-08-22)


### Bug Fixes

* classify provider usage limits as permanent, not transient ([3e81196](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3e81196af27c2d30753545b232737dc26abdae1e))

## [0.65.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.64.2...v0.65.0) (2026-08-22)


### Features

* verify ledger plan handoffs ([c4daa57](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c4daa57cf5fa69a96a302422ba6ac33778b824b1))


### Bug Fixes

* account for capacity deferral holders ([2c2bf82](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2c2bf826fe65ffb862dade08bb9d19a039d40bc0))

## [0.64.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.64.1...v0.64.2) (2026-08-22)


### Bug Fixes

* reclaim green terminal wip slots ([f41f457](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f41f4578778ed44988c80bcfbaf234d07629eda5))

## [0.64.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.64.0...v0.64.1) (2026-08-22)


### Bug Fixes

* classify codex remote compaction failures ([4ab62a9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4ab62a980a158108b5070469b4d7786c4ae91dd3))

## [0.64.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.63.0...v0.64.0) (2026-08-22)


### Features

* pin Codex model tiers for factory ACP nodes ([7ca091d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7ca091d67c6f85a94d6ae28ae13d3c9299db1c10))

## [0.63.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.17...v0.63.0) (2026-08-22)


### Features

* emit dispatch factory telemetry ([370d841](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/370d841ea553f90995c872f643715def8cbde107))

## [0.62.17](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.16...v0.62.17) (2026-08-22)


### Bug Fixes

* diagnose capacity-held dispatch slots ([ae20af1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ae20af10ad2b1e37b62560f594bb73b1d991bfc9))

## [0.62.16](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.15...v0.62.16) (2026-08-22)


### Bug Fixes

* preserve unmodeled work-item metadata ([a2fbb36](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a2fbb36b331f9988f15a17fab3c99651874c29d7))

## [0.62.15](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.14...v0.62.15) (2026-08-22)


### Bug Fixes

* mark remote run_turn guard unobservable ([e105ea3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e105ea36e3639ccb15cf756ffedf87ebdbe5cc5f))

## [0.62.14](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.13...v0.62.14) (2026-08-21)


### Bug Fixes

* recover malformed plan archive timestamps ([08f92c7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/08f92c7409c4617c90916e2273cfaecee3718533))

## [0.62.13](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.12...v0.62.13) (2026-08-21)


### Bug Fixes

* keep plan archive timestamps parseable ([1bd8f6f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1bd8f6fe0c0a26e0e272bace9b610919da191b12))

## [0.62.12](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.11...v0.62.12) (2026-08-21)


### Bug Fixes

* **plan:** count ID-hierarchy children in the archive disposition gate ([ca83f58](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ca83f581203b0d502cc864ea32e3b232eabcaaa9))

## [0.62.11](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.10...v0.62.11) (2026-08-21)


### Bug Fixes

* allow reconcile-merged recovery from parked statuses ([8bc1f08](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8bc1f08d0e763bbc8e0909424000ee8a4e6c3cd2))

## [0.62.10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.9...v0.62.10) (2026-08-21)


### Bug Fixes

* cover malformed plan timeline comments ([1fb58d0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1fb58d033ed7d4a67e4b766ed846ed3f79bce7a1))

## [0.62.9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.8...v0.62.9) (2026-08-21)


### Bug Fixes

* avoid list-work-items child fanout ([ba8ac6b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ba8ac6bf4a7ac42427acb97bfdd15122ee052d3e))
* union dotted parents in list projection ([63274f8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/63274f8803620edee94f94fc2612a778cc844ce4))

## [0.62.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.7...v0.62.8) (2026-08-21)


### Bug Fixes

* journal resolved dispatch factory ([dc6319d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/dc6319d8b64e96a9960e299da383b2c605227259))

## [0.62.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.6...v0.62.7) (2026-08-21)


### Bug Fixes

* **dispatcher:** stop shipping the gh-refresh payload in one argv slot ([465f177](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/465f1775d2561921ebc51da21012637e24d9d807))

## [0.62.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.5...v0.62.6) (2026-08-21)


### Bug Fixes

* **otel:** backfill correlation by fabro run id ([2a9c03b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2a9c03bf83b374c080841f4bb983509cae029ee6))

## [0.62.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.4...v0.62.5) (2026-08-21)


### Bug Fixes

* project parent labels in work item JSON ([a3b2515](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a3b25154841d1e6c6367d8cbca52dcd755588ba0))

## [0.62.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.3...v0.62.4) (2026-08-21)


### Bug Fixes

* **dispatcher:** make the gh-wrapper bundle root resolvable so its tests are hermetic ([843207c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/843207c1f2dd2bde24fe667a5639773e4dd17365))
* project gh mint helper into sandbox ([1018548](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/101854805aa7dfdb5c33213971b492ac2bbf3e70))

## [0.62.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.2...v0.62.3) (2026-08-21)


### Bug Fixes

* stamp fabro run id from span events ([9afb620](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9afb6205827b9c311f369f7f26141d6114ccffee))

## [0.62.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.1...v0.62.2) (2026-08-20)


### Bug Fixes

* scope heading coverage TODO ownership arming ([7da375d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7da375da02fc016b4ca313310e1eb4dc9ddea369))

## [0.62.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.62.0...v0.62.1) (2026-08-20)


### Bug Fixes

* **intake:** put apply_intake_dor on the IOResult railway ([8a4ee4a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8a4ee4a2efff51c205937a5d8854ef79a1b8a3e5))
* **spec-reader:** put read_specification_history on the IOResult railway ([df316ea](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/df316eac3e0f410afeafb246535fbf5944d100de))

## [0.62.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.61.0...v0.62.0) (2026-08-20)


### Features

* **plan:** warn when plan-record authoring runs past a daily threshold ([7da225c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7da225c227f4f326f60de6658175e841367a5164))

## [0.61.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.60.0...v0.61.0) (2026-08-20)


### Features

* **plan:** let a session dispose a plan child with a recorded rationale ([7e732aa](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7e732aa4ec148c6399829e4c4bef76a0836266fd))

## [0.60.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.11...v0.60.0) (2026-08-20)


### Features

* **plan:** take the single recorded next action on an unattended resume ([8e6e7b5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8e6e7b5b82b3b2ef7a7d8920b27e561615a95fea))

## [0.59.11](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.10...v0.59.11) (2026-08-20)


### Bug Fixes

* read the list payload fabro inspect actually returns ([c617088](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c617088352e9da8c1b67534a49ea70f8607b0c06))

## [0.59.10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.9...v0.59.10) (2026-08-20)


### Bug Fixes

* preserve legacy content during tenant migration ([144e971](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/144e9716de509fc77a3d6c9ccc0d600a76a1ffc5))
* store acceptance criteria in native bead fields ([f27864f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f27864fe1a64a091ce930a99901f809170baa513))

## [0.59.9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.8...v0.59.9) (2026-08-20)


### Bug Fixes

* model deferred ledger status ([349def5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/349def5c5bc5ae271f418e7ef969829f2083cc72))

## [0.59.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.7...v0.59.8) (2026-08-20)


### Bug Fixes

* explain bd status open refusals ([e7bc570](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e7bc570f6663135a4b5b4ef22d1ce3dc62eea27a))

## [0.59.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.6...v0.59.7) (2026-08-20)


### Bug Fixes

* enforce authoritative bd dependency child surface ([93b6a15](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/93b6a158a5c6fd0136e72f0c547ce82ad0b8d33f))
* probe bd show child divergence ([0a1c614](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0a1c614f72cd08fa27aca3c314e67a82c8f96f66))

## [0.59.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.5...v0.59.6) (2026-08-20)


### Bug Fixes

* route fabro callers through port ([5b82627](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5b82627e40ece203e39794a735a5fe8260bb5d55))

## [0.59.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.4...v0.59.5) (2026-08-20)


### Bug Fixes

* document master-red recovery ([834bccf](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/834bccffab0f2c02f20a7652d1d20cca6bb5d7e4))

## [0.59.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.3...v0.59.4) (2026-08-20)


### Bug Fixes

* degrade post-merge primary pull failures ([3ae648b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3ae648b8f889189ffb57515f4d445f7f865e7045))

## [0.59.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.2...v0.59.3) (2026-08-20)


### Bug Fixes

* **honeycomb:** make the run_turn dead-man window sane and the payload API-valid ([462611c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/462611c04dc00d855979a79e1aa171c0c89a4fe3))

## [0.59.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.1...v0.59.2) (2026-08-19)


### Bug Fixes

* distinguish sibling-status lookup failure causes and kill the omission trap ([5f9a082](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5f9a082216f9b6f3e73d7d2a3114a4db1bb5de86))

## [0.59.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.59.0...v0.59.1) (2026-08-19)


### Bug Fixes

* count tracked plan children ([e83370f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e83370f2517da0cf6a0b2b273a113a7acf922a29))

## [0.59.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.16...v0.59.0) (2026-08-19)


### Features

* add fabro port facade ([a37cae1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a37cae1151b3c3360cd632494c73e1cfbe0e03d5))

## [0.58.16](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.15...v0.58.16) (2026-08-19)


### Bug Fixes

* instrument otel trace receiver diagnostics ([8344d72](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8344d722ab56406007c8fb514d8b1a8208b09706))

## [0.58.15](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.14...v0.58.15) (2026-08-19)


### Bug Fixes

* route sandbox otel to owned receiver ([721c581](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/721c5818737e941e18214b0241f49bd045d94dce))

## [0.58.14](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.13...v0.58.14) (2026-08-19)


### Bug Fixes

* keep sandbox otel service identity ([a08c448](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a08c448f802b75c566d97efb91fad86bb5138253))
* project fabro service name for sandbox otel ([5cf21cb](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5cf21cb8427ae455215391c8102771b45ee21bdf))

## [0.58.13](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.12...v0.58.13) (2026-08-19)


### Bug Fixes

* diagnose run_turn export marker attempts ([9a8fa5c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9a8fa5c1f0417f2ac4315423fb6ea1505bb00bc6))

## [0.58.12](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.11...v0.58.12) (2026-08-19)


### Bug Fixes

* use host-global run_turn export marker ([d4af39f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d4af39f35f044a807f937c6782de77c13482120a))

## [0.58.11](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.10...v0.58.11) (2026-08-19)


### Bug Fixes

* **audit:** track the renamed fleet factory App login ([00e864f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/00e864fae1a3732838483e4d123bd4137e52c0d1))
* bound run_turn guard to dispatch window ([95d017a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/95d017aa425e609522f4de5cbb04d9b4e4566bad))
* **effects:** move the tenant-verification cache out of the repo to XDG ([21de9c7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/21de9c7a4e465cf0285d8c151b9517a9f5471956))
* prevent stale factory retry fallthrough ([4b6e45f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4b6e45f35b2d781c2d63258ea0eb4793c347eaf6))

## [0.58.10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.9...v0.58.10) (2026-08-17)


### Bug Fixes

* **effects:** cross-process tenant-verification cache for one-shot CLI processes ([09dc590](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/09dc590aa65f80b39bf68bf0f1449a3dbbf9f991))

## [0.58.9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.8...v0.58.9) (2026-08-17)


### Bug Fixes

* recompute anchor probe query hash in rehearsal tests ([9a59859](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9a598594b1425d5ed18cc7bb15a66751a1390598))

## [0.58.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.7...v0.58.8) (2026-08-17)


### Bug Fixes

* reject pi-incompatible skill frontmatter ([fcf3e86](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fcf3e86d938ceb8655909d372bb9fe91409a1981))

## [0.58.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.6...v0.58.7) (2026-08-17)


### Bug Fixes

* preserve sandbox gh path refresh ([0eb97d3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0eb97d371e4d183fb369eb30b066c5ad7580cce8))

## [0.58.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.5...v0.58.6) (2026-08-17)


### Bug Fixes

* preserve sandbox path for gh refresh ([d70aafa](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d70aafa5860c197c359a3092c85894344a099d07))
* refresh sandbox gh tokens ([170fc70](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/170fc70c8c2b22bdc61483b3924fa419ae5acf41))
* refresh sandbox gh wrapper robustly ([6cee8fc](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6cee8fcab95362b2f96e5b2c4795a94d443c5678))

## [0.58.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.4...v0.58.5) (2026-08-17)


### Bug Fixes

* recognize plan parent-child edges ([1f62a25](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1f62a25871d1524117b8e85b4134afa30f683c73))

## [0.58.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.3...v0.58.4) (2026-08-17)


### Bug Fixes

* guard fabro run_turn telemetry absence ([edbfca6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/edbfca6f4a121074b47ae4636ad5fb3fd8b95f28))
* guard real fabro run_turn export shape ([b0c6ebb](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b0c6ebb66c02f0fe800002f1db3422f4e027419d))

## [0.58.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.2...v0.58.3) (2026-08-17)


### Bug Fixes

* correct plan archive dependency direction ([3f93312](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3f9331281ad17a5769f6b4ece63ea821ffb4eac4))

## [0.58.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.1...v0.58.2) (2026-08-17)


### Bug Fixes

* surface fabro failure cause ([e7e9c58](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e7e9c58a78603a5079bcdfe8914fdd93b35a97ce))

## [0.58.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.58.0...v0.58.1) (2026-08-17)


### Bug Fixes

* persist dispatch factory metadata ([1485021](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/148502170719ddc0278f4503ec0ab09c49c44b30))

## [0.58.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.57.7...v0.58.0) (2026-08-17)


### Features

* **ci:** batch the cheap checks — ~90 matrix jobs become ~11 gating jobs ([55a16c5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/55a16c5b071e71f9c8f4dd321305d8608a1669c2))


### Bug Fixes

* catch raw plan child records ([232392e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/232392ed21a2b27a1f7c3139aa413dfa5b041458))
* memoize bd tenant validation per invoke key ([4238d55](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4238d553fc0de062ec48117f29e8a25376f96973))
* skip closed dispatch factory lookups ([a01bdd8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a01bdd8a3e564fdcaefba6526853238c2cc97911))

## [0.57.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.57.6...v0.57.7) (2026-08-17)


### Bug Fixes

* **pre-commit:** wire repo-state checks into the doc-only subset ([93d5f5a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/93d5f5af7999673d1626647efe621a188e593751))

## [0.57.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.57.5...v0.57.6) (2026-08-17)


### Bug Fixes

* **check:** harden the coverage dedup — clean-env producer + consume-once consumer ([23aaf21](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/23aaf21b3347e80ba547c9d00e8151019518322c))
* correct rehearsal fixture label identity ([c426a43](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c426a432b75db86dd8369983dadca5627cc921d2))
* **dispatcher:** widen review-gate verdicts to not-reached and blocked ([88f2276](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/88f2276eb99d1231fa224f330d38dad65cf1c5eb))
* **effects:** memoize repo tenant verification between bd invocations ([80bf7d6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/80bf7d68ce55e44d4a4526819489f42b72d5dd3f))

## [0.57.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.57.4...v0.57.5) (2026-08-16)


### Bug Fixes

* surface dispatcher capacity deferrals ([c0985a1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c0985a1fb32fb43166fff9fa28b96bb1be1b6f18))

## [0.57.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.57.3...v0.57.4) (2026-08-16)


### Bug Fixes

* surface stranded pre-branch dispatches ([0f7945a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0f7945aded14c0e403ae8ee18e87afc5b60e4f3c))

## [0.57.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.57.2...v0.57.3) (2026-08-16)


### Bug Fixes

* reap orphaned stale fabro runs ([b13f8c0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b13f8c0ec96346e801a408efb46a1220deeeb048))

## [0.57.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.57.1...v0.57.2) (2026-08-16)


### Bug Fixes

* keep queued fabro runs out of stall watchdog ([721524a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/721524a7196924acffd7f795f2e6ddb673cfd13f))
* reap stale fabro queued runs ([64e38e5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/64e38e5bd1d961c8027f15fe39e1581da1778ec3))
* tolerate item status lookup failures ([e654b1a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e654b1a2fef63c09dd188991e0f02d9994519d4f))

## [0.57.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.57.0...v0.57.1) (2026-08-16)


### Bug Fixes

* distinguish blocked dispatch exits ([0b235c3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0b235c3c93d6a97748e78cf877ec04450197502b))

## [0.57.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.56.5...v0.57.0) (2026-08-16)


### Features

* orchestrate plan archive review evidence ([2a7e910](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2a7e91076ffb4209c3b5fb2791f6dd6c89a19f71))

## [0.56.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.56.4...v0.56.5) (2026-08-16)


### Bug Fixes

* persist review findings context ([1fc97b4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1fc97b462c3c43bf506894a34e6edf37bd2c515b))

## [0.56.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.56.3...v0.56.4) (2026-08-16)


### Bug Fixes

* reject unbalanced-brace sibling-clone dispatcher setup scripts ([94956aa](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/94956aa7ba09ed50999c43a40880c0f29d7c3631))

## [0.56.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.56.2...v0.56.3) (2026-08-16)


### Bug Fixes

* **dispatcher:** place fabro --server flag after the subcommand, not before ([6de3a8a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6de3a8a191ad457bfc5841a4d553142ee36fab6c))

## [0.56.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.56.1...v0.56.2) (2026-08-16)


### Bug Fixes

* commit shared vps fabro default ([61eb1bc](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/61eb1bc7b93291c5e5f36a75367f892355ecdada))
* **dispatcher:** tolerate per-member sibling-clone failures in sandbox prepare ([89fe7ed](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/89fe7edb77375c00b0bd9833b2d01f871a4cc933))

## [0.56.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.56.0...v0.56.1) (2026-08-15)


### Bug Fixes

* login to dev-token fabro factory ([ccc30b5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ccc30b5587ae129aebacb982c01c4bf2ba8332e3))

## [0.56.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.55.2...v0.56.0) (2026-08-15)


### Features

* gate the pi package surface with check-pi-plugin-structure ([300fb6b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/300fb6b0cc6a2ae62f136773b5a1b8969526810b))

## [0.55.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.55.1...v0.55.2) (2026-08-15)


### Bug Fixes

* gate plan archive on parent children ([eab456b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/eab456b0c2c45c458f42c00b6629890b63a0aa54))

## [0.55.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.55.0...v0.55.1) (2026-08-15)


### Bug Fixes

* record dispatch factory on ledger ([b7e9de8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b7e9de84233e317dc350530dc5daba4307f1c0d1))

## [0.55.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.54.0...v0.55.0) (2026-08-15)


### Features

* thread factory selection into fabro dispatch ([ebfc523](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ebfc523c9a563fbd46af9cf6d1a033687d8ce3b7))

## [0.54.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.53.0...v0.54.0) (2026-08-15)


### Features

* resolve fabro factory target ([a0107ef](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a0107ef9bf5348f3bb9e7d93064d39518b2c41cb))

## [0.53.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.52.4...v0.53.0) (2026-08-15)


### Features

* add append_supervisor_handoff computing the reserved author literal ([ccf217f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ccf217f38098a486819d28b57b43c84911ba505c))

## [0.52.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.52.3...v0.52.4) (2026-08-14)


### Bug Fixes

* resolve configured sibling terminal states ([3e4928e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3e4928e795cec6b40361896bbde99051a358d189))

## [0.52.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.52.2...v0.52.3) (2026-08-13)


### Bug Fixes

* **ci:** add MISE_HTTP_RETRIES alongside UV_HTTP_RETRIES ([403f878](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/403f878fa25f9e3094535ad1f627d2028f261f77))

## [0.52.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.52.1...v0.52.2) (2026-08-13)


### Bug Fixes

* rename the residual plan-thread prose in shipped Python ([6e37f95](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6e37f95f83485a0a32d1084647c57763cb976ac0))

## [0.52.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.52.0...v0.52.1) (2026-08-12)


### Bug Fixes

* gather needs-attention plans from ledger ([7a68b4b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7a68b4b7086e6dd34bda9d23fe5e076a369d923f))

## [0.52.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.51.0...v0.52.0) (2026-08-12)


### Features

* rename list surface to list-plans ([eaeb000](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/eaeb000881f83a06f29a5ac75fddbc2d11602669))

## [0.51.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.50.2...v0.51.0) (2026-08-11)


### Features

* add plan ledger handoff behavior ([95ff4e5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/95ff4e572ce3bd0708361c6eb077e61923a1f19c))


### Bug Fixes

* gate plan archive on ledger child edges ([6b5d01f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6b5d01f96fab6019f5717023cca712d1e2f80ec6))

## [0.50.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.50.1...v0.50.2) (2026-08-04)


### Bug Fixes

* restore per-file coverage producer ([487a5b0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/487a5b0172574428be2e84a571f601664625e4c5))
* restore standalone per-file coverage recipe ([fb83c5e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fb83c5e74714ca88ed4e4d9f692f06c54223be28))

## [0.50.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.50.0...v0.50.1) (2026-08-03)


### Bug Fixes

* **dispatcher:** an unreadable policy config is not an unconfigured one ([5b4813a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5b4813a31a05a9a57a3b37ac37360bdde03181de))

## [0.50.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.11...v0.50.0) (2026-08-03)


### Features

* publish awaits scope override signal ([c3d41a5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c3d41a53e5e5458617d182d52d705b731abb4786))

## [0.49.11](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.10...v0.49.11) (2026-08-03)


### Bug Fixes

* **image:** prove guarded Beads lifecycle behavior ([e2f0a1e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e2f0a1eacb4527a4015a2280e1176314c1f3fa3b))
* **image:** prove quote-safe guarded Beads lifecycle ([976caf9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/976caf9744b8a6c1159434da8f2102081935f419))

## [0.49.10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.9...v0.49.10) (2026-08-03)


### Chores

* **release:** document and publish Codex hook guard ([0e7ff6e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0e7ff6edde996ab7510ad55b63d352a175af9ac2))

## [0.49.9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.8...v0.49.9) (2026-08-02)


### Bug Fixes

* require supervised Fabro web console ([b9d30fa](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b9d30fa267a3777e1094c4781fa63066f0b599a7))

## [0.49.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.7...v0.49.8) (2026-08-02)


### Bug Fixes

* detect release canary without env seam ([74950f2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/74950f298e6b30f703bc882a8a9380ad12285318))

## [0.49.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.6...v0.49.7) (2026-08-02)


### Bug Fixes

* rewire dispatcher self update to releases ([747f641](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/747f641142fb4f63439078da2493b44982683329))

## [0.49.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.5...v0.49.6) (2026-08-02)


### Bug Fixes

* **mint-app-token:** make it safe to ask the command what it does ([b087d54](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b087d54a8ca677c8d82f16ba6819aac8b5bff1c1))

## [0.49.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.4...v0.49.5) (2026-08-01)


### Bug Fixes

* **hooks:** wire codex_yolo_gate for BOTH resolve_owner shapes ([12830ee](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/12830ee59918e1dbd59c4c2c3f8f1245429ab2e5))

## [0.49.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.3...v0.49.4) (2026-07-30)


### Reverts

* remove unqualified v1.1.2 guard harness ([67ce30c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/67ce30c9f4b2bb18a045e8cb03dd7be45f1861c2))

## [0.49.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.2...v0.49.3) (2026-07-30)


### Bug Fixes

* retire host dispatch cap ([0eeca13](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0eeca13123282ea360fa4ef21c31edcee0d399d4))

## [0.49.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.1...v0.49.2) (2026-07-30)


### Bug Fixes

* make Codex ACP full access explicit ([d53080b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d53080b2128668947c18cb506df4e1acb8f9435d))

## [0.49.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.49.0...v0.49.1) (2026-07-30)


### Bug Fixes

* **factory:** raise Fabro checkpoint commit timeout ([be5f7ae](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/be5f7ae60cfbd4f87f3cd79877b8f8ba6116cde6))

## [0.49.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.48.2...v0.49.0) (2026-07-30)


### Features

* gate Claude credential usability before dispatch ([37f028c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/37f028c7c50aa1a0a9d1b141d61807a15a4c8306))

## [0.48.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.48.1...v0.48.2) (2026-07-29)


### Bug Fixes

* **hooks:** wire codex_yolo_gate for BOTH parse_manifest shapes before the pin re-lands ([8af024c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8af024cff8ba4e94aad5796884f798f5a3295050))

## [0.48.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.48.0...v0.48.1) (2026-07-29)


### Reverts

* pin livespec-dev-tooling back to v1.0.3 to restore green master ([cf1b7a8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cf1b7a8efc3f308b96158d7ba5af96d0cf3dd405))

## [0.48.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.47.1...v0.48.0) (2026-07-28)


### Features

* add sandbox image override coverage ([168d449](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/168d449317bd2ef6f4c46ac1aa680bab493713ed))

## [0.47.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.47.0...v0.47.1) (2026-07-28)


### Bug Fixes

* honor workflow scope override ([26f2b1b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/26f2b1bd51134b22b2e4c30d718b6de649c8d424))

## [0.47.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.25...v0.47.0) (2026-07-28)


### Features

* add master ci dispatch preflight ([2ae4b2b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2ae4b2be85293bfdc76a390304363bc7cd795b7f))


### Bug Fixes

* journal reject rework valve ([521d7f7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/521d7f71bb50ae5be08eedc627911c6021e3f209))

## [0.46.25](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.24...v0.46.25) (2026-07-27)


### Bug Fixes

* **bd-guard:** allow help on direct mutation commands ([9e652a3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9e652a3476f7446ec6543e4a0f2bae22bb315457))

## [0.46.24](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.23...v0.46.24) (2026-07-27)


### Bug Fixes

* clear assignee on operator moves ([a219f88](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a219f88fa78453ca23c7cf6b5ae59f299c29d72f))

## [0.46.23](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.22...v0.46.23) (2026-07-26)


### Bug Fixes

* provision the worktree pack in the post-merge janitor checkout ([14c3cae](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/14c3cae32c28bc1e7b2cab4d85dde1dfc497e308))

## [0.46.22](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.21...v0.46.22) (2026-07-26)


### Bug Fixes

* reject dead groom priority input ([d3d7cfd](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d3d7cfd76d70095585e044c21b50bdc558cb3ab0))

## [0.46.21](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.20...v0.46.21) (2026-07-26)


### Bug Fixes

* reclaim dead claims for uncapped admission ([5b32017](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5b32017b9d2d3bbc12b12ceb97374136879c3b0e))
* reclaim dead dispatch claims ([e156b36](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e156b369e59bcdcea6e8ffa322aa7d5a90e8de4c))

## [0.46.20](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.19...v0.46.20) (2026-07-26)


### Bug Fixes

* align needs-attention approve advertisement ([8e46eea](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8e46eeaa02115ca3f4bf75a12f437f716f07b168))

## [0.46.19](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.18...v0.46.19) (2026-07-26)


### Bug Fixes

* surface stranded dispatch attention lane ([ebe7419](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ebe7419ee6334fdc7a8a5011512503852ef2cefb))

## [0.46.18](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.17...v0.46.18) (2026-07-26)


### Bug Fixes

* refuse bare active moves ([817aeb1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/817aeb1e1c8dc61526c3f5742c822df2ed32fafa))

## [0.46.17](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.16...v0.46.17) (2026-07-26)


### Bug Fixes

* resolve reconcile fabro binary ([47c75ac](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/47c75ac53e1751afba496f7c16e657a019a067d0))

## [0.46.16](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.15...v0.46.16) (2026-07-26)


### Bug Fixes

* accept zero wip cap in drive config ([3262f60](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3262f60ac589d1a3ddeeefb34cb85c1fc50e0a48))

## [0.46.15](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.14...v0.46.15) (2026-07-26)


### Bug Fixes

* honor zero wip cap ([a60986e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a60986e2fefcedfb027bef73b250306f25e2348d))

## [0.46.14](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.13...v0.46.14) (2026-07-26)


### Bug Fixes

* reclaim stale dispatch locks ([acf061c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/acf061cf669c56e5588c3465fc34dae6adc471ef))

## [0.46.13](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.12...v0.46.13) (2026-07-26)


### Bug Fixes

* harden dispatch lock claims ([a869253](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a869253e79679fb099c5402731b2788bd08c3c80))

## [0.46.12](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.11...v0.46.12) (2026-07-26)


### Bug Fixes

* **config:** describe the current role-key regime, not the retired fallback ([aab10e3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/aab10e37c5cac777094b85778f844f5109f16dff))

## [0.46.11](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.10...v0.46.11) (2026-07-24)


### Bug Fixes

* count disposition review rounds ([995b9a3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/995b9a362cda5c802b87e0e993e840806ca05028))

## [0.46.10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.9...v0.46.10) (2026-07-24)


### Bug Fixes

* allow unreleased dispatcher plugin builds ([ad715ea](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ad715ea343704132fb85c3ba615b11e4efc221c3))
* gate stale dispatcher plugin builds ([33bf8d5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/33bf8d5dd64986f6429a654614c2b522cdaee9ba))
* staleness gate warns and proceeds when release context is unobservable (bd-ib-n7ce4n deadlock case) ([96ce547](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/96ce547e03c2efe6c9f58d08fdd561731a7e4728))

## [0.46.9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.8...v0.46.9) (2026-07-24)


### Bug Fixes

* harden admission mutex pid reuse tests ([3d6a9a8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3d6a9a8300781d3852ea090870a36e90d4754894))

## [0.46.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.7...v0.46.8) (2026-07-24)


### Bug Fixes

* classify fabro human input required as blocked ([a8c16fb](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a8c16fbd504968bdf76b55e36744e79b8f5d0d85))

## [0.46.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.6...v0.46.7) (2026-07-24)


### Bug Fixes

* thread resolved fabro_bin into the admission cap gauge and count all non-terminal non-parked runs (bd-ib-3zek, bd-ib-4cw9) ([edbff85](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/edbff85d571054070ffef5edccfae6d69e2a6238))

## [0.46.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.5...v0.46.6) (2026-07-24)


### Bug Fixes

* refuse origin-unreachable dispatch source ([03c8bf3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/03c8bf35a5e0813ace218c4a16afab85c6acefed))

## [0.46.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.4...v0.46.5) (2026-07-24)


### Bug Fixes

* demote dispatch admission mutex to the host_dispatch_cap counting cap (bd-ib-sd8o deliverable b) ([a84182e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a84182e19f60e8e36b19dd215b229bcb02d690a9))

## [0.46.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.3...v0.46.4) (2026-07-24)


### Bug Fixes

* refresh PR publish base before push ([231e9a4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/231e9a48ecec36096f1312668382d70db00b529a))

## [0.46.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.2...v0.46.3) (2026-07-24)


### Bug Fixes

* add dispatch admission mutex coverage ([f29c968](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f29c9682e936784c69e5628121ae068ad4e03638))

## [0.46.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.1...v0.46.2) (2026-07-24)


### Bug Fixes

* guard factory workflow edits ([3fe97cc](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3fe97cc8d02902b15ba489b57c846d15ec96ca69))

## [0.46.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.46.0...v0.46.1) (2026-07-23)


### Bug Fixes

* refuse workflow edits before dispatch ([8eb81fa](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8eb81fae38a1dc7a4836314b809b1c821ec25312))

## [0.46.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.20...v0.46.0) (2026-07-23)


### Features

* **readiness:** resolve CLOSED cross-repo siblings via sibling_status_lookup (qiqz6b Part B) ([b4e926d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b4e926d30bd019ec7390e1ae0e08be83701e656c))

## [0.45.20](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.19...v0.45.20) (2026-07-21)


### Bug Fixes

* **needs-attention:** surface un-triaged backlog work-items ([5804141](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5804141ee00b010ca53aae5c36da6ee99162282d))

## [0.45.19](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.18...v0.45.19) (2026-07-21)


### Bug Fixes

* drop set -euo pipefail from the non-root prepare step (dash, not bash) ([fd98be2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fd98be21cbdc423c9e3a26b19a28c0d7bdd50d89))

## [0.45.18](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.17...v0.45.18) (2026-07-20)


### Bug Fixes

* preserve jsonc comments on config writes ([108d390](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/108d3902252643ad84f501cce889adcec71b7a40))

## [0.45.17](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.16...v0.45.17) (2026-07-20)


### Bug Fixes

* route the janitor reclaim mutex's own I/O onto the Result track ([0cf21c5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0cf21c536108886e66436edb9dcbadd7fca30c88))

## [0.45.16](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.15...v0.45.16) (2026-07-20)


### Bug Fixes

* restore the janitor gate for non-root runners and cover the reclaim mutex ([ff97ad8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ff97ad8990758058816757a97f16c747a5b7705a))

## [0.45.15](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.14...v0.45.15) (2026-07-20)


### Bug Fixes

* derive review cap telemetry from plan ([349fe79](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/349fe79f6bd3b87a8a72cc903c144c3429d4229d))

## [0.45.14](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.13...v0.45.14) (2026-07-20)


### Bug Fixes

* honor global auto approval in valves ([952d874](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/952d874c5c3c7fe5206efb7aa3925c71f47fc567))

## [0.45.13](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.12...v0.45.13) (2026-07-20)


### Bug Fixes

* protect janitor stale reclaim race ([ba9fdaf](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ba9fdafef8952ed964ce8236b17a0c84b33f8023))

## [0.45.12](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.11...v0.45.12) (2026-07-20)


### Bug Fixes

* **fabro:** point review_adapter at the renamed package it already bakes ([a3137d4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a3137d46d677ed985aaabd6d0127db74ee8868cd))

## [0.45.11](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.10...v0.45.11) (2026-07-20)


### Bug Fixes

* discover the dispatch target's own committed Fabro workflow ([c8bde4a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c8bde4a512c1b6e92f257b08ab25109693af8592))

## [0.45.10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.9...v0.45.10) (2026-07-20)


### Bug Fixes

* harden janitor checkout lock ([70cd9df](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/70cd9df8046be09b35392e0a66cd539d3dfea080))

## [0.45.9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.8...v0.45.9) (2026-07-19)


### Bug Fixes

* preserve reconcile journal on ambiguous PR ([8e812ba](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8e812ba2f50c491586994f5542a4e0685cd960c9))

## [0.45.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.7...v0.45.8) (2026-07-19)


### Bug Fixes

* load codex yolo gate from plugin hook ([8055848](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8055848d2a7f1047f2392cdf1d3e18f71bc451a2))
* load codex yolo gate from plugin root ([73f5a52](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/73f5a521315bb4d6cc5457dda6c3b90f4023cc2d))

## [0.45.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.6...v0.45.7) (2026-07-19)


### Bug Fixes

* close reconcile merged race ([e957b35](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e957b35c8b002c6c36950bc36542eee519ed8069))

## [0.45.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.5...v0.45.6) (2026-07-19)


### Bug Fixes

* fail closed on codex yolo gate errors ([eeb80fe](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/eeb80febabde1174ff7719adaa3d9bb0d8da2a34))
* fail closed when codex gate load aborts ([8283d5e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8283d5e00abf3daa4d3f7e23df0ee2f4ba834cce))
* force codex refresh full access ([1b87d99](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1b87d99e8a403675dc3baeea4daf06ff66cf3830))
* guard reconcile merged liveness ([cff7225](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cff7225bab5a24a3d3d193baec5543dc8c257434))
* make spec codex handoff EOF-safe ([91b3117](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/91b3117f9be2e3fe509d70790434b4d3971d672f))

## [0.45.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.4...v0.45.5) (2026-07-19)


### Bug Fixes

* add reconcile merged dispatcher red ([3f60465](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3f60465919634c17009d8cb824349f4ef794789a))

## [0.45.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.3...v0.45.4) (2026-07-19)


### Bug Fixes

* **ci:** feed jq its large JSON payloads on stdin, not argv ([c6ae317](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c6ae317c50e7d465c380ba6985e05951495fafe2))

## [0.45.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.2...v0.45.3) (2026-07-19)


### Bug Fixes

* **dispatcher:** degrade a missing executable to exit 127, not a crash ([74fe125](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/74fe125085aa1e435c29d8462549a7cc872dfca5))

## [0.45.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.1...v0.45.2) (2026-07-19)


### Bug Fixes

* isolate dispatched tmux sockets ([861e40c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/861e40c3505b7ccf66d89b1a394eb1691749a70f))

## [0.45.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.45.0...v0.45.1) (2026-07-19)


### Bug Fixes

* **otel:** allowlist the O4 run_turn span attributes ([4614493](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/461449337b3337d24fa12e71f89b7bbed55ce1d7))

## [0.45.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.44.4...v0.45.0) (2026-07-18)


### Features

* surface host-only attention items ([e1536b4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e1536b46d148d4705446544cee00138cb7e8b605))

## [0.44.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.44.3...v0.44.4) (2026-07-18)


### Bug Fixes

* retire factory safety prose fallback ([285321e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/285321e264aa9a304cb50f949e40ef7f922564dc))

## [0.44.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.44.2...v0.44.3) (2026-07-18)


### Bug Fixes

* encode factory safety in beads store ([591fe0c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/591fe0c65f5060add23b81245836a3ae8dadb3f9))

## [0.44.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.44.1...v0.44.2) (2026-07-18)


### Bug Fixes

* **bd-guard:** exclude POST-subcommand tenant/db selectors from create-forcing ([bf0f1b5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bf0f1b54996a41c82340a51c1421e15debb5f003))

## [0.44.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.44.0...v0.44.1) (2026-07-18)


### Bug Fixes

* **bd-guard:** harden create-normalization (2 deploy-blockers + edges) ([be48d54](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/be48d548063440ae11f6526fa2a981ed832ccf0d))

## [0.44.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.43.1...v0.44.0) (2026-07-18)


### Features

* **bd-guard:** normalize bd create to lifecycle backlog (close create drift) ([07bc66f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/07bc66f04109c4e52afa288675a41d70442af43a))

## [0.43.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.43.0...v0.43.1) (2026-07-17)


### Bug Fixes

* route expected failures through effects ([8858c90](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8858c904206cdac400e2556417d2d5dece3686b3))

## [0.43.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.42.0...v0.43.0) (2026-07-17)


### Features

* **drive:** clear-to-inherit for the per-item cap-override verbs ([7b94230](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7b942305e9c575e6558e55bbea07173df8a5b416))

## [0.42.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.41.3...v0.42.0) (2026-07-17)


### Features

* **drive:** per-item cap-override actions and guarded operator move ([b620304](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b620304e3f0b55e26e6e879552367bf80e910824))

## [0.41.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.41.2...v0.41.3) (2026-07-16)


### Bug Fixes

* journal dispatcher auto dispositions ([e579911](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e5799117b6c1b5c99ea0b7545ac58fb659a8017f))

## [0.41.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.41.1...v0.41.2) (2026-07-16)


### Bug Fixes

* preserve dispositions before review telemetry ([3d2ff13](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3d2ff13189aed9748755cf4e40bba79fdc248c92))

## [0.41.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.41.0...v0.41.1) (2026-07-16)


### Bug Fixes

* add review workflow fallback edge ([3c832d6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3c832d693be74fcabd29cdef205fb9dce72f6c9d))

## [0.41.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.40.0...v0.41.0) (2026-07-16)


### Features

* auto-rework failed AI acceptance ([adfed7e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/adfed7e32a507e2aa1b14bfd4e076d5a5a2f6658))

## [0.40.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.39.0...v0.40.0) (2026-07-16)


### Features

* block review gate at cap ([bdb84d1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bdb84d159f256adbd7a31a851a1bbe9756b5d094))

## [0.39.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.38.0...v0.39.0) (2026-07-16)


### Features

* add real acceptance pass coverage ([1da5747](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1da5747af9ff6d15b1f0e7dedeb162ad0916e5ef))

## [0.38.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.37.0...v0.38.0) (2026-07-16)


### Features

* add drive config surface ([f43a80a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f43a80a2872ca0003974d2c7b873abb77ca1c986))

## [0.37.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.36.0...v0.37.0) (2026-07-16)


### Features

* replace dispatcher mode loop surface ([0cef76a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0cef76a50b43221b67f092d5c844c221e2007771))

## [0.36.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.35.0...v0.36.0) (2026-07-15)


### Features

* add dispatcher needs-human blocked path ([69c3ef6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/69c3ef6881b72b59bedead79a1f62e3ac820b58b))


### Bug Fixes

* surface blocked needs-human resolver ([3ebc82a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3ebc82adb43c7603548e97f6d4905138bfe6e464))

## [0.35.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.34.2...v0.35.0) (2026-07-15)


### Features

* add guarded Codex credential refresh ([2206248](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/22062480dc7dd3597be225642d7bac5981cded97))


### Bug Fixes

* fail stale Codex credential refresh ([0a7202d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0a7202d76f2ed77568c1b8c86b590d001b94b464))
* report codex refresh dry-run decision ([069d85c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/069d85c4d6a5efe4ceaef951ed4c3d997de061d9))

## [0.34.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.34.1...v0.34.2) (2026-07-15)


### Bug Fixes

* retire needs-human resolver ([5e8c2d9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5e8c2d9ab5cb0c651c3cc1ff9354cbd4ea4d15c3))

## [0.34.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.34.0...v0.34.1) (2026-07-15)


### Bug Fixes

* cover review gate telemetry failure modes ([fda7106](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fda7106894fd264e8abe38fe834247454d748eb0))

## [0.34.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.33.0...v0.34.0) (2026-07-15)


### Features

* emit review gate telemetry ([29a253b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/29a253bb8329527c000d4822e2e7df4d894579db))

## [0.33.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.32.0...v0.33.0) (2026-07-15)


### Features

* add codex credential status alarm ([cd29e9a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cd29e9affe064ebbe3b23b1ef6e122905cc9fb92))

## [0.32.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.31.0...v0.32.0) (2026-07-15)


### Features

* add dispatcher policy setting coverage ([43b399c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/43b399c7ecb56d7bca1c314a9dfd3917acf35778))

## [0.31.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.30.6...v0.31.0) (2026-07-15)


### Features

* factory-bypass audit — surface merged product-code PRs not authored by the factory GitHub App (work-item bd-ib-c4a2bi) ([68e7ce0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/68e7ce02ffc0b1c0a7085bd52161e3e2e41d929c))

## [0.30.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.30.5...v0.30.6) (2026-07-15)


### Bug Fixes

* **bd-guard:** guard bd ready --claim + bd defer, harden mode-file read ([6df358f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6df358f1c700cfb8431943a9cb654bed02373492))

## [0.30.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.30.4...v0.30.5) (2026-07-14)


### Bug Fixes

* **bd-guard:** close --format bypass, add host-wide mode file, emit span on fail-mode block ([0831120](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0831120bb0b4eb0111a2ecacf9324ed43917e4d3))

## [0.30.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.30.3...v0.30.4) (2026-07-14)


### Bug Fixes

* **dispatcher:** contain the Codex refresh sentinel inside the sandbox ([2e98870](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2e9887050e976294d32407418127878d3a8d520e))

## [0.30.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.30.2...v0.30.3) (2026-07-14)


### Bug Fixes

* **ci:** restore mise trust scope inside the wrapper for the greeting assertion ([4ffad84](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4ffad842510afc5e520443a97698deb99f274e51))

## [0.30.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.30.1...v0.30.2) (2026-07-14)


### Bug Fixes

* **ci:** resolve just inside the 1Password wrapper in the golden-master gate ([4876dea](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4876dea1f1fa77652deb690efffc5c88db9dc3ef))

## [0.30.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.30.0...v0.30.1) (2026-07-13)


### Bug Fixes

* keep janitor worktrees out of repo root ([103f7c8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/103f7c8a70dc27304bbf94bb3562ce62039e7e12))

## [0.30.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.29.1...v0.30.0) (2026-07-13)


### Features

* **bd-guard:** emit bd.invoke OTLP span per call (default-on, fail-open) ([e30ada0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e30ada0f635e3495344947abf3652d245c4af2a0))

## [0.29.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.29.0...v0.29.1) (2026-07-13)


### Bug Fixes

* consume baked codex-acp global fetch-free (drop [@0](https://github.com/0).16.0 pin) ([9158752](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/915875223999a7a867be7d7f81d21c17b4c033c1))

## [0.29.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.28.1...v0.29.0) (2026-07-13)


### Features

* codex-acp golden-master gate (repository_dispatch + status callback) ([0d0b0c2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0d0b0c234b505880d4ca5907564604f02f7ad9d0))

## [0.28.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.28.0...v0.28.1) (2026-07-13)


### Bug Fixes

* **ledger-gate:** print each written remap on partial heal; project not reload ([4328aa9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4328aa95889762294a70bfb05c207fe3c011fc86))

## [0.28.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.27.0...v0.28.0) (2026-07-13)


### Features

* **ledger-gate:** auto-heal-loud pre-push conformance gate ([86632ad](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/86632adc731e60c094119bae79d664bb98d0de2e))

## [0.27.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.26.0...v0.27.0) (2026-07-13)


### Features

* **bd-guard:** guard bd reopen + harden install.sh fresh-provision relocate ([6635f22](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6635f22e341e77fd91fa5dc5f1af5fe6996e02c9))

## [0.26.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.25.0...v0.26.0) (2026-07-13)


### Features

* bd guard wrapper (warn-first) — reject non-lifecycle status/claim ops ([65b2d68](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/65b2d68cff57d1680156ee71d13a61b5d892c0d3))


### Bug Fixes

* **bd-guard:** repair install/rollback self-recognition; close claim/-- holes ([299dc5e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/299dc5e323536423a5b2cb97371e3ef8af62a532))

## [0.25.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.24.0...v0.25.0) (2026-07-12)


### Features

* pre-push ledger-conformance gate (fail-soft, case-aware heal guidance) ([0fb66ed](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0fb66ed204a125b62a6a475a9f285503751630c1))

## [0.24.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.23.0...v0.24.0) (2026-07-12)


### Features

* drive the file-tail OTel egress driver (P-factory, livespec-3lev.2) ([5e683e4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5e683e4ec7163ddc8e65b2fefd062e9b1d22919f))


### Bug Fixes

* bind OTLP receiver to the docker bridge gateway (P-factory, livespec-3lev.2) ([fc17518](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fc17518e24ff680fdd60bf152798bb0fe84dfd9c))

## [0.23.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.22.3...v0.23.0) (2026-07-12)


### Features

* standalone ledger-normalize + generalize status normalizer (in_progress→active) ([9ea4f1a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9ea4f1ac97db5b6b2acd1e4658dc29e6f5e8bbc2))

## [0.22.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.22.2...v0.22.3) (2026-07-12)


### Bug Fixes

* reflector file_new sets lifecycle status (backlog) after create ([ea1e441](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ea1e441759365fc817fddf2453609f2314cecd4d))

## [0.22.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.22.1...v0.22.2) (2026-07-12)


### Bug Fixes

* **golden-master:** register custom statuses + seed a ready item ([b13afd1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b13afd1da938e54ad2188f927ad96bb0cf099d9a))

## [0.22.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.22.0...v0.22.1) (2026-07-12)


### Bug Fixes

* split dispatcher run commands ([fb3f078](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fb3f07833fe0b98fdd0e625251c4a47cffd9bf58))

## [0.22.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.21.0...v0.22.0) (2026-07-12)


### Features

* extract dispatcher run commands ([456e40e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/456e40e49bafbe86060871d3d0c787c92790dc82))


### Bug Fixes

* preserve dispatcher mini-hub imports ([9b6c094](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9b6c0946f174ccc6dec1b02b171ba7197190374a))

## [0.21.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.20.1...v0.21.0) (2026-07-12)


### Features

* extract dispatcher run checks ([9344760](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9344760e7f1c3ac180a614b57191005edce88f05))

## [0.20.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.20.0...v0.20.1) (2026-07-12)


### Bug Fixes

* remove dispatcher loop facade ([d78ef03](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d78ef034d303e0ff1a9c55927765f39eb2ffb88f))

## [0.20.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.19.0...v0.20.0) (2026-07-12)


### Features

* extract dispatcher loop primitives ([d161818](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d161818c35abfcb39bbbb34ab2dadc99259703f8))

## [0.19.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.18.0...v0.19.0) (2026-07-12)


### Features

* extract dispatcher otel wiring ([f3ac8b3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f3ac8b38604272ec55a3b168d9a70cd836de8a69))

## [0.18.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.24...v0.18.0) (2026-07-11)


### Features

* extract dispatcher post-verdict reflector ([f2005e1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f2005e158efcd7127b05f131319cc67ea59b9bff))

## [0.17.24](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.23...v0.17.24) (2026-07-11)


### Bug Fixes

* extract dispatcher calibration emit cluster ([8f77084](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8f7708458364c11eec9cb8ea62563bd12072f0ca))
* preserve calibration emit token supplier ([09246fd](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/09246fd1d7ee3fa6bd9b6a434372faf467bea827))

## [0.17.23](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.22...v0.17.23) (2026-07-11)


### Bug Fixes

* make beads invoke embedded-ledger-aware (skip family-secret + tenant-match guards) ([b65a6b2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b65a6b2a3d921eb8e7be28a8b5aeb57139fc6bbf))

## [0.17.22](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.21...v0.17.22) (2026-07-11)


### Bug Fixes

* extract dispatcher ledger close cluster ([72d8ca8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/72d8ca833b74631bb525e448739d7278c68934d3))

## [0.17.21](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.20...v0.17.21) (2026-07-11)


### Bug Fixes

* decompose dispatcher credentials cluster ([9071b6b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9071b6ba0cb5079ba1f4119c8a9fa99119218498))
* split dispatcher codex auth cluster ([bdf4e59](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bdf4e5907e61a13f5cd56036ce00026109dcb266))

## [0.17.20](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.19...v0.17.20) (2026-07-11)


### Bug Fixes

* extract needs-human dispatcher routing ([00a44af](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/00a44affbf2743a1f30a0eb69dabf4635c79e12f))

## [0.17.19](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.18...v0.17.19) (2026-07-11)


### Refactoring

* extract dispatcher completion cluster ([755fbf2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/755fbf244986ba873cca6394c9a9d985b2efe45c))

## [0.17.18](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.17...v0.17.18) (2026-07-11)


### Refactoring

* extract dispatcher admission cluster ([bc2ac76](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bc2ac76d683f1977e7c0800afff63cdbee988037))

## [0.17.17](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.16...v0.17.17) (2026-07-11)


### Bug Fixes

* expose dispatcher self-update boundary ([1ad7f01](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1ad7f012ec8a970d3400d2c31500643965832304))

## [0.17.16](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.15...v0.17.16) (2026-07-11)


### Bug Fixes

* decompose dispatcher planning layer for honest per-file LLOC (bd-ib-9t1) ([61112ef](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/61112ef48f37090de9478a47e39efa38a36c278b))

## [0.17.15](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.14...v0.17.15) (2026-07-11)


### Bug Fixes

* derive dispatch tenant-secret requirement from beads ledger mode ([cca9372](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cca93727ff16a4a866f065e8a3af192f32f85bc1))

## [0.17.14](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.13...v0.17.14) (2026-07-11)


### Bug Fixes

* address dispatcher merge review findings ([1b0efc2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1b0efc2521c59b9add5910bf64592b407ba3d2f1))
* decompose dispatcher merge engine ([ba5fa8b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ba5fa8b23cfc7aa7b7d23ad5dc7ac3bfd3480dc5))
* decompose otel receiver parsing ([75a5e82](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/75a5e82e4556d6b7fc41fe4dd2b01249a1186fad))

## [0.17.13](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.12...v0.17.13) (2026-07-11)


### Bug Fixes

* decompose beads client argv helpers ([471ae04](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/471ae0450d71e12997505939a63af272034b58a2))

## [0.17.12](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.11...v0.17.12) (2026-07-11)


### Bug Fixes

* extract drive human valve actions ([b06dbc6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b06dbc6097559aed3848b7a71cc4c1e036dc95c0))

## [0.17.11](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.10...v0.17.11) (2026-07-11)


### Bug Fixes

* extract dispatcher reflection spans ([8be2f30](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/8be2f30e0e9bb0e4608f49c37daf9287e1ed3a32))

## [0.17.10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.9...v0.17.10) (2026-07-11)


### Bug Fixes

* extract store mutations ([21c836e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/21c836e59bf342087e6d78b0fbc68275877aa7b5))

## [0.17.9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.8...v0.17.9) (2026-07-11)


### Bug Fixes

* extract needs-attention core roots ([3ba8a83](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3ba8a83ba740cc305dca1f4b213e415040540099))
* extract otel enrich tail ingest ([f69a22a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/f69a22a448d8af9bfadb2246e043c44c1fc9ed7e))

## [0.17.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.7...v0.17.8) (2026-07-11)


### Bug Fixes

* extract dispatcher cost gate cluster ([abb5d71](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/abb5d715778f024cb12d9c0b3ac53387c6aafee7))

## [0.17.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.6...v0.17.7) (2026-07-11)


### Bug Fixes

* decompose dispatcher cost sink span pricing ([46e8ea0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/46e8ea09077d22a23ad07a660efc75926b83d946))

## [0.17.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.5...v0.17.6) (2026-07-11)


### Bug Fixes

* extract dispatcher fabro launcher io ([ae4120b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ae4120b06cf32d2a8822992efaccfedddbdea96e))

## [0.17.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.4...v0.17.5) (2026-07-11)


### Bug Fixes

* decompose reflector oob helpers ([720be73](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/720be73c8998c98e5f118266fb1ce2092eca5d7c))
* remove reflector private helper facade ([af4a5c2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/af4a5c29af669f0100bbd5c22c6016aa1f68b913))

## [0.17.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.3...v0.17.4) (2026-07-11)


### Refactoring

* decompose dispatcher plan ([16ad6cb](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/16ad6cb4272b6d77be642df099c9349328769d87))

## [0.17.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.2...v0.17.3) (2026-07-11)


### Bug Fixes

* extract dispatcher path helpers ([a3a9190](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a3a91906678b5aa502a460f047ae9580bd305862))

## [0.17.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.1...v0.17.2) (2026-07-11)


### Bug Fixes

* deliver the oversized-body 400 cleanly (drain before close) to end the OTEL receiver RST flake ([530776c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/530776c945bdbb87d6007ded830049897a44e3b3))

## [0.17.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.17.0...v0.17.1) (2026-07-11)


### Bug Fixes

* fail open when the autonomous audit journal is unreadable ([98be824](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/98be824817ac7e57ff31346063dbc5956154f305))

## [0.17.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.16.0...v0.17.0) (2026-07-11)


### Features

* add the in-band needs-human resolve-or-escalate stage (bd-ib-82a.4) ([3f5f795](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3f5f79578f1154f7c81569656712112ecbb26614))

## [0.16.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.15.0...v0.16.0) (2026-07-11)


### Features

* collapse the two human-delegable valves under armed autonomous mode (bd-ib-82a.3) ([9a1c8ec](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9a1c8ec926e7b87c87dbb5c5822264a5d4d29435))

## [0.15.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.14.1...v0.15.0) (2026-07-11)


### Features

* publish the per-decision autonomous audit record + read surface (bd-ib-82a.2) ([ca28c00](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ca28c001d84e32a0ed8cc10a36d6123f738117f3))

## [0.14.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.14.0...v0.14.1) (2026-07-10)


### Bug Fixes

* avoid duplicate otel error replies ([50fa105](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/50fa10540649a89969570a98ab2fd4c79fe946ea))
* clear phase-1 structural warnings ([3d395fa](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3d395fa18a6a1feec2a711b77889edc36661bbdf))
* preserve verdict value contracts ([c85147c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c85147c5f92b1c76ca28695e7e7dd4b314047120))

## [0.14.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.16...v0.14.0) (2026-07-10)


### Features

* arm full autonomous mode via two-factor loop opt-in (bd-ib-82a.1) ([580c55b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/580c55b8280494c3ce9496b36dcc9bbcd3aed75a))

## [0.13.16](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.15...v0.13.16) (2026-07-10)


### Bug Fixes

* route cli writes through io seam ([833287f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/833287f0e2226957405adaa937de7bc5ecfdcbd0))

## [0.13.15](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.14...v0.13.15) (2026-07-10)


### Bug Fixes

* bounce human-gate-blocked runs to backlog in the unattended factory ([7d822d8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7d822d84a23484282b118bf8b3d3fc6e4dcdbe22))

## [0.13.14](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.13...v0.13.14) (2026-07-10)


### Dependencies

* bump Fabro sandbox image pin v0.37.2 → v0.37.3 (restore dev-tooling lockstep) ([b6dd408](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b6dd408e77ebaba9c0512d2e81498bdf61cb7b7d))

## [0.13.13](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.12...v0.13.13) (2026-07-10)


### Dependencies

* bump Fabro sandbox image pin v0.37.1 → v0.37.2 (restore dev-tooling lockstep) ([0900e1a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/0900e1a91bf4bd728c47e4fe4839a1f0ed66d08d))

## [0.13.12](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.11...v0.13.12) (2026-07-10)


### Bug Fixes

* rename misleading image-pin-freshness gate to pin-lockstep ([d7b4120](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d7b4120be867e82ba52c051996124c2f90e6980f))


### Dependencies

* bump Fabro sandbox image to v0.37.1 to restore pin lockstep ([b2c63c2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b2c63c2985bec2fa0ad6ef0cca1dc5cd8156986f))

## [0.13.11](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.10...v0.13.11) (2026-07-10)


### Bug Fixes

* restore strict shared wrapper_shape gate; revert B1 fork ([a8a69f0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a8a69f0a14b763796e72064de8f5bf938f57b155))

## [0.13.10](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.9...v0.13.10) (2026-07-10)


### Bug Fixes

* burn down phase1 mechanical warnings ([6ee0118](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/6ee011860a01c5d7e58ec32306152d806411cecb))

## [0.13.9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.8...v0.13.9) (2026-07-08)


### Bug Fixes

* repair codex plugin root resolver ([e17495a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e17495a12425f3ddb758bea2acc505d1a68c7867))

## [0.13.8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.7...v0.13.8) (2026-07-08)


### Bug Fixes

* unshadow Fabro's fresh sandbox token by projecting GITHUB_TOKEN ([06da7b8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/06da7b8114dd6d302ebaf2ffb5e97f70b17c2b07))

## [0.13.7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.6...v0.13.7) (2026-07-08)


### Bug Fixes

* supervise credential wrapper reexec ([e0b8a5b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e0b8a5b4fb56f561923e9df31e388903a0cfcf51))

## [0.13.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.5...v0.13.6) (2026-07-08)


### Bug Fixes

* guard Fabro sandbox image pin freshness ([4926b65](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/4926b65dde741361a310052b72c61c3ffac4393d))

## [0.13.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.4...v0.13.5) (2026-07-08)


### Bug Fixes

* fail fast on active real-work container ([fe48615](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/fe4861576d08465df7e9d6390ac1057da028defb))

## [0.13.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.3...v0.13.4) (2026-07-08)


### Bug Fixes

* normalize beads open before ledger gate ([843b0c9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/843b0c994f28ca90639c2cf551aaa054aea3484d))

## [0.13.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.2...v0.13.3) (2026-07-08)


### Bug Fixes

* **needs-attention:** honor configured spec next argv ([506614d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/506614dab339bdf3c83e44bf8857e5f2595b0d1c))

## [0.13.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.1...v0.13.2) (2026-07-08)


### Bug Fixes

* **codex:** require binding cwd plugin identity ([bd8ca1a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bd8ca1a323a87eb53c6185edba6cbd2519449c8c))

## [0.13.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.13.0...v0.13.1) (2026-07-08)


### Bug Fixes

* **needs-attention:** invoke spec-next cross-plane instead of emitting a pointer ([c39ed04](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c39ed0411ab82eb56eaa8e546d320c4243caceb9))

## [0.13.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.12.0...v0.13.0) (2026-07-06)


### Features

* add plan thread listing primitive ([cc093ea](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cc093ea41c990f4d8da1a6ae3c974740e17655c9))

## [0.12.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.11.2...v0.12.0) (2026-07-06)


### Features

* rename orchestrate operator to drive ([e0eabb2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e0eabb22aebadd190f92399cc72840e881c2acfc))

## [0.11.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.11.1...v0.11.2) (2026-07-05)


### Bug Fixes

* resolve pull-primary default branch ([a7218b4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a7218b49443a9dd58e0ea0a55cfefc861b114055))

## [0.11.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.11.0...v0.11.1) (2026-07-05)


### Bug Fixes

* refresh post-verdict github tokens ([dea771f](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/dea771fd09c7a4ae9df98f048e10cc951e076e07))

## [0.11.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.10.0...v0.11.0) (2026-07-05)


### Features

* inject ratified lessons into the dispatch brief (S2) ([71e137c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/71e137ce649cc7da430b846e136511d4a1f184f0))

## [0.10.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.9.6...v0.10.0) (2026-07-05)


### Features

* ratified-lessons reader for dispatch-brief injection (S1) ([a8a74f7](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a8a74f7d5ea55b839d79178e3279ee1ab9107429))

## [0.9.6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.9.5...v0.9.6) (2026-07-05)


### Bug Fixes

* guard dispatch surfaces from retired fleet pat ([150349c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/150349cfc0d5960e4cb36809b19cbfa5bf8aa01b))

## [0.9.5](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.9.4...v0.9.5) (2026-07-05)


### Bug Fixes

* surface adopter wrapper credentials ([944c92a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/944c92a92bfb924462935cac3920eadaddce8e5a))

## [0.9.4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.9.3...v0.9.4) (2026-07-05)


### Bug Fixes

* make the fabro_bin default a smart resolver (home path, else PATH lookup) ([a2ac042](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a2ac0429fb0917fd5146f35467607231f279e703))

## [0.9.3](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.9.2...v0.9.3) (2026-07-05)


### Bug Fixes

* resolve fabro_bin from config/env with absolute-path default and preflight-refuse before admission ([d0b5eef](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d0b5eefa5ca2881d1c3969b87987435b425d40af))

## [0.9.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.9.1...v0.9.2) (2026-07-04)


### Bug Fixes

* route shell beads commands through target repo ([e2d86c4](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e2d86c4838d321d58b2eb5ff11098c9f4eca0e2e))
* validate beads tenant through target repo ([7ebe4e6](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/7ebe4e640b84ca89904418480ce6222b6b8318dc))

## [0.9.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.9.0...v0.9.1) (2026-07-04)


### Bug Fixes

* project currency gate into dispatch overlay ([1e3df57](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1e3df57dbfee4c3e00a6b030b7392978b59c4a43))

## [0.9.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.8.2...v0.9.0) (2026-07-04)


### Features

* align orchestrate approval policy actions ([9503866](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/950386661a994fe6ed719cfb5edd4f20c5f03513))

## [0.8.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.8.1...v0.8.2) (2026-07-04)


### Bug Fixes

* dispatcher lessons_path moves to top-level loop-reflection-gate/ (livespec-gt7crt) ([c15f973](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c15f97339f115134d7fd8249d4d2d71a76b72387))

## [0.8.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.8.0...v0.8.1) (2026-07-03)


### Bug Fixes

* detect dispatcher self-update short paths ([190c68a](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/190c68a9ec5356c02a49bd2653a3a97eef3135ce))
* preserve dispatcher self-update prefix matching ([51a46c8](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/51a46c84a60a7a5c2b61a02cb93201f22a22f5e9))

## [0.8.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.7.0...v0.8.0) (2026-07-03)


### Features

* add orchestrate human valve action coverage ([a8d4e18](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a8d4e18218c75966214f314047b10c1852216975))


### Bug Fixes

* require regroom merge evidence ([c8c4087](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c8c40877714d294ddff675f570352c2e127029b7))
* require regroom reject to revert merge ([9f7db0e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9f7db0eebe3220be840f2dabdf42612a31ed7681))

## [0.7.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.6.1...v0.7.0) (2026-07-03)


### Features

* route groom through backlog lifecycle ([bcc06f9](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/bcc06f9b1802011e8d2f81f3967b7bc108015834))

## [0.6.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.6.0...v0.6.1) (2026-07-03)


### Bug Fixes

* route intake dor into lifecycle states ([ac0b477](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ac0b477df4668701d0977b40f0e8480f95ac42bf))

## [0.6.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.5.0...v0.6.0) (2026-07-03)


### Features

* add migrate tenant command ([e3cb24e](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/e3cb24e218103720606718014854a01582e11c45))

## [0.5.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.4.0...v0.5.0) (2026-07-03)


### Features

* route factory GitHub auth through the target credential_wrapper App-token provider ([296dadd](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/296dadd5af595d8af3bf26735d9b859f646b0357))
* self-heal beads CLI credentials via credential_wrapper re-exec ([860f671](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/860f67162245e80c4a2f01d345c1b13f9a0bab5a))


### Bug Fixes

* derive + wire the status-conformance doctor gate ([cbc3399](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/cbc33991dd8e65159ded7c3e1c5f890b48fcdb06))
* enforce lifecycle status ledger invariant ([53fff0d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/53fff0da20203d452679bc6f21937077526bde1f))
* fail fast on terminal merge checks ([65b84dd](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/65b84dd1572be84cc03396097f4cf671a9c52fe1))
* map beads acceptance and notes ([1485fb1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/1485fb188bad12c65df80ece6db802f41c1f7a4d))
* parse connection shaped PR checks ([9ebb43b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/9ebb43b99b776e8783a68d57e39cb2cbc2b8ba48))
* parse context shaped PR checks ([5b1f68c](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/5b1f68c0635dac4fda57e23784b29889d9f560c3))
* per-wrapper required-credential sets so the mint CLI needs no tenant secret ([ceecd34](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/ceecd34ece9eaf2e3f1db25dcb385ec6e3011683))
* provision core for post-merge janitor ([b87201d](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/b87201d66550f164990559abc0984c1396c84d9a))
* render spec id in dispatch goal ([2fd4efd](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/2fd4efd91ce920eb610f2f175d7113406fa75825))

## [0.4.0](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.3.2...v0.4.0) (2026-06-30)


### Features

* **token:** mint a GitHub App installation token in tested Python ([c1b0877](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/c1b0877649fab1299d1b16c063f3d6cac305e6bd))
* **token:** wire the App-token CLI into the orchestrator entrypoint ([3ddde18](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/3ddde180be08059c74f71f2b34c0d08aa759cf05))

## [0.3.2](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.3.1...v0.3.2) (2026-06-30)


### Bug Fixes

* **dispatcher:** project LIVESPEC_CORE_PLUGIN_ROOT into the sandbox env so fleet janitors resolve core ([d62499b](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/d62499be673abd8939d0f0cbfd498174c3d8615f))

## [0.3.1](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/compare/v0.3.0...v0.3.1) (2026-06-30)


### Bug Fixes

* **dispatcher:** make self-update + fleet-manifest projection clean no-ops on a read-only cache ([a0e4f45](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/a0e4f45a13398afc3e8aa14b2743b7800c523d8c))
* **dispatcher:** resolve Fabro workflow + bin from the plugin root; ship workflow in payload ([be34561](https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro/commit/be34561a31548e4bd34950b79973e575b5411625))

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
