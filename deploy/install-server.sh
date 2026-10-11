#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/report_parser"
REPO_URL="https://github.com/bhanuroyal002/Report_Parser.git"
SERVICE="report-parser"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run this installer with sudo or as root."
    exit 1
fi

if ! command -v git >/dev/null 2>&1; then
    echo "ERROR: git is required."
    exit 1
fi

PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v "$candidate")"
        break
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    echo "ERROR: Python 3.10+ is required."
    exit 1
fi

if ! id reportparser >/dev/null 2>&1; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin reportparser
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
    mkdir -p "$(dirname "$APP_DIR")"
    git clone "$REPO_URL" "$APP_DIR"
else
    git -C "$APP_DIR" pull --ff-only
fi

cd "$APP_DIR"
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

mkdir -p data
cp -n .env.example .env || true

# Server listens on the corporate interface; team members reach it through VPN.
if grep -q '^HOST=' .env; then
    sed -i 's/^HOST=.*/HOST=0.0.0.0/' .env
else
    echo 'HOST=0.0.0.0' >> .env
fi

if grep -q '^PORT=' .env; then
    sed -i 's/^PORT=.*/PORT=8080/' .env
else
    echo 'PORT=8080' >> .env
fi

chown -R reportparser:reportparser "$APP_DIR"
install -m 0644 deploy/report-parser.service /etc/systemd/system/report-parser.service
install -m 0755 deploy/report-parser-healthcheck.sh /usr/local/sbin/report-parser-healthcheck
install -m 0644 deploy/report-parser-healthcheck.service /etc/systemd/system/report-parser-healthcheck.service
install -m 0644 deploy/report-parser-healthcheck.timer /etc/systemd/system/report-parser-healthcheck.timer
mkdir -p /var/lib/report-parser-monitoring
chmod 0750 /var/lib/report-parser-monitoring
systemctl daemon-reload
systemctl enable --now "$SERVICE" report-parser-healthcheck.timer

systemctl --no-pager --full status "$SERVICE" || true

echo
echo "Report Parser should now be available at: http://<server-ip>:8080"
