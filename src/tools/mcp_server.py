"""MCP server (stdio) exposing the exact customs tools: lookup_code, get_applicable_sros, compute_duty.

Run:  .venv/Scripts/python -m src.tools.mcp_server
Every tool returns plain JSON (money and rates are strings, never floats). No LLM is called here.
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import compute_duty as _compute_duty
from . import get_applicable_sros as _get_applicable_sros
from . import lookup_code as _lookup_code

mcp = MCPServer("customs-copilot-tools")


@mcp.tool()
def lookup_code(code: str, as_of_date: str) -> dict:
    """Tariff line for a Pakistan Customs Tariff (PCT) code on a date (YYYY-MM-DD): description, heading, CD rate or
    specific duty, source file and page, row status. Returns 'not_found' with the nearest codes if the code is not a line."""
    return _lookup_code(code, as_of_date)


@mcp.tool()
def get_applicable_sros(code: str, as_of_date: str) -> dict:
    """Every RD, ACD, sales tax and income tax rule that applies to an 8-digit code on a date, with SRO number, clause,
    rate, conditions, source file, page and status (needs_review is flagged), plus the rows excluded by 'except'
    clauses, by the date, by a tariff-CD slab test or because they are supply-only rules."""
    return _get_applicable_sros(code, as_of_date)


@mcp.tool()
def compute_duty(code: str, assessable_value_pkr: str, as_of_date: str, importer: dict | None = None,
                 quantity: str | None = None, quantity_unit: str | None = None, goods: dict | None = None,
                 claimed_rules: list[str] | None = None, rounding: str = "paisa") -> dict:
    """Itemised import bill (CD, RD, ACD, sales tax, value addition tax, income tax) with the rule, SRO/clause, source
    file and page for every line. If an input the law requires is missing the result has status 'needs_input' and a
    'missing_inputs' list and NO total; ask the user those questions and call again.
    importer: registration_status ('registered'|'unregistered'), commercial_importer (bool), manufacturer_in_house_use (bool),
      licensed_oil_marketing_company (bool), registered_service_provider_in_house_use (bool), income_tax_category.
    goods: vehicle_form ('CKD'|'CBU'), engine_cc, used_vehicle_commercial_import_ipo (bool), import_regime (list),
      plant_machinery_for_manufacturing (bool), c_and_f_value_usd_per_unit, retail_price_total_pkr, running_time_minutes, age_years."""
    return _compute_duty(code, assessable_value_pkr, as_of_date, importer=importer, quantity=quantity,
                         quantity_unit=quantity_unit, goods=goods, claimed_rules=claimed_rules, rounding=rounding)


if __name__ == "__main__":
    mcp.run(transport="stdio")
