#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# Print a repository's committed dispatcher.default_factory as read from its origin
# default branch, never a literal. Exits non-zero, printing nothing, when the key is
# absent or ambiguous.
# Usage: resolve-default-factory.sh <repo-path>
set -euo pipefail
git -C "$1" fetch -q origin
git -C "$1" show origin/HEAD:.livespec.jsonc 2>/dev/null \
  | python3 -c 'import re,sys
t=re.sub(r"(?m)^\s*//.*$","",sys.stdin.read())
m=re.findall(r"\"default_factory\"\s*:\s*\"([^\"]+)\"",t)
sys.exit(1) if len(set(m))!=1 else print(m[0])'
