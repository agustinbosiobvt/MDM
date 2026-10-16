#!/bin/sh
# Run gitleaks (pinned image) against this repo.
#   scripts/gitleaks.sh staged   - staged changes (pre-commit hook)
#   scripts/gitleaks.sh history  - all commits
#   scripts/gitleaks.sh tree     - working tree (ignored paths allowlisted in .gitleaks.toml)
# Fails closed: if Docker isn't available, nothing is scanned and the exit code is 1.
set -eu
IMAGE=zricethezav/gitleaks:v8.28.0
ROOT=$(git rev-parse --show-toplevel)
MODE=${1:-staged}

if ! docker info >/dev/null 2>&1; then
  echo "gitleaks: Docker is not running, so the secrets scan cannot run. Start Docker Desktop and retry." >&2
  exit 1
fi

case "$MODE" in
  staged)  CMD="gitleaks git /repo --pre-commit --staged" ;;
  history) CMD="gitleaks git /repo" ;;
  tree)    CMD="gitleaks dir /repo" ;;
  *) echo "usage: $0 staged|history|tree" >&2; exit 2 ;;
esac

# The repo is owned by the host user; tell git inside the container it's safe.
MSYS_NO_PATHCONV=1 docker run --rm -v "$ROOT:/repo" --entrypoint sh "$IMAGE" -c \
  "git config --global --add safe.directory /repo && $CMD --config /repo/.gitleaks.toml --no-banner --redact"
