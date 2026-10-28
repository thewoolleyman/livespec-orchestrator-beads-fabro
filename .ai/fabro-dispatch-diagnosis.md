# Fabro dispatch diagnosis

## Read a run through its factory client

The Fabro client on the dispatching host's `PATH` cannot decode a Petri-era
factory run whose sandbox type is Kubernetes. Its failed inspection reports:

> unknown variant `kubernetes`

That error is a client/version mismatch, not evidence that the run's data is
missing.

Use the factory-addressed reader instead:

```sh
dispatcher.py inspect --factory petri <run-id>
```

It resolves Petri's declared `dispatcher.factories.petri.bin` and the factory
registry address together. To export the complete run record for later
inspection, use `dispatcher.py inspect --factory petri <run-id> -o <directory>`.

When recording sequential manual reads with a client wrapper, start with a fresh
invocation log (or clear the existing log first).

Start every export capture with a fresh invocation log. Otherwise an earlier
`inspect` invocation remains appended and can be mistaken for the `dump` invocation
that performs the export.
