"""The web server answers requests in a thread pool, so the exact tools must be safe when several run at once."""
import threading

import pytest

from src.store.db import DEFAULT_DB_PATH

pytestmark = pytest.mark.skipif(not DEFAULT_DB_PATH.exists(), reason="legal store not built (data is not in the public repository)")


def test_lookup_and_bill_from_many_threads_at_once():
    from src.tools import compute_duty
    from src.tools.code_lookup import search_codes

    search_codes("warm up", "2026-11-09", 3, None, None)          # load the search indexes once, like a running server
    errors: list[str] = []

    def work():
        try:
            assert search_codes("solar inverter 5 kW", "2026-11-09", 5, None, None)
            compute_duty("61091000", 2500000, "2026-11-09")
        except Exception as e:                                        # noqa: BLE001
            errors.append(f"{type(e).__name__}: {str(e)[:100]}")

    threads = [threading.Thread(target=work) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
