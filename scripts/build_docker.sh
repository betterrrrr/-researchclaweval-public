#!/usr/bin/env bash
# ============================================================================
# build_docker.sh — Build Docker images for all frameworks
#
# Usage:
#   bash scripts/build_docker.sh              # Build all buildable images
#   bash scripts/build_docker.sh 01 04        # Build specific frameworks only
#   bash scripts/build_docker.sh --all        # Build all 7 frameworks
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ---- Framework images ----
# Format: "name|Dockerfile|image_tag|context_dir"
declare -A IMAGES
IMAGES["01"]="AI-Researcher|AI-Researcher/docker/Dockerfile|ai-researcher:runtime-ready|AI-Researcher"
IMAGES["01-exec"]="AI-Researcher (exec)|AI-Researcher/docker/Dockerfile|ai-researcher-exec:runtime-ready|AI-Researcher"
# NOTE: 02 points at a Dockerfile the upstream repository does not ship. It is
# kept for reference only and will fail until that image has a public recipe.
IMAGES["02"]="AI-Scientist-v2|AI-Scientist-v2/Dockerfile|ai-scientist-v2:runtime-ready|AI-Scientist-v2"
IMAGES["04"]="AutoResearchClaw|AutoResearchClaw/researchclaw/docker/Dockerfile|autoresearchclaw:runtime-ready|AutoResearchClaw"
IMAGES["04-oc"]="AutoResearchClaw (opencode overlay)|real_eval/docker/autoresearchclaw_opencode_runtime.Dockerfile|autoresearchclaw:runtime-opencode|real_eval/docker"
IMAGES["03"]="ARIS|real_eval/docker/aris_runtime.Dockerfile|aris:runtime-ready|real_eval/docker"
IMAGES["05"]="DeepScientist|real_eval/docker/deepscientist_runtime.Dockerfile|deepscientist:runtime-ready|real_eval/docker"
IMAGES["05-tdc"]="DeepScientist (TDC overlay)|real_eval/docker/deepscientist_tdc_runtime.Dockerfile|deepscientist:tdc-runtime-ready|real_eval/docker"
# NOTE: 06 copies the framework source into the image (COPY . /workspace/dr-claw/),
# so its build context must be the dr-claw checkout, not real_eval/docker.
IMAGES["06"]="Dr. Claw|real_eval/docker/drclaw_start_mode.Dockerfile|dr-claw:runtime-ready|dr-claw"
IMAGES["06-mc"]="Dr. Claw (MountainCar overlay)|real_eval/docker/drclaw_mountaincar_runtime.Dockerfile|dr-claw:runtime-ready-mountaincar|real_eval/docker"
IMAGES["06-arc3"]="Dr. Claw (ARC overlay)|real_eval/docker/drclaw_arc3_runtime.Dockerfile|dr-claw:runtime-ready-arc3|real_eval/docker"
IMAGES["07"]="EvoScientist|EvoScientist/Dockerfile|evoscientist:runtime-ready|EvoScientist"
IMAGES["07-mc"]="EvoScientist (MountainCar overlay)|real_eval/docker/evoscientist_mountaincar_runtime.Dockerfile|evoscientist:runtime-ready-mountaincar|real_eval/docker"

# ---- Parse arguments ----
if [[ $# -gt 0 ]]; then
  if [[ "$1" == "--all" ]]; then
    SELECTED=("01" "01-exec" "03" "04" "04-oc" "05" "05-tdc" "06" "06-arc3" "06-mc" "07" "07-mc")
  else
    SELECTED=("$@")
    # Also add exec images for AI-Researcher if requested
    for fw in "$@"; do
      if [[ "$fw" == "01" ]]; then
        SELECTED+=("01-exec")
      fi
    done
  fi
else
  SELECTED=("01" "01-exec" "03" "04" "04-oc" "05" "05-tdc" "06" "06-arc3" "06-mc" "07" "07-mc")
fi

# ============================================================================
# Build images
# ============================================================================
for fw_key in "${SELECTED[@]}"; do
  IFS='|' read -r fw_name dockerfile image_tag context_dir <<< "${IMAGES[$fw_key]:-}"
  if [[ -z "$fw_name" ]]; then
    warn "Unknown image key: $fw_key"
    continue
  fi

  echo ""
  info "Building $image_tag for $fw_name..."

  # 06's Dockerfile copies an entrypoint script that belongs to this repository,
  # not to the framework checkout, while its build context is the checkout. Stage
  # it into the context for the duration of the build and remove it afterwards.
  staged_entrypoint=""
  if [[ "$fw_key" == "06" ]]; then
    staged_entrypoint="$ROOT/$context_dir/drclaw_start_entrypoint.sh"
    cp "$ROOT/real_eval/docker/drclaw_start_entrypoint.sh" "$staged_entrypoint"
    trap 'rm -f "$staged_entrypoint"' EXIT
  fi

  if [[ ! -f "$ROOT/$dockerfile" ]]; then
    error "Dockerfile not found: $ROOT/$dockerfile"
    info "Make sure the framework source is cloned first:"
    info "  bash setup.sh --frameworks ${fw_key%%-*}"
    continue
  fi

  if [[ ! -d "$ROOT/$context_dir" ]]; then
    error "Framework directory not found: $ROOT/$context_dir"
    info "Run: bash setup.sh --frameworks ${fw_key%%-*}"
    continue
  fi

  # AI-Researcher exec image uses the same Dockerfile but with a different target
  if [[ "$fw_key" == "01-exec" ]]; then
    # The exec image is built from the same Dockerfile, often as a separate stage
    docker build -t "$image_tag" \
      -f "$ROOT/$dockerfile" \
      --target exec \
      "$ROOT/$context_dir" 2>/dev/null && \
      ok "$image_tag built successfully" || {
      # If no explicit target, build with a different Dockerfile name convention
      exec_dockerfile="${ROOT}/AI-Researcher/docker/Dockerfile.exec"
      if [[ -f "$exec_dockerfile" ]]; then
        docker build -t "$image_tag" -f "$exec_dockerfile" "$ROOT/$context_dir" && \
          ok "$image_tag built successfully" || \
          error "Failed to build $image_tag"
      else
        # Build outer image first, then exec as same image
        warn "No separate exec Dockerfile found, using outer image as exec"
        docker tag ai-researcher:runtime-ready ai-researcher-exec:runtime-ready 2>/dev/null || true
        ok "$image_tag tagged (same as outer image)"
      fi
    }
  else
    docker build -t "$image_tag" \
      -f "$ROOT/$dockerfile" \
      "$ROOT/$context_dir" && \
      ok "$image_tag built successfully" || \
      error "Failed to build $image_tag"
  fi
done

echo ""
ok "Docker build complete"
echo ""
info "Available images:"
docker images --format "  {{.Repository}}:{{.Tag}}" | grep -E "runtime-ready" | sort || true
echo ""