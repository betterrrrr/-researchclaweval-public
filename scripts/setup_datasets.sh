#!/usr/bin/env bash
# ============================================================================
# setup_datasets.sh — Download and prepare datasets for full runs
#
# This script downloads publicly available datasets and prepares them
# for evaluation. Some datasets may require additional permissions.
#
# Usage:
#   bash scripts/setup_datasets.sh                                    # Download all public datasets
#   bash scripts/setup_datasets.sh --dataset arc_wbe_2026             # Download specific dataset
#   bash scripts/setup_datasets.sh --dir /path/to/datasets            # Custom output directory
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
DATASET=""
DATA_DIR="$ROOT/data"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dataset) DATASET="$2"; shift 2 ;;
    --dir) DATA_DIR="$2"; shift 2 ;;
    *) error "Unknown option: $1"; exit 1 ;;
  esac
done

mkdir -p "$DATA_DIR"

# ============================================================================
# ARC-WBE-2026 (public, from HuggingFace)
# ============================================================================
download_arc_wbe_2026() {
  header "ARC-WBE-2026 Dataset"

  local target="$DATA_DIR/arc_white_box_estimation_2026"
  if [[ -d "$target" ]] && [[ -f "$target/manifest.json" ]]; then
    ok "ARC-WBE-2026 already downloaded at $target"
    return 0
  fi

  info "This dataset is available from AIcrowd via HuggingFace."
  info "You can download it using the preparation script:"
  echo ""
  echo "  # Install dependencies"
  echo "  pip install datasets huggingface-hub"
  echo ""
  echo "  # Download and prepare the dataset"
  echo "  python3 automation/scripts/prepare_arc_wbe_2026_dataset.py \\"
  echo "    --output-root $target \\"
  echo "    --splits mini,full"
  echo ""
  echo "  # Or manually from HuggingFace:"
  echo "  # https://huggingface.co/datasets/aicrowd/arc-whestbench-public-2026"
  echo ""
  echo "  # Then set:"
  echo "  export ARC_WBE_2026_DATASET_ROOT=$target"
  echo ""

  # Try automated download if datasets is installed
  if python3 -c "import datasets" 2>/dev/null; then
    info "datasets library found, attempting download..."
    python3 automation/scripts/prepare_arc_wbe_2026_dataset.py \
      --output-root "$target" \
      --splits mini 2>/dev/null && \
      ok "ARC-WBE-2026 downloaded (mini split)" || \
      warn "ARC-WBE-2026 download failed (may need HuggingFace auth)"
  else
    warn "datasets library not available. Install with: pip install datasets"
  fi
}

# ============================================================================
# GAVE2 (public, from webis)
# ============================================================================
download_gave2() {
  header "GAVE2 Dataset"

  local target="$DATA_DIR/gave2/task2"
  if [[ -d "$target" ]] && [[ -f "$target/manifest.json" ]]; then
    ok "GAVE2 already downloaded at $target"
    return 0
  fi

  echo "  GAVE2-Task2 dataset is available from Webis:"
  echo "  https://gave2.webis.de/"
  echo ""
  echo "  After downloading, set:"
  echo "  export GAVE2_DATASET_ROOT=/path/to/GAVE2_preliminary"
  echo ""
}

# ============================================================================
# BabyLM (public)
# ============================================================================
download_babylm() {
  header "BabyLM Dataset"

  local target="$DATA_DIR/babylm"
  if [[ -d "$target" ]]; then
    ok "BabyLM already downloaded at $target"
    return 0
  fi

  echo "  BabyLM-10M dataset is available from:"
  echo "  https://babylm.github.io/"
  echo ""
  echo "  After downloading, set:"
  echo "  export BABYLM_DATASET_ROOT=/path/to/BabyLM-2026-Strict-Small"
  echo ""
}

# ============================================================================
# PsyDefDetect (beta, contact maintainers)
# ============================================================================
download_psydefdetect() {
  header "PsyDefDetect Dataset"

  echo "  PsyDefDetect is currently in beta."
  echo "  Contact the maintainers for access."
  echo ""
  echo "  After obtaining, set:"
  echo "  export PSYDEFDETECT_DATASET_ROOT=/path/to/PsyDefDetect"
  echo ""
}

# ============================================================================
# TDC-ADMET-Tox (public)
# ============================================================================
download_tdc_admet_tox() {
  header "TDC-ADMET-Tox Dataset"

  echo "  TDC ADMET dataset is available from:"
  echo "  https://tdcommons.ai/"
  echo ""
  echo "  After downloading, set:"
  echo "  export TDC_ADMET_TOX_DATASET_ROOT=/path/to/TDC-ADMET-Tox-public"
  echo ""
}

# ============================================================================
# Main
# ============================================================================
header "Dataset Setup"

if [[ -n "$DATASET" ]]; then
  case "$DATASET" in
    arc_wbe_2026) download_arc_wbe_2026 ;;
    gave2) download_gave2 ;;
    babylm) download_babylm ;;
    psydefdetect) download_psydefdetect ;;
    tdc_admet_tox) download_tdc_admet_tox ;;
    *) error "Unknown dataset: $DATASET"; exit 1 ;;
  esac
else
  download_arc_wbe_2026
  download_gave2
  download_babylm
  download_psydefdetect
  download_tdc_admet_tox
fi

echo ""
ok "Dataset setup complete"
echo ""
echo "Don't forget to set the corresponding environment variables:"
echo "  export ARC_WBE_2026_DATASET_ROOT=$DATA_DIR/arc_white_box_estimation_2026"
echo "  export GAVE2_DATASET_ROOT=/path/to/GAVE2_preliminary"
echo "  export BABYLM_DATASET_ROOT=/path/to/BabyLM-2026-Strict-Small"
echo "  export PSYDEFDETECT_DATASET_ROOT=/path/to/PsyDefDetect"
echo "  export TDC_ADMET_TOX_DATASET_ROOT=/path/to/TDC-ADMET-Tox-public"