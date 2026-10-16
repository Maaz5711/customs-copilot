"""Unit tests run the agent without the heading-hint LLM call (their FakeLLM scripts do not expect it). tests/test_agent_hints.py turns it on explicitly."""
import os

os.environ["AGENT_USE_HINTS"] = "0"
os.environ["AGENT_ASK_CONCESSIONS"] = "0"      # tests/test_agent_concessions.py turns it on explicitly
