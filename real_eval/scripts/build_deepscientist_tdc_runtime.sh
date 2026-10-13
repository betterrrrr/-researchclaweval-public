#!/usr/bin/env bash
set -euo pipefail

ROOT="${RESEARCHCLAWEVAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
IMAGE="${DEEPSCIENTIST_TDC_RUNTIME_IMAGE:-deepscientist:tdc-runtime-ready}"

docker build \
  --pull=false \
  --tag "$IMAGE" \
  --file "$ROOT/real_eval/docker/deepscientist_tdc_runtime.Dockerfile" \
  "$ROOT/real_eval/docker"
