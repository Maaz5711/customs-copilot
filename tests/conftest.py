"""Unit tests run the agent without the heading-hint LLM call (their FakeLLM scripts do not expect it). tests/test_agent_hints.py turns it on explicitly."""
import os

os.environ["AGENT_USE_HINTS"] = "0"
os.environ["AGENT_EXPLORE_STEPS"] = "0"        # tests/test_agent_explore.py turns it on explicitly
os.environ["AGENT_ASK_CONCESSIONS"] = "0"      # tests/test_agent_concessions.py turns it on explicitly


# Tests that need the built data (the legal store and the tables read from the FBR PDFs, which are not in the public repository) are skipped,
# with a reason, when it is absent. Build it first (README, "Quick start") to run them. Add a module here when a new test needs the data.
import pathlib

import pytest

NEEDS_BUILT_DATA = {"test_concessions", "test_fed_compute", "test_ground_truth", "test_owner_answers", "test_a3_sro", "test_a3_rules", "test_code_lookup"}


def pytest_collection_modifyitems(config, items):
    if pathlib.Path("data/processed/a3_sro_rules.csv").exists() and pathlib.Path("data/processed/legal_store.sqlite").exists():
        return
    skip = pytest.mark.skip(reason="needs the built data store (see README, Quick start); it is derived from FBR PDFs and is not in the repository")
    for item in items:
        if item.module.__name__.rsplit(".", 1)[-1] in NEEDS_BUILT_DATA:
            item.add_marker(skip)
