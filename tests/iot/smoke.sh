#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/lib.sh"
trap d07_down EXIT
d07_up
d07_reset
SENSOR_COUNT=10 PUBLISH_INTERVAL_SECONDS=0.2 SIM_DURATION_SECONDS=8 DUP_RATE=0.25 REORDER_RATE=0.2 SIMULATED_OUTAGE_START_SECONDS=2 SIMULATED_OUTAGE_DURATION_SECONDS=2 SIMULATOR_SUMMARY_PATH=/evidence/simulacion-smoke.json d07_run_simulator
d07_verify
