"""
LLM Client - Opencode Zen gateway integration.

Endpoint per model family (from https://opencode.ai/zen):
- Claude models  -> /zen/v1/messages       (Anthropic format)
- GPT-5 models   -> /zen/v1/responses       (OpenAI Responses format)
- Other models   -> /zen/v1/chat/completions (OpenAI-compatible)

Auth: Authorization: Bearer <OPENCODE_API_KEY>
Model list: GET https://opencode.ai/zen/v1/models
"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://opencode.ai/zen/v1"
TIMEOUT = 120.0


class OpencodeClient:
    """Client for the Opencode Zen LLM gateway."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Opencode API key is required")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _endpoint_for(self, model: str) -> str:
        """Pick the right endpoint based on the model family."""
        m = model.lower()
        if m.startswith("claude") or "haiku" in m or "opus" in m or "sonnet" in m:
            return f"{BASE_URL}/messages"
        if m.startswith("gpt-5") or m.startswith("gpt-6") or "codex" in m:
            return f"{BASE_URL}/responses"
        return f"{BASE_URL}/chat/completions"

    async def complete(
        self,
        prompt: str,
        model: str = "claude-sonnet-4-5",
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Send a completion request and return the text response.
        Raises RuntimeError with a readable message on failure.
        """
        url = self._endpoint_for(model)
        headers = self._headers()

        m = model.lower()
        is_anthropic_style = m.startswith("claude") or "haiku" in m or "opus" in m or "sonnet" in m
        is_responses_style = m.startswith("gpt-5") or m.startswith("gpt-6") or "codex" in m

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                if is_anthropic_style:
                    body: dict = {
                        "model": model,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                    if system:
                        body["system"] = system
                    resp = await client.post(url, headers=headers, json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    # Anthropic format: content[].text
                    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
                    return "".join(parts)

                elif is_responses_style:
                    body = {
                        "model": model,
                        "input": prompt,
                        "max_output_tokens": max_tokens,
                        "temperature": temperature,
                    }
                    if system:
                        body["instructions"] = system
                    resp = await client.post(url, headers=headers, json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    # Responses format: output[].content[].text
                    out_text = []
                    for item in data.get("output", []):
                        for c in item.get("content", []):
                            if c.get("type") in ("output_text", "text"):
                                out_text.append(c.get("text", ""))
                    if out_text:
                        return "".join(out_text)
                    # Fallback for simpler payloads
                    return data.get("output_text", "")

                else:
                    # OpenAI-compatible chat/completions
                    messages = []
                    if system:
                        messages.append({"role": "system", "content": system})
                    messages.append({"role": "user", "content": prompt})
                    body = {
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    }
                    resp = await client.post(url, headers=headers, json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]

        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            detail = e.response.text[:300]
            if status == 401:
                raise RuntimeError("API key Opencode non valida o scaduta (401).")
            if status == 402:
                raise RuntimeError("Credito Opencode esaurito (402).")
            if status == 429:
                raise RuntimeError("Rate limit Opencode superato (429). Riprova tra poco.")
            raise RuntimeError(f"Errore Opencode HTTP {status}: {detail}")
        except httpx.TimeoutException:
            raise RuntimeError("Timeout nella chiamata a Opencode (120s).")
        except Exception as e:
            raise RuntimeError(f"Errore nella chiamata LLM: {e}")

    async def list_models(self) -> list[str]:
        """Fetch the available model IDs from the gateway."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(f"{BASE_URL}/models", headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                return [m.get("id") for m in data.get("data", []) if m.get("id")]
        except Exception as e:
            logger.error(f"Could not list models: {e}")
            return []

    async def validate_key(self) -> bool:
        """
        Check whether the API key actually works by making a minimal
        completion request. GET /models is public and proves nothing.
        """
        try:
            await self.complete(
                prompt="Rispondi solo con: OK",
                model="claude-haiku-4-5",
                max_tokens=16,
            )
            return True
        except RuntimeError as e:
            msg = str(e)
            # 401 means the key itself is bad; other errors mean the key worked
            if "401" in msg:
                return False
            return True
        except Exception:
            return False

    async def get_quota_info(self) -> dict:
        """
        Probe the key with a real (tiny) request and classify the result.
        Returns {"valid": bool, "error": str|None}.
        """
        try:
            await self.complete(
                prompt="Rispondi solo con: OK",
                model="claude-haiku-4-5",
                max_tokens=16,
            )
            return {"valid": True, "error": None}
        except RuntimeError as e:
            msg = str(e)
            if "401" in msg:
                return {"valid": False, "error": "API key Opencode non valida (401)."}
            if "402" in msg:
                return {"valid": False, "error": "Credito Opencode esaurito (402)."}
            if "429" in msg:
                return {"valid": True, "error": "Chiave valida ma rate limit raggiunto (429)."}
            return {"valid": True, "error": f"Chiave valida,warning: {msg}"}
        except Exception as e:
            return {"valid": False, "error": str(e)}
