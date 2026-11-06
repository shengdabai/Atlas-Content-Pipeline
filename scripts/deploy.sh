#!/bin/bash
# deploy.sh — Automated deploy script for Atlas Content Pipeline
set -euo pipefail

PROJECT_NAME="atlas-content-pipeline"
BUILD_ENV=${1:-docker}

echo "🚀 Deploying ${PROJECT_NAME} (${BUILD_ENV})..."

if [ "${BUILD_ENV}" = "docker" ]; then
  TAG="${DOCKER_TAG:-${PROJECT_NAME}:latest}"
  echo "Building Docker image: ${TAG}..."
  docker build -t "${TAG}" .
  echo "Running smoke test..."
  SMOKE_OUTPUT=$(docker run --rm -i "${TAG}" --source /dev/stdin \
    --dry-run --selection first --limit 1 --provider heuristic <<'MARKDOWN'
## 1. Atlas smoke test {#note-1}

Synthetic input for the dry-run smoke test.
MARKDOWN
  )
  if printf '%s\n' "${SMOKE_OUTPUT}" | grep -Fq '"title": "Atlas smoke test",'; then
    echo "✅ Smoke test passed"
  else
    echo "❌ Smoke test failed: dry-run did not return the synthetic note" >&2
    exit 1
  fi
  echo "📦 Image ready: ${TAG}"

else
  echo "Unknown: ${BUILD_ENV}. Use 'docker'."
  exit 1
fi
