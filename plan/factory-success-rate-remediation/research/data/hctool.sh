#!/bin/sh
# usage: hctool.sh <tool_name> <arguments-json>
# Requires HONEYCOMB_MCP_API_KEY_LIVESPEC in env (run under with-livespec-env.sh).
# Prints the tool's result text (already-unwrapped MCP content) as JSON when possible.
K="$HONEYCOMB_MCP_API_KEY_LIVESPEC"
tool="$1"; args="$2"
body=$(printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"%s","arguments":%s}}' "$tool" "$args")
resp=$(curl -s \
  -H "Authorization: Bearer $K" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -X POST https://mcp.honeycomb.io/mcp \
  -d "$body" | sed -n 's/^data: //p')
# Try to pull result.content[0].text (the payload), else dump raw
echo "$resp" | jq -r 'if .result.content then (.result.content[].text) elif .error then ("ERROR: " + (.error|tostring)) else tostring end' 2>/dev/null || echo "$resp"
