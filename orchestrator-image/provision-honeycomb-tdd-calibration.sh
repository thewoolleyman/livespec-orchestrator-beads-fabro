#!/usr/bin/env bash
# Provision the TDD-calibration Honeycomb resources from their COMMITTED,
# VERSIONED definitions (plan factory-test-first-enforcement slice S3,
# work-item bd-ib-3h5vfq): two derived columns that classify post-hoc Red, one
# board showing the share by repository and adapter, and one trigger on that
# share.
#
# IDEMPOTENT by construction: every resource is looked up by its stable
# identity (a derived column by `alias`, the board by `name`, the trigger by
# `name`), updated with PUT when it exists and created with POST when it does
# not. Re-running changes nothing but the resources' contents, so this is safe
# to run after editing a definition file.
#
# SECRETS NEVER REACH ARGV OR THE LOG. The API key is read from the
# environment and passed to curl only through a header; no `set -x`, no echo
# of any header, and the recipient lister redacts email local-parts (the same
# discipline provision-honeycomb-run-turn-trigger.sh established).
#
# HOST-WRAPPER EXECUTION. The Honeycomb configuration key lives in 1Password,
# so run this THROUGH the project's configured env wrapper rather than
# exporting the key by hand:
#
#   with-livespec-env.sh -- \
#     orchestrator-image/provision-honeycomb-tdd-calibration.sh
#
# DRY_RUN=1 prints every payload it would send and makes NO network call, which
# is the mode the hermetic test tier and a review both use. Point
# HONEYCOMB_API_BASE at a local fixture to exercise the full create/update
# path with no live account.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
definitions="${here}/honeycomb"

api_key="${HONEYCOMB_CONFIG_KEY_LIVESPEC:-${HONEYCOMB_TEAM_KEY_LIVESPEC:-}}"
api_base="${HONEYCOMB_API_BASE:-https://api.honeycomb.io}"
dataset="${HONEYCOMB_DISPATCHER_DATASET:-livespec-dispatcher}"
recipient_selector="${HONEYCOMB_OPERATOR_ALERT_RECIPIENT:-}"

# The post-hoc classification threshold: a median Red-to-Green gap at or below
# this many seconds reads as "the commit shape was produced after the fact".
# 120s is a STARTING value, not a calibrated one: the fleet-wide measurement in
# plan/factory-test-first-enforcement/research/opening-research-2026-09-30.md
# put the median at 197s across 147 product-touching commits with a p25 of
# 152s, so a 120s wall classifies the fastest quarter of today's population and
# leaves room for the distribution to move once the order guard and the
# rewritten prompt take effect. Re-derive it from the board before treating it
# as settled.
gap_seconds="${HONEYCOMB_TDD_POST_HOC_GAP_SECONDS:-120}"

# The monitoring threshold: the SHARE of classified dispatches reading post-hoc
# at or above which the trigger fires. A fraction, because the query averages a
# 0/1 flag.
share_threshold="${HONEYCOMB_TDD_POST_HOC_SHARE_THRESHOLD:-0.25}"
window_seconds="${HONEYCOMB_TDD_TRIGGER_WINDOW_SECONDS:-86400}"
frequency_seconds="${HONEYCOMB_TDD_TRIGGER_FREQUENCY_SECONDS:-7200}"

# Which resources to provision. Default is all three; narrow it to re-apply one
# definition without touching the others.
resources="${HONEYCOMB_TDD_RESOURCES:-derived_columns,board,trigger}"

dry_run="${DRY_RUN:-0}"

if [[ -z "${api_key}" && "${dry_run}" != "1" ]]; then
  printf '%s\n' "HONEYCOMB_CONFIG_KEY_LIVESPEC is required (run through with-livespec-env.sh)." >&2
  exit 2
fi

for definition in tdd-calibration-derived-columns.json tdd-calibration-board.json tdd-calibration-trigger.json; do
  if [[ ! -f "${definitions}/${definition}" ]]; then
    printf 'missing committed definition: %s\n' "${definitions}/${definition}" >&2
    exit 2
  fi
done

tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT

curl_json() {
  local method="$1"
  local url="$2"
  local data_arg=()
  if [[ "$#" -eq 3 ]]; then
    data_arg=(--data @"$3")
  fi
  curl --fail-with-body --silent --show-error \
    --request "${method}" \
    --url "${url}" \
    --header "X-Honeycomb-Team: ${api_key}" \
    --header "Content-Type: application/json" \
    "${data_arg[@]}"
}

wants() {
  [[ ",${resources}," == *",$1,"* ]]
}

# Render one definition file's payload(s) with the configured substitutions.
# The tokens are literal `__NAME__` strings inside the committed JSON, so a
# definition file stays valid JSON that a reviewer can read and a test can
# parse — no templating language, and nothing that could be mistaken for one.
render() {
  local definition="$1"
  local out="$2"
  python3 - "${definitions}/${definition}" "${out}" \
    "${gap_seconds}" "${share_threshold}" "${window_seconds}" "${frequency_seconds}" <<'PY'
import json
import sys

source, out, gap, share, window, frequency = sys.argv[1:]

with open(source, encoding="utf-8") as handle:
    document = json.load(handle)

NUMERIC = {
    "__GAP_SECONDS__": int(gap),
    "__POST_HOC_SHARE_THRESHOLD__": float(share),
    "__WINDOW_SECONDS__": int(window),
    "__FREQUENCY_SECONDS__": int(frequency),
}
# Rendered into prose rather than compared, so it is a STRING substitution.
TEXT = {
    "__GAP_SECONDS__": str(int(gap)),
    "__POST_HOC_SHARE_PERCENT__": f"{float(share) * 100:g}",
    "__WINDOW_SECONDS__": str(int(window)),
    "__FREQUENCY_SECONDS__": str(int(frequency)),
    "__POST_HOC_SHARE_THRESHOLD__": str(float(share)),
}


def substitute(node):
    """Replace every token, keeping a whole-string token NUMERIC.

    A field whose entire value is one token (a threshold, a frequency, a time
    range) must arrive as a JSON NUMBER — Honeycomb rejects a string there, and
    a quoted threshold would compare as text. A token EMBEDDED in prose is
    rendered as text instead, which is what the operator-facing description
    needs.
    """
    if isinstance(node, dict):
        return {key: substitute(value) for key, value in node.items()}
    if isinstance(node, list):
        return [substitute(value) for value in node]
    if isinstance(node, str):
        if node in NUMERIC:
            return NUMERIC[node]
        rendered = node
        for token, value in TEXT.items():
            rendered = rendered.replace(token, value)
        return rendered
    return node


payloads = document.get("payloads")
if payloads is None:
    payloads = [document["payload"]]
with open(out, "w", encoding="utf-8") as handle:
    json.dump([substitute(payload) for payload in payloads], handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

# Split a rendered payload array into one file per element, printing each path.
split_payloads() {
  local rendered="$1"
  local prefix="$2"
  python3 - "${rendered}" "${prefix}" <<'PY'
import json
import sys

rendered, prefix = sys.argv[1:]
with open(rendered, encoding="utf-8") as handle:
    payloads = json.load(handle)
for index, payload in enumerate(payloads):
    path = f"{prefix}.{index}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(path)
PY
}

# The id of an existing resource whose `field` equals `value`, or empty.
existing_id() {
  local listing="$1"
  local field="$2"
  local value="$3"
  python3 - "${listing}" "${field}" "${value}" <<'PY'
import json
import sys

listing, field, value = sys.argv[1:]
with open(listing, encoding="utf-8") as handle:
    records = json.load(handle)
if isinstance(records, dict):
    records = records.get("derived_columns") or records.get("boards") or []
for record in records:
    if isinstance(record, dict) and record.get(field) == value:
        print(record.get("id", ""))
        break
PY
}

payload_field() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$1" "$2"
}

# Create-or-update one resource, keyed on `field`. `list_url` is where the
# existing population is read from, `collection_url` is where a create POSTs,
# and an update PUTs to `<collection_url>/<id>`.
apply_resource() {
  local kind="$1"
  local payload="$2"
  local field="$3"
  local list_url="$4"
  local collection_url="$5"

  local identity
  identity="$(payload_field "${payload}" "${field}")"

  if [[ "${dry_run}" == "1" ]]; then
    printf 'DRY_RUN %s %s=%s payload:\n' "${kind}" "${field}" "${identity}"
    cat "${payload}"
    return 0
  fi

  local listing="${tmpdir}/${kind}-listing.json"
  curl_json GET "${list_url}" >"${listing}"
  local id
  id="$(existing_id "${listing}" "${field}" "${identity}")"
  if [[ -n "${id}" ]]; then
    curl_json PUT "${collection_url}/${id}" "${payload}" >/dev/null
    printf 'updated %s %s (%s=%s)\n' "${kind}" "${id}" "${field}" "${identity}"
  else
    local created="${tmpdir}/${kind}-created.json"
    curl_json POST "${collection_url}" "${payload}" >"${created}"
    printf 'created %s %s (%s=%s)\n' \
      "${kind}" "$(payload_field "${created}" id)" "${field}" "${identity}"
  fi
}

if wants derived_columns; then
  render tdd-calibration-derived-columns.json "${tmpdir}/derived-columns.json"
  while read -r payload; do
    apply_resource derived_column "${payload}" alias \
      "${api_base}/1/derived_columns/${dataset}" \
      "${api_base}/1/derived_columns/${dataset}"
  done < <(split_payloads "${tmpdir}/derived-columns.json" "${tmpdir}/derived-column")
fi

if wants board; then
  render tdd-calibration-board.json "${tmpdir}/board.json"
  while read -r payload; do
    apply_resource board "${payload}" name "${api_base}/1/boards" "${api_base}/1/boards"
  done < <(split_payloads "${tmpdir}/board.json" "${tmpdir}/board-payload")
fi

if wants trigger; then
  render tdd-calibration-trigger.json "${tmpdir}/trigger.json"
  recipient_id=""
  if [[ "${dry_run}" != "1" ]]; then
    curl_json GET "${api_base}/1/recipients" >"${tmpdir}/recipients.json"
    recipient_id="$(
      python3 - "${tmpdir}/recipients.json" "${recipient_selector}" <<'PY'
import json
import sys

path, selector = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    recipients = json.load(handle)


def redact(value):
    """Render an email so a log names the recipient without publishing it."""
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", maxsplit=1)
    if len(local) <= 2:
        return (local[0] + "***" if local else "***") + "@" + domain
    return f"{local[0]}***{local[-1]}@{domain}"


def describe(recipient):
    details = recipient.get("details") or {}
    parts = [f"id={recipient.get('id', '<missing>')}", f"type={recipient.get('type', '<missing>')}"]
    for key in ("email_address", "name", "webhook_name", "slack_channel"):
        value = details.get(key)
        if value:
            parts.append(f"{key}={redact(value) if key == 'email_address' else value}")
    return " ".join(parts)


def print_available():
    print("available Honeycomb recipients:", file=sys.stderr)
    for recipient in recipients:
        print(f"  - {describe(recipient)}", file=sys.stderr)


if not selector:
    # DISCOVER the recipient from the account rather than inventing an address:
    # a wrong address is a trigger that fires into nowhere.
    print("HONEYCOMB_OPERATOR_ALERT_RECIPIENT is required.", file=sys.stderr)
    print(
        "Set it to an existing Honeycomb recipient id, name, email address, "
        "webhook name, or Slack channel from the list below.",
        file=sys.stderr,
    )
    print_available()
    raise SystemExit(1)

for recipient in recipients:
    details = recipient.get("details") or {}
    candidates = {
        recipient.get("id"),
        recipient.get("target"),
        details.get("email_address"),
        details.get("name"),
        details.get("webhook_name"),
        details.get("slack_channel"),
    }
    if selector in candidates:
        print(recipient["id"])
        raise SystemExit(0)

print(f"no Honeycomb recipient matched {selector!r}", file=sys.stderr)
print_available()
raise SystemExit(1)
PY
    )"
  fi
  python3 - "${tmpdir}/trigger.json" "${recipient_id}" <<'PY'
import json
import sys

path, recipient_id = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    payloads = json.load(handle)
for payload in payloads:
    window = payload["query"]["time_range"]
    frequency = payload["frequency"]
    if window < frequency:
        # Honeycomb reports this as a 422 whose detail is only in the response
        # body; refuse here with a message that names the fix instead.
        print(
            f"window ({window}s) must be >= frequency ({frequency}s); raise "
            "HONEYCOMB_TDD_TRIGGER_WINDOW_SECONDS or lower "
            "HONEYCOMB_TDD_TRIGGER_FREQUENCY_SECONDS",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if recipient_id:
        payload["recipients"] = [{"id": recipient_id}]
with open(path, "w", encoding="utf-8") as handle:
    json.dump(payloads, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
  while read -r payload; do
    apply_resource trigger "${payload}" name \
      "${api_base}/1/triggers/${dataset}" \
      "${api_base}/1/triggers/${dataset}"
  done < <(split_payloads "${tmpdir}/trigger.json" "${tmpdir}/trigger-payload")
fi

printf 'done: dataset=%s resources=%s dry_run=%s\n' "${dataset}" "${resources}" "${dry_run}"
