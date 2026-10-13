#!/usr/bin/env bash
# ============================================================================
# quickstart.sh — ResearchClawEval 快速验证脚本
# Verifies that the setup is correct and ready for evaluation runs.
#
# Usage:
#   bash scripts/quickstart.sh                          # Run all checks
#   bash scripts/quickstart.sh --env /path/to/.env      # Use custom env file
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
header()  { echo -e "\n${CYAN}════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $*${NC}"; echo -e "${CYAN}════════════════════════════════════════════${NC}"; }

# ---- Parse arguments ----
ENV_FILE="$ROOT/.env"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV_FILE="$2"; shift 2 ;;
    *) error "Unknown option: $1"; exit 1 ;;
  esac
done

# ---- Load .env if exists ----
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
  ok "Loaded environment from $ENV_FILE"
else
  warn "No .env file found at $ENV_FILE"
  warn "Create one from .env.example: cp .env.example .env"
fi

# ============================================================================
# Check 1: Prerequisites
# ============================================================================
header "Check 1: Prerequisites"

FAILED=0
command -v python3 >/dev/null 2>&1 && ok "python3 found: $(python3 --version)" || { error "python3 not found"; FAILED=1; }
command -v uv >/dev/null 2>&1 && ok "uv found: $(uv --version)" || warn "uv not found (will use pip)"
command -v docker >/dev/null 2>&1 && ok "docker found" || warn "docker not found (needed for full runs)"
command -v git >/dev/null 2>&1 && ok "git found: $(git --version)" || { error "git not found"; FAILED=1; }

# ============================================================================
# Check 2: Framework source code
# ============================================================================
header "Check 2: Framework Source Code"

FRAMEWORKS=("01:AI-Researcher" "02:AI-Scientist-v2" "04:AutoResearchClaw")
for fw in "${FRAMEWORKS[@]}"; do
  IFS=':' read -r fw_id fw_name <<< "$fw"
  if [[ -d "$ROOT/$fw_name/.git" ]]; then
    ok "$fw_name [$fw_id] — ready"
  else
    warn "$fw_name [$fw_id] — not found. Run: bash setup.sh --frameworks $fw_id"
  fi
done

# ============================================================================
# Check 3: Project dependencies
# ============================================================================
header "Check 3: Project Dependencies"

if command -v uv >/dev/null 2>&1; then
  uv run rceval --help >/dev/null 2>&1 && ok "rceval CLI is available" || { error "rceval CLI not working"; FAILED=1; }
else
  python3 -m researchclaweval.cli --help >/dev/null 2>&1 && ok "rceval CLI is available" || { error "rceval CLI not working"; FAILED=1; }
fi

# ============================================================================
# Check 4: API connectivity
# ============================================================================
header "Check 4: API Connectivity"

if [[ -n "${OPENAI_API_KEY:-}" && -n "${OPENAI_BASE_URL:-}" ]]; then
  masked_key="${OPENAI_API_KEY:0:8}...${OPENAI_API_KEY: -4}"
  ok "API key configured: $masked_key"
  ok "API endpoint: $OPENAI_BASE_URL"
  if [[ -n "${OPENAI_MODEL:-}" ]]; then
    ok "Default model: $OPENAI_MODEL"
  else
    warn "OPENAI_MODEL not set"
  fi
else
  warn "API key not configured. Set OPENAI_API_KEY and OPENAI_BASE_URL in .env"
fi

# ============================================================================
# Check 5: Registry validation
# ============================================================================
header "Check 5: Registry Validation"

if command -v uv >/dev/null 2>&1; then
  uv run rceval validate registry 2>/dev/null && ok "Registry is valid" || warn "Registry validation had issues"
else
  warn "uv not available, skipping registry validation"
fi

# ============================================================================
# Check 6: Dry-run test
# ============================================================================
header "Check 6: Dry-Run Test (no Docker required)"

DRY_RUN_DIR="/tmp/rceval-quickstart-$$"
if command -v uv >/dev/null 2>&1; then
  if uv run rceval dry-run --topic arc_wbe_2026 --mode smoke --output-dir "$DRY_RUN_DIR" 2>/dev/null; then
    ok "Dry-run passed for arc_wbe_2026/smoke"
    rm -rf "$DRY_RUN_DIR"
  else
    warn "Dry-run failed (expected if datasets are not available)"
    rm -rf "$DRY_RUN_DIR" 2>/dev/null || true
  fi
else
  warn "uv not available, skipping dry-run"
fi

# ============================================================================
# Check 7: Full-run readiness (Docker + datasets)
# ============================================================================
header "Check 7: Full-Run Readiness"

# Check Docker
if command -v docker >/dev/null 2>&1; then
  # Check required images
  MISSING_IMAGES=()
  for img in "ai-researcher:runtime-ready" "ai-scientist-v2:runtime-ready" "autoresearchclaw:runtime-ready"; do
    docker image inspect "$img" >/dev/null 2>&1 || MISSING_IMAGES+=("$img")
  done

  if [[ ${#MISSING_IMAGES[@]} -eq 0 ]]; then
    ok "All Docker images found"
  else
    warn "Missing Docker images: ${MISSING_IMAGES[*]}"
    warn "Build them with: bash scripts/build_docker.sh"
  fi

  # Check for nvidia-container-toolkit (GPU support)
  if command -v nvidia-smi >/dev/null 2>&1; then
    ok "GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
  else
    warn "No GPU detected or nvidia-smi not available"
  fi
else
  warn "Docker not installed. Full runs will not work."
fi

# Check datasets
if [[ -n "${ARC_WBE_2026_DATASET_ROOT:-}" ]] && [[ -d "$ARC_WBE_2026_DATASET_ROOT" ]]; then
  ok "ARC-WBE-2026 dataset: $ARC_WBE_2026_DATASET_ROOT"
else
  warn "ARC_WBE_2026_DATASET_ROOT not set or not found"
fi

if [[ -n "${GAVE2_DATASET_ROOT:-}" ]] && [[ -d "$GAVE2_DATASET_ROOT" ]]; then
  ok "GAVE2 dataset: $GAVE2_DATASET_ROOT"
else
  warn "GAVE2_DATASET_ROOT not set or not found"
fi

if [[ -n "${BABYLM_DATASET_ROOT:-}" ]] && [[ -d "$BABYLM_DATASET_ROOT" ]]; then
  ok "BabyLM dataset: $BABYLM_DATASET_ROOT"
else
  warn "BABYLM_DATASET_ROOT not set or not found"
fi

# Check provider config
if [[ -n "${PROVIDER_CONFIG:-}" ]] && [[ -f "$PROVIDER_CONFIG" ]]; then
  ok "Provider config: $PROVIDER_CONFIG"
else
  warn "PROVIDER_CONFIG not set or not found"
  warn "Create one from provider.example.toml"
fi

# ============================================================================
# Summary
# ============================================================================
header "Quickstart Summary"

if [[ "$FAILED" -eq 1 ]]; then
  echo ""
  error "Required checks failed. Fix the issues above and re-run."
  exit 1
fi

# The control plane -- registry, validators, dry-run -- needs only Python and
# uv, and works right now in this checkout. Full runs additionally need Docker
# images, a dataset, and a provider config. Report the two levels separately:
# a green summary must never be readable as "ready to launch a framework".
readiness=()

if command -v docker >/dev/null 2>&1; then
  for img in "ai-researcher:runtime-ready" "ai-scientist-v2:runtime-ready" "autoresearchclaw:runtime-ready"; do
    if ! docker image inspect "$img" >/dev/null 2>&1; then
      readiness+=("Docker image $img  ->  bash scripts/build_docker.sh")
      break
    fi
  done
else
  readiness+=("Docker (not installed)")
fi

have_dataset=0
for var in ARC_WBE_2026_DATASET_ROOT BABYLM_DATASET_ROOT PSYDEFDETECT_DATASET_ROOT \
           TDC_ADMET_TOX_DATASET_ROOT MOUNTAINCAR_CONTINUOUS_DATASET_ROOT; do
  if [[ -n "${!var:-}" && -d "${!var}" ]]; then have_dataset=1; fi
done
(( have_dataset )) || readiness+=("a dataset  ->  obtain it from the topic's official source and export its *_DATASET_ROOT")

if [[ -z "${PROVIDER_CONFIG:-}" || ! -f "${PROVIDER_CONFIG:-/nonexistent}" ]]; then
  readiness+=("PROVIDER_CONFIG  ->  cp provider.example.toml my_provider.toml, then edit it")
fi

echo ""
echo "  ✅ Control plane ready. In this checkout right now, no Docker, no"
echo "     datasets and no API key needed:"
echo ""
echo "       uv run rceval validate registry"
echo "       uv run rceval registry list"
echo "       uv run rceval dry-run --topic arc_wbe_2026 --mode smoke --output-dir /tmp/rceval-plan"
echo ""

if (( ${#readiness[@]} == 0 )); then
  echo "  ✅ Full-run prerequisites are in place."
  echo ""
else
  echo "  ⚠️  Full runs are NOT ready yet. Still missing:"
  echo ""
  for item in "${readiness[@]}"; do
    echo "       - $item"
  done
  echo ""
fi

echo "  A full run launches your framework in Docker and must produce the"
echo "  artifacts named in automation/<topic>_contract.md. See SETUP.md and"
echo "  real_eval/docs/wrapper_interface.md before your first run."
echo ""
