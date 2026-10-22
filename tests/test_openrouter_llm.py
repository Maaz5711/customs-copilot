"""OpenRouterLLM (MiniMax M3.1 Flash free). A fake HTTP post and clock are injected: no network, no key, no waiting."""
import pytest

from src.agent.llm import LLMBadResponse, LLMRateLimited, LLMUnavailable, OpenRouterLLM, make_llm


class Resp:
    def __init__(self, status=200, content='{"a": 1}', error=None, headers=None):
        self.status_code, self._c, self._e = status, content, error
        self.headers = headers or {}
        self.text = "body"

    def json(self):
        if self._e is not None:
            return {"error": {"message": self._e}}
        return {"choices": [{"message": {"content": self._c}}], "usage": {"prompt_tokens": 50, "completion_tokens": 10}}


class Poster:
    def __init__(self, *resps):
        self.resps, self.calls = list(resps), []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append(dict(url=url, headers=headers, body=json))
        return self.resps[min(len(self.calls) - 1, len(self.resps) - 1)]


class Clock:
    def __init__(self):
        self.t, self.slept = 100.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def make(tmp_path, *resps, **kw):
    p, c = Poster(*resps), Clock()
    return OpenRouterLLM(api_key="or-test", cache_dir=tmp_path, post=p, sleep=c.sleep, clock=c, **kw), p, c


def test_default_model_is_minimax_free_and_request_is_json_mode(tmp_path):
    llm, p, _ = make(tmp_path, Resp())
    r = llm.complete_json(task="t", system="sys", prompt="p")
    b = p.calls[0]["body"]
    assert r.data == {"a": 1} and b["model"] == "minimax/minimax-m3.1-flash:free"
    assert b["response_format"] == {"type": "json_object"} and p.calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert p.calls[0]["headers"]["Authorization"] == "Bearer or-test" and "thinking" not in b
    assert isinstance(make_llm("openrouter", api_key="x", cache_dir=tmp_path), OpenRouterLLM)


def test_think_block_is_removed_before_json_parsing(tmp_path):
    llm, _, _ = make(tmp_path, Resp(content='<think>maybe {"x": 0} or not</think>\n{"code": "8471.3010"}'))
    assert llm.complete_json(task="t", system="s", prompt="p").data == {"code": "8471.3010"}


def test_free_model_calls_are_spaced_to_stay_under_20_a_minute(tmp_path):
    llm, p, c = make(tmp_path, Resp())
    llm.complete_json(task="t", system="s", prompt="p1")
    llm.complete_json(task="t", system="s", prompt="p2")
    assert len(p.calls) == 2 and c.slept and abs(sum(c.slept) - 3.2) < 1e-9


def test_daily_free_limit_stops_at_once_with_a_clear_message(tmp_path):
    llm, p, _ = make(tmp_path, Resp(429, error="Rate limit exceeded: free-models-per-day", headers={"X-RateLimit-Reset": "1792368000000"}))
    with pytest.raises(LLMRateLimited, match="daily limit for free models") as e:
        llm.complete_json(task="t", system="s", prompt="p")
    assert len(p.calls) == 1 and "UTC" in str(e.value)


def test_per_minute_429_is_retried(tmp_path):
    llm, p, _ = make(tmp_path, Resp(429, error="Rate limit exceeded: free-models-per-min"), Resp())
    assert llm.complete_json(task="t", system="s", prompt="p").data == {"a": 1} and len(p.calls) == 2


def test_no_endpoint_for_data_policy_explains_the_privacy_setting(tmp_path):
    llm, _, _ = make(tmp_path, Resp(404, error="No endpoints found matching your data policy"))
    with pytest.raises(LLMUnavailable, match="privacy"):
        llm.complete_json(task="t", system="s", prompt="p")


def test_error_body_with_status_200_is_not_taken_as_an_answer(tmp_path):
    llm, p, _ = make(tmp_path, Resp(200, error="provider error"), retries=2)
    with pytest.raises(LLMBadResponse):
        llm.complete_json(task="t", system="s", prompt="p")
    assert len(p.calls) == 2


def test_missing_key_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("src.agent.llm.ROOT", tmp_path)          # no .env there
    llm = OpenRouterLLM(cache_dir=tmp_path, post=Poster(Resp()), sleep=lambda s: None)
    with pytest.raises(LLMUnavailable, match="OPENROUTER_API_KEY"):
        llm.complete_json(task="t", system="s", prompt="p")
