#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cp "$ROOT_DIR/.env.demo" "$ROOT_DIR/.env"
echo "Demo mode restored."
echo "Current mode: BigQuery demo tables + rule_based SQL planner."
