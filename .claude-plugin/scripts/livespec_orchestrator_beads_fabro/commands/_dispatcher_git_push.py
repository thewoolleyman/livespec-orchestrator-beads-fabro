"""Push-time authentication for script nodes, installed beside the mint helper.

The engine's URL credential outranks every credential helper. A process-only
URL rewrite removes it without changing the clone's config. The replacement
helper reads a newly minted token from this process's environment, and never
stores it. Wrapping the command also preserves the publication lease program
and each node's existing hook policy.
"""

__all__: list[str] = ["PUSH_ORIGIN_SOURCE"]

PUSH_ORIGIN_SOURCE = r"""#!/usr/bin/env bash
set +x
set -eu
url=$(git remote get-url --push origin)
case "$url" in
    https://*|http://*) ;;
    *) exec "$@" ;;
esac
rest=${url#*://}
authority=${rest%%/*}
host=${authority##*@}
clean="${url%%://*}://$host/${rest#*/}"
api=${GITHUB_API_URL:-https://api.github.com}
api=${api#*://}
api=${api%%/*}
if test "$api" = api.github.com; then api=github.com; fi
if test "$host" != "$api"; then
    echo 'LIVESPEC_PUSH_AUTH_HOST: origin is not the configured GitHub host' >&2
    exit 1
fi
old_password=''
case "$authority" in
    *@*) old_user=${authority%@*}; old_password=${old_user#*:} ;;
esac
mint="$(dirname "$0")/mint_app_token.py"
# Append to inherited process config so hook policy and callers' config survive.
export GIT_CONFIG_COUNT=${GIT_CONFIG_COUNT:-0}
add_config() {
    export "GIT_CONFIG_KEY_$GIT_CONFIG_COUNT=$1"
    export "GIT_CONFIG_VALUE_$GIT_CONFIG_COUNT=$2"
    GIT_CONFIG_COUNT=$((GIT_CONFIG_COUNT + 1))
}
add_config "url.$clean.insteadOf" "$url"
add_config "credential.$clean.helper" ''
add_config "credential.$clean.helper" '!f() {
    cat >/dev/null
    if test "$1" = get; then
        printf "username=x-access-token\npassword=%s\n" "$LIVESPEC_PUSH_TOKEN"
    fi
}; f'
add_config http.extraHeader ''
add_config "http.$clean.extraHeader" ''
# Keep diagnostics in memory until credentials have been removed. In particular,
# trace output or an origin error must not print URL credentials or Basic auth.
redact_output() {
    local secret encoded
    for secret in "$LIVESPEC_PUSH_TOKEN" "$old_password"; do
        if test -n "$secret"; then
            output=${output//"$secret"/[redacted]}
        fi
    done
    encoded=$(printf 'x-access-token:%s' "$LIVESPEC_PUSH_TOKEN" | base64 | tr -d '\n')
    output=${output//"$encoded"/[redacted]}
}
for attempt in 1 2; do
    # A separate provider process forces a new installation-token mint each time.
    if ! token=$(python3 "$mint" 2>/dev/null) || test -z "$token"; then
        echo 'LIVESPEC_PUSH_AUTH_MINT: installation token could not be minted' >&2
        exit 1
    fi
    export LIVESPEC_PUSH_TOKEN="$token"
    if output=$("$@" 2>&1); then status=0; else status=$?; fi
    redact_output
    printf '%s\n' "$output"
    if test "$status" -eq 0 || test "$attempt" -eq 2; then exit "$status"; fi
    case "$output" in
        *'HTTP 401'*|*'error: 401'*|*'Authentication failed'*|*'Invalid username or token'*)
            echo 'LIVESPEC_PUSH_AUTH_RETRY: authentication refused; reminting once' >&2 ;;
        *) exit "$status" ;;
    esac
done
"""
