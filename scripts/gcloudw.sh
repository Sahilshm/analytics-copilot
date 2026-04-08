#!/bin/zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
GCLOUD_BIN="/opt/homebrew/Caskroom/gcloud-cli/563.0.0/google-cloud-sdk/bin/gcloud"
DEFAULT_CONFIG_DIR="$HOME/.config/gcloud"
LOCAL_CONFIG_DIR="$ROOT_DIR/.gcloud"

if [[ -n "${CLOUDSDK_CONFIG:-}" ]]; then
  CONFIG_DIR="$CLOUDSDK_CONFIG"
elif [[ -d "$DEFAULT_CONFIG_DIR" ]]; then
  CONFIG_DIR="$DEFAULT_CONFIG_DIR"
else
  CONFIG_DIR="$LOCAL_CONFIG_DIR"
fi

export CLOUDSDK_CONFIG="$CONFIG_DIR"
mkdir -p "$CLOUDSDK_CONFIG"
exec "$GCLOUD_BIN" "$@"
