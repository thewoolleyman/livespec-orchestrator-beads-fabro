#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — read-only readback of the running fleet launchers.
#
# A stopgap whose first-class replacements are the livespec console application
# and the committed launch-loop tool bd-ib-jr6w7v; see README.md.
#
# A bash launcher keeps executing the script content it started with
# (bd-ib-5ycmsm). This command lists every running launcher of this user, whose
# script is a dispatch-dual*.sh or resume-capped*.sh, with the version of the
# script content it is executing and the version of the script file it was
# started from as that file is on disk now, and marks each launcher whose two
# versions differ. A version is the first 12 hex digits of the sha256 of the
# script's bytes. The running content is read from the file descriptor bash holds
# open on the script (fd 255), so it is right even after the file was replaced.
#
# Usage: launcher-versions.sh
# Output, one row per launcher, then a summary line:
#   PID STATE RUNNING ON-DISK ITEM SCRIPT
# STATE is `current`, `STALE` (the versions differ) or `UNKNOWN` (a version
# could not be read). It reads /proc and the script files only and changes
# nothing; it always exits 0.
set -u

script_version() { sha256sum < "$1" 2>/dev/null | cut -c1-12; }

rows=""
for dir in /proc/[0-9]*; do
  pid=${dir#/proc/}
  argv=()
  mapfile -d '' -t argv < "$dir/cmdline" 2>/dev/null || continue
  [ "${#argv[@]}" -ge 2 ] || continue
  case ${argv[0]##*/} in bash|sh|dash) ;; *) continue ;; esac
  script=${argv[1]}
  case ${script##*/} in dispatch-dual*.sh|resume-capped*.sh) ;; *) continue ;; esac
  # A command substitution forks a copy of the launcher with the same argv; only the original counts.
  ppid=$(sed -n 's/^PPid:[[:space:]]*//p' "$dir/status" 2>/dev/null)
  parent_argv=()
  if [ -n "$ppid" ]; then mapfile -d '' -t parent_argv < "/proc/$ppid/cmdline" 2>/dev/null; fi
  [ "${parent_argv[1]:-}" = "$script" ] && continue
  case $script in
    /*) path=$script ;;
    *) path="$(readlink "$dir/cwd" 2>/dev/null)/$script" ;;
  esac
  running=$(script_version "$dir/fd/255")
  on_disk=$(script_version "$path")
  if [ -z "$running" ] || [ -z "$on_disk" ]; then state=UNKNOWN
  elif [ "$running" = "$on_disk" ]; then state=current
  else state=STALE
  fi
  rows="${rows}${pid} ${state} ${running:-unreadable} ${on_disk:-unreadable} ${argv[2]:-none} ${path}"$'\n'
done

printf 'PID STATE RUNNING ON-DISK ITEM SCRIPT\n'
if [ -n "$rows" ]; then printf '%s' "$rows" | sort -n; fi
total=0
stale=0
if [ -n "$rows" ]; then
  total=$(printf '%s' "$rows" | grep -c .)
  stale=$(printf '%s' "$rows" | awk '$2!="current"' | grep -c .)
fi
printf '%d running launchers, %d not on the script now on disk\n' "$total" "$stale"
