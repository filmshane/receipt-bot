from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from receipt_bot.llm.prompts import CHAT_SYSTEM, EXTRACTION_SYSTEM
from receipt_bot.llm.xai_oauth import XaiOAuthError, resolve_xai_oauth_runtime_credentials
from receipt_bot.models import ExtractionResult

log = logging.getLogger(__name__)


def _parse_json_content(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise


class GrokClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.x.ai/v1",
        *,
        use_hermes_oauth: bool = True,
        hermes_home: str | None = None,
        token_file: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.use_hermes_oauth = use_hermes_oauth
        self.hermes_home = hermes_home
        self.token_file = token_file  # legacy optional override

    def _resolve_api_key(self, *, force_refresh: bool = False) -> str:
        """
        Credential order (Hermes-compatible OAuth first when enabled):
        1. Hermes auth.json xAI OAuth with proactive refresh (same as Hermes)
        2. Optional token_file (legacy)
        3. Static XAI_API_KEY
        """
        if self.use_hermes_oauth:
            try:
                from pathlib import Path

                hh = Path(self.hermes_home).expanduser() if self.hermes_home else None
                creds = resolve_xai_oauth_runtime_credentials(
                    hermes_home=hh,
                    force_refresh=force_refresh,
                    refresh_if_expiring=True,
                )
                key = (creds.get("api_key") or "").strip()
                if key:
                    # Keep base_url pinned to oauth-validated host when provided
                    bu = (creds.get("base_url") or "").strip().rstrip("/")
                    if bu:
                        self.base_url = bu
                    return key
            except XaiOAuthError as exc:
                log.warning("xAI OAuth resolve failed (%s): %s", exc.code, exc)
                if force_refresh:
                    # Already forced; fall through to static key
                    pass
            except Exception as exc:
                log.warning("xAI OAuth resolve unexpected error: %s", exc)

        if self.token_file:
            try:
                from pathlib import Path

                p = Path(self.token_file)
                if p.is_file():
                    tok = p.read_text(encoding="utf-8").strip()
                    if tok:
                        return tok
            except OSError:
                pass

        return (self.api_key or "").strip()

    def _headers(self, *, force_refresh: bool = False) -> dict:
        return {
            "Authorization": f"Bearer {self._resolve_api_key(force_refresh=force_refresh)}",
            "Content-Type": "application/json",
        }

    async def _post_chat(
        self, payload: dict, *, timeout: float = 120.0
    ) -> httpx.Response:
        """POST chat/completions; on 401 force OAuth refresh once and retry."""
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(force_refresh=False),
                json=payload,
            )
            if r.status_code == 401 and self.use_hermes_oauth:
                log.info("Grok API 401 — forcing xAI OAuth refresh and retrying once")
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(force_refresh=True),
                    json=payload,
                )
            return r

    async def extract_receipt_from_image(
        self, image_bytes: bytes, mime: str = "image/jpeg"
    ) -> ExtractionResult:
        if not self._resolve_api_key():
            return ExtractionResult(
                is_receipt=False, confidence=0.0, error="XAI_API_KEY not configured"
            )
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime};base64,{b64}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract expense fields from this receipt or invoice image.",
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "temperature": 0.1,
        }
        r = await self._post_chat(payload)
        if r.status_code >= 400:
            return ExtractionResult(
                is_receipt=False,
                confidence=0.0,
                error=f"Grok API {r.status_code}: {r.text[:300]}",
            )
        data = r.json()
        try:
            content = data["choices"][0]["message"]["content"]
            parsed = _parse_json_content(content)
            return ExtractionResult.model_validate(parsed)
        except Exception as e:
            return ExtractionResult(
                is_receipt=False, confidence=0.0, error=f"Parse error: {e}"
            )

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        """Return assistant message dict (may include tool_calls)."""
        if not self._resolve_api_key():
            return {"role": "assistant", "content": "XAI_API_KEY is not configured."}
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": CHAT_SYSTEM}] + messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        r = await self._post_chat(payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]


EXPENSE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "sum_expenses",
            "description": "Sum Total for expenses matching optional filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["Travel", "Food", "Equipment", "Other"],
                    },
                    "date_from": {
                        "type": "string",
                        "description": "YYYY-MM-DD inclusive",
                    },
                    "date_to": {
                        "type": "string",
                        "description": "YYYY-MM-DD inclusive",
                    },
                    "telegram_user_id": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_expenses",
            "description": "List expense rows matching filters (max 50).",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["Travel", "Food", "Equipment", "Other"],
                    },
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "telegram_user_id": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent",
            "description": "List the most recent N expenses for a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "default": 10},
                    "telegram_user_id": {"type": "integer"},
                },
            },
        },
    },
]
