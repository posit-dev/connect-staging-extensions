#!/usr/bin/env bash
# Run the integration test for a Node.js extension against a local Connect.
#
# Published Connect images do not include a Node.js runtime, so a plain
# `with-connect` run cannot execute Node.js content. This script starts Connect,
# provisions Node into the running container (via provision-node.sh, shared with
# the CI action), and runs the extension's integration test against it.
#
# Usage: nodejs-integration-test.sh <connect-version> <extension-name>
set -euo pipefail

CONNECT_VERSION="${1:?connect version required}"
EXTENSION_NAME="${2:?extension name required}"

: "${WITH_CONNECT:=with-connect}"
: "${LICENSE_FILE:=./license.lic}"
: "${UV:=uv}"
: "${PYTEST_ARGS:=-s}"

cd "$(dirname "$0")"
mkdir -p reports logs

# Start Connect without Node. with-connect prints CONNECT_API_KEY,
# CONNECT_SERVER, and CONTAINER_ID for us to eval into this shell. Capture first so
# a with-connect failure surfaces here, instead of eval'ing "" and failing later
# with a misleading error.
CONNECT_API_KEY=""
CONNECT_SERVER=""
CONTAINER_ID=""
if ! with_connect_env="$("$WITH_CONNECT" --version "$CONNECT_VERSION" --license "$LICENSE_FILE" \
  -e CONNECT_SERVER_EMAILPROVIDER=None \
  -e CONNECT_APPLICATIONS_PACKAGEAUDITINGENABLED=true)"; then
  echo "Error: with-connect failed to start Connect $CONNECT_VERSION" >&2
  exit 1
fi
eval "$with_connect_env"

# Always stop Connect on exit, however we exit.
trap '"$WITH_CONNECT" --stop "$CONTAINER_ID" >/dev/null 2>&1 || true' EXIT

# Install a Node.js runtime into the container and restart Connect so it loads.
# The provisioning is shared with the CI action via provision-node.sh. No mounted
# config here (with-connect was started without --config), so it edits the
# container's own config directly.
bash provision-node.sh "$CONTAINER_ID" "$CONNECT_SERVER"

# Run the tests against the provisioned Connect.
export CONNECT_SERVER CONNECT_API_KEY
"$UV" run tests/posit/connect/set_bootstrap_admin_email.py
EXTENSION_NAME="$EXTENSION_NAME" BUNDLE_BASE_PATH="$PWD/bundles" \
  "$UV" run pytest $PYTEST_ARGS --junit-xml="./reports/${CONNECT_VERSION}.xml" 2>&1 \
  | tee "./logs/${CONNECT_VERSION}.log"
