"""DeepSeekLLM (OpenAI-style API). A fake HTTP post is injected: no network, no key needed."""
import json

import pytest

from src.agent.llm import DeepSeekLLM, LLMBudgetExceeded, LLMRateLimited, LLMUnavailable, make_llm


class Resp:
    def __init__(self, status=200, content='{"a": 1}', usage=None):
        self.status_code = status
        self._c = content
        self._u = usage if usage is not None else {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        self.text = "body"

    def json(self):
        return {"choices": [{"message": {"content": self._c}}], "usage": self._u}


class Poster:
    def __init__(self, *resps):
        self.resps = list(resps)
        self.calls = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append(dict(url=url, headers=headers, body=json))
        r = self.resps[min(len(self.calls) - 1, len(self.resps) - 1)]
        if isinstance(r, Exception):
            raise r
        return r


def make(tmp_path, *resps, **kw):
    p = Poster(*resps)
    return DeepSeekLLM(api_key="sk-test-123", cache_dir=tmp_path, post=p, sleep=lambda s: None, **kw), p


def test_request_shape_json_mode_and_thinking_off_by_default(tmp_path):
    llm, p = make(tmp_path, Resp())
    r = llm.complete_json(task="t", system="sys", prompt="p")
    b = p.calls[0]["body"]
    assert r.data == {"a": 1} and b["response_format"] == {"type": "json_object"} and b["thinking"] == {"type": "disabled"}
    assert b["model"] == "deepseek-flash" and b["messages"][0] == {"role": "system", "content": "sys"} and b["temperature"] == 0.0
    assert p.calls[0]["headers"]["Authorization"] == "Bearer sk-test-123" and p.calls[0]["url"].startswith("https://api.deepseek.com/")
    assert (llm.stats["tokens_in"], llm.stats["tokens_out"]) == (100, 20)


def test_second_identical_call_is_served_from_the_cache(tmp_path):
    llm, p = make(tmp_path, Resp())
    llm.complete_json(task="t", system="s", prompt="p")
    r = llm.complete_json(task="t", system="s", prompt="p")
    assert r.cached and len(p.calls) == 1 and llm.stats["cache_hits"] == 1


def test_model_and_thinking_are_part_of_the_cache_key(tmp_path):
    a, _ = make(tmp_path, Resp())
    a.complete_json(task="t", system="s", prompt="p")
    b, pb = make(tmp_path, Resp(), model="deepseek-v4-pro")
    c, pc = make(tmp_path, Resp(), thinking="enabled")
    assert not b.complete_json(task="t", system="s", prompt="p").cached and not c.complete_json(task="t", system="s", prompt="p").cached
    assert "temperature" not in pc.calls[0]["body"] and pc.calls[0]["body"]["thinking"] == {"type": "enabled"}


def test_retries_server_errors_then_succeeds(tmp_path):
    llm, p = make(tmp_path, Resp(503), Resp(429), Resp())
    assert llm.complete_json(task="t", system="s", prompt="p").data == {"a": 1} and len(p.calls) == 3


def test_invalid_json_is_retried_and_finally_reported(tmp_path):
    llm, p = make(tmp_path, Resp(content="not json"), Resp(content='```json\n{"a": 2}\n```'))
    assert llm.complete_json(task="t", system="s", prompt="p").data == {"a": 2}


def test_bad_key_empty_balance_and_budget(tmp_path):
    llm, _ = make(tmp_path, Resp(401))
    with pytest.raises(LLMUnavailable, match="rejected the API key"):
        llm.complete_json(task="t", system="s", prompt="p")
    llm, _ = make(tmp_path, Resp(402))
    with pytest.raises(LLMRateLimited, match="balance"):
        llm.complete_json(task="t", system="s", prompt="p")
    llm, p = make(tmp_path, Resp(), max_calls=1)
    llm.complete_json(task="t", system="s", prompt="p1")
    with pytest.raises(LLMBudgetExceeded):
        llm.complete_json(task="t", system="s", prompt="p2")


def test_key_never_appears_in_cache_files_or_errors(tmp_path):
    llm, _ = make(tmp_path, Resp())
    llm.complete_json(task="t", system="s", prompt="p")
    assert all("sk-test-123" not in f.read_text(encoding="utf8") for f in tmp_path.rglob("*.json"))
    llm, _ = make(tmp_path, Resp(500), retries=2)
    with pytest.raises(Exception) as e:
        llm.complete_json(task="t", system="s", prompt="other")
    assert "sk-test-123" not in str(e.value)


def test_missing_key_message_and_registry(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None, raising=False)
    with pytest.raises(LLMUnavailable, match="DEEPSEEK_API_KEY"):
        DeepSeekLLM(cache_dir=tmp_path, post=Poster(Resp())).complete_json(task="t", system="s", prompt="p")
    assert isinstance(make_llm("deepseek", api_key="x", cache_dir=tmp_path), DeepSeekLLM)
    with pytest.raises(ValueError):
        DeepSeekLLM(api_key="x", thinking="maybe")
