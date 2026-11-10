# shellcheck shell=bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch host configuration.
#
# The ONE place a fleet-launch script reads a host-specific value. Every script in
# fleet-launch/ sources this file and never writes a host value inline. This
# directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see README.md).
#
# Each value can be overridden from the environment, which is how the hermetic
# harness points the scripts at stub boards and throwaway directories.

# Repository and seat identity.
: "${FLEET_LAUNCH_ORCH_REPO:=/data/projects/livespec-orchestrator-beads-fabro}"
: "${FLEET_LAUNCH_SEAT:=petri-factory-on-gmktec}"

# Data directory: logs, verdicts, the shared fleet-cap file and the hold file.
# It holds data only, never a script.
: "${FLEET_LAUNCH_STATE_DIR:=$FLEET_LAUNCH_ORCH_REPO/tmp/petri-canary}"
: "${FLEET_LAUNCH_FLEET_CAP_FILE:=$FLEET_LAUNCH_STATE_DIR/fleet-cap}"
: "${FLEET_LAUNCH_HOLD_FILE:=$FLEET_LAUNCH_STATE_DIR/hold-gmktec}"
# A repository hold is hold-repo-<target-checkout-basename> in this directory.
# It scopes a red repository to its own launches without stopping other tenants.
: "${FLEET_LAUNCH_REPO_HOLD_DIR:=$FLEET_LAUNCH_STATE_DIR}"

# Factory servers. hp-xubuntu and vps are retired as factories and are never read.
: "${FLEET_LAUNCH_GMK_SERVER:=https://gmktec-xubuntu.perch-rudd.ts.net:32276}"
: "${FLEET_LAUNCH_HL_SERVER:=https://gmktec-xubuntu.perch-rudd.ts.net:32277}"
: "${FLEET_LAUNCH_GMK_SSH:=cwoolley@gmktec-xubuntu}"
: "${FLEET_LAUNCH_GMK_SERVER_ENV:=/home/cwoolley/.fabro/storage/server.env}"
# Per-factory ceilings, from the gitops host_vars for gmktec-xubuntu.
: "${FLEET_LAUNCH_GMK_CAP:=8}"
: "${FLEET_LAUNCH_HL_CAP:=2}"
# Minimum gmktec idle CPU percentage before a launch.
: "${FLEET_LAUNCH_GMK_MIN_IDLE:=25}"

# The Fabro client that reads the boards: the build gmktec serves, bbe693847,
# which requests compressed board reads and filters plain `ps` on the server
# (bd-ib-xoh477). Keep it equal to dispatcher.factories.petri.bin.
: "${FLEET_LAUNCH_FABRO:=/home/ubuntu/.local/state/fabro-web-prod/v0393-bbe693847/fabro}"

# The shared factory-board snapshot (board-snapshot.sh). Every launcher on the host reads a factory's
# board through one snapshot file per factory, so the factory server receives at most one run listing
# per FLEET_LAUNCH_BOARD_TTL_S from them however many launchers are queued. 0 turns the sharing off.
# A launcher waits at most FLEET_LAUNCH_BOARD_REFRESH_WAIT_S for another launcher's refresh to finish
# (one listing costs the petri server 25-40 s) before it reads the board as unknown.
: "${FLEET_LAUNCH_BOARD_SNAPSHOT_DIR:=/run/user/1000/fleet-board-snapshot.d}"
: "${FLEET_LAUNCH_BOARD_TTL_S:=60}"
: "${FLEET_LAUNCH_BOARD_REFRESH_WAIT_S:=180}"

# Cross-seat coordination directories (shared by every seat on this host).
: "${FLEET_LAUNCH_INFLIGHT_DIR:=/run/user/1000/fleet-inflight.d}"
: "${FLEET_LAUNCH_GMK_QUEUE_DIR:=/run/user/1000/gmktec-launch-queue.d}"
: "${FLEET_LAUNCH_GMK_LOCK_DIR:=/run/user/1000/gmktec-launch-lock.d}"

# The orchestrator plugin registry and cache, used to resolve the installed build.
: "${FLEET_LAUNCH_PLUGIN_REGISTRY:=/home/ubuntu/.claude/plugins/installed_plugins.json}"
: "${FLEET_LAUNCH_PLUGIN_CACHE:=/home/ubuntu/.claude/plugins/cache/livespec-orchestrator-beads-fabro/livespec-orchestrator-beads-fabro}"
: "${FLEET_LAUNCH_PLUGIN_KEY:=livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro}"

# Credential wrappers. The default is the family wrapper; independent tenants
# pass WRAPPER=<fleet-launch/wrappers/...> per launch.
: "${FLEET_LAUNCH_DEFAULT_WRAPPER:=/usr/local/bin/with-livespec-env.sh}"
: "${FLEET_LAUNCH_DOLT_SERVER_WRAPPER:=/usr/local/bin/with-dolt-server-env.sh}"
: "${FLEET_LAUNCH_OPENBRAIN_WRAPPER:=/data/projects/1password-env-wrapper/with-openbrain-env.sh}"
: "${FLEET_LAUNCH_RESUME_WRAPPER:=/data/projects/resume/with-resume-env.sh}"
: "${FLEET_LAUNCH_RESUME_COMMAND:=resume}"
: "${FLEET_LAUNCH_HOMELAB_AWS_WRAPPER:=/usr/local/bin/with-homelab-aws.sh}"
: "${FLEET_LAUNCH_HL_CLI:=/home/ubuntu/.nix-profile/bin/hl}"

# Timing.
: "${FLEET_LAUNCH_MAX_WAIT_S:=86400}"
: "${FLEET_LAUNCH_ABANDON_S:=1200}"
: "${FLEET_LAUNCH_POLL_S:=30}"
: "${FLEET_LAUNCH_PREFLIGHT_REUSE_S:=600}"
# How many times a launcher runs the ready-set check, one poll apart, before it gives up on a
# refusal. A refusal that clears on its own (a blocker that has just closed, a ledger read that
# lagged) keeps the launcher's ticket; one that persists ends with a terminal line and a ledger comment.
: "${FLEET_LAUNCH_READY_RETRY_POLLS:=5}"
: "${FLEET_LAUNCH_MUTEX_HOLD_S:=900}"
# The two fixed poll intervals below are waits on an observed state (a free
# mutex, a listed run); the hermetic harness shortens them so each of its cases
# advances on that state instead of sitting out a production-sized interval.
: "${FLEET_LAUNCH_MUTEX_POLL_S:=10}"
: "${FLEET_LAUNCH_LISTING_POLL_S:=15}"
# How long an impl launcher waits for a drive it stopped for a hold to exit after TERM before it
# sends KILL.
: "${FLEET_LAUNCH_STOP_GRACE_S:=30}"
# How long a resume launcher keeps its in-flight marker counted after the resume
# client has exited, while it waits for the run to list on the factory board.
: "${FLEET_LAUNCH_LISTING_WAIT_S:=600}"
