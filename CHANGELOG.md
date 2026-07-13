# Changelog

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
