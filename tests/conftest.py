"""Shared pytest setup for packages kept under services/."""

import sys
from pathlib import Path


COMMON_PACKAGE = Path(__file__).resolve().parents[1] / "services" / "common"
WAREHOUSE_API = Path(__file__).resolve().parents[1] / "services" / "warehouse-api"
sys.path.insert(0, str(COMMON_PACKAGE))
sys.path.insert(0, str(WAREHOUSE_API))
