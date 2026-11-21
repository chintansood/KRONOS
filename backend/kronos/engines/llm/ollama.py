"""Minimal client for the local Ollama server (no data leaves the machine)."""
from __future__ import annotations

import httpx

from ...config import settings


class LLMUnavailable(RuntimeError):
    pass


_avail = {"t": 0.0, "v": False}
_ft = {"t": 0.0, "v": False}


def _ft_up() -> bool:
    """Is the local fine-tuned model server (mlx_lm.server, OpenAI-compatible) reachable? Cached for 30 s."""
    import time
    if settings.llm_backend == "ollama":
        return False
    if time.time() - _ft["t"] < 30:
        return _ft["v"]
    try:
        v = httpx.get(f"{settings.llm_url}/models", timeout=1.0).status_code == 200
    except Exception:  # noqa: BLE001
        v = False
    _ft.update(t=time.time(), v=v)
    return v


def model_name() -> str:
    return settings.llm_ft_name if _ft_up() else settings.llm_model


def available() -> bool:
    if _ft_up():
        return True
    """LLM availability, cached for 30 s and checked with a short timeout so that health checks never block
    on a busy model."""
    import time
    if time.time() - _avail["t"] < 30:
        return _avail["v"]
    try:
        r = httpx.get(f"{settings.ollama_url}/api/tags", timeout=1.0)
        names = {m["name"] for m in r.json().get("models", [])}
        v = settings.llm_model in names or settings.llm_model.split(":")[0] in {n.split(":")[0] for n in names}
    except Exception:  # noqa: BLE001
        v = _avail["v"]          # keep last known state on a transient timeout
    _avail.update(t=time.time(), v=v)
    return v


def _chat_openai(messages: list[dict], temperature: float, max_tokens: int, json_mode: bool) -> str:
    msgs = [dict(m) for m in messages]
    if json_mode:     # no server-side JSON grammar: ask for it and cut the object out of the reply
        msgs[0]["content"] += "\nRespond with one JSON object only, no other text."
    body = {"messages": msgs, "temperature": temperature, "max_tokens": max_tokens,
            "repetition_penalty": 1.15, "repetition_context_size": 128}
    try:
        r = httpx.post(f"{settings.llm_url}/chat/completions", json=body, timeout=settings.llm_timeout_s)
        r.raise_for_status()
        out = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        raise LLMUnavailable(str(e)) from e
    if json_mode:
        import re
        m = re.search(r"\{.*\}", out, re.S)
        out = m.group(0) if m else "{}"
    return out


def chat(messages: list[dict], temperature: float = 0.1, max_tokens: int = 700, json_mode: bool = False) -> str:
    if settings.llm_backend == "openai" or (settings.llm_backend == "auto" and _ft_up()):
        return _chat_openai(messages, temperature, max_tokens, json_mode)
    body = {"model": settings.llm_model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_ctx": settings.llm_context_tokens, "num_predict": max_tokens,
                        "seed": 7, "repeat_penalty": 1.15, "repeat_last_n": 128}}
    if json_mode:
        body["format"] = "json"
    try:
        r = httpx.post(f"{settings.ollama_url}/api/chat", json=body, timeout=settings.llm_timeout_s)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()
    except Exception as e:  # noqa: BLE001
        raise LLMUnavailable(str(e)) from e


def embed(texts: list[str]) -> list[list[float]]:
    try:
        r = httpx.post(f"{settings.ollama_url}/api/embed", json={"model": settings.embed_model, "input": texts},
                       timeout=settings.llm_timeout_s)
        r.raise_for_status()
        return r.json()["embeddings"]
    except Exception as e:  # noqa: BLE001
        raise LLMUnavailable(str(e)) from e


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
