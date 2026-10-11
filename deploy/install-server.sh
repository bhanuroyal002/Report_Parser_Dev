#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/report_parser"
REPO_URL="https://github.com/bhanuroyal002/Report_Parser.git"
SERVICE="report-parser"
CONTAINER="report-parser-container"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Run this installer with sudo or as root."
    exit 1
fi
for tool in git docker rsync curl; do
    command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: $tool is required."; exit 1; }
done
docker info >/dev/null

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
mkdir -p data
cp -n .env.example .env || true
if grep -q '^HOST=' .env; then sed -i 's/^HOST=.*/HOST=0.0.0.0/' .env; else echo 'HOST=0.0.0.0' >> .env; fi
if grep -q '^PORT=' .env; then sed -i 's/^PORT=.*/PORT=8080/' .env; else echo 'PORT=8080' >> .env; fi
chown -R 10001:10001 data

install -m 0755 deploy/report-parser-healthcheck.sh /usr/local/sbin/report-parser-healthcheck
install -m 0644 deploy/report-parser-healthcheck.service /etc/systemd/system/report-parser-healthcheck.service
install -m 0644 deploy/report-parser-healthcheck.timer /etc/systemd/system/report-parser-healthcheck.timer
mkdir -p /var/lib/report-parser-monitoring
chmod 0750 /var/lib/report-parser-monitoring
systemctl daemon-reload
systemctl enable --now report-parser-healthcheck.timer

docker build --pull -t report-parser:initial .
systemctl stop "$SERVICE" || true
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" --restart unless-stopped --publish 8080:8080 \
    --env HOST=0.0.0.0 --env PORT=8080 \
    --env DATABASE_PATH=/app/data/gct_report_parser.db \
    --volume "$APP_DIR/data:/app/data" report-parser:initial

for attempt in $(seq 1 20); do
    if curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8080/healthz >/dev/null; then
        docker ps --filter "name=$CONTAINER"
        echo "Report Parser Docker deployment is healthy at http://<server-ip>:8080"
        exit 0
    fi
    sleep 3
done

docker logs --tail 80 "$CONTAINER" || true
echo "ERROR: Docker deployment did not pass health check."
exit 1
