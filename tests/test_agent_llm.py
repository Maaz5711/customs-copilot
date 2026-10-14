"""Tests for src/agent/llm.py. No network: the HTTP layer is a fake."""
import datetime as dt
import json

import pytest

from src.agent.llm import (
    FakeLLM, GeminiLLM, LLMBadResponse, LLMBudgetExceeded, LLMRateLimited, LLMUnavailable, QuotaBook, ResponseCache,
    make_llm, next_daily_reset, parse_429, parse_json_text,
)

KEY = "test-key-DO-NOT-LEAK-123"


class R:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, status, body):
        self.status_code, self._b = status, body
        self.text = json.dumps(body)

    def json(self):
        return self._b


def ok(payload: dict, model_text=None):
    text = model_text if model_text is not None else json.dumps(payload)
    return R(200, {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
                   "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}})


def quota(daily: bool, retry="34s"):
    return R(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "You exceeded your current quota.",
                              "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                                           "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier" if daily
                                                           else "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
                                          {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry}]}})


class Net:
    """Scripted fake for requests.post: responses keyed by model name (taken from the URL), consumed in order."""

    def __init__(self, by_model):
        self.by_model = {m: list(v) for m, v in by_model.items()}
        self.urls = []

    def __call__(self, url, headers=None, json=None, timeout=None):
        model = url.split("/models/")[1].split(":")[0]
        self.urls.append(model)
        assert headers["x-goog-api-key"] == KEY
        q = self.by_model[model]
        return q.pop(0) if len(q) > 1 else q[0]


def make(net, tmp_path, models=("m1", "m2"), **kw):
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("quota_book", QuotaBook(path=tmp_path / "quota.json", clock=kw.get("clock", lambda: 1_000_000.0)))
    return GeminiLLM(api_key=KEY, models=list(models), post=net, cache_dir=tmp_path / "cache", **kw)


def call(llm, prompt="p", task="t"):
    return llm.complete_json(task=task, system="s", prompt=prompt)


# ------------------------------------------------------------------------------------- basics
def test_parse_json_text_tolerates_fences_and_prose():
    assert parse_json_text('{"a": 1}') == {"a": 1}
    assert parse_json_text('```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert parse_json_text('Here you go: {"a": {"b": 2}} thanks') == {"a": {"b": 2}}
    with pytest.raises(ValueError):
        parse_json_text("no json here")


def test_success_returns_parsed_json_and_model(tmp_path):
    net = Net({"m1": [ok({"x": 1})]})
    r = call(make(net, tmp_path))
    assert r.data == {"x": 1} and r.model == "m1" and not r.cached and r.usage["promptTokenCount"] == 10


def test_cache_hit_makes_no_request_and_works_without_a_key(tmp_path):
    net = Net({"m1": [ok({"x": 1})]})
    llm = make(net, tmp_path)
    call(llm, "same prompt")
    assert net.urls == ["m1"]
    r = call(llm, "same prompt")
    assert r.cached and r.data == {"x": 1} and net.urls == ["m1"] and llm.stats["cache_hits"] == 1
    # a brand-new object with NO key and no network still serves the cached answer (offline replay)
    offline = GeminiLLM(api_key=None, models=["m1"], post=None, cache_dir=tmp_path / "cache", quota_book=QuotaBook(path=None))
    again = offline.complete_json(task="t", system="s", prompt="same prompt")
    assert again.cached and again.data == {"x": 1} and offline._api_key is None   # the key was never even looked up


def test_different_prompt_or_temperature_is_a_cache_miss(tmp_path):
    net = Net({"m1": [ok({"x": 1}), ok({"x": 2})]})
    llm = make(net, tmp_path)
    assert call(llm, "a").data == {"x": 1}
    assert call(llm, "b").data == {"x": 2}
    assert ResponseCache.key("t", "s", "a", 0.0) != ResponseCache.key("t", "s", "a", 0.5)


def test_cache_can_be_disabled(tmp_path):
    net = Net({"m1": [ok({"x": 1}), ok({"x": 2})]})
    llm = make(net, tmp_path, cache=False)
    assert call(llm).data == {"x": 1} and call(llm).data == {"x": 2}


# ------------------------------------------------------------------------------------- 429 handling and fallback
def test_parse_429_reads_daily_and_retry_delay():
    daily, retry, msg = parse_429(quota(True, "12.5s"))
    assert daily is True and retry == 12.5 and "quota" in msg
    daily, retry, _ = parse_429(quota(False, "7s"))
    assert daily is False and retry == 7.0


def test_daily_429_falls_back_to_next_model_and_is_remembered(tmp_path):
    net = Net({"m1": [quota(True)], "m2": [ok({"from": "m2"})]})
    llm = make(net, tmp_path)
    r = call(llm, "q1")
    assert r.model == "m2" and net.urls == ["m1", "m2"]
    # the book now blocks m1 until the next reset: a new request goes straight to m2 without touching m1
    r2 = call(llm, "q2")
    assert r2.model == "m2" and net.urls == ["m1", "m2", "m2"]
    # and a fresh object sharing the same quota file also skips m1 (persisted)
    llm2 = make(Net({"m1": [ok({})], "m2": [ok({"again": 1})]}), tmp_path)
    assert call(llm2, "q3").model == "m2"


def test_per_minute_429_waits_then_retries_same_model(tmp_path):
    slept = []
    net = Net({"m1": [quota(False, "5s"), ok({"x": 1})]})
    llm = make(net, tmp_path, sleep=slept.append)
    r = call(llm)
    assert r.model == "m1" and net.urls == ["m1", "m1"] and slept and 5 <= slept[0] <= 6


def test_per_minute_429_with_long_delay_falls_back_instead_of_waiting(tmp_path):
    slept = []
    net = Net({"m1": [quota(False, "55s")], "m2": [ok({"x": 2})]})
    llm = make(net, tmp_path, sleep=slept.append)
    assert call(llm).model == "m2" and slept == []


def test_all_models_rate_limited_raises_clear_error_with_reset_time(tmp_path):
    net = Net({"m1": [quota(True)], "m2": [quota(True)]})
    llm = make(net, tmp_path)
    with pytest.raises(LLMRateLimited) as e:
        call(llm)
    msg = str(e.value)
    assert "m1" in msg and "m2" in msg and "out of quota" in msg and "Nothing was computed" in msg
    assert e.value.retry_at and e.value.retry_at > 1_000_000.0
    assert KEY not in msg
    # next call does not even send requests: the book knows both are blocked
    n = len(net.urls)
    with pytest.raises(LLMRateLimited):
        call(llm, "other")
    assert len(net.urls) == n


def test_model_not_found_404_skips_to_next(tmp_path):
    net = Net({"m1": [R(404, {"error": {"message": "models/m1 is not found"}})], "m2": [ok({"x": 3})]})
    assert call(make(net, tmp_path)).model == "m2"


def test_server_error_retries_once_then_falls_back(tmp_path):
    net = Net({"m1": [R(503, {"error": {"message": "overloaded"}})], "m2": [ok({"x": 4})]})
    llm = make(net, tmp_path)
    assert call(llm).model == "m2" and net.urls == ["m1", "m1", "m2"]


def test_bad_api_key_is_a_clear_unavailable_error(tmp_path):
    net = Net({"m1": [R(400, {"error": {"message": "API key not valid. Please pass a valid API key."}})]})
    with pytest.raises(LLMUnavailable) as e:
        call(make(net, tmp_path))
    assert "API key" in str(e.value) and KEY not in str(e.value)


def test_invalid_json_falls_back_then_raises_bad_response(tmp_path):
    net = Net({"m1": [ok({}, model_text="not json at all")], "m2": [ok({"x": 5})]})
    assert call(make(net, tmp_path)).model == "m2"
    net2 = Net({"m1": [ok({}, model_text="nope")], "m2": [ok({}, model_text="still nope")]})
    with pytest.raises(LLMBadResponse):
        call(make(net2, tmp_path / "other"))


def test_fenced_json_answer_is_accepted(tmp_path):
    net = Net({"m1": [ok({}, model_text='```json\n{"x": 6}\n```')]})
    assert call(make(net, tmp_path)).data == {"x": 6}


def test_thought_parts_are_ignored(tmp_path):
    body = {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": '{"x": 7}'}]}}]}
    net = Net({"m1": [R(200, body)]})
    assert call(make(net, tmp_path)).data == {"x": 7}


def test_a_model_that_just_failed_with_503_is_tried_last_next_time(tmp_path):
    now = [1_000_000.0]
    net = Net({"m1": [R(503, {"error": {"message": "overloaded"}})], "m2": [ok({"x": 1}), ok({"x": 2})]})
    llm = make(net, tmp_path, clock=lambda: now[0])
    assert call(llm, "a").model == "m2" and net.urls == ["m1", "m1", "m2"]            # m1 failed twice (one retry), m2 answered
    # next request: m2 goes first, m1 is not wasted on again
    assert call(llm, "b").model == "m2" and net.urls == ["m1", "m1", "m2", "m2"]
    # after the cooldown m1 is back at the front of the line
    now[0] += 200.0
    net.by_model["m1"] = [ok({"x": 9})]
    assert call(llm, "c").model == "m1"


def test_cooldown_does_not_stop_a_model_being_used_when_it_is_the_only_one_left(tmp_path):
    err = R(503, {"error": {"message": "overloaded"}})
    net = Net({"m1": [err, err, ok({"x": 1})]})          # the first request is retried once, so two 503s make one failed call
    llm = make(net, tmp_path, models=("m1",))
    with pytest.raises(LLMUnavailable):
        call(llm, "a")                       # fails, m1 is cooling
    assert call(llm, "b").data == {"x": 1}   # but it is still tried (cooldown only changes the order)


# ------------------------------------------------------------------------------------- budget, key, secrets
def test_live_call_budget_stops_before_sending(tmp_path):
    net = Net({"m1": [ok({"x": 1}), ok({"x": 2})]})
    llm = make(net, tmp_path, max_calls=1)
    call(llm, "a")
    with pytest.raises(LLMBudgetExceeded):
        call(llm, "b")
    assert net.urls == ["m1"]
    assert call(llm, "a").cached    # cache hits do not count against the budget


def test_missing_key_is_a_clear_error_and_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    net = Net({"m1": [ok({})]})
    llm = GeminiLLM(api_key=None, models=["m1"], post=net, cache_dir=tmp_path / "c", quota_book=QuotaBook(path=None))
    with pytest.raises(LLMUnavailable) as e:
        call(llm)
    assert "GEMINI_API_KEY" in str(e.value) and net.urls == []


def test_key_never_appears_in_errors_stats_or_cache(tmp_path):
    net = Net({"m1": [quota(True)], "m2": [ok({"x": 1})]})
    llm = make(net, tmp_path)
    call(llm)
    assert KEY not in json.dumps(llm.stats)
    for p in (tmp_path / "cache").rglob("*.json"):
        assert KEY not in p.read_text(encoding="utf8")
    assert KEY not in (tmp_path / "quota.json").read_text(encoding="utf8")


def test_models_come_from_env_when_not_given(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_MODELS", "alpha, beta")
    assert GeminiLLM(api_key="k", cache_dir=tmp_path).models == ["alpha", "beta"]


# ------------------------------------------------------------------------------------- reset time
def utc(*a):
    return dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp()


def test_next_daily_reset_is_midnight_pacific():
    # 14 Oct 2026 12:00 UTC: US daylight time (UTC-7) -> next midnight Pacific = 15 Oct 07:00 UTC
    assert next_daily_reset(utc(2026, 10, 14, 12)) == utc(2026, 10, 15, 7)
    # 14 Dec 2026: standard time (UTC-8) -> 15 Dec 08:00 UTC
    assert next_daily_reset(utc(2026, 12, 14, 12)) == utc(2026, 12, 15, 8)
    # 14 Oct 2026 03:00 UTC is still 13 Oct 20:00 Pacific -> reset 14 Oct 07:00 UTC
    assert next_daily_reset(utc(2026, 10, 14, 3)) == utc(2026, 10, 14, 7)


def test_quota_book_expires(tmp_path):
    now = [1000.0]
    qb = QuotaBook(path=tmp_path / "q.json", clock=lambda: now[0])
    qb.mark("m", 2000.0, "daily")
    assert qb.blocked("m")
    now[0] = 2001.0
    assert qb.blocked("m") is None


# ------------------------------------------------------------------------------------- FakeLLM
def test_fake_llm_scripts():
    f = FakeLLM({"a": {"k": 1}, "b": [{"n": 1}, {"n": 2}], "c": lambda prompt, n: {"echo": prompt, "n": n}, "d": LLMUnavailable("down")})
    assert f.complete_json(task="a", system="", prompt="").data == {"k": 1}
    assert [f.complete_json(task="b", system="", prompt="").data["n"] for _ in range(3)] == [1, 2, 2]   # last repeats
    assert f.complete_json(task="c", system="", prompt="hi").data == {"echo": "hi", "n": 0}
    with pytest.raises(LLMUnavailable):
        f.complete_json(task="d", system="", prompt="")
    with pytest.raises(AssertionError):
        f.complete_json(task="never_scripted", system="", prompt="")
    assert f.count("a") == 1 and f.count("b") == 3


def test_make_llm_registry():
    assert make_llm("fake", script={}).name == "fake"
    with pytest.raises(ValueError):
        make_llm("nope")
