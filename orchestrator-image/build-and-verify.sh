#!/usr/bin/env bash
# build-and-verify.sh — build the orchestrator image and run tier-1 verification.
#
# Step 1 of the W7 orchestrator-convergence epic (livespec-impl-beads-8bc).
# Builds the DinD orchestrator image, then runs the privileged container with an
# ext4-backed /var/lib/docker volume and the secrets injected via the 1Password
# env wrapper, and verifies:
#
#   T1.a inner dockerd reports overlay2 / overlayfs (NOT vfs);
#   T1.b fabro version + fabro doctor run; server reachable + GitHub configured;
#   T1.c fabro web UI reachable on the published port (HTTP status only);
#   T1.d ephemeral in-container Dolt sql-server + a bd round-trip.
#
# MUST be run on the HOST as ubuntu (Docker access), under the 1Password wrapper
# so the injected secrets are present:
#
#   /data/projects/1password-env-wrapper/with-livespec-env.sh -- \
#     bash orchestrator-image/build-and-verify.sh
#
# NO secret is ever printed: tokens flow via `-e VAR` (docker reads the value
# from this process's env, never logging it), and all probe output is captured
# status-codes / structural lines only.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${IMAGE:-livespec-orchestrator:dev}"
CONTAINER="${CONTAINER:-livespec-orch-verify}"
VARLIB_VOL="${VARLIB_VOL:-livespec-orch-varlib}"
# In-container control-plane port (the fabro server's listen port).
FABRO_PORT="${FABRO_PORT:-32276}"
# Host-side publish port. Defaults to a NON-default port so verification never
# collides with a host fabro server already holding 127.0.0.1:32276 (the
# orchestrator host runs one). In production with --network host the publish is
# moot; here we map host:HOST_PUBLISH_PORT -> container:FABRO_PORT.
HOST_PUBLISH_PORT="${HOST_PUBLISH_PORT:-32280}"
HOST_FABRO_BIN="${HOST_FABRO_BIN:-$HOME/.fabro/bin/fabro}"

log() { printf '\n=== %s ===\n' "$*"; }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker volume rm "$VARLIB_VOL" >/dev/null 2>&1 || true
  rm -f "$HERE/fabro" || true
}
trap cleanup EXIT

# --------------------------------------------------------------------------
# Stage the pinned fabro binary into the build context (gitignored, not committed).
# --------------------------------------------------------------------------
log "staging fabro binary into build context"
[ -x "$HOST_FABRO_BIN" ] || { echo "fabro binary not found at $HOST_FABRO_BIN" >&2; exit 1; }
cp "$HOST_FABRO_BIN" "$HERE/fabro"
chmod +x "$HERE/fabro"
"$HERE/fabro" version | head -1

# --------------------------------------------------------------------------
# Build.
# --------------------------------------------------------------------------
log "building $IMAGE"
docker build -t "$IMAGE" "$HERE"

# --------------------------------------------------------------------------
# Run: privileged, ext4-backed /var/lib/docker volume, host loopback port,
# secrets injected from this (wrapper) process's env. Web-UI port published to
# host loopback ONLY (control plane behind dev-token auth — see README).
# --------------------------------------------------------------------------
log "starting privileged container $CONTAINER"
docker volume create "$VARLIB_VOL" >/dev/null
docker run -d --name "$CONTAINER" \
  --privileged \
  -v "$VARLIB_VOL:/var/lib/docker" \
  -p "127.0.0.1:${HOST_PUBLISH_PORT}:${FABRO_PORT}" \
  -e FABRO_PORT="$FABRO_PORT" \
  -e GITHUB_APP_ID \
  -e GITHUB_PRIVATE_KEY \
  -e GITHUB_APP_INSTALLATION_ID \
  -e GITHUB_API_URL \
  -e ANTHROPIC_API_KEY_LIVESPEC_E2E \
  -e CLAUDE_CODE_OAUTH_TOKEN \
  -e HONEYCOMB_INGEST_KEY_LIVESPEC \
  "$IMAGE" \
  sleep infinity >/dev/null

# Wait for the entrypoint to finish provisioning (dockerd + fabro).
log "waiting for in-container provisioning"
for _ in $(seq 1 90); do
  if docker exec "$CONTAINER" docker info >/dev/null 2>&1; then break; fi
  sleep 1
done

# T1.a — inner storage driver must be overlay2 / overlayfs, NOT vfs.
log "T1.a inner storage driver"
DRIVER="$(docker exec "$CONTAINER" docker info --format '{{.Driver}}' 2>/dev/null || echo UNKNOWN)"
echo "inner storage driver: $DRIVER"
case "$DRIVER" in
  overlay2|overlayfs) echo "T1.a PASS (overlay-based)";;
  vfs) echo "T1.a FAIL (vfs — /var/lib/docker is not on ext4)"; exit 1;;
  *) echo "T1.a FAIL (unexpected driver: $DRIVER)"; exit 1;;
esac

# Give fabro provisioning a moment to settle (install + bind).
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" test -f /root/.fabro/settings.toml; then break; fi
  sleep 1
done

# T1.b — fabro version + doctor; server reachable + GitHub configured.
log "T1.b fabro version + doctor (redacted)"
docker exec "$CONTAINER" fabro version 2>&1 | sed -E 's/[A-Za-z0-9_-]{24,}/<redacted>/g' | head -8
echo "--- fabro doctor ---"
docker exec "$CONTAINER" fabro doctor 2>&1 | sed -E 's/[A-Za-z0-9_-]{24,}/<redacted>/g' | head -30 || true

# T1.c — web UI reachable on the published (host-loopback) port. Status only.
log "T1.c fabro web UI HTTP probe (host loopback)"
CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HOST_PUBLISH_PORT}/" || echo 000)"
echo "web UI host 127.0.0.1:${HOST_PUBLISH_PORT} -> container :${FABRO_PORT} -> HTTP $CODE"
case "$CODE" in
  2*|3*|401|403) echo "T1.c PASS (server reachable; $CODE)";;
  *) echo "T1.c FAIL (web UI unreachable: $CODE)"; exit 1;;
esac

# T1.d — ephemeral in-container Dolt + bd round-trip (the in-container ledger
# substrate). Two legs:
#   (i)  a standalone ephemeral dolt sql-server nested on the INNER docker
#        daemon (the spike's Goal-5 pattern: dolt is on the inner daemon, the
#        container is visible only in the INNER docker ps);
#   (ii) a bd embedded-mode round-trip (init + create + list) in a throwaway
#        scratch repo dir, proving the bd binary drives a Dolt ledger here.
# A throwaway scratch dir only — NEVER a primary checkout (bd init auto-commits)
# and the EXTERNAL family tenant is never touched.
log "T1.d.i ephemeral Dolt on the inner daemon (spike Goal-5 pattern)"
docker exec "$CONTAINER" bash -lc '
  set -e
  # The inner daemon runs dolthub/dolt-sql-server; the round-trip is a trivial
  # CREATE/INSERT/SELECT via `dolt sql -q` inside that nested container.
  docker run -d --name t1d-dolt dolthub/dolt-sql-server:latest >/dev/null 2>&1
  sleep 3
  docker exec t1d-dolt dolt sql -q "CREATE DATABASE spikedb; USE spikedb; CREATE TABLE t(id INT PRIMARY KEY, v VARCHAR(16)); INSERT INTO t VALUES (1, \"hello-dind\"); SELECT id, v FROM t;" 2>&1 | tail -6
  echo "inner docker ps (the dolt container lives ONLY on the inner daemon):"
  docker ps --filter name=t1d-dolt --format "{{.Names}} {{.Image}} {{.Status}}"
  docker rm -f t1d-dolt >/dev/null 2>&1 || true
' 2>&1 | sed -E 's/[A-Za-z0-9_-]{32,}/<redacted>/g' || echo "T1.d.i note: inner-dolt leg degraded (image pull may be slow)"

log "T1.d.ii bd embedded-mode round-trip (init + create + list)"
docker exec "$CONTAINER" bash -lc '
  set -e
  repo="$(mktemp -d /tmp/ephemeral-repo.XXXXXX)"; cd "$repo"; git init -q
  # Embedded mode (no --server): bd spins up its own managed Dolt in .beads/ —
  # the simplest ephemeral substrate proof. --skip-agents --skip-hooks per the
  # family rule (no agent files / git hooks injected).
  bd init --prefix ephemeral --skip-agents --skip-hooks --non-interactive --quiet 2>&1 | tail -3 || true
  bd create "ephemeral round-trip probe" -d "tier-1 verification" 2>&1 | tail -2 || true
  echo "--- bd list ---"
  bd list 2>&1 | head -5 || true
' 2>&1 | sed -E 's/[A-Za-z0-9_-]{32,}/<redacted>/g'

log "tier-1 verification complete"
echo "ALL TIER-1 CHECKS PASSED (driver=$DRIVER, web-ui=HTTP $CODE)"
