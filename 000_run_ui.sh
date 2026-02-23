#!/usr/bin/env bash
# Launch the SPL-Flow Streamlit UI
# Usage: bash 000_run_ui.sh [-- <extra streamlit args>]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$SCRIPT_DIR/src/ui/streamlit/SPL_Flow🌊.py"
streamlit cache clear
exec streamlit run "$APP" "$@"
