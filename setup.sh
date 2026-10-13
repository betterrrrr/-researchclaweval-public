#!/usr/bin/env bash
# ============================================================================
# setup.sh — ResearchClawEval 一键协作设置脚本
# One-click collaboration setup for ResearchClawEval
#
# Usage:
#   bash setup.sh                        # Set up all 3 frameworks (01, 02, 04)
#   bash setup.sh --quick                # Quick setup for 3 frameworks (same as default)
#   bash setup.sh --frameworks 01,04     # Set up specific frameworks only
#   bash setup.sh --model gpt-5.4        # Set default model
#   bash setup.sh --dir /path/to/dir     # Clone frameworks to a custom directory
#   bash setup.sh --skip-venv            # Skip Python virtual environment setup
#   bash setup.sh --help                 # Show help
# ============================================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ---- Framework definitions (from real_eval/registry/frameworks.json) ----
declare -A FRAMEWORKS
FRAMEWORKS["01"]="AI-Researcher|https://github.com/HKUDS/AI-Researcher.git|f9a6f8480860c193afff600eeffe3defcee8a978|adapters/01-ai-researcher|pip|~1.7 GB"
FRAMEWORKS["02"]="AI-Scientist-v2|https://github.com/SakanaAI/AI-Scientist-v2.git|96bd51617cfdbb494a9fc283af00fe090edfae48|adapters/02-ai-scientist-v2|pip|~12 MB"
FRAMEWORKS["04"]="AutoResearchClaw|https://github.com/aiming-lab/AutoResearchClaw.git|ea77ec19fefe9198ac1364d2cdb4f9e928cf0705|adapters/04-autoresearchclaw|uv|~256 MB"
FRAMEWORKS["03"]="ARIS|https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep.git|590ce825e028d6789ef9844b01b6e8b4ea736077|adapters/03-aris|pip|~38 MB"
FRAMEWORKS["05"]="DeepScientist|https://github.com/ResearAI/DeepScientist.git|b36624417f0c6b8238ec02db37b94d6db2faa5b0|adapters/05-deepscientist|uv|~128 MB"
FRAMEWORKS["06"]="Dr. Claw|https://github.com/OpenLAIR/dr-claw.git|0fab72c75368efa8f248b1d44634fe2354bee686|adapters/06-dr-claw|npm|~35 MB"
FRAMEWORKS["07"]="EvoScientist|https://github.com/EvoScientist/EvoScientist.git|690b903f850454c4ead3b0dda78ec82d02afc646|adapters/07-evoscientist|pip|~21 MB"

# ---- Colors ----
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
SELECTED_FRAMEWORKS="01,02,03,04,05,06,07"
FRAMEWORK_DIR="$ROOT"
SKIP_VENV=false
DEFAULT_MODEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick|--frameworks)
      if [[ "$1" == "--quick" ]]; then
        # A small subset: enough to smoke-test the harness without a 2 GB clone.
        SELECTED_FRAMEWORKS="04,07"
      else
        SELECTED_FRAMEWORKS="$2"; shift
      fi
      shift ;;
    --dir) FRAMEWORK_DIR="$(cd "$2" && pwd)"; shift 2 ;;
    --model) DEFAULT_MODEL="$2"; shift 2 ;;
    --skip-venv) SKIP_VENV=true; shift ;;
    --help)
      echo "Usage: bash setup.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --quick               Set up all 3 frameworks (01, 02, 04) — default"
      echo "  --frameworks LIST     Comma-separated framework IDs (default: 01,02,04)"
      echo "  --model NAME          Default LLM model name (e.g. gpt-5.4)"
      echo "  --dir PATH            Directory to clone frameworks into (default: repo root)"
      echo "  --skip-venv           Skip Python venv creation"
      echo "  --help                Show this help"
      exit 0
      ;;
    *) error "Unknown option: $1"; exit 1 ;;
  esac
done

# ============================================================================
# Pre-flight checks
# ============================================================================
header "Prerequisites Check"

command -v git    >/dev/null 2>&1 || { error "git is required but not installed."; exit 1; }
command -v python3 >/dev/null 2>&1 || { error "python3 is required but not installed."; exit 1; }
command -v uv     >/dev/null 2>&1 || warn "uv is not installed. Will use pip instead."
command -v docker >/dev/null 2>&1 || warn "docker is not installed. Full runs will require Docker."
ok "All prerequisites met"

# ---- Parse selected frameworks ----
IFS=',' read -ra SELECTED_IDS <<< "$SELECTED_FRAMEWORKS"

# Show what will be installed
echo ""
info "Selected frameworks:"
for fw_id in "${SELECTED_IDS[@]}"; do
  fw_id="$(echo "$fw_id" | xargs)"
  IFS='|' read -r fw_name fw_url fw_commit fw_adapter fw_pkg_mgr fw_size <<< "${FRAMEWORKS[$fw_id]:-}"
  if [[ -n "$fw_name" ]]; then
    echo "  [$fw_id] $fw_name — $fw_size"
  fi
done

# Estimate total download size
total_size=""
for fw_id in "${SELECTED_IDS[@]}"; do
  fw_id="$(echo "$fw_id" | xargs)"
  IFS='|' read -r fw_name fw_url fw_commit fw_adapter fw_pkg_mgr fw_size <<< "${FRAMEWORKS[$fw_id]:-}"
  if [[ -n "$fw_size" ]]; then
    total_size="${total_size}${total_size:+, }$fw_name ($fw_size)"
  fi
done
info "Estimated download: $total_size"
echo ""

# ============================================================================
# Step 1: Clone / update frameworks
# ============================================================================
header "Step 1: Cloning Framework Source Code"

for fw_id in "${SELECTED_IDS[@]}"; do
  fw_id="$(echo "$fw_id" | xargs)"
  IFS='|' read -r fw_name fw_url fw_commit fw_adapter fw_pkg_mgr fw_size <<< "${FRAMEWORKS[$fw_id]:-}"

  if [[ -z "$fw_name" ]]; then
    warn "Unknown framework ID: $fw_id, skipping"
    continue
  fi

  # The clone directory must match source_dir in real_eval/registry/frameworks.json,
  # which real_eval_resolve_framework_source() looks up by framework id. Derive it
  # from the upstream URL rather than the display name: those differ for 03 and 06.
  TARGET_DIR="$FRAMEWORK_DIR/$(basename "$fw_url" .git)"
  echo ""

  if [[ -d "$TARGET_DIR/.git" ]]; then
    info "Updating $fw_name (existing clone)..."
    cd "$TARGET_DIR"
    git fetch origin 2>/dev/null || true
    git checkout "$fw_commit" 2>/dev/null || {
      warn "Could not checkout pinned commit, trying fetch..."
      git fetch --depth=100 origin 2>/dev/null || true
      git checkout "$fw_commit" 2>/dev/null || {
        error "Failed to checkout pinned commit for $fw_name"
        cd "$ROOT"
        continue
      }
    }
    cd "$ROOT"
    ok "$fw_name updated to pinned commit"
  else
    info "Downloading $fw_name ($fw_size)..."
    git clone --depth 1 "$fw_url" "$TARGET_DIR" 2>/dev/null || {
      error "Failed to clone $fw_name from $fw_url"
      continue
    }
    cd "$TARGET_DIR"
    git fetch --depth=100 origin "$fw_commit" 2>/dev/null || warn "Could not fetch pinned commit, using latest"
    git checkout "$fw_commit" 2>/dev/null || {
      git checkout main 2>/dev/null || git checkout master 2>/dev/null || true
    }
    cd "$ROOT"
    ok "$fw_name downloaded and checked out"
  fi

  # ---- Apply patches ----
  PATCH_DIR="$ROOT/$fw_adapter/patches"
  if [[ -d "$PATCH_DIR" ]]; then
    for patch_file in "$PATCH_DIR"/*.patch; do
      if [[ -f "$patch_file" ]]; then
        info "Applying patch: $(basename "$patch_file")..."
        cd "$TARGET_DIR"
        if git apply --check "$patch_file" 2>/dev/null; then
          git apply "$patch_file"
          ok "Patch applied"
        else
          warn "Patch already applied, skipping"
        fi
        cd "$ROOT"
      fi
    done
  fi
done

# ============================================================================
# Step 2: Install project dependencies
# ============================================================================
header "Step 2: Installing Project Dependencies"

if command -v uv >/dev/null 2>&1; then
  info "Installing with uv..."
  uv sync --extra dev 2>/dev/null && ok "Project dependencies installed" || warn "uv sync had issues"
else
  warn "uv not found, falling back to pip"
  python3 -m pip install -e ".[dev]" 2>/dev/null && ok "Project dependencies installed" || warn "pip install had issues"
fi

# ============================================================================
# Step 3: Install framework dependencies
# ============================================================================
header "Step 3: Installing Framework Dependencies"

for fw_id in "${SELECTED_IDS[@]}"; do
  fw_id="$(echo "$fw_id" | xargs)"
  IFS='|' read -r fw_name fw_url fw_commit fw_adapter fw_pkg_mgr fw_size <<< "${FRAMEWORKS[$fw_id]:-}"
  if [[ -z "$fw_name" ]]; then continue; fi

  # The clone directory must match source_dir in real_eval/registry/frameworks.json,
  # which real_eval_resolve_framework_source() looks up by framework id. Derive it
  # from the upstream URL rather than the display name: those differ for 03 and 06.
  TARGET_DIR="$FRAMEWORK_DIR/$(basename "$fw_url" .git)"
  if [[ ! -d "$TARGET_DIR" ]]; then
    warn "$fw_name not found, skipping dependencies"
    continue
  fi

  info "Installing dependencies for $fw_name..."
  if [[ "$fw_pkg_mgr" == "uv" ]] && command -v uv >/dev/null 2>&1; then
    if [[ -f "$TARGET_DIR/pyproject.toml" ]]; then
      cd "$TARGET_DIR"
      uv sync 2>/dev/null && ok "$fw_name dependencies installed" || warn "uv sync failed"
      cd "$ROOT"
    fi
  elif [[ -f "$TARGET_DIR/requirements.txt" ]]; then
    python3 -m pip install -r "$TARGET_DIR/requirements.txt" 2>/dev/null && \
      ok "$fw_name dependencies installed" || warn "pip install failed"
  elif [[ -f "$TARGET_DIR/setup.cfg" ]] || [[ -f "$TARGET_DIR/setup.py" ]]; then
    python3 -m pip install -e "$TARGET_DIR" 2>/dev/null && \
      ok "$fw_name installed" || warn "pip install -e failed"
  elif [[ -f "$TARGET_DIR/pyproject.toml" ]]; then
    python3 -m pip install -e "$TARGET_DIR" 2>/dev/null && \
      ok "$fw_name installed" || warn "pip install failed"
  else
    warn "No dependency file found for $fw_name"
  fi
done

# ============================================================================
# Step 4: Generate .env file from template
# ============================================================================
header "Step 4: Environment Configuration"

ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"

if [[ ! -f "$ENV_FILE" ]] && [[ -f "$ENV_EXAMPLE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
  ok "Created .env from .env.example — please edit .env to add your API keys"

  # If a default model was provided, set it in .env
  if [[ -n "$DEFAULT_MODEL" ]]; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      sed -i '' "s/OPENAI_MODEL=.*/OPENAI_MODEL=$DEFAULT_MODEL/" "$ENV_FILE"
    else
      sed -i "s/OPENAI_MODEL=.*/OPENAI_MODEL=$DEFAULT_MODEL/" "$ENV_FILE"
    fi
    ok "Default model set to: $DEFAULT_MODEL"
  fi
elif [[ -f "$ENV_FILE" ]]; then
  ok ".env already exists, skipping"
else
  warn ".env.example not found, skipping .env generation"
fi

# ============================================================================
# Step 5: Verify setup
# ============================================================================
header "Step 5: Verification"

if command -v uv >/dev/null 2>&1; then
  uv run rceval validate registry 2>/dev/null && \
    ok "Registry validation passed" || \
    warn "Registry validation had issues (expected if datasets are not available)"
  echo ""
  info "Registered frameworks:"
  uv run rceval registry list 2>/dev/null || true
fi

# ============================================================================
# Summary
# ============================================================================
header "Setup Complete!"

echo ""
echo "  Frameworks installed:"
for fw_id in "${SELECTED_IDS[@]}"; do
  fw_id="$(echo "$fw_id" | xargs)"
  IFS='|' read -r fw_name fw_url fw_commit fw_adapter fw_pkg_mgr fw_size <<< "${FRAMEWORKS[$fw_id]:-}"
  if [[ -z "$fw_name" ]]; then continue; fi
  # The clone directory must match source_dir in real_eval/registry/frameworks.json,
  # which real_eval_resolve_framework_source() looks up by framework id. Derive it
  # from the upstream URL rather than the display name: those differ for 03 and 06.
  TARGET_DIR="$FRAMEWORK_DIR/$(basename "$fw_url" .git)"
  if [[ -d "$TARGET_DIR" ]]; then
    echo "    ✅ $fw_name [$fw_id]"
  else
    echo "    ❌ $fw_name [$fw_id] — missing"
  fi
done

echo ""
echo "  Quickstart:"
echo "    bash scripts/quickstart.sh"
echo ""
echo "  For detailed instructions:"
echo "    cat SETUP.md"
echo ""