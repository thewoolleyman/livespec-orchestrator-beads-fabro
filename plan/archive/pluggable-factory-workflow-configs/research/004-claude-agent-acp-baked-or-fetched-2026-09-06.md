# Research note 004: is `@agentclientprotocol/claude-agent-acp` fetched at run time, or baked into the sandbox image?

Written 2026-09-06 by the factory run implementing `bd-ib-yqpdrt.2`, from
inside the sandbox image the bundled workflow pins. This note is the decision
note that item's first acceptance criterion asks for; it records the verdict,
the command output that proves it, the mechanism behind the verdict, and the
two pin mechanisms that were evaluated and rejected.

Notation used below: an item id in backticks is a beads work-item in this
repository's tenant unless prefixed with another tenant's name. "The bundled
workflow" means
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.toml`. "The
adapter" means the npm package `@agentclientprotocol/claude-agent-acp`. "The
version-less form" means the adapter command line as the bundled workflow
writes it today, `npx -y @agentclientprotocol/claude-agent-acp`, with no
`@version` suffix.

## Verdict

**The adapter is BAKED into the sandbox image. It is NOT fetched from npm at
run time, and its version is NOT a moving comparand.**

The version-less form resolves a globally-installed copy that the image build
already pinned to an exact version. The adapter is therefore pinned exactly as
the item asked it to be — the pin simply lives in the image, one layer below
where the item expected to find it, and is consumed through the immutable
`docker` image tag the bundled workflow already commits.

This falsifies the item's stated premise. The item's PROBLEM paragraph reads
"the adapter is the one moving input left unpinned" and "two dispatches days
apart can run different adapter builds with no record of the change". Neither
holds: two dispatches on the same committed image tag run the same adapter
bytes, because the tag is immutable and the adapter is inside it.

## Evidence

Four independent measurements, each capable of returning the opposite answer.
The first three were taken inside the live sandbox of run
`01M1VY91XND0G38K16S1JYTA7S` on image tag
`ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.52.12`, the tag
committed at `workflow.toml` line 292. The fourth was taken at the image's
source of truth.

### E1 — the live process tree of the run writing this note

The strongest available evidence, because the process under inspection IS the
adapter invocation under question: this note is being written by the
`implement` node that the version-less form spawned.

```
$ ps -eo pid,ppid,user,args
752  0    root  /bin/bash -lc ... user_command='npx -y @agentclientprotocol/claude-agent-acp' ...
762  752  root  npm exec @agentclientprotocol/claude-agent-acp
791  762  root  sh -c "claude-agent-acp"
792  791  root  node /root/.local/share/mise/installs/node/26.3.0/bin/claude-agent-acp
806  792  root  /root/.local/share/mise/installs/node/26.3.0/lib/node_modules/@agentclientprotocol/claude-agent-acp/node_modules/@anthropic-ai/claude-agent-sdk-linux-x64/claude ...
```

Read the chain downward. PID 752 carries the version-less command line
verbatim from the bundled workflow. PID 762 is `npm exec` resolving it. PID 791
shows what `npm exec` decided to run: the bare bin NAME `claude-agent-acp`, not
a package tarball. PID 792 shows the path that name resolved to — the node
installation's GLOBAL bin directory. PID 806 shows the Claude binary loading
from inside that same global `node_modules` tree.

No path in this chain lies under an npx cache. The adapter executing this run
is the baked global.

### E2 — the global install, and the absence of an npx cache

```
$ npm root -g
/root/.local/share/mise/installs/node/26.3.0/lib/node_modules

$ npm ls -g --depth=0
/root/.local/share/mise/installs/node/26.3.0/lib
+-- @agentclientprotocol/claude-agent-acp@0.44.0
+-- @zed-industries/codex-acp@0.16.0
`-- npm@11.16.0

$ ls -la /root/.local/share/mise/installs/node/26.3.0/bin
claude-agent-acp -> ../lib/node_modules/@agentclientprotocol/claude-agent-acp/dist/index.js
codex-acp -> ../lib/node_modules/@zed-industries/codex-acp/bin/codex-acp.js

$ ls -d ~/.npm/_npx
ls: cannot access '/root/.npm/_npx': No such file or directory
```

The adapter is present as a global at exact version `0.44.0`, and its bin is
linked into the global bin directory that `npm exec` searches.

The last line is the load-bearing one. `~/.npm/_npx` is where `npm exec`
materializes a package it had to INSTALL. This run had already invoked the
version-less form to spawn the `implement` node before the directory was
probed, and the directory did not exist. Had that invocation fetched the
adapter from npm, the cache would have been there.

### E3 — controlled offline probe, with a positive control

E1 and E2 establish what happened. E3 establishes the resolution RULE, and
carries a positive control so the probe cannot report a false negative: probe C
is a spec the baked copy cannot satisfy, and it must fall through to a network
install if the probe is capable of detecting one at all.

Each probe deletes `~/.npm/_npx` first, runs under `--offline` (so any attempt
to reach the registry fails loudly instead of silently succeeding), and then
reports whether a cache directory appeared.

```
----- A: version-less (the form the bundled workflow commits) -----
cmd: npx --offline -y @agentclientprotocol/claude-agent-acp --version
exit: 0
npx-cache: ABSENT (baked global resolved, no install)

----- B: exact pin AT the baked version -----
cmd: npx --offline -y @agentclientprotocol/claude-agent-acp@0.44.0 --version
exit: 0
npx-cache: ABSENT (baked global resolved, no install)

----- C: exact pin at a DIFFERENT version (positive control) -----
cmd: npx --offline -y @agentclientprotocol/claude-agent-acp@0.43.0 --version
exit: 1
npm error code ENOTCACHED
npm error request to https://registry.npmjs.org/@anthropic-ai/claude-agent-sdk/-/claude-agent-sdk-0.3.169.tgz failed: cache mode is 'only-if-cached' but no cached response is available.
npx-cache: CREATED (network/install path taken)
```

Probe C is what makes A and B evidence rather than assertion. It proves the
instrument can see an install: pointed at a version the baked copy does not
satisfy, the same command reached for `registry.npmjs.org` and created the
cache directory. A and B did neither.

### E4 — the source of truth for the bake

From the sibling checkout `livespec-dev-tooling`, file
`docker/fabro-sandbox/agent/Dockerfile` — the file that builds this image
layer:

```dockerfile
ARG CLAUDE_AGENT_ACP_VERSION=0.44.0

RUN npm install -g --fetch-retries=5 \
        @agentclientprotocol/claude-agent-acp@${CLAUDE_AGENT_ACP_VERSION}
```

Its header comment states the intent in as many words: both ACP adapters are
preinstalled, "`@agentclientprotocol/claude-agent-acp` (Claude) as a global so
`npx -y <adapter>` resolves locally".

So the version-less form is not an oversight that happens to work. It is the
consumer half of a two-part design whose producer half is this `npm install -g`
line, and the exact version pin the item asks for already exists, as
`CLAUDE_AGENT_ACP_VERSION`.

## Why the version-less form resolves the baked copy

`npx` is `npm exec`. Given a package spec, it does not fetch first; it first
looks for the spec's bin NAME among the bins already available — the project's
`node_modules/.bin`, then the global bin directory — and runs that copy if the
installed version satisfies the requested spec. Only when no satisfying copy is
found does it install into `~/.npm/_npx`.

The version-less form requests no particular version, so ANY installed copy
satisfies it. The image installs the adapter globally, which links its bin
`claude-agent-acp` into the global bin directory (E2). The lookup therefore
hits on the first try and no install is attempted (E1, E3-A).

This is also exactly why probe C behaved differently: `@0.43.0` is a spec the
installed `0.44.0` cannot satisfy, so the lookup missed and the install path
ran.

## Consequences for the item's remaining acceptance criteria

The item's criteria are written as a conditional pair — one branch if the
package is fetched at run time, one if it is baked. The measurements above
settle the antecedent as BAKED, so:

- The three "if the package is fetched at run time" criteria — an exact
  `@version` on every adapter default, a dev-tooling check rejecting the
  version-less form, and a bump process for a workflow-side adapter version —
  have a FALSE antecedent and are satisfied vacuously. Implementing any of
  them would be actively wrong; see the two rejected mechanisms below.
- The "if the package is baked into the sandbox image" criterion is the live
  one. This note records why the version-less form resolves the baked copy
  (section above), and the bundled workflow's adapter-defaults comment block
  now says so at the point of use.

## The bump process, which already exists

Because the adapter is baked, bumping the adapter version IS bumping the
sandbox image tag. That process is already documented in the bundled workflow
at the `docker` pin (line 292 and the comment above it), and it already
mirrors the mechanism the item asked the adapter pin to mirror:

1. The version is declared once, as `CLAUDE_AGENT_ACP_VERSION` in
   livespec-dev-tooling's agent-layer Dockerfile.
2. An image build publishes it under an immutable tag,
   `python-agent-v<X.Y.Z>`.
3. This repository consumes it by committing that tag as `docker` in the
   bundled workflow, where the shared `bump-pin` autodiscovery rewrites the
   version in lockstep with the livespec-dev-tooling pin in `pyproject.toml`,
   preserving the `python-agent-` layer prefix.

A change of adapter version is therefore already a reviewable diff on a
committed line in this repository, which is the property the item wanted. Note
one asymmetry worth knowing when bumping: the Dockerfile comment records that
`CLAUDE_AGENT_ACP_VERSION` "has no repo-side pin source — it mirrors the host
toolchain and is tracked only here", unlike its sibling `CODEX_ACP_VERSION`,
which the pin-autodiscovery walk emits and the freshness surface bumps against
npm `latest`.

## Two pin mechanisms evaluated and REJECTED

### Rejected: adding an exact `@version` to the adapter defaults

This is the item's headline proposal, and probe B shows it would work today —
`@0.44.0` resolves the baked global offline, with no install.

It is rejected because "today" is the whole problem. An exact pin in
`workflow.toml` would be a SECOND declaration of a version whose first
declaration is the image, and the two would have to be advanced in lockstep by
hand forever. Probe C measures the cost of a single missed bump: the moment the
image's baked version and the workflow's pinned version diverge, every adapter
invocation stops resolving the baked copy and starts installing from npm
instead. That is strictly worse than today's state on both axes the item cares
about — it reintroduces the per-run download the baked image exists to
eliminate, AND it silently runs an adapter build that is not the one the image
was tested with.

So the proposed fix for a moving comparand would, on its first desynchronized
bump, manufacture one. A single pin that cannot desynchronize is the better
mechanism, and it already exists.

This also satisfies the constraint the pre-dispatch rider set: whatever pin
mechanism is chosen "must be one a variant directory can reproduce, not a
dispatcher-side rewrite". The baked pin reproduces in a registered
workflow-variant directory for free, because a variant carries its own
`docker` image tag in its own `workflow.toml` — no per-variant adapter string
edit, and no way for a variant to drift the adapter without also drifting the
image it declares.

### Rejected: switching the adapter defaults to `npx --no-install`

`--no-install` would refuse rather than download when no baked copy is present,
converting the residual hazard below from silent to loud. The successor Codex
adapter is invoked in a related style, at a baked path.

It is rejected because it would break a stated design property of two of these
six defaults. The `pr_adapter` comment records that it "defaults to an un-pinned
Claude adapter so a bare `fabro run` of this config still works" — that is, the
bundled workflow is meant to remain runnable outside the family sandbox image,
where there is no baked global and the download is the intended fallback.
`--no-install` would make a bare `fabro run` fail on a machine that has done
nothing wrong. Trading that for a louder failure in a case that the image pin
already prevents is not a good trade, and it is outside this item's scope.

## Residual hazard, already documented and not re-litigated here

The one real weakness of baked resolution is that it degrades silently. If the
committed image tag ever pointed at an image WITHOUT the baked adapter, the
version-less form would not fail — it would quietly download npm-latest, which
is precisely the moving-comparand behaviour the item describes.

This is a known and recorded hazard, not a new finding: the comment above the
`docker` pin in the bundled workflow already warns that the slim `python-`
layer "carries NO ACP adapters", that a sandbox pinned to it "does NOT fail
loudly", and that "this pin MUST keep the `python-agent-` prefix" for exactly
this reason. The `bump-pin` autodiscovery preserves that prefix mechanically.

Recording it here rather than acting on it: closing the hazard means either
`--no-install` (rejected above, on the bare-`fabro run` regression) or a
dev-tooling check asserting the image tag carries the `python-agent-` prefix.
The latter is plausible and cheap, but it guards the IMAGE pin rather than the
ADAPTER pin, so it is a different item than this one.
