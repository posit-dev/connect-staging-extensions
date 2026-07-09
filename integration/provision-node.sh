#!/usr/bin/env bash
# Install a Node.js runtime into a running Connect container and restart it, so
# Connect can run Node.js content. Published Connect images ship no Node runtime,
# so this is needed for both the local `make` harness (nodejs-integration-test.sh)
# and the CI integration-test action; keeping it here means the download / copy /
# enable / restart logic lives in one place.
#
# Usage: provision-node.sh <container-id> <connect-server-url> [host-gcfg-path]
#   host-gcfg-path: the host path of the Connect config file mounted into the
#     container. Pass it when Connect was started with a mounted config (CI): that
#     mount is read-only from inside the container, so the [NodeJs] section must be
#     appended to the host file. Omit it when Connect was started without a mounted
#     config (local `make`): then the container's own config is edited directly.
#
# NODE_VERSION (env, default 24.14.0) picks the Node release to install.
set -euo pipefail

CID="${1:?container id required}"
SERVER="${2:?connect server url required}"
HOST_GCFG="${3:-}"
NODE_VERSION="${NODE_VERSION:-24.14.0}"

# Match the Node.js build to the container's architecture (arm64 on Apple Silicon,
# x64 on CI runners); a mismatched build can't execute.
case "$(docker exec "$CID" uname -m)" in
  x86_64) NODE_ARCH="x64" ;;
  aarch64) NODE_ARCH="arm64" ;;
  *) echo "Unsupported container architecture"; exit 1 ;;
esac

# Download and unpack Node on this host, then copy it into the container (the
# Connect images do not reliably include curl/tar/xz).
curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz" -o /tmp/node.tar.xz
rm -rf "/tmp/node/${NODE_VERSION}"
mkdir -p "/tmp/node/${NODE_VERSION}"
tar -xJf /tmp/node.tar.xz -C "/tmp/node/${NODE_VERSION}" --strip-components=1
docker exec "$CID" mkdir -p /opt/node
docker cp "/tmp/node/${NODE_VERSION}" "$CID:/opt/node/${NODE_VERSION}"

# Turn Node on in Connect's config, then restart so it loads. Connect validates the
# configured executable at startup, so Node must be in place before the restart.
if [ -n "$HOST_GCFG" ]; then
  # CI: the mounted config is read-only inside the container; edit the host file.
  printf '\n[NodeJs]\nEnabled = true\nExecutable = /opt/node/%s/bin/node\n' "$NODE_VERSION" >> "$HOST_GCFG"
else
  # local make: no mounted config; edit the container's own config.
  docker exec "$CID" sh -c \
    "printf '\n[NodeJs]\nEnabled = true\nExecutable = /opt/node/${NODE_VERSION}/bin/node\n' >> /etc/rstudio-connect/rstudio-connect.gcfg"
fi
docker restart "$CID" >/dev/null

echo "Waiting for Connect to restart with Node enabled..."
for _ in $(seq 1 45); do
  if curl -fsS "${SERVER}/__api__/server_settings" >/dev/null 2>&1; then
    exit 0
  fi
  sleep 2
done
echo "Connect did not come back up after enabling Node:"
docker logs "$CID" 2>&1 | tail -60
exit 1
