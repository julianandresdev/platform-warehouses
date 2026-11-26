#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../../tests/iot/lib.sh"
trap d07_down EXIT
d07_up
d07_reset
SENSOR_COUNT=100 PUBLISH_INTERVAL_SECONDS=2 SIM_DURATION_SECONDS="${SIM_DURATION_SECONDS:-600}" DUP_RATE=0.02 REORDER_RATE=0.05 SIMULATED_OUTAGE_START_SECONDS=60 SIMULATED_OUTAGE_DURATION_SECONDS=20 SIMULATOR_SUMMARY_PATH=/evidence/simulacion-10min.json d07_run_simulator
d07_verify docs/evidencias/fase-12/simulacion-10min.json
