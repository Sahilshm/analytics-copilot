#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cp "$ROOT_DIR/.env.paused" "$ROOT_DIR/.env"
echo "Project paused."
echo "Current mode: local low-cost mode (rule_based + demo warehouse)."
