from __future__ import annotations

import json as _json
import time
from collections.abc import Iterator
from typing import Protocol

from ..config import settings
from ..logging_conf import get_logger

log = get_logger("services.llm")


class LLMProvider(Protocol):
    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str: ...

    def stream(self, system: str, prompt: str) -> Iterator[str]:
        ...


def _backoff(resp, attempt: int) -> float:
    if resp is not None:
        retry_after = resp.headers.get("Retry-After") or resp.headers.get(
            "X-RateLimit-Reset"
        )
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except ValueError:
                pass
    return min(1.5 * (2 ** attempt), 30.0)


class MockLLM:

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        # Very small templated synthesis. Real generation happens in the real
        # providers; this just keeps shapes realistic without a key. The report
        # node tolerates non-JSON here and backfills from source snippets.
        head = prompt.strip().splitlines()[0] if prompt.strip() else "the company"
        return (
            f"[mock summary] {head} "
            "Based on the gathered research, the organisation shows a mix of "
            "growth signals and open questions worth probing in the meeting. "
            "Key themes span market position, recent momentum, and leadership."
        )

    def stream(self, system: str, prompt: str) -> Iterator[str]:
        # Emit word-by-word with a tiny delay so the UI exercises its streaming
        # path even offline.
        text = self.complete(system, prompt)
        for word in text.split(" "):
            yield word + " "
            time.sleep(0.03)


class AnthropicLLM:
    def __init__(self) -> None:
        import anthropic  # imported lazily so the mock path needs no SDK

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for the anthropic provider")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.resolved_llm_model

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=settings.llm_max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    def stream(self, system: str, prompt: str) -> Iterator[str]:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=settings.llm_max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield text


class OpenAICompatibleLLM:

    def __init__(self) -> None:
        self._base = settings.resolved_openai_base_url
        self._key = settings.resolved_openai_api_key
        self._model = settings.resolved_llm_model
        if not self._key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for remote OpenAI-compatible providers"
            )

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        import httpx

        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            # Optional OpenRouter attribution headers (ignored by others):
            "HTTP-Referer": "http://localhost",
            "X-Title": settings.app_name,
        }
        base_payload = {
            "model": self._model,
            "max_tokens": settings.llm_max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        want_json = json_mode and settings.llm_use_json_mode
        retries = max(1, settings.llm_max_retries)
        last_err: Exception | None = None

        for attempt in range(retries):
            payload = dict(base_payload)
            if want_json:
                payload["response_format"] = {"type": "json_object"}
            try:
                resp = httpx.post(
                    f"{self._base}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=settings.llm_request_timeout,
                )
            except httpx.RequestError as exc:  # network/timeout — retry
                last_err = exc
                wait = _backoff(None, attempt)
                log.warning(
                    "LLM request error (attempt %d/%d): %s — retry in %.1fs",
                    attempt + 1, retries, exc, wait,
                )
                time.sleep(wait)
                continue

            # Rate limited or server hiccup: back off and retry.
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = RuntimeError(f"HTTP {resp.status_code}")
                if attempt < retries - 1:
                    wait = _backoff(resp, attempt)
                    log.warning(
                        "LLM %s from %s (attempt %d/%d) — retry in %.1fs",
                        resp.status_code, self._model, attempt + 1, retries, wait,
                    )
                    time.sleep(wait)
                    continue

            # Model rejected response_format: drop it and retry immediately.
            if want_json and resp.status_code in (400, 422):
                log.info("JSON mode unsupported by %s — retrying as plain text", self._model)
                want_json = False
                continue

            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            content = _extract_message_content(choice.get("message", {}))

            # Free models occasionally return empty content — one retry helps.
            if not content and attempt < retries - 1:
                last_err = RuntimeError("empty content")
                log.warning(
                    "Empty LLM content from %s (finish=%s) — retrying",
                    self._model, choice.get("finish_reason"),
                )
                time.sleep(_backoff(None, attempt))
                continue

            if len(content) < 40:
                log.warning(
                    "Short LLM response from %s (finish_reason=%s): %r",
                    data.get("model", self._model),
                    choice.get("finish_reason"),
                    content[:120],
                )
            return content

        raise RuntimeError(
            f"LLM request to {self._model} failed after {retries} attempts: {last_err}"
        )

    def stream(self, system: str, prompt: str) -> Iterator[str]:
        import httpx

        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": settings.app_name,
        }
        payload = {
            "model": self._model,
            "max_tokens": settings.llm_max_tokens,
            "stream": True,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        got_any = False
        try:
            with httpx.stream(
                "POST",
                f"{self._base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=settings.llm_request_timeout,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if line == "[DONE]":
                        break
                    try:
                        event = _json.loads(line)
                    except ValueError:
                        continue
                    delta = (event.get("choices") or [{}])[0].get("delta", {})
                    chunk = delta.get("content")
                    if chunk:
                        got_any = True
                        yield chunk
        except Exception as exc:  # noqa: BLE001 — fall back to non-streaming
            log.warning("Streaming failed (%s); falling back to single completion", exc)

        # If streaming yielded nothing (model/provider quirk), fall back so the
        # user still gets an answer.
        if not got_any:
            yield self.complete(system, prompt)


def _extract_message_content(message: dict) -> str:
    """Normalise OpenAI / OpenRouter message shapes into plain text."""
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        joined = "".join(parts).strip()
        if joined:
            return joined
    for key in ("reasoning", "reasoning_content"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return content.strip() if isinstance(content, str) else ""


def get_llm() -> LLMProvider:
    provider = settings.resolved_llm_provider
    if provider == "anthropic":
        log.info("Using Anthropic LLM provider (%s)", settings.resolved_llm_model)
        return AnthropicLLM()
    if provider == "openai":
        log.info(
            "Using OpenAI-compatible provider (%s @ %s)",
            settings.resolved_llm_model,
            settings.resolved_openai_base_url,
        )
        return OpenAICompatibleLLM()
    log.info("Using mock LLM provider (no API keys or local URL configured)")
    return MockLLM()
