#!/bin/sh
# docker-entrypoint.sh
#
# Runs npm install before starting the dev server so that node_modules
# is always in sync with package.json — even when the anonymous Docker
# volume (/app/node_modules) is stale from a previous container run.
#
# Why this is needed:
#   docker-compose mounts an anonymous volume at /app/node_modules to
#   prevent the host bind-mount (./frontend:/app) from wiping out the
#   image's node_modules. However, Docker never re-seeds an existing
#   anonymous volume from the image layer — so after package.json changes
#   and an image rebuild, the old volume wins and the new packages are
#   missing.
#
#   Running `npm install` here is cheap: if node_modules is already
#   correct it finishes in a few seconds; if packages are missing it
#   installs only the delta.

set -e

echo "[entrypoint] Syncing node_modules with package.json..."
npm install

echo "[entrypoint] Starting dev server..."
exec "$@"
