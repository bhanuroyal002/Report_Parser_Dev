#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: this deployment helper must run as root."
    exit 1
fi

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 /path/to/report-parser-<build>.tar.gz"
    exit 2
fi

ARTIFACT="$1"
APP_DIR="/opt/report_parser"
SERVICE="report-parser"

if [[ ! -f "$ARTIFACT" ]]; then
    echo "ERROR: artifact not found: $ARTIFACT"
    exit 3
fi

case "$ARTIFACT" in
    */report-parser-*.tar.gz) ;;
    *)
        echo "ERROR: unexpected artifact name: $ARTIFACT"
        exit 4
        ;;
esac

TMP_DIR="$(mktemp -d /tmp/report-parser-deploy.XXXXXX)"
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

tar -xzf "$ARTIFACT" -C "$TMP_DIR"

for required in app.py parser.py history.py report_builder.py requirements.txt gunicorn.conf.py deploy/report-parser-healthcheck.sh deploy/report-parser-healthcheck.service deploy/report-parser-healthcheck.timer; do
    if [[ ! -f "$TMP_DIR/$required" ]]; then
        echo "ERROR: deployment artifact is missing $required"
        exit 5
    fi
done

mkdir -p "$APP_DIR/data"

rsync -a --delete \
    --exclude='.env' \
    --exclude='data/' \
    --exclude='.venv/' \
    --exclude='.git/' \
    "$TMP_DIR/" "$APP_DIR/"

if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
    python3 -m venv "$APP_DIR/.venv"
fi

"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R reportparser:reportparser "$APP_DIR"

systemctl restart "$SERVICE"
systemctl is-active --quiet "$SERVICE"

echo "Deployment completed: $APP_DIR"
