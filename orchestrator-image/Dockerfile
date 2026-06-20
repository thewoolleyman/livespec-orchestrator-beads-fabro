# livespec dark-factory orchestrator — Beads/Dolt + Fabro, Docker-in-Docker.
#
# Step 1 of the W7 orchestrator-convergence epic (livespec-impl-beads-8bc).
# Builds the PRODUCTION orchestrator image from the known-good DinD recipe the
# step-0 spike proved (research/w7-orchestrator-convergence/dind-spike.md). The
# container runs an *inner* dockerd; Fabro spawns its sandboxes on that inner
# daemon, fully decoupled from the host daemon (DinD, not DooD — no host socket
# is ever mounted). An ephemeral in-container Dolt sql-server is available for a
# throwaway/scratch ledger; the production family-tenant ledger is EXTERNAL and
# injected as an endpoint at run time.
#
# The image is SECRET-FREE by construction. Every credential (model key, GitHub
# token, per-tenant Dolt password, Honeycomb ingest key, Claude Code OAuth
# token) is injected at `docker run` via env / mounts; NONE is baked in. See
# README.md for the run invocation and the injectable externals.

# --- Base: glibc >= 2.39 is a HARD FLOOR (fabro v0.254.0 links GLIBC_2.39). ---
# debian:12 (glibc 2.36) is TOO OLD; Alpine (musl) won't run the binary at all.
# ubuntu:24.04 (noble) ships glibc 2.39 — exactly the minimum. Proven by the
# step-0 spike's base-image table.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# --- Base system + inner Docker daemon. distro docker.io on noble == Docker
#     29.x (containerd image store / overlayfs snapshotter), proven to nest
#     cleanly. Plus the orchestrator's host-level runtime: git, ca-certs,
#     curl/jq for provisioning, python3 (3.12 on noble) plus the small stdlib
#     compatibility shim imported by the mounted dispatcher runtime, gh
#     (GitHub CLI), and iptables (dockerd networking inside the container). ---
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        docker.io \
        ca-certificates \
        curl \
        gpg \
        jq \
        git \
        python3 \
        python3-typing-extensions \
        iptables \
        uidmap \
 && rm -rf /var/lib/apt/lists/*

# --- GitHub CLI (gh) — the dispatcher's PR/merge surface. Installed from the
#     official cli.github.com apt repo (keyring pinned). ---
RUN mkdir -p -m 755 /etc/apt/keyrings \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends gh \
 && rm -rf /var/lib/apt/lists/*

# --- mise — needed by the dispatcher itself after a PR merge. Fabro sandboxes
#     provision their own toolchain, but the orchestrator container owns the
#     post-merge primary refresh and janitor checkout (`mise trust` +
#     `mise exec -- just check`), so mise must be present in the production
#     runtime too. ---
RUN mkdir -p -m 755 /etc/apt/keyrings \
 && curl -fsSL https://mise.jdx.dev/gpg-key.pub \
        | gpg --dearmor -o /etc/apt/keyrings/mise-archive-keyring.gpg \
 && chmod go+r /etc/apt/keyrings/mise-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/mise-archive-keyring.gpg] https://mise.jdx.dev/deb stable main" \
        > /etc/apt/sources.list.d/mise.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends mise \
 && rm -rf /var/lib/apt/lists/* \
 && mise --version

# --- uv (Astral) — the Python toolchain manager (family convention: uv pins
#     Python + Python packages; mise pins non-Python binaries). Pinned to the
#     family version (0.5.20) from the official installer, then verified. ---
ENV UV_VERSION=0.5.20
RUN curl -fsSL "https://astral.sh/uv/${UV_VERSION}/install.sh" \
        -o /tmp/uv-install.sh \
 && env UV_INSTALL_DIR=/usr/local/bin sh /tmp/uv-install.sh \
 && rm -f /tmp/uv-install.sh \
 && /usr/local/bin/uv --version

# --- bd (beads CLI), pinned v1.0.5 at /usr/local/bin/bd (matches the host pin).
#     The release TARBALL is content-pinned by sha256; the extracted binary is
#     re-verified against the proven v1.0.5 binary sha. ---
ENV BD_VERSION=1.0.5 \
    BD_TARBALL_SHA256=24706f65c7131c7b3261388709ae8781c8db53f0795398f67aa40538750aacf3 \
    BD_BINARY_SHA256=463b7655041345ce5d4bac00c3a5d465166bb30166147e11ef1c6e07df0a4486
RUN curl -fsSL -o /tmp/beads.tar.gz \
        "https://github.com/gastownhall/beads/releases/download/v${BD_VERSION}/beads_${BD_VERSION}_linux_amd64.tar.gz" \
 && echo "${BD_TARBALL_SHA256}  /tmp/beads.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/beads.tar.gz -C /tmp \
 && echo "${BD_BINARY_SHA256}  /tmp/bd" | sha256sum -c - \
 && install -m 0755 /tmp/bd /usr/local/bin/bd \
 && rm -rf /tmp/beads.tar.gz /tmp/bd /tmp/README.md /tmp/LICENSE /tmp/CHANGELOG.md \
 && /usr/local/bin/bd version

# --- dolt, pinned v2.1.4 (matches the host pin) at /usr/local/bin/dolt — for
#     the ephemeral in-container ledger substrate (the spike's Goal-5 pattern).
#     The production family-tenant ledger is EXTERNAL, not run here. ---
ENV DOLT_VERSION=2.1.4 \
    DOLT_TARBALL_SHA256=f3bd2329fc469d9d557af377dc36280da2c4ed13315cc2e4a82fe2b5ae682929
RUN curl -fsSL -o /tmp/dolt.tar.gz \
        "https://github.com/dolthub/dolt/releases/download/v${DOLT_VERSION}/dolt-linux-amd64.tar.gz" \
 && echo "${DOLT_TARBALL_SHA256}  /tmp/dolt.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/dolt.tar.gz -C /tmp \
 && install -m 0755 /tmp/dolt-linux-amd64/bin/dolt /usr/local/bin/dolt \
 && rm -rf /tmp/dolt.tar.gz /tmp/dolt-linux-amd64 \
 && /usr/local/bin/dolt version

# --- Fabro binary. Pin the version + the glibc floor together. The binary is
#     COPIED in (not apt-installed). It is fetched into the build context from
#     the host's ~/.fabro/bin/fabro (v0.254.0) by build-and-verify.sh and is
#     gitignored — NEVER committed (it is a 111MB blob, and pinning the floor
#     here documents the coupling). ---
ENV FABRO_VERSION=0.254.0
COPY fabro /usr/local/bin/fabro
RUN chmod +x /usr/local/bin/fabro \
 && /usr/local/bin/fabro version | head -1

# --- LIVESPEC_BD_PATH: the impl-beads wrappers shell out to $LIVESPEC_BD_PATH.
ENV LIVESPEC_BD_PATH=/usr/local/bin/bd

# --- Storage driver: overlay2/overlayfs, but /var/lib/docker MUST be on a
#     non-overlay filesystem or the inner daemon silently falls back to vfs.
#     The VOLUME declaration is load-bearing (mirrors the official docker:dind
#     image). At `docker run` time this is backed by an ext4 volume/bind. ---
VOLUME /var/lib/docker

# --- Fabro web-UI / control-plane port. The in-container fabro server listens
#     on 0.0.0.0:32276 (set by the entrypoint's templated settings.toml) so a
#     published port is reachable; the README documents binding it to the HOST
#     loopback only (-p 127.0.0.1:32276:32276) behind dev-token auth. ---
EXPOSE 32276

# --- Entrypoint supervisor: starts dockerd -> waits for the socket ->
#     provisions ~/.fabro/settings.toml + the headless fabro server (LLM +
#     GitHub, non-interactive) -> execs the dispatcher (or a passed command). ---
COPY orchestrator-entrypoint.sh /usr/local/bin/orchestrator-entrypoint.sh
RUN chmod +x /usr/local/bin/orchestrator-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/orchestrator-entrypoint.sh"]
# Default command: the dispatcher loop is the orchestrator's reason for being,
# but it requires the injectable externals (ledger endpoint + creds) and a
# mounted impl-beads checkout, so the image defaults to an interactive shell;
# operators pass the real `dispatcher.py loop ...` command (see README).
CMD ["bash"]
