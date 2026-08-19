"""Unit tests for Hermes-compatible xAI OAuth helpers (no network)."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest

from receipt_bot.llm.xai_oauth import (
    access_token_is_expiring,
    jwt_exp_unix,
    proactive_refresh_skew_seconds,
    resolve_xai_oauth_runtime_credentials,
)


def _make_jwt(exp: float) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"exp": int(exp)}).encode()
    ).decode().rstrip("=")
    return f"{header}.{payload}.sig"


def test_jwt_exp_and_skew():
    now = time.time()
    tok = _make_jwt(now + 7200)
    assert jwt_exp_unix(tok) == pytest.approx(now + 7200, abs=2)
    assert access_token_is_expiring(tok, skew_seconds=0) is False
    assert access_token_is_expiring(tok, skew_seconds=8000) is True
    # Long-lived remaining > 45m → full 1h skew
    assert proactive_refresh_skew_seconds(tok) == 3600


def test_short_jwt_uses_narrow_skew():
    now = time.time()
    tok = _make_jwt(now + 10 * 60)  # 10 minutes left
    assert proactive_refresh_skew_seconds(tok) == 120


def test_resolve_reads_auth_store(tmp_path: Path, monkeypatch):
    # Point resolver at a temp auth.json with a non-expiring JWT
    now = time.time()
    access = _make_jwt(now + 10_000)
    auth = {
        "version": 1,
        "providers": {
            "xai-oauth": {
                "auth_mode": "oauth_pkce",
                "discovery": {
                    "token_endpoint": "https://auth.x.ai/oauth2/token",
                    "authorization_endpoint": "https://auth.x.ai/oauth2/authorize",
                },
                "tokens": {
                    "access_token": access,
                    "refresh_token": "rt-test-not-used",
                    "token_type": "Bearer",
                },
            }
        },
    }
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps(auth), encoding="utf-8")
    monkeypatch.setenv("XAI_AUTH_JSON", str(auth_file))
    # hermes_home unused when XAI_AUTH_JSON set
    creds = resolve_xai_oauth_runtime_credentials(
        hermes_home=tmp_path,
        force_refresh=False,
        refresh_if_expiring=True,
    )
    assert creds["api_key"] == access
    assert creds["source"] == "hermes-auth-store"
    assert creds["base_url"] == "https://api.x.ai/v1"
