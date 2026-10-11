#!/usr/bin/env bash
set -uo pipefail

HEALTH_URL="http://127.0.0.1:8080/healthz"
STATE_DIR="/var/lib/report-parser-monitoring"
STATE_FILE="$STATE_DIR/last-status"
mkdir -p "$STATE_DIR"
chmod 0750 "$STATE_DIR"

send_notification() {
    local message="$1"
    if [[ -z "${REPORT_PARSER_WEBHOOK_URL:-}" ]]; then
        echo "$message (webhook not configured)"
        return 0
    fi

    local payload
    payload="$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1]}))' "$message")"
    if ! curl --silent --show-error --fail --max-time 8 \
        -H 'Content-Type: application/json' \
        --data-binary "$payload" "$REPORT_PARSER_WEBHOOK_URL" >/dev/null; then
        echo "WARNING: health notification webhook request failed."
    fi
}

if curl --fail --silent --show-error --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then
    current="healthy"
else
    current="unhealthy"
fi

previous="$(cat "$STATE_FILE" 2>/dev/null || true)"
if [[ "$current" != "$previous" ]]; then
    if [[ "$current" == "unhealthy" ]]; then
        send_notification "ALERT: Report Parser health check failed at $(date -Is). Endpoint: $HEALTH_URL"
    elif [[ "$previous" == "unhealthy" ]]; then
        send_notification "RECOVERY: Report Parser is healthy again at $(date -Is)."
    fi
    printf '%s\n' "$current" > "$STATE_FILE.tmp"
    mv "$STATE_FILE.tmp" "$STATE_FILE"
fi

echo "Report Parser health status: $current"
