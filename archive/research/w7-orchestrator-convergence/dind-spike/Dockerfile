# PROTOTYPE — spike evidence only, NOT the production orchestrator image.
#
# This captures the known-good DinD recipe proven by the o2f spike
# (research/w7-orchestrator-convergence/dind-spike.md). It is a reference
# starting point for step 1 of the W7 orchestrator-convergence epic, which must
# still add: the fabro `settings.toml` provisioning, an entrypoint supervisor
# (start dockerd -> wait for socket -> start the dispatcher), and runtime
# injection of the externals (ledger endpoint, model key, git creds, Honeycomb
# key). Do NOT bake any secret into the image.

# --- Base: glibc >= 2.39 is a HARD FLOOR (fabro v0.254.0 links GLIBC_2.39). ---
# debian:12 (glibc 2.36) is TOO OLD; Alpine (musl) won't run the binary at all.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# --- Inner Docker daemon. distro docker.io on noble == Docker 29.x (containerd
#     image store / overlayfs snapshotter), proven to nest cleanly. ---
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        docker.io \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# --- Storage driver: overlay2/overlayfs, but /var/lib/docker MUST be on a
#     non-overlay filesystem or the inner daemon silently falls back to vfs.
#     The VOLUME declaration is load-bearing (mirrors the official docker:dind
#     image). At `docker run` time this is backed by an ext4 volume/bind. ---
VOLUME /var/lib/docker

# --- Fabro binary. Pin the version + the glibc floor together. The binary is
#     copied in (not apt-installed). Build-context placement is step-1's call;
#     during the spike it was `docker cp ~/.fabro/bin/fabro <c>:/usr/local/bin`.
# COPY fabro /usr/local/bin/fabro
# RUN chmod +x /usr/local/bin/fabro

# --- Privileged is REQUIRED at run time for the inner dockerd:
#       docker run --privileged \
#         -v <ext4-vol>:/var/lib/docker \
#         --network host \                  # to reach the external Dolt tenant
#         -e BEADS_DOLT_PASSWORD_<tenant>=... \   # injected via 1Password wrapper
#         -e <MODEL_API_KEY>=... \
#         -e HONEYCOMB_API_KEY=... \
#         <image>
#     (the GitHub token flows via `fabro secret` / `fabro install github`).
#
# --- Entrypoint (step 1): a tiny supervisor that
#       1. starts `dockerd` in the background,
#       2. blocks until /var/run/docker.sock exists and `docker info` succeeds,
#       3. provisions ~/.fabro/settings.toml from injected config/secrets,
#       4. launches the dispatcher.
# ENTRYPOINT ["/usr/local/bin/orchestrator-entrypoint.sh"]
