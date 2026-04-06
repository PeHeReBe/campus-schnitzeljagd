#!/usr/bin/env bash
set -euo pipefail

IMAGE="ghcr.io/peherebe/campus-schnitzeljagd:latest"
SERVICE="campus-schnitzeljagd"
COMPOSE_FILE="${COMPOSE_FILE:-$(dirname "$0")/docker-compose.yml}"
CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-60}"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "Compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi

while true; do
  if docker pull "$IMAGE"; then
    set +e
    CURRENT_IMAGE_ID="$(docker compose -f "$COMPOSE_FILE" images -q "$SERVICE" 2>&1)"
    COMPOSE_STATUS=$?
    set -e

    if [ $COMPOSE_STATUS -ne 0 ]; then
      echo "[$(date -Iseconds)] Could not read current service image: $CURRENT_IMAGE_ID" >&2
      CURRENT_IMAGE_ID=""
    fi

    LATEST_IMAGE_ID="$(docker image inspect "$IMAGE" --format '{{.Id}}' 2>/dev/null || true)"

    if [ -z "$CURRENT_IMAGE_ID" ]; then
      echo "[$(date -Iseconds)] Service not running or no current image; ensuring service is up..."
      docker compose -f "$COMPOSE_FILE" up -d "$SERVICE"
    elif [ -n "$LATEST_IMAGE_ID" ] && [ "$CURRENT_IMAGE_ID" != "$LATEST_IMAGE_ID" ]; then
      echo "[$(date -Iseconds)] New image detected, updating service..."
      docker compose -f "$COMPOSE_FILE" up -d "$SERVICE"
    else
      echo "[$(date -Iseconds)] No update available."
    fi
  else
    echo "[$(date -Iseconds)] Failed to pull image: $IMAGE" >&2
  fi

  sleep "$CHECK_INTERVAL_SECONDS"
done
