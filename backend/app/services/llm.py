"""Optional local LLM through any OpenAI-compatible server – free and open source:

* Ollama        (default)  http://localhost:11434/v1   e.g. `ollama pull qwen2.5:3b`
* LM Studio               http://localhost:1234/v1
* llama.cpp server         http://localhost:8080/v1

Nothing here is required: when no server answers, callers fall back to the
deterministic engine. Only the minimum text needed is sent, and by default it
never leaves your machine (the base URL is localhost).
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from ..config import get_settings

log = logging.getLogger("hisaab.llm")
_status_cache: dict = {"at": 0.0, "value": None}


class LLMUnavailable(RuntimeError):
    pass


def _request(path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
    s = get_settings()
    url = f"{s.llm_base_url}{path}"
    headers = {"Content-Type": "application/json"}
    if s.llm_api_key:
        headers["Authorization"] = f"Bearer {s.llm_api_key}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout or s.llm_timeout) as resp:  # noqa: S310 - configured URL
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise LLMUnavailable(f"LLM server error {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise LLMUnavailable(f"LLM server not reachable at {s.llm_base_url} ({exc})") from exc


def is_local() -> bool:
    host = urlparse(get_settings().llm_base_url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local")


def status(force: bool = False) -> dict:
    s = get_settings()
    if not s.llm_enabled:
        return {"enabled": False, "available": False, "reason": "LLM_ENABLED=false"}
    now = time.monotonic()
    if not force and _status_cache["value"] is not None and now - _status_cache["at"] < 30:
        return _status_cache["value"]
    try:
        models = [m.get("id") for m in _request("/models", timeout=2).get("data", [])]
        available = s.llm_model in models or any(m and m.split(":")[0] == s.llm_model.split(":")[0] for m in models)
        value = {"enabled": True, "available": available, "base_url": s.llm_base_url, "model": s.llm_model, "installed_models": models,
                 "local": is_local(), "reason": None if available else f"Model '{s.llm_model}' is not installed. Run: ollama pull {s.llm_model}"}
    except LLMUnavailable as exc:
        value = {"enabled": True, "available": False, "base_url": s.llm_base_url, "model": s.llm_model, "local": is_local(), "reason": str(exc)}
    _status_cache.update(at=now, value=value)
    return value


def chat(messages: list[dict], tools: list[dict] | None = None, json_mode: bool = False, temperature: float = 0.1) -> dict:
    """One chat completion; returns the assistant message dict (may contain tool_calls)."""
    s = get_settings()
    payload: dict = {"model": s.llm_model, "messages": messages, "temperature": temperature, "stream": False}
    if tools:
        payload["tools"] = tools
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = _request("/chat/completions", payload)
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise LLMUnavailable("Unexpected response from the LLM server") from exc


def categorize(items: list[dict], category_names: list[str]) -> list[dict]:
    """Ask the model to pick a category (from the given list only) for each narration.

    items: [{"id": 1, "text": "UPI/…/SWIGGY", "amount": "340.00", "type": "expense"}]
    returns: [{"id": 1, "category": "Food/Food delivery", "merchant": "Swiggy", "confidence": 0.8}]
    """
    system = (
        "You categorise Indian bank transactions. Choose exactly one category for each item from the allowed list "
        "(copy it verbatim) and extract a short clean merchant name. If unsure use 'Other'. Reply with JSON: "
        '{"results": [{"id": <id>, "category": "<allowed>", "merchant": "<name or empty>", "confidence": <0-1>}]}'
    )
    user = json.dumps({"allowed_categories": category_names, "items": items}, ensure_ascii=False)
    message = chat([{"role": "system", "content": system}, {"role": "user", "content": user}], json_mode=True)
    try:
        content = message.get("content") or "{}"
        content = content[content.find("{"): content.rfind("}") + 1]
        results = json.loads(content).get("results", [])
    except ValueError as exc:
        raise LLMUnavailable("The model did not return valid JSON") from exc
    allowed = {c.lower(): c for c in category_names}
    clean = []
    for r in results:
        cat = allowed.get(str(r.get("category", "")).strip().lower())
        if cat is None:
            continue  # never accept a category the user doesn't have
        try:
            conf = max(0.0, min(1.0, float(r.get("confidence", 0.6))))
        except (TypeError, ValueError):
            conf = 0.6
        clean.append({"id": r.get("id"), "category": cat, "merchant": str(r.get("merchant") or "")[:80], "confidence": conf})
    return clean
