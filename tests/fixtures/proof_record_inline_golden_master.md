Proof of Done — host_verified — session 01M44GOLDENSESSION — 2026-10-07T12:00:00Z

## Build identity

- Release tag: v0.173.7
- Installed build: abc123def456

## Assertion 1 — The released build resolves the host mode on an operator host.

Proof mode: host_captured

Governing scenario: ## Scenario 136 — A host-captured assertion holds the item in acceptance

Reproduction steps:

1. Run the installed entry point.
2. Read the mode it reports. Produces proof 01.

Proof:

```
$ livespec-orchestrator-beads-fabro-dispatcher --version
0.173.7
```

Reproduced: yes.

## Assertion 2 — A record under budget with inline output publishes exactly as it does today.

Proof mode: host_captured

Governing scenario: no scenario governs this assertion

Reproduction steps:

1. Render a record whose proof carries its own ``` fence.

Proof:

````
outer
```
inner fence
```
done
````

Reproduced: yes.
