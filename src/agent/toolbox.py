"""The exact tools as the agent sees them (C1).

`ToolBox` calls src.tools in-process (the same functions the MCP server in src/tools/mcp_server.py exposes). The agent never
does arithmetic and never states a rate: every number in an answer is copied from what these three functions return.
"""
from __future__ import annotations

from src.tools import compute_duty as _compute_duty
from src.tools import get_applicable_sros as _get_applicable_sros
from src.tools import lookup_code as _lookup_code
from src.tools._util import coverage, get_conn

FALLBACK_RANGE = ("2025-07-01", "2027-06-30")     # FY2025-26 and FY2026-27; the store's own coverage is read first


class ToolBox:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def lookup_code(self, code, as_of_date) -> dict:
        return _lookup_code(code, as_of_date, db_path=self.db_path)

    def get_applicable_sros(self, code, as_of_date) -> dict:
        return _get_applicable_sros(code, as_of_date, db_path=self.db_path)

    def compute_duty(self, code, assessable_value_pkr, as_of_date, importer=None, goods=None, quantity=None,
                     quantity_unit=None, claimed_rules=None, rounding="paisa") -> dict:
        return _compute_duty(code, assessable_value_pkr, as_of_date, importer=importer, quantity=quantity,
                             quantity_unit=quantity_unit, goods=goods, claimed_rules=claimed_rules, rounding=rounding,
                             db_path=self.db_path)

    def supported_range(self) -> tuple[str, str]:
        """First and last date the dated store covers (the tariffs stop there)."""
        try:
            lo, hi = coverage(get_conn(self.db_path))
            return lo, hi
        except Exception:
            return FALLBACK_RANGE

    def code_in_tariff(self, code: str) -> bool:
        """True when a 4, 6 or 8 digit code exists in either supported fiscal year (used to vet codes found in free text)."""
        lo, hi = self.supported_range()
        for d in (lo, hi):
            r = self.lookup_code(code, d)
            if r.get("status") in ("found", "not_a_full_code"):
                return True
        return False
