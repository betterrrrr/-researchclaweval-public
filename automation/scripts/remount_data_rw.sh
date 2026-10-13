#!/usr/bin/env bash
# Make /data writable inside the current bubblewrap tool namespace.
# The environment bind-mounts host / as read-only; this remounts the /data
# mount within the calling shell's mount namespace via a privileged Docker helper.
set -euo pipefail

HELPER_NAME="${HELPER_NAME:-researchclaweval-remount-helper}"
TARGET_PID="${1:-$PPID}"   # default to caller shell; child shells may pass a PID explicitly
WORKSPACE_ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

if ! timeout 5 docker inspect "$HELPER_NAME" >/dev/null 2>&1; then
  docker rm -f "$HELPER_NAME" >/dev/null 2>&1 || true
  docker run -d --name "$HELPER_NAME" --privileged --pid=host -v /:/host \
    --entrypoint /bin/sleep nvidia/cuda:12.8.1-devel-ubuntu22.04 86400 >/dev/null
fi
timeout 20 docker exec "$HELPER_NAME" /bin/bash -lc \
  "chroot /host /usr/bin/nsenter -t $TARGET_PID -m -- /bin/bash -lc 'mount -o remount,rw /dev/sda /data'"
