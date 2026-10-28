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
