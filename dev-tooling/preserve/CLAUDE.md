# dev-tooling/preserve/

These are operator scripts that copy a live factory run's git tree to origin before a cancel. Read
`README.md` here before running or editing them.

Constraints an agent editing this directory must satisfy:

- **Read-only on fleet hosts.** Only `kubectl get`, `crictl ps` / `crictl inspect`, `sudo find` and
  `sudo cat` may reach a host. Never add a command that changes a host; fleet_host_guard refuses `tar`
  too.
- **Keep every guard rule in README.md.** That means the run branch over HEAD, fsck before push, the
  ancestry guard (write a `-<sha12>` sibling, never move a ref), push retry, ls-remote verify, and the
  create-only `needs-human/<RUN_ULID>` ref.
- **Shell only.** There is no product Python here, so the Red-Green-Replay ritual does not apply. Commit
  changes as `chore(dev-tooling):`.
- **Stopgap.** bd-ib-vraou4 (cancel-for-restart preserve path) is the durable product path that retires
  these scripts. Do not grow them into a product.
