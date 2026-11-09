"""A4 Task/Dataset extraction; use the delivered Contract v2 implementation."""
import sys
from pathlib import Path

CONTRACT_PACKAGE = Path(__file__).resolve().parents[2] / "handoff/mxh_contract_v2"
if str(CONTRACT_PACKAGE) not in sys.path:
    sys.path.insert(0, str(CONTRACT_PACKAGE))
