# pi dogfooding

Moved word for word from `AGENTS.md` §"pi dogfooding" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

## pi dogfooding (`@earendil-works/pi-coding-agent`)

This repo's operation surface can also be dogfooded from the pi coding agent,
alongside Claude Code and OpenAI Codex. Unlike Codex's host-wide plugin
registration, pi package enablement is project-scoped: the package install
creates project-local state under `.pi/`, and pi's project-trust gate controls
whether that state is honored.

Install the three pi git packages in the governed project: livespec CORE, the
`livespec-driver-pi` pi Driver, and THIS repo's orchestrator package:

```bash
# livespec CORE (spec-side prose + wrappers):
pi install git:github.com/thewoolleyman/livespec@release -l --approve

# The pi Driver (supplies the spec-side livespec-* pi skill surface):
pi install git:github.com/thewoolleyman/livespec-driver-pi@release -l --approve

# This repo's orchestrator package (ships its OWN pi skill bindings):
pi install git:github.com/thewoolleyman/livespec-orchestrator-beads-fabro@release -l --approve
```

pi has a flat skill namespace: it cannot express the Claude/Codex
`/livespec-orchestrator-beads-fabro:<op>` form. This package therefore exposes
each operation as `livespec-orchestrator-beads-fabro-<op>`; for example,
`drive` is registered as `livespec-orchestrator-beads-fabro-drive`. Keep the
full prefix. Shortening it is forbidden because other fleet repos share the
same suffix.

Each pi binding lives under `.claude-plugin/.pi-plugin/skills/`, and the
binding directory name MUST equal the frontmatter `name`. pi has tolerated a
directory/frontmatter mismatch, but the Agent Skills standard does not, and
this repo's `check-pi-plugin-structure` gate rejects the mismatch. Frontmatter
values that contain `: `, such as descriptions with `Mutating: ...`, must be
quoted so pi parses the field instead of silently dropping it.

Do not claim pi support from a non-interactive one-shot alone. A
non-interactive pi invocation (`-p`, `--mode json`, `--mode rpc`) can silently
ignore project-local packages unless trust is already established. Claim or
debug pi support only after a live interactive pi session shows this package's
skills in pi's human discoverability surface and drives an operation through the
installed package. Use a scoped tmux socket for scripted evidence; never use the
default tmux socket for repo acceptance proof.
