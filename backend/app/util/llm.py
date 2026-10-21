"""OpenAI-compatible completions, tool calls and streamed output.

Reserve tokens for reasoning, preserve provider-specific output limits, and retry
explicitly rejected optional parameters. Both token-limit fields are sent to
compatible and local servers because some silently ignore unknown fields.
"""

from __future__ import annotations

import re

import contextvars
import json
import time
from typing import AsyncIterator

import httpx

from ..database import store
from . import providers


CONNECT_TIMEOUT = 10.0
TIMEOUT = httpx.Timeout(300.0, connect=CONNECT_TIMEOUT)
STREAM_TIMEOUT = httpx.Timeout(600.0, connect=CONNECT_TIMEOUT)


NOT_CONFIGURED = (
    'No model configured — open Settings: choose “Local model” and enter the address and model name (local Ollama is http://127.0.0.1:11434/v1), or choose “OpenAI compatible” and enter a key'
)


def describe_error(exc: BaseException) -> str:
    base = ""
    try:
        if not store.llm_configured()["configured"]:

            return NOT_CONFIGURED
        base = store.get_active_llm_config()["base_url"]
    except Exception:      # noqa: BLE001
        pass
    where = f"（{base}）" if base else ""
    if isinstance(exc, httpx.ConnectTimeout):
        return f'Could not connect within {int(CONNECT_TIMEOUT)} seconds to the model service{where}. Check the provider endpoint in Settings.'
    if isinstance(exc, httpx.ConnectError):
        return f'The model service refused the connection{where}. Check the provider endpoint in Settings and confirm that the service is running.'
    if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return f'The model service timed out{where}. Retry later or choose another provider.'
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return 'The model service rejected the API key or permissions. Check Settings.'
        if code == 429:
            return 'The model service rate limit was reached. Retry later.'
        if code == 404:
            return f'The model endpoint or model was not found{where}. Check the endpoint and model name in Settings.'
        if code == 400:


            try:
                payload = exc.response.json()
                detail = " ".join(str((payload.get("error") or {}).get("message") or "").split())
            except (ValueError, AttributeError, httpx.ResponseNotRead):
                detail = ""
            detail = re.sub(r"https?://\S+", '[address]', detail)
            detail = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[key]", detail)
            if detail:
                return f'The model service rejected the request: {detail[:180]}'
            return f'The model service returned 400{where}'
        if code >= 500:
            return f'The model service returned {code}{where}. The provider may be unavailable; retry later.'
        return f'The model service returned {code}{where}'
    if isinstance(exc, httpx.HTTPError):
        return f'Connection to the model service failed{where}：{type(exc).__name__}'
    text = str(exc).strip() or type(exc).__name__
    return text[:200]


def _headers(config: dict | None = None) -> dict[str, str]:
    cfg = config or store.get_active_llm_config()
    return {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}


REASONING_RESERVE = 600


_DATA_URI = re.compile(r"\]\(data:[a-zA-Z0-9.+/-]+;base64,[^)\s]{16,}\)")


def sanitize_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, str) and "data:" in c:
            m = {**m, "content": _DATA_URI.sub('](embedded image)', c)}
        out.append(m)
    return out


ctx_user: contextvars.ContextVar[str] = contextvars.ContextVar("llm_user", default="")
ctx_feature: contextvars.ContextVar[str] = contextvars.ContextVar("llm_feature", default="")


ctx_cache_key: contextvars.ContextVar[str] = contextvars.ContextVar("llm_cache_key", default="")


def set_cache_key(note_id: str, mode_key: str) -> None:
    ctx_cache_key.set(f"{(note_id or '-')[:40]}:{(mode_key or '-')[:24]}")


def _cache_key() -> str:
    base = ctx_cache_key.get()
    if not base:
        return ""
    step = (ctx_feature.get() or "").rsplit(":", 1)[-1]
    return f"{base}:{step}" if step else base


def _cached_of(usage: dict) -> tuple[int, int]:
    for key in ("prompt_tokens_details", "input_tokens_details"):
        d = usage.get(key)
        if isinstance(d, dict):
            return int(d.get("cached_tokens") or 0), int(d.get("cache_write_tokens") or 0)
    return 0, 0


ctx_usage_sink: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "llm_usage_sink", default=None)


def bind_usage_sink(sink: dict) -> None:
    ctx_usage_sink.set(sink)


def _tally(u: dict) -> None:
    sink = ctx_usage_sink.get()
    if sink is None:
        return
    cached, _write = _cached_of(u)
    sink["calls"] = sink.get("calls", 0) + 1
    sink["prompt_tokens"] = sink.get("prompt_tokens", 0) + int(u.get("prompt_tokens") or 0)
    sink["completion_tokens"] = (sink.get("completion_tokens", 0)
                                 + int(u.get("completion_tokens") or 0))
    sink["cached_tokens"] = sink.get("cached_tokens", 0) + cached


def _record(usage: dict | None, model: str, t0: float) -> None:
    try:
        _tally(usage or {})
    except Exception:                                      # noqa: BLE001


        sink = ctx_usage_sink.get()
        if sink is not None:
            sink["tally_error"] = sink.get("tally_error", 0) + 1
    try:
        u = usage or {}
        cached, cache_write = _cached_of(u)
        store.record_llm_usage(ctx_user.get() or "", ctx_feature.get() or "", model,
                               int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0),
                               int((time.perf_counter() - t0) * 1000),
                               cached_tokens=cached, cache_write_tokens=cache_write)
    except Exception:      # noqa: BLE001
        pass


def _payload(messages: list[dict], *, stream: bool, max_tokens: int,
             temperature: float, effort: str,
             tools: list[dict] | None = None,
             config: dict | None = None) -> dict:
    cfg = config or store.get_active_llm_config()
    body = {
        "model": cfg["model"],
        "messages": sanitize_messages(messages),
        # Reserve additional budget for reasoning beyond the requested output.
        "max_completion_tokens": max_tokens + REASONING_RESERVE,
        "temperature": temperature,
        "stream": stream,
    }

    # Compatible servers may silently ignore an unknown limit field. Send both
    # and remove one only when the server explicitly rejects it.
    if providers.family_for(cfg) != "openai":
        body["max_tokens"] = max_tokens + REASONING_RESERVE

    body["reasoning_effort"] = effort
    key = _cache_key()
    if key:


        body["prompt_cache_key"] = key
    if stream:
        body["stream_options"] = {"include_usage": True}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    return body


def _rejects_effort_with_tools(status_code: int, body: bytes) -> bool:
    if status_code != 400:
        return False
    try:
        err = json.loads(body).get("error") or {}
    except (json.JSONDecodeError, AttributeError):
        return False
    return (err.get("param") == "reasoning_effort"
            and "tool" in str(err.get("message", "")).lower())


def _rejects_cache_key(status_code: int, body: bytes) -> bool:
    if status_code != 400:
        return False
    try:
        err = json.loads(body).get("error") or {}
    except (json.JSONDecodeError, AttributeError):
        return False
    return err.get("param") == "prompt_cache_key"


def rejects_max_tokens(status_code: int, body: bytes) -> bool:
    if status_code != 400:
        return False
    try:
        err = json.loads(body).get("error") or {}
    except (json.JSONDecodeError, AttributeError):
        err = {}
    if err:
        return err.get("param") == "max_tokens"
    return b"max_completion_tokens" in body


def swap_to_max_completion_tokens(payload: dict) -> bool:
    if "max_tokens" not in payload:
        return False
    payload["max_completion_tokens"] = payload.pop("max_tokens")
    return True


def _rejects_temperature(status_code: int, body: bytes) -> bool:
    if status_code != 400:
        return False
    try:
        err = json.loads(body).get("error") or {}
    except (json.JSONDecodeError, AttributeError):
        return False
    if err.get("param") != "temperature":
        return False


    if err.get("code") == "unsupported_value":
        return True
    message = str(err.get("message") or "").lower()
    return ("unsupported value" in message
            and "temperature" in message
            and ("default" in message or "does not support" in message))


def drop_unsupported_temperature(payload: dict, status_code: int, body: bytes) -> bool:
    if not _rejects_temperature(status_code, body) or "temperature" not in payload:
        return False
    payload.pop("temperature")
    return True


def _drop_rejected_param(payload: dict, status_code: int, body: bytes) -> bool:
    if "reasoning_effort" in payload and _rejects_reasoning_effort(status_code, body):
        payload.pop("reasoning_effort")
        return True
    if "prompt_cache_key" in payload and _rejects_cache_key(status_code, body):
        payload.pop("prompt_cache_key", None)
        return True
    if drop_unsupported_temperature(payload, status_code, body):
        return True


    if rejects_max_tokens(status_code, body) and "max_completion_tokens" in payload:
        payload.pop("max_tokens", None)
        return True
    if _rejects_max_completion_tokens(status_code, body) and "max_tokens" in payload:
        payload.pop("max_completion_tokens", None)
        return True
    return False


def _rejects_reasoning_effort(status_code: int, body: bytes) -> bool:
    if status_code != 400:
        return False
    try:
        error = json.loads(body).get("error") or {}
    except (json.JSONDecodeError, AttributeError):
        return False
    if not isinstance(error, dict):
        return False
    if error.get("param") == "reasoning_effort":
        return True
    message = str(error.get("message") or "").lower()
    return bool(re.search(
        r"(?:unrecognized request argument supplied|unsupported parameter)"
        r"\s*:\s*['\"]?reasoning_effort\b", message))


_PARAM_RETRY_LIMIT = 5


def _rejects_max_completion_tokens(status_code: int, body: bytes) -> bool:
    if status_code != 400:
        return False
    try:
        err = json.loads(body).get("error") or {}
    except (json.JSONDecodeError, AttributeError):
        return False
    return err.get("param") == "max_completion_tokens"


rejects_max_completion_tokens = _rejects_max_completion_tokens
"""Public name: `routers/settings.probe_endpoint` sends `max_completion_tokens` first for the `openai`
family; if the other side only accepts `max_tokens` (a custom endpoint put in the wrong tier), it uses this to
switch back and retry once."""


async def complete(messages: list[dict], *, max_tokens: int = 1500,
                   temperature: float = 0.3, effort: str = "low",
                   stats: dict | None = None,
                   config: dict | None = None) -> str:
    cfg = config or store.get_active_llm_config()
    payload = _payload(messages, stream=False, max_tokens=max_tokens,
                       temperature=temperature, effort=effort, config=cfg)
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for _ in range(_PARAM_RETRY_LIMIT):
            r = await client.post(f"{cfg['base_url']}/chat/completions",
                                  headers=_headers(cfg), json=payload)
            if not _drop_rejected_param(payload, r.status_code, r.content):
                break
        r.raise_for_status()
        data = r.json()
    _record(data.get("usage"), cfg["model"], t0)
    if stats is not None and data.get("choices") and data["choices"][0].get("finish_reason"):
        stats["finish_reason"] = data["choices"][0]["finish_reason"]
    return (data["choices"][0]["message"].get("content") or "").strip()


async def complete_json(messages: list[dict], *, max_tokens: int = 1500,
                        temperature: float = 0.3, effort: str = "low",
                        cap: int = 4000) -> dict | list | None:
    parsed, _text = await complete_json_raw(messages, max_tokens=max_tokens,
                                            temperature=temperature, effort=effort, cap=cap)
    return parsed


async def complete_json_raw(messages: list[dict], *, max_tokens: int = 1500,
                            temperature: float = 0.3, effort: str = "low",
                            cap: int = 4000) -> tuple[dict | list | None, str]:
    budget = max_tokens
    text = ""
    for _attempt in range(2):
        stats: dict = {}
        text = await complete(messages, max_tokens=budget, temperature=temperature,
                              effort=effort, stats=stats)
        if stats.get("finish_reason") != "length" or budget >= cap:
            break
        budget = min(budget * 2, cap)
    return extract_json(text), text


async def complete_raw(messages: list[dict], *, max_tokens: int = 1500,
                       temperature: float = 0.3, effort: str = "low",
                       tools: list[dict] | None = None) -> dict:
    cfg = store.get_active_llm_config()
    payload = _payload(messages, stream=False, max_tokens=max_tokens,
                       temperature=temperature, effort=effort, tools=tools)
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for _ in range(_PARAM_RETRY_LIMIT):
            r = await client.post(f"{cfg['base_url']}/chat/completions",
                                  headers=_headers(), json=payload)
            if payload.get("reasoning_effort") not in (None, "none") and _rejects_effort_with_tools(r.status_code, r.content):


                payload["reasoning_effort"] = "none"
                continue
            if _drop_rejected_param(payload, r.status_code, r.content):
                continue
            break
        if r.status_code >= 500:


            r = await client.post(f"{cfg['base_url']}/chat/completions",
                                  headers=_headers(), json=payload)
        r.raise_for_status()
        data = r.json()
    _record(data.get("usage"), cfg["model"], t0)
    msg = data["choices"][0]["message"]


    out: dict = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        out["tool_calls"] = msg["tool_calls"]
    return out


async def stream(messages: list[dict], *, max_tokens: int = 1200,
                 temperature: float = 0.7, effort: str = "low",
                 stats: dict | None = None) -> AsyncIterator[str]:
    cfg = store.get_active_llm_config()
    payload = _payload(messages, stream=True, max_tokens=max_tokens,
                       temperature=temperature, effort=effort)
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=STREAM_TIMEOUT) as client:
        url = f"{cfg['base_url']}/chat/completions"
        for _ in range(_PARAM_RETRY_LIMIT):
            async with client.stream("POST", url, headers=_headers(), json=payload) as response:


                if response.is_error:
                    body = await response.aread()
                    if _drop_rejected_param(payload, response.status_code, body):
                        continue
                response.raise_for_status()
                async for piece in _consume_sse(response, stats, model=cfg["model"], t0=t0):
                    yield piece
                return


async def stream_events(messages: list[dict], *, max_tokens: int = 1200,
                        temperature: float = 0.3, effort: str = "low",
                        ) -> AsyncIterator[tuple[str, str]]:
    cfg = store.get_active_llm_config()
    t0 = time.perf_counter()
    payload = _payload(messages, stream=True, max_tokens=max_tokens,
                       temperature=temperature, effort=effort)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        url = f"{cfg['base_url']}/chat/completions"
        for _ in range(_PARAM_RETRY_LIMIT):
            async with client.stream("POST", url, headers=_headers(), json=payload) as response:
                if response.is_error:
                    body = await response.aread()
                    if _drop_rejected_param(payload, response.status_code, body):
                        continue
                response.raise_for_status()
                async for ev in _consume_tagged(response, model=cfg["model"], t0=t0):
                    yield ev
                return


async def _consume_tagged(r: httpx.Response, *, model: str = "",
                          t0: float | None = None) -> AsyncIterator[tuple[str, str]]:
    usage: dict | None = None
    async for line in r.aiter_lines():
        if not line.startswith("data: "):
            continue
        chunk = line[6:].strip()
        if chunk == "[DONE]":
            break
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if obj.get("usage"):
            usage = obj["usage"]
        choices = obj.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        think = delta.get("reasoning_content")
        if think:
            yield ("thinking", think)
        piece = delta.get("content")
        if piece:
            yield ("output", piece)
    if t0 is not None:
        _record(usage, model, t0)


async def _consume_sse(r: httpx.Response, stats: dict | None = None, *,
                       model: str = "", t0: float | None = None) -> AsyncIterator[str]:
    usage: dict | None = None
    async for line in r.aiter_lines():
        if not line.startswith("data: "):
            continue
        chunk = line[6:].strip()
        if chunk == "[DONE]":
            break
        try:
            obj = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if obj.get("usage"):
            usage = obj["usage"]
        choices = obj.get("choices") or []
        if not choices:
            continue
        if stats is not None and choices[0].get("finish_reason"):
            stats["finish_reason"] = choices[0]["finish_reason"]
        piece = (choices[0].get("delta") or {}).get("content")
        if piece:
            yield piece
    if t0 is not None:
        _record(usage, model, t0)


def extract_json(text: str) -> dict | list | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.startswith("json"):
            text = text[4:]


    pairs = {"{": "}", "[": "]"}
    starts = [(text.find(o), o) for o in pairs]
    starts = sorted((s for s in starts if s[0] >= 0), key=lambda x: x[0])
    for start, opener in starts:


        stack = [pairs[opener]]
        in_str = False
        escape = False
        end_index = None
        for i in range(start + 1, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in pairs:
                stack.append(pairs[ch])
            elif stack and ch == stack[-1]:
                stack.pop()
                if not stack:
                    end_index = i
                    break
        if end_index is not None:
            try:
                return json.loads(text[start:end_index + 1])
            except json.JSONDecodeError:
                continue
        if stack:
            # Ran out of text with brackets still open -- the model's own
            # output got cut off before the final bracket(s), observed for
            # real (not hypothetical) even on short, otherwise-valid-looking
            # responses, not just ones truncated by hitting max_tokens.
            # Close the dangling string (if any), then every still-open
            # bracket innermost-first (the stack is already in that order),
            # and retry once.
            repaired = text[start:]
            if in_str:
                repaired += '"'
            repaired += "".join(reversed(stack))
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                continue
    return None
