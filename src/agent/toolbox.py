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


class McpToolBox(ToolBox):
    """The same three tools, called through the MCP server (`python -m src.tools.mcp_server`, stdio) instead of in-process.

    The MCP session lives in one background task of its own event loop, so the (synchronous) graph nodes can call it from any thread.
    Results are identical to ToolBox because the server wraps the same functions. Use `close()` when done (the CLI does)."""

    def __init__(self, db_path=None, python: str | None = None, cwd=None, startup_timeout: float = 90.0, call_timeout: float = 180.0):
        import asyncio
        import os
        import sys
        import threading
        from pathlib import Path

        super().__init__(db_path)
        self.call_timeout = call_timeout
        self._asyncio = asyncio
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stop = None
        self._error: Exception | None = None
        self._session = None
        env = {**os.environ, **({"CUSTOMS_DB": str(db_path)} if db_path else {})}
        self._params = dict(command=python or sys.executable, args=["-m", "src.tools.mcp_server"], cwd=str(cwd or Path(__file__).resolve().parents[2]), env=env)
        self._thread = threading.Thread(target=self._run, name="mcp-toolbox", daemon=True)
        self._thread.start()
        if not self._ready.wait(startup_timeout) or self._error is not None:
            self.close()
            raise RuntimeError(f"the MCP tool server did not start: {self._error or 'timeout'}")

    def _run(self):
        self._asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stop = self._asyncio.Event()
        try:
            async with stdio_client(StdioServerParameters(**self._params)) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    self._session = s
                    self._ready.set()
                    await self._stop.wait()
        except Exception as e:           # start-up or transport failure: report it to the constructor / the next call
            self._error = e
            self._ready.set()

    def _call(self, name: str, args: dict) -> dict:
        import json

        if self._session is None:
            raise RuntimeError(f"the MCP tool server is not running: {self._error}")
        fut = self._asyncio.run_coroutine_threadsafe(self._session.call_tool(name, {k: v for k, v in args.items() if v is not None}), self._loop)
        res = fut.result(timeout=self.call_timeout)
        text = res.content[0].text if res.content else ""
        try:
            return json.loads(text)
        except ValueError:
            raise RuntimeError(f"MCP tool {name} failed: {text[:300]}")

    def lookup_code(self, code, as_of_date) -> dict:
        return self._call("lookup_code", {"code": str(code), "as_of_date": str(as_of_date)})

    def get_applicable_sros(self, code, as_of_date) -> dict:
        return self._call("get_applicable_sros", {"code": str(code), "as_of_date": str(as_of_date)})

    def compute_duty(self, code, assessable_value_pkr, as_of_date, importer=None, goods=None, quantity=None, quantity_unit=None, claimed_rules=None, rounding="paisa") -> dict:
        return self._call("compute_duty", {"code": str(code), "assessable_value_pkr": str(assessable_value_pkr), "as_of_date": str(as_of_date), "importer": importer,
                                           "goods": goods, "quantity": None if quantity is None else str(quantity), "quantity_unit": quantity_unit,
                                           "claimed_rules": claimed_rules, "rounding": rounding})

    def close(self) -> None:
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(10)
