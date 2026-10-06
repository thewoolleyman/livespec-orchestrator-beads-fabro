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
# THE BOARD IS BUILT IN THREE STEPS, not one POST. The current Create a Board
# API takes a `type: flexible` board whose query panels reference PERSISTED
# query identifiers; it has no inline-query form, so the committed definition's
# per-panel query SPECIFICATIONS are first materialized through the Queries API
# and named by QUERY ANNOTATIONS, and only then does the board itself reference
# the identifiers that came back. Panel idempotence cannot use the same
# lookup-by-identity trick the three resources above do, because a Query has no
# list, get or update verb at all: the annotation carries the caption AND a
# digest of the specification it names, so an unchanged digest reuses the
# persisted query while a changed one persists a fresh query and re-points the
# SAME annotation. See `board_panel_plan` and the board definition's
# `panel_identity_key`.
#
# SECRETS NEVER REACH ARGV OR THE LOG. The API key is read from the
# environment and passed to curl only through a header; no `set -x`, no echo
# of any header, and the recipient lister redacts email local-parts (the same
# discipline provision-honeycomb-run-turn-trigger.sh established). A FAILURE
# diagnostic quotes the response body, so `sanitize` replaces the key in
# anything quoted — a server that echoed the credential back must not be able
# to route it into the log.
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

# The marker the board's query annotations carry in front of their query
# specification digest. NOT configurable: it is the only observable record of
# which specification a persisted query id holds (a Query has no list, get or
# update verb), so a run that changed it would stop recognising every panel it
# had already provisioned and silently rebuild the whole set.
fingerprint_marker="query-spec-fingerprint="

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

# Print a captured file with the configured API key replaced. The secret is
# read from the ENVIRONMENT inside python, never passed as an argument, exactly
# as curl receives it only through a header. The redaction exists because the
# failure report below QUOTES a response body: a server that echoed the
# credential back would otherwise route it straight into the operator's log.
sanitize() {
  python3 - "$1" <<'PY'
import os
import sys

path = sys.argv[1]
secret = (
    os.environ.get("HONEYCOMB_CONFIG_KEY_LIVESPEC")
    or os.environ.get("HONEYCOMB_TEAM_KEY_LIVESPEC")
    or ""
)
try:
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
except FileNotFoundError:
    text = ""
if secret:
    text = text.replace(secret, "***REDACTED***")
print(text.strip() or "<empty>")
PY
}

# One HTTP call, named by the RESOURCE it is acting on. On success the response
# body goes to stdout, exactly as a caller expects.
#
# On failure the resource, the request, the status and the SANITIZED response
# body reach stderr BEFORE the script unwinds. That ordering is the whole
# repair: the previous version sent every response into a temp file under the
# cleanup trap or into /dev/null, so a real rejection — measured against the
# live API as `unknown column name: tdd.first_product_write_before_red` — left
# the operator with nothing but `curl: (22) The requested URL returned error:
# 400` and deleted the one artifact that said what was wrong.
api_call() {
  local label="$1"
  local method="$2"
  local url="$3"
  local data_arg=()
  if [[ "$#" -eq 4 ]]; then
    data_arg=(--data @"$4")
  fi
  local body="${tmpdir}/api-response-body"
  local curl_stderr="${tmpdir}/api-curl-stderr"
  local status
  if status="$(
    curl --fail-with-body --silent --show-error \
      --request "${method}" \
      --url "${url}" \
      --header "X-Honeycomb-Team: ${api_key}" \
      --header "Content-Type: application/json" \
      "${data_arg[@]}" \
      --output "${body}" \
      --write-out '%{http_code}' 2>"${curl_stderr}"
  )"; then
    cat "${body}"
    return 0
  fi
  {
    printf 'Honeycomb API request FAILED\n'
    printf '  resource: %s\n' "${label}"
    printf '  request: %s %s\n' "${method}" "${url}"
    printf '  http status: %s\n' "${status:-<none>}"
    printf '  response: %s\n' "$(sanitize "${body}")"
    printf '  curl: %s\n' "$(sanitize "${curl_stderr}")"
  } >&2
  exit 1
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

# --- board panels ----------------------------------------------------------
#
# The current Create a Board API takes a FLEXIBLE board whose query panels
# reference PERSISTED query identifiers; it has no inline-query form at all.
# The committed definition therefore carries each panel's query SPECIFICATION,
# and the three helpers below turn those specifications into the real panels:
# `board_panel_plan` writes one spec file per panel, `annotation_payload`
# builds the query annotation that carries the panel's caption, and
# `assemble_board` substitutes the resolved identifiers back into the board.

# Write each committed panel's query specification to its own file and print
# one planning row per panel:
#
#   board<TAB>panel<TAB>fingerprint<TAB>caption<TAB>annotation_id<TAB>query_id<TAB>spec_path
#
# `annotation_id` and `query_id` are the identifiers to REUSE, or the literal
# `-` when the panel needs a fresh one. A sentinel rather than an empty field
# because tab is an IFS WHITESPACE character, so bash's `read` folds
# consecutive tabs into one delimiter and an empty field would shift every
# later column left. `annotations` is the query-annotation listing, or `-` in
# dry-run mode, where nothing may be read from the network.
#
# Reuse is keyed on the caption, which is the annotation `name`, and GATED on
# the fingerprint: a Query has no list, get or update verb, so the digest the
# provisioner wrote into the annotation description is the only observable
# record of which specification a persisted query id holds. An unchanged
# fingerprint reuses the query; a changed one leaves `query_id` empty so a
# fresh query is persisted and the SAME annotation is re-pointed at it. Reusing
# unconditionally would leave a moved specification rendering the stale query
# forever, which an idempotence rule would otherwise hide.
board_panel_plan() {
  local rendered="$1"
  local prefix="$2"
  local annotations="$3"
  python3 - "${rendered}" "${prefix}" "${annotations}" "${fingerprint_marker}" <<'PY'
import hashlib
import json
import sys

rendered, prefix, annotations_path, marker = sys.argv[1:]

with open(rendered, encoding="utf-8") as handle:
    payloads = json.load(handle)

existing = {}
if annotations_path != "-":
    with open(annotations_path, encoding="utf-8") as handle:
        listing = json.load(handle)
    if isinstance(listing, dict):
        listing = listing.get("query_annotations") or []
    for record in listing:
        if isinstance(record, dict) and record.get("name"):
            existing[record["name"]] = record

for board_index, payload in enumerate(payloads):
    for index, panel in enumerate(payload["panels"]):
        specification = panel["query_panel"]["query"]
        caption = panel["query_panel"]["caption"]
        canonical = json.dumps(specification, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        path = f"{prefix}.{board_index}.{index}.query.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(specification, handle, indent=2, sort_keys=True)
            handle.write("\n")
        record = existing.get(caption) or {}
        annotation_id = record.get("id") or ""
        query_id = record.get("query_id") or ""
        if marker + fingerprint not in (record.get("description") or ""):
            query_id = ""
        print(
            "\t".join(
                (
                    str(board_index),
                    str(index),
                    fingerprint,
                    caption,
                    annotation_id or "-",
                    query_id or "-",
                    path,
                )
            )
        )
PY
}

# Build the query annotation that names one panel's persisted query. The
# annotation `name` IS the committed caption: a flexible board renders the
# annotation as the panel's title, so carrying the caption here is what keeps
# the operator-facing labels the legacy board had. The `description` carries
# the specification fingerprint, which is what makes the next run's reuse
# decision observable.
annotation_payload() {
  local caption="$1"
  local fingerprint="$2"
  local query_id="$3"
  local out="$4"
  python3 - "${caption}" "${fingerprint}" "${query_id}" "${out}" "${fingerprint_marker}" <<'PY'
import json
import sys

caption, fingerprint, query_id, out, marker = sys.argv[1:]
payload = {
    "name": caption,
    "description": (
        "Provisioned from orchestrator-image/honeycomb/tdd-calibration-board.json "
        f"(livespec work-item bd-ib-3h5vfq). {marker}{fingerprint}"
    ),
    "query_id": query_id,
}
with open(out, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

# Replace every panel's committed query SPECIFICATION with the identifiers the
# API handed back, which is the shape /1/boards accepts. `resolved` carries
# `board<TAB>panel<TAB>query_id<TAB>annotation_id` rows.
assemble_board() {
  local rendered="$1"
  local resolved="$2"
  local out="$3"
  python3 - "${rendered}" "${resolved}" "${out}" <<'PY'
import json
import sys

rendered, resolved, out = sys.argv[1:]

identifiers = {}
with open(resolved, encoding="utf-8") as handle:
    for line in handle:
        if not line.strip():
            continue
        board_index, index, query_id, annotation_id = line.rstrip("\n").split("\t")
        identifiers[(int(board_index), int(index))] = (query_id, annotation_id)

with open(rendered, encoding="utf-8") as handle:
    payloads = json.load(handle)

for board_index, payload in enumerate(payloads):
    for index, panel in enumerate(payload["panels"]):
        query_id, annotation_id = identifiers[(board_index, index)]
        panel_query = panel["query_panel"]
        # `query` and `caption` are inputs to the provisioner, not fields the
        # board resource has: the specification becomes a Query and the caption
        # becomes that query's annotation.
        del panel_query["query"]
        del panel_query["caption"]
        panel_query["query_id"] = query_id
        panel_query["query_annotation_id"] = annotation_id

with open(out, "w", encoding="utf-8") as handle:
    json.dump(payloads, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

# Persist every panel's query and annotation, then apply the assembled board.
apply_board() {
  local rendered="$1"
  local prefix="$2"
  local plan="${prefix}.plan.tsv"
  local resolved="${prefix}.resolved.tsv"
  local annotations="-"
  if [[ "${dry_run}" != "1" ]]; then
    annotations="${prefix}.annotations.json"
    api_call query_annotation GET "${api_base}/1/query_annotations/${dataset}" \
      >"${annotations}"
  fi
  board_panel_plan "${rendered}" "${prefix}" "${annotations}" >"${plan}"
  : >"${resolved}"
  local board panel fingerprint caption annotation_id query_id spec
  while IFS=$'\t' read -r board panel fingerprint caption annotation_id query_id spec; do
    local annotation="${prefix}.${board}.${panel}.annotation.json"
    if [[ "${annotation_id}" == "-" ]]; then
      annotation_id=""
    fi
    if [[ "${query_id}" == "-" ]]; then
      query_id=""
    fi
    if [[ "${dry_run}" == "1" ]]; then
      query_id="<query-id-assigned-at-apply>"
      annotation_id="<query-annotation-id-assigned-at-apply>"
      printf 'DRY_RUN query panel=%s caption=%s payload:\n' "${panel}" "${caption}"
      cat "${spec}"
      annotation_payload "${caption}" "${fingerprint}" "${query_id}" "${annotation}"
      printf 'DRY_RUN query_annotation panel=%s name=%s payload:\n' "${panel}" "${caption}"
      cat "${annotation}"
    else
      if [[ -n "${query_id}" ]]; then
        printf 'reused query %s (panel=%s)\n' "${query_id}" "${panel}"
      else
        local created_query="${prefix}.${board}.${panel}.query-created.json"
        api_call query POST "${api_base}/1/queries/${dataset}" "${spec}" >"${created_query}"
        query_id="$(payload_field "${created_query}" id)"
        printf 'created query %s (panel=%s)\n' "${query_id}" "${panel}"
      fi
      annotation_payload "${caption}" "${fingerprint}" "${query_id}" "${annotation}"
      if [[ -n "${annotation_id}" ]]; then
        api_call query_annotation PUT "${api_base}/1/query_annotations/${dataset}/${annotation_id}" \
          "${annotation}" >/dev/null
        printf 'updated query_annotation %s (panel=%s)\n' "${annotation_id}" "${panel}"
      else
        local created_annotation="${prefix}.${board}.${panel}.annotation-created.json"
        api_call query_annotation POST "${api_base}/1/query_annotations/${dataset}" "${annotation}" \
          >"${created_annotation}"
        annotation_id="$(payload_field "${created_annotation}" id)"
        printf 'created query_annotation %s (panel=%s)\n' "${annotation_id}" "${panel}"
      fi
    fi
    printf '%s\t%s\t%s\t%s\n' "${board}" "${panel}" "${query_id}" "${annotation_id}" >>"${resolved}"
  done <"${plan}"
  assemble_board "${rendered}" "${resolved}" "${prefix}.assembled.json"
  while read -r payload; do
    apply_resource board "${payload}" name "${api_base}/1/boards" "${api_base}/1/boards"
  done < <(split_payloads "${prefix}.assembled.json" "${prefix}-payload")
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
  api_call "${kind}" GET "${list_url}" >"${listing}"
  local id
  id="$(existing_id "${listing}" "${field}" "${identity}")"
  if [[ -n "${id}" ]]; then
    api_call "${kind}" PUT "${collection_url}/${id}" "${payload}" >/dev/null
    printf 'updated %s %s (%s=%s)\n' "${kind}" "${id}" "${field}" "${identity}"
  else
    local created="${tmpdir}/${kind}-created.json"
    api_call "${kind}" POST "${collection_url}" "${payload}" >"${created}"
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
  apply_board "${tmpdir}/board.json" "${tmpdir}/board-panel"
fi

if wants trigger; then
  render tdd-calibration-trigger.json "${tmpdir}/trigger.json"
  recipient_id=""
  if [[ "${dry_run}" != "1" ]]; then
    api_call recipient GET "${api_base}/1/recipients" >"${tmpdir}/recipients.json"
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
