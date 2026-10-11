#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then echo "ERROR: run as root."; exit 1; fi
if [[ $# -ne 1 ]]; then echo "Usage: $0 /path/to/report-parser-<build>.tar.gz"; exit 2; fi
ARTIFACT="$1"
APP_DIR="/opt/report_parser"
SERVICE="report-parser"
CONTAINER="report-parser-container"
BUILD_ID="$(basename "$ARTIFACT" | sed -E 's/^report-parser-([0-9]+)[.]tar[.]gz$/\1/')"
IMAGE="report-parser:${BUILD_ID}"
TMP_DIR="$(mktemp -d /tmp/report-parser-deploy.XXXXXX)"
OLD_IMAGE=""
HAD_CONTAINER=0
SERVICE_WAS_ACTIVE=0
trap 'rm -rf "$TMP_DIR"' EXIT

[[ -f "$ARTIFACT" ]] || { echo "ERROR: artifact not found: $ARTIFACT"; exit 3; }
case "$ARTIFACT" in */report-parser-*.tar.gz) ;; *) echo "ERROR: unexpected artifact name: $ARTIFACT"; exit 4;; esac
command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker is required."; exit 5; }
docker info >/dev/null
tar -xzf "$ARTIFACT" -C "$TMP_DIR"

for required in app.py parser.py history.py report_builder.py requirements.txt gunicorn.conf.py Dockerfile docker-compose.yml deploy/report-parser-healthcheck.sh deploy/report-parser-healthcheck.service deploy/report-parser-healthcheck.timer; do
    [[ -f "$TMP_DIR/$required" ]] || { echo "ERROR: artifact is missing $required"; exit 6; }
done

mkdir -p "$APP_DIR/data"
rsync -a --delete --exclude='.env' --exclude='data/' --exclude='.venv/' --exclude='.git/' "$TMP_DIR/" "$APP_DIR/"
chown -R 10001:10001 "$APP_DIR/data"

if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
    HAD_CONTAINER=1
    OLD_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$CONTAINER")"
fi
if systemctl is-active --quiet "$SERVICE"; then SERVICE_WAS_ACTIVE=1; fi

echo "Building $IMAGE; unchanged dependency layers will use Docker cache."
docker build --pull -t "$IMAGE" "$APP_DIR"

install -m 0755 "$TMP_DIR/deploy/report-parser-healthcheck.sh" /usr/local/sbin/report-parser-healthcheck
install -m 0644 "$TMP_DIR/deploy/report-parser-healthcheck.service" /etc/systemd/system/report-parser-healthcheck.service
install -m 0644 "$TMP_DIR/deploy/report-parser-healthcheck.timer" /etc/systemd/system/report-parser-healthcheck.timer
mkdir -p /var/lib/report-parser-monitoring
chmod 0750 /var/lib/report-parser-monitoring
systemctl daemon-reload
systemctl enable --now report-parser-healthcheck.timer

systemctl stop "$SERVICE" || true
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
start_container() {
    local image="$1"
    local -a env_args=()
    if [[ -f "$APP_DIR/.env" ]]; then
        env_args+=(--env-file "$APP_DIR/.env")
    fi
    docker run -d --name "$CONTAINER" --restart unless-stopped --publish 8080:8080 \
        "${env_args[@]}" \
        --env HOST=0.0.0.0 --env PORT=8080 \
        --env DATABASE_PATH=/app/data/gct_report_parser.db \
        --volume "$APP_DIR/data:/app/data" "$image"
}
rollback() {
    echo "Deployment failed; attempting rollback."
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    if [[ "$HAD_CONTAINER" -eq 1 && -n "$OLD_IMAGE" ]]; then
        start_container "$OLD_IMAGE" || true
    elif [[ "$SERVICE_WAS_ACTIVE" -eq 1 ]]; then
        systemctl start "$SERVICE" || true
    fi
}
if ! start_container "$IMAGE"; then
    rollback
    exit 7
fi

healthy=0
for attempt in $(seq 1 20); do
    if curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8080/healthz >/dev/null; then healthy=1; break; fi
    sleep 3
done
if [[ "$healthy" -ne 1 ]]; then
    docker logs --tail 80 "$CONTAINER" || true
    rollback
    exit 8
fi

echo "Docker deployment completed: image=$IMAGE container=$CONTAINER"
docker ps --filter "name=$CONTAINER"
