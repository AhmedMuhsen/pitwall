#!/usr/bin/env bash
# Builds the image from this checkout and (re)starts the container on port 80. Run on the server:
#   ./deploy/deploy.sh          first deploy, and every update (pulls the latest main first)
# Safe to run again: it replaces the running container.
set -euo pipefail
cd "$(dirname "$0")/.."

git pull --ff-only
docker build -t pitwall:latest .
docker rm -f pitwall >/dev/null 2>&1 || true
# The app needs about 400 MB; the limit keeps a runaway process from taking the whole instance.
docker run -d --name pitwall --restart unless-stopped --memory 1200m -p 80:8501 pitwall:latest

echo "Waiting for the app to become healthy..."
for _ in $(seq 1 40); do
    status=$(docker inspect --format '{{.State.Health.Status}}' pitwall)
    [ "$status" = "healthy" ] && { echo "pitwall is healthy"; exit 0; }
    sleep 3
done
echo "pitwall did not become healthy; last log lines:" >&2
docker logs --tail 40 pitwall >&2
exit 1
