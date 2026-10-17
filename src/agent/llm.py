"""LLM access for the agent (C1).

One small interface, `LLM.complete_json(task, system, prompt)`, so a provider can be swapped:

* `GeminiLLM`  : Gemini through the REST API (free tier). On-disk response cache, clear errors on 429, automatic fallback
                 across a list of Gemini models (each model name has its own free quota), a persistent "quota book" so a
                 model that is out of daily quota is skipped without a request, and a hard budget of live calls.
* `FakeLLM`    : scripted answers for tests. No network.

To add another provider (OpenAI, Claude, a local model): write a class with `name` and `complete_json(...)` that returns
an `LLMResult`, raise the `LLMError` subclasses below on failure, and register it in `PROVIDERS`.

The API key is read from the environment (`GEMINI_API_KEY`, loaded from `.env`). It is never printed, logged or cached.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "processed" / "cache" / "llm"          # gitignored (data/processed/cache/)
QUOTA_FILE = ROOT / "data" / "processed" / "cache" / "gemini_quota.json"

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Order = preference. The first two were used for the A2 vision work on this key. The rest are extra fallbacks:
# every model name has its own free-tier quota, so each one adds capacity. Override with GEMINI_MODELS="a,b,c".
# gemini-2.5-flash answers "no longer available to new users" (live test, 2026-10-14), so the 2.5 models are not in the chain.
DEFAULT_MODELS = (
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)
CACHE_VERSION = "v1"


# --------------------------------------------------------------------------------------------- errors
class LLMError(RuntimeError):
    """Base class for every LLM failure. `str(e)` is a clear message that is safe to show to the user."""


class LLMUnavailable(LLMError):
    """No API key, network down, key rejected, or every model failed for a non-quota reason."""


class LLMRateLimited(LLMError):
    """Every configured model is out of quota (HTTP 429). `per_model` says why, `retry_at` is the earliest reset (epoch seconds)."""

    def __init__(self, message: str, per_model: dict[str, str] | None = None, retry_at: float | None = None):
        super().__init__(message)
        self.per_model = per_model or {}
        self.retry_at = retry_at


class LLMBadResponse(LLMError):
    """The model answered, but not with usable JSON."""


class LLMBudgetExceeded(LLMError):
    """The configured cap on live LLM calls for this process was reached (protects the free quota)."""


# --------------------------------------------------------------------------------------------- interface
@dataclass
class LLMResult:
    data: Any                       # parsed JSON (dict or list)
    model: str                      # model name that produced it (cache hits keep the original model)
    cached: bool = False
    text: str = ""                  # raw text of the answer
    usage: dict = field(default_factory=dict)


class LLM(Protocol):
    name: str

    def complete_json(self, *, task: str, system: str, prompt: str, temperature: float = 0.0) -> LLMResult:
        """Return the model's answer parsed as JSON. Raises an LLMError subclass on failure."""
        ...


def parse_json_text(text: str) -> Any:
    """Parse a model answer as JSON. Tolerates code fences and prose around one JSON value. Raises ValueError."""
    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON value found")
    i = min(starts)
    closer = "}" if s[i] == "{" else "]"
    j = s.rfind(closer)
    if j <= i:
        raise ValueError("unterminated JSON value")
    return json.loads(s[i:j + 1])


# --------------------------------------------------------------------------------------------- cache
class ResponseCache:
    """Files under data/processed/cache/llm/. Key = hash of (version, task, system, prompt, temperature), NOT of the
    model: an answer obtained from any Gemini model serves later identical requests (the model is stored inside)."""

    def __init__(self, directory: Path | str | None = CACHE_DIR, enabled: bool = True):
        self.dir = Path(directory) if directory else None
        self.enabled = bool(enabled and self.dir)

    @staticmethod
    def key(task: str, system: str, prompt: str, temperature: float) -> str:
        blob = json.dumps([CACHE_VERSION, task, system, prompt, round(float(temperature), 3)], ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        if not self.enabled:
            return None
        p = self._path(key)
        try:
            return json.loads(p.read_text(encoding="utf8"))
        except (OSError, ValueError):
            return None

    def put(self, key: str, entry: dict) -> None:
        if not self.enabled:
            return
        p = self._path(key)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf8") as f:
                json.dump(entry, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
        except OSError:
            pass   # a cache that cannot be written must never break an answer


# --------------------------------------------------------------------------------------------- quota book
def _nth_sunday(year: int, month: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    first = d + dt.timedelta(days=(6 - d.weekday()) % 7)
    return first + dt.timedelta(weeks=n - 1)


def _pacific_offset_hours(utc: dt.datetime) -> int:
    """-7 during US daylight saving time (2nd Sunday of March 02:00 to 1st Sunday of November 02:00), else -8."""
    start = dt.datetime.combine(_nth_sunday(utc.year, 3, 2), dt.time(10, 0), tzinfo=dt.timezone.utc)
    end = dt.datetime.combine(_nth_sunday(utc.year, 11, 1), dt.time(9, 0), tzinfo=dt.timezone.utc)
    return -7 if start <= utc < end else -8


def next_daily_reset(now_epoch: float) -> float:
    """Epoch seconds of the next midnight Pacific time (Google resets daily free-tier quotas then). No tzdata needed."""
    utc = dt.datetime.fromtimestamp(now_epoch, dt.timezone.utc)
    off = _pacific_offset_hours(utc)
    local = utc + dt.timedelta(hours=off)
    midnight = dt.datetime(local.year, local.month, local.day) + dt.timedelta(days=1)
    return (midnight - dt.timedelta(hours=off)).replace(tzinfo=dt.timezone.utc).timestamp()


class QuotaBook:
    """Remembers, across processes, which models are out of quota and until when (a small JSON file).

    This only avoids pointless requests. If the real quota resets earlier than the book says, set
    GEMINI_IGNORE_QUOTA_BOOK=1 (or delete data/processed/cache/gemini_quota.json)."""

    def __init__(self, path: Path | str | None = QUOTA_FILE, clock: Callable[[], float] = time.time):
        self.path = Path(path) if path else None
        self.clock = clock
        self.ignore = os.environ.get("GEMINI_IGNORE_QUOTA_BOOK", "").strip() in ("1", "true", "yes")
        self._mem: dict[str, dict] = {}

    def _load(self) -> dict:
        data = dict(self._mem)
        if self.path:
            try:
                data = {**json.loads(self.path.read_text(encoding="utf8")), **data}
            except (OSError, ValueError):
                pass
        return data

    def blocked(self, model: str) -> dict | None:
        if self.ignore:
            return None
        e = self._load().get(model)
        if e and float(e.get("until", 0)) > self.clock():
            return e
        return None

    def mark(self, model: str, until: float, reason: str) -> None:
        self._mem[model] = {"until": float(until), "reason": reason, "marked_at": self.clock()}
        if not self.path or self.ignore:
            return
        try:
            data = {}
            try:
                data = json.loads(self.path.read_text(encoding="utf8"))
            except (OSError, ValueError):
                pass
            now = self.clock()
            data = {m: e for m, e in data.items() if float(e.get("until", 0)) > now}   # drop expired entries
            data[model] = self._mem[model]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=1), encoding="utf8")
        except OSError:
            pass

    def clear(self) -> None:
        self._mem.clear()
        if self.path:
            try:
                self.path.unlink()
            except OSError:
                pass


def _fmt_epoch(ts: float | None) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "unknown"


# --------------------------------------------------------------------------------------------- Gemini
class _Skip(Exception):
    """This model cannot serve the request right now; try the next one. `rate_limited` marks quota problems."""

    def __init__(self, reason: str, rate_limited: bool = False, until: float | None = None):
        super().__init__(reason)
        self.reason, self.rate_limited, self.until = reason, rate_limited, until


def _error_body(resp) -> dict:
    try:
        body = resp.json()
    except Exception:
        return {}
    return body.get("error", body) if isinstance(body, dict) else {}


def parse_429(resp) -> tuple[bool, float | None, str]:
    """(daily_quota_exhausted, retry_after_seconds, message) from a Gemini 429 response."""
    err = _error_body(resp)
    msg = str(err.get("message") or getattr(resp, "text", "") or "rate limited")[:300]
    daily, retry = False, None
    for d in err.get("details") or []:
        if not isinstance(d, dict):
            continue
        for v in d.get("violations") or []:
            if "perday" in str(v.get("quotaId", "")).lower().replace("_", "").replace("-", ""):
                daily = True
        m = re.fullmatch(r"\s*([\d.]+)\s*s\s*", str(d.get("retryDelay", "")))
        if m:
            retry = float(m.group(1))
    low = msg.lower()
    if "per day" in low or "daily" in low or "perday" in low:
        daily = True
    if retry is None:
        m = re.search(r"retry in ([\d.]+)\s*s", low)
        if m:
            retry = float(m.group(1))
    return daily, retry, msg


class GeminiLLM:
    """Gemini via REST. See the module docstring. `post(url, headers=..., json=..., timeout=...)` is injectable for tests."""

    name = "gemini"

    def __init__(self, api_key: str | None = None, models: list[str] | tuple[str, ...] | None = None, *,
                 cache: bool = True, cache_dir: Path | str | None = None, post: Callable | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.time,
                 max_calls: int | None = None, max_failures: int = 30, quota_book: QuotaBook | None = None,
                 timeout: float = 180.0, max_wait_s: float = 25.0):
        self._api_key = api_key
        env_models = os.environ.get("GEMINI_MODELS", "")
        self.models = list(models) if models else ([m.strip() for m in env_models.split(",") if m.strip()] or list(DEFAULT_MODELS))
        self.cache = ResponseCache(cache_dir or CACHE_DIR, enabled=cache)
        self._post = post
        self._sleep, self._clock = sleep, clock
        self.max_calls, self.max_failures = max_calls, max_failures
        self.quota = quota_book if quota_book is not None else QuotaBook(clock=clock)
        self.timeout, self.max_wait_s = timeout, max_wait_s
        self.cooldown_s = 90.0
        self._cool: dict[str, float] = {}       # model -> epoch until which it is tried last (it just failed for a non-quota reason)
        self.stats = {"live_calls": 0, "failed_requests": 0, "cache_hits": 0, "by_model": {}, "log": []}

    # ---- key / http
    def _key(self) -> str:
        if self._api_key:
            return self._api_key
        try:
            from dotenv import load_dotenv

            load_dotenv(ROOT / ".env")
        except Exception:
            pass
        k = os.environ.get("GEMINI_API_KEY", "").strip()
        if not k:
            raise LLMUnavailable("GEMINI_API_KEY is not set. Copy .env.example to .env and put your Gemini key in it "
                                 "(the file is gitignored; never commit a key).")
        self._api_key = k
        return k

    def _http_post(self, url, headers, body):
        post = self._post
        if post is None:
            import requests

            post = requests.post
        return post(url, headers=headers, json=body, timeout=self.timeout)

    # ---- one model
    def _call_model(self, model: str, system: str, prompt: str, temperature: float) -> tuple[Any, str, dict]:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
        }
        headers = {"x-goog-api-key": self._key(), "content-type": "application/json"}
        url = GEMINI_URL.format(model=model)
        attempts = 0
        while True:
            attempts += 1
            if self.max_calls is not None and self.stats["live_calls"] >= self.max_calls:
                raise LLMBudgetExceeded(f"live LLM call budget reached ({self.max_calls} calls this run); nothing more was sent")
            if self.stats["failed_requests"] >= self.max_failures:
                raise LLMUnavailable(f"too many failed LLM requests ({self.max_failures}); stopping to protect the quota")
            try:
                resp = self._http_post(url, headers, body)
            except Exception as e:     # network problems (requests.RequestException and friends)
                self.stats["failed_requests"] += 1
                if attempts < 2:
                    self._sleep(2.0)
                    continue
                raise _Skip(f"network error: {type(e).__name__}")
            status = resp.status_code
            if status == 200:
                self.stats["live_calls"] += 1
                self.stats["by_model"][model] = self.stats["by_model"].get(model, 0) + 1
                return self._parse_ok(resp, model)
            self.stats["failed_requests"] += 1
            if status == 429:
                daily, retry, msg = parse_429(resp)
                if daily:
                    until = next_daily_reset(self._clock())
                    raise _Skip(f"daily free-tier quota used up ({msg[:120]})", True, until)
                if attempts < 2 and retry is not None and retry <= self.max_wait_s:
                    self._sleep(retry + 0.5)
                    continue
                until = self._clock() + (retry if retry is not None else 60.0)
                raise _Skip(f"per-minute rate limit ({msg[:120]})", True, until)
            if status in (500, 502, 503, 504):
                if attempts < 2:
                    self._sleep(3.0)
                    continue
                raise _Skip(f"server error {status}: {_error_body(resp).get('message', '')[:120]}")
            err = _error_body(resp)
            msg = str(err.get("message", ""))[:200]
            if status == 404:
                raise _Skip(f"model not available for this key ({msg})")
            if status in (400, 401, 403) and re.search(r"api key|permission|unauthenticated|credential", msg, re.I):
                raise LLMUnavailable(f"Gemini rejected the API key ({status}). Check GEMINI_API_KEY in .env.")
            raise _Skip(f"http {status}: {msg}")

    def _parse_ok(self, resp, model: str):
        try:
            data = resp.json()
        except Exception:
            raise _Skip("answer was not JSON at the HTTP level")
        cands = data.get("candidates") or []
        if not cands:
            block = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise _Skip(f"no answer ({block})")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        if not text.strip():
            raise _Skip(f"empty answer (finishReason {cands[0].get('finishReason', '?')})")
        try:
            parsed = parse_json_text(text)
        except ValueError as e:
            raise _Skip(f"answer was not valid JSON ({e})")
        return parsed, text, dict(data.get("usageMetadata") or {})

    def _ordered_models(self) -> list[str]:
        """Models that failed recently (503, timeout, bad JSON) go to the back of the line instead of being tried first again."""
        now = self._clock()
        return [m for m in self.models if self._cool.get(m, 0) <= now] + [m for m in self.models if self._cool.get(m, 0) > now]

    # ---- public
    def complete_json(self, *, task: str, system: str, prompt: str, temperature: float = 0.0) -> LLMResult:
        key = self.cache.key(task, system, prompt, temperature)
        hit = self.cache.get(key)
        if hit is not None:
            self.stats["cache_hits"] += 1
            return LLMResult(data=hit["response"], model=hit.get("model", "?"), cached=True, text=hit.get("text", ""), usage=hit.get("usage", {}))
        problems: dict[str, str] = {}
        rate_limited: dict[str, str] = {}
        retry_at: list[float] = []
        for model in self._ordered_models():
            blocked = self.quota.blocked(model)
            if blocked:
                problems[model] = f"skipped, quota used up until {_fmt_epoch(blocked['until'])} ({blocked.get('reason', '')[:80]})"
                rate_limited[model] = problems[model]
                retry_at.append(float(blocked["until"]))
                continue
            try:
                parsed, text, usage = self._call_model(model, system, prompt, temperature)
            except _Skip as s:
                problems[model] = s.reason
                self.stats["log"].append(f"{model}: {s.reason}")
                if s.rate_limited:
                    rate_limited[model] = s.reason
                    if s.until:
                        retry_at.append(s.until)
                        self.quota.mark(model, s.until, s.reason)
                else:
                    self._cool[model] = self._clock() + (3600.0 if "not available" in s.reason else self.cooldown_s)
                continue
            self._cool.pop(model, None)
            self.cache.put(key, {"task": task, "model": model, "response": parsed, "text": text, "usage": usage,
                                 "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "system": system, "prompt": prompt,
                                 "temperature": temperature})
            return LLMResult(data=parsed, model=model, cached=False, text=text, usage=usage)
        detail = "; ".join(f"{m}: {r}" for m, r in problems.items()) or "no models configured"
        if problems and len(rate_limited) == len(problems):
            when = _fmt_epoch(min(retry_at)) if retry_at else "unknown"
            raise LLMRateLimited(
                "The Gemini free tier is out of quota for every configured model (HTTP 429). "
                f"Nothing was computed. Earliest reset: about {when}. Details: {detail}. "
                "Wait for the reset, or set GEMINI_MODELS to models that still have quota.",
                per_model=rate_limited, retry_at=min(retry_at) if retry_at else None)
        if any("valid JSON" in r or "empty answer" in r or "no answer" in r for r in problems.values()) and not any(
                "not available" in r or "network" in r for r in problems.values()):
            raise LLMBadResponse(f"No Gemini model returned usable JSON. Details: {detail}")
        raise LLMUnavailable(f"No Gemini model could answer. Details: {detail}")

    def available_models(self) -> list[str]:
        """Names of Gemini models that support generateContent for this key (ListModels does not use generation quota)."""
        import requests

        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": self._key()},
                         params={"pageSize": 200}, timeout=60)
        if r.status_code != 200:
            raise LLMUnavailable(f"ListModels failed with HTTP {r.status_code}")
        return sorted(m["name"].split("/", 1)[1] for m in r.json().get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", []))


# --------------------------------------------------------------------------------------------- fake (tests)
class FakeLLM:
    """Scripted LLM for tests. `script[task]` is one of:
        a dict / list-as-JSON      -> returned every time
        a list of such values      -> returned in order; the last one repeats
        a callable(prompt, n)      -> called with the prompt text and the 0-based call index for this task
        an Exception (instance)    -> raised
    A task with no script raises AssertionError, so an unexpected LLM call fails the test loudly.
    Every call is recorded in `.calls` (task, system, prompt)."""

    name = "fake"

    def __init__(self, script: dict[str, Any] | None = None):
        self.script = dict(script or {})
        self.calls: list[dict] = []
        self._n: dict[str, int] = {}

    def count(self, task: str) -> int:
        return sum(1 for c in self.calls if c["task"] == task)

    def complete_json(self, *, task: str, system: str, prompt: str, temperature: float = 0.0) -> LLMResult:
        self.calls.append({"task": task, "system": system, "prompt": prompt})
        n = self._n.get(task, 0)
        self._n[task] = n + 1
        if task not in self.script:
            raise AssertionError(f"FakeLLM got an unexpected '{task}' call")
        item = self.script[task]
        if isinstance(item, list) and item and not isinstance(item, dict):
            # a list of responses (each a dict or exception); a JSON-array answer must be wrapped in a callable
            item = item[min(n, len(item) - 1)]
        if callable(item):
            item = item(prompt, n)
        if isinstance(item, BaseException):
            raise item
        return LLMResult(data=copy.deepcopy(item), model="fake", cached=False, text=json.dumps(item))


# --------------------------------------------------------------------------------------------- DeepSeek
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_CACHE_DIR = ROOT / "data" / "processed" / "cache" / "llm_deepseek"     # separate from Gemini: the cache key has no model name


class DeepSeekLLM:
    """DeepSeek through its OpenAI-style chat API (paid, no daily quota). Key: DEEPSEEK_API_KEY in .env.

    Model: DEEPSEEK_MODEL (default 'deepseek-flash'; 'deepseek-v4-pro' is the bigger one).
    Thinking mode: DEEPSEEK_THINKING = 'disabled' (default, cheaper and faster) or 'enabled'. Keep it the same for every system in one evaluation.
    Own cache folder, and the model and thinking mode are part of the cache key, so another provider's answer is never served as DeepSeek's.
    """

    name = "deepseek"

    def __init__(self, api_key: str | None = None, model: str | None = None, *, thinking: str | None = None, cache: bool = True,
                 cache_dir: Path | str | None = None, post: Callable | None = None, sleep: Callable[[float], None] = time.sleep,
                 max_calls: int | None = None, max_failures: int = 30, timeout: float = 180.0, retries: int = 4,
                 overrides: dict | None = None):
        self._api_key = api_key
        self.overrides = dict(overrides or {})     # task -> {'model': ..., 'thinking': 'enabled'|'disabled'}, for example the Classify step only
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "").strip() or "deepseek-flash"
        self.thinking = (thinking or os.environ.get("DEEPSEEK_THINKING", "").strip() or "disabled").lower()
        if self.thinking not in ("enabled", "disabled"):
            raise ValueError("thinking must be 'enabled' or 'disabled'")
        self.cache = ResponseCache(cache_dir or DEEPSEEK_CACHE_DIR, enabled=cache)
        self._post, self._sleep = post, sleep
        self.max_calls, self.max_failures, self.timeout, self.retries = max_calls, max_failures, timeout, retries
        self.stats = {"live_calls": 0, "failed_requests": 0, "cache_hits": 0, "tokens_in": 0, "tokens_out": 0, "tokens_in_cached": 0, "log": []}

    def _key(self) -> str:
        if self._api_key:
            return self._api_key
        try:
            from dotenv import load_dotenv

            load_dotenv(ROOT / ".env")
        except Exception:
            pass
        k = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not k:
            raise LLMUnavailable("DEEPSEEK_API_KEY is not set. Put it in .env (gitignored; never commit a key).")
        self._api_key = k
        return k

    def complete_json(self, *, task: str, system: str, prompt: str, temperature: float = 0.0) -> LLMResult:
        ov = self.overrides.get(task, {})
        model, thinking = ov.get("model", self.model), ov.get("thinking", self.thinking)
        ckey = self.cache.key(task, system + f"\n#{model}/{thinking}", prompt, temperature)
        hit = self.cache.get(ckey)
        if hit is not None:
            self.stats["cache_hits"] += 1
            return LLMResult(data=hit["response"], model=hit.get("model", "?"), cached=True, text=hit.get("text", ""), usage=hit.get("usage", {}))
        body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"}, "thinking": {"type": thinking}, "stream": False}
        if thinking == "disabled":
            body["temperature"] = temperature
        headers = {"Authorization": f"Bearer {self._key()}", "content-type": "application/json"}
        post = self._post
        if post is None:
            import requests

            post = requests.post
        last = "no attempt"
        for attempt in range(1, self.retries + 1):
            if self.max_calls is not None and self.stats["live_calls"] >= self.max_calls:
                raise LLMBudgetExceeded(f"live LLM call budget reached ({self.max_calls} calls this run); nothing more was sent")
            if self.stats["failed_requests"] >= self.max_failures:
                raise LLMUnavailable(f"too many failed LLM requests ({self.max_failures}); stopping")
            try:
                resp = post(DEEPSEEK_URL, headers=headers, json=body, timeout=self.timeout)
            except Exception as e:
                self.stats["failed_requests"] += 1
                last = f"network error: {type(e).__name__}"
                self._sleep(2.0 * attempt)
                continue
            st = resp.status_code
            if st == 200:
                self.stats["live_calls"] += 1
                try:
                    j = resp.json()
                    text = j["choices"][0]["message"]["content"] or ""
                    usage = j.get("usage") or {}
                    parsed = parse_json_text(text)
                except (ValueError, KeyError, IndexError, TypeError):
                    last = "answer was not valid JSON"
                    self.stats["failed_requests"] += 1
                    continue
                self.stats["tokens_in"] += int(usage.get("prompt_tokens") or 0)
                self.stats["tokens_out"] += int(usage.get("completion_tokens") or 0)
                self.stats["tokens_in_cached"] += int(usage.get("prompt_cache_hit_tokens") or 0)     # DeepSeek's own server-side prefix cache (billed at a fraction of the normal input price)
                self.cache.put(ckey, {"task": task, "model": model, "response": parsed, "text": text,
                                      "usage": {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens")},
                                      "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "system": system, "prompt": prompt,
                                      "temperature": temperature, "thinking": thinking})
                return LLMResult(data=parsed, model=model, cached=False, text=text, usage=usage)
            self.stats["failed_requests"] += 1
            if st in (401, 403):
                raise LLMUnavailable(f"DeepSeek rejected the API key ({st}). Check DEEPSEEK_API_KEY in .env.")
            if st == 402:
                raise LLMRateLimited("DeepSeek balance is empty (HTTP 402). Top up the account, then run again; nothing more was sent.")
            if st in (429, 500, 502, 503, 504):
                last = f"http {st}"
                self._sleep(3.0 * attempt)
                continue
            raise LLMUnavailable(f"DeepSeek http {st}: {resp.text[:200]}")
        raise LLMBadResponse(f"DeepSeek did not give a usable answer after {self.retries} attempts ({last})")


PROVIDERS: dict[str, Callable[..., LLM]] = {"gemini": GeminiLLM, "deepseek": DeepSeekLLM, "fake": FakeLLM}


def make_llm(provider: str = "gemini", **kwargs) -> LLM:
    try:
        return PROVIDERS[provider](**kwargs)
    except KeyError:
        raise ValueError(f"unknown LLM provider '{provider}'; known: {sorted(PROVIDERS)}") from None
