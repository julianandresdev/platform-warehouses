"""Shared pytest setup for packages kept under services/."""

import sys
from pathlib import Path


COMMON_PACKAGE = Path(__file__).resolve().parents[1] / "services" / "common"
WAREHOUSE_API = Path(__file__).resolve().parents[1] / "services" / "warehouse-api"
BATCH = Path(__file__).resolve().parents[1] / "services" / "batch"
IOT = Path(__file__).resolve().parents[1] / "services" / "iot"
sys.path.insert(0, str(COMMON_PACKAGE))
sys.path.insert(0, str(WAREHOUSE_API))
REPORT_VALIDATOR = (
    Path(__file__).resolve().parents[1] / "services" / "lambda" / "report_validator"
)
sys.path.insert(0, str(BATCH))
sys.path.insert(0, str(REPORT_VALIDATOR))
sys.path.insert(0, str(IOT))
