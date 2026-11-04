# Fabro dispatch diagnosis

## Read a run through its factory client

The Fabro client on the dispatching host's `PATH` cannot decode a Petri-era
factory run whose sandbox type is Kubernetes. Its failed inspection reports:

> unknown variant `kubernetes`

That error is a client/version mismatch, not evidence that the run's data is
missing. A `dump` of the same run through the same client can instead fail with
`Invalid Response Payload`; it is the same mismatch.

Use the factory-addressed reader instead:

```sh
dispatcher.py inspect --factory petri <run-id>
```

It resolves Petri's declared `dispatcher.factories.petri.bin` and the factory
registry address together. To export the complete run record for later
inspection, use `dispatcher.py inspect --factory petri <run-id> -o <directory>`.

The reader refuses, naming the missing `bin` field or the unresolved factory
name, and runs no client, when the factory declares no `bin` or its address
cannot be resolved. It never falls back to the host `PATH` client.

When recording sequential manual reads with a client wrapper, start with a fresh
invocation log (or clear the existing log first).

Start every export capture with a fresh invocation log. Otherwise an earlier
`inspect` invocation remains appended and can be mistaken for the `dump`
invocation that performs the export.

## The host PATH `fabro` is the legacy 0.254 client; read Petri boards with a factory's committed `bin`

On the dispatching host, `fabro` on `PATH` is `~/.local/bin/fabro`, a symlink to
`~/.fabro/bin/fabro`. That is `fabro 0.254.0 (8869e88)`, the legacy carrier
build (measured 2026-11-03). It fails `fabro ps`, `fabro ps -a` and
`fabro dump` against any Petri-era board that holds a Kubernetes-sandbox run,
with "unknown variant `kubernetes`". Seats keep falling into this, so do not
reach for the PATH client when reading a factory:

- Prefer `dispatcher.py inspect --factory <name> <run-id>` (section above).
- For a board listing, run the factory's own committed client, i.e. the
  `dispatcher.factories.<name>.bin` path in `.livespec.jsonc`, with
  `ps --server https://<host>:<port>`. Since 2026-11-04 both `petri` and
  `candidate` name `~/.local/state/fabro-web-prod/v0393-c39bdbded/fabro`.

Do NOT fix this by copying a newer build over `~/.fabro/bin/fabro`. That file is
also the binary the dev host's own `fabro-server` units (`127.0.0.1:32276` and
`:32277`) start. It is declared in livespec-dev-tooling's
`ansible/inventory/host_vars/vps.yml`, so a hand copy changes two live servers
at their next restart and drifts from GitOps. The default client is moved only
through the dev-host play, as step 2 of `bd-ib-zb2hso`. Step 1's preconditions
held on 2026-11-03: `livespec-dev-tooling-lirki2` (pinned client staging) is
closed, and no fleet repository's `.livespec.jsonc` still declares a `legacy`
factory.
