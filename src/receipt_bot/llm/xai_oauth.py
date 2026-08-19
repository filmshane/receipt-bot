"""xAI Grok OAuth credential resolution — same method as Hermes Agent.

Mirrors hermes_cli.auth.resolve_xai_oauth_runtime_credentials:

* Read tokens from Hermes auth store (~/.hermes/auth.json)
* Cross-process lock on auth.lock (portalocker)
* Decode JWT exp; proactive refresh with adaptive skew (up to 1h early)
* POST grant_type=refresh_token to auth.x.ai token endpoint
* Persist rotated access_token + refresh_token back to auth.json
  (xAI rotates refresh tokens — must write through or Hermes breaks)

Static XAI_API_KEY remains a fallback when OAuth is disabled or unavailable.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import stat
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
import portalocker

log = logging.getLogger(__name__)

# Match Hermes constants (hermes_cli/auth.py)
DEFAULT_XAI_OAUTH_BASE_URL = "https://api.x.ai/v1"
XAI_OAUTH_ISSUER = "https://auth.x.ai"
XAI_OAUTH_DISCOVERY_URL = f"{XAI_OAUTH_ISSUER}/.well-known/openid-configuration"
XAI_OAUTH_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 3600
AUTH_LOCK_TIMEOUT_SECONDS = 15.0
DEFAULT_REFRESH_TIMEOUT_SECONDS = 20.0

_thread_lock = threading.RLock()


class XaiOAuthError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "xai_oauth_error",
        relogin_required: bool = False,
    ):
        super().__init__(message)
        self.code = code
        self.relogin_required = relogin_required


def default_hermes_home() -> Path:
    override = (os.environ.get("HERMES_HOME") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".hermes"


def auth_file_path(hermes_home: Optional[Path] = None) -> Path:
    explicit = (os.environ.get("XAI_AUTH_JSON") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return (hermes_home or default_hermes_home()) / "auth.json"


def auth_lock_path(auth_file: Path) -> Path:
    # Hermes default profile uses ~/.hermes/auth.lock (not auth.json.lock)
    if auth_file.name == "auth.json":
        return auth_file.with_name("auth.lock")
    return auth_file.with_suffix(".lock")


@contextmanager
def _auth_store_lock(auth_file: Path, timeout_seconds: float = AUTH_LOCK_TIMEOUT_SECONDS):
    lock_path = auth_lock_path(auth_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Touch lock file so portalocker has a path
    if not lock_path.exists():
        lock_path.touch()
    with open(lock_path, "a+", encoding="utf-8") as handle:
        deadline = time.time() + max(1.0, float(timeout_seconds))
        while True:
            try:
                portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
                break
            except portalocker.LockException:
                if time.time() >= deadline:
                    raise XaiOAuthError(
                        "Timed out waiting for auth store lock",
                        code="xai_auth_lock_timeout",
                    )
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                portalocker.unlock(handle)
            except Exception:
                pass


def _load_auth_store(auth_file: Path) -> Dict[str, Any]:
    if not auth_file.exists():
        return {"version": 1, "providers": {}}
    try:
        raw = json.loads(auth_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise XaiOAuthError(
            f"Failed to parse auth store {auth_file}: {exc}",
            code="xai_auth_parse_error",
        ) from exc
    if not isinstance(raw, dict):
        return {"version": 1, "providers": {}}
    raw.setdefault("providers", {})
    return raw


def _atomic_save_auth_store(auth_file: Path, auth_store: Dict[str, Any]) -> None:
    """Atomic 0o600 write — same idea as Hermes _save_auth_store."""
    auth_file.parent.mkdir(parents=True, exist_ok=True)
    auth_store["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(auth_store, indent=2) + "\n"
    tmp_path = auth_file.with_name(
        f"{auth_file.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
    )
    try:
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(tmp_path), str(auth_file))
        try:
            os.chmod(auth_file, 0o600)
        except OSError:
            pass
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _xai_state_from_store(auth_store: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    providers = auth_store.get("providers")
    state = providers.get("xai-oauth") if isinstance(providers, dict) else None
    tokens = state.get("tokens") if isinstance(state, dict) else None
    if isinstance(tokens, dict):
        access = str(tokens.get("access_token") or "").strip()
        refresh = str(tokens.get("refresh_token") or "").strip()
        if access and refresh:
            return state

    # Credential pool fallback (Hermes multi-entry)
    pool = auth_store.get("credential_pool")
    entries = pool.get("xai-oauth") if isinstance(pool, dict) else None
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            access = str(entry.get("access_token") or "").strip()
            refresh = str(entry.get("refresh_token") or "").strip()
            if not access or not refresh:
                continue
            merged = dict(state or {})
            merged["tokens"] = {
                "access_token": access,
                "refresh_token": refresh,
                "token_type": str(entry.get("token_type") or "Bearer"),
            }
            if entry.get("last_refresh"):
                merged["last_refresh"] = entry.get("last_refresh")
            merged.setdefault("auth_mode", "oauth_pkce")
            return merged
    return state if isinstance(state, dict) else None


def jwt_exp_unix(access_token: str) -> Optional[float]:
    if not isinstance(access_token, str) or access_token.count(".") < 2:
        return None
    try:
        payload_b64 = access_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
        )
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            return float(exp)
    except Exception:
        return None
    return None


def access_token_is_expiring(access_token: str, skew_seconds: int = 0) -> bool:
    exp = jwt_exp_unix(access_token)
    if exp is None:
        return False
    return exp <= (time.time() + max(0, int(skew_seconds)))


def proactive_refresh_skew_seconds(access_token: str) -> int:
    """Hermes adaptive skew: short JWTs use 120s; long sessions use up to 1h."""
    max_skew = XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS
    exp = jwt_exp_unix(access_token)
    if exp is None:
        return max_skew
    remaining = exp - time.time()
    if remaining <= 0:
        return max_skew
    if remaining <= 45 * 60:
        return min(120, max_skew)
    return max_skew


def validate_oauth_endpoint(url: str, *, field: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise XaiOAuthError(
            f"xAI OIDC {field} is not HTTPS: {url!r}",
            code="xai_discovery_invalid",
        )
    host = (parsed.hostname or "").lower()
    if not host or (host != "x.ai" and not host.endswith(".x.ai")):
        raise XaiOAuthError(
            f"xAI OIDC {field} host not on x.ai: {url!r}",
            code="xai_discovery_invalid",
        )
    return url


def oauth_discovery(timeout_seconds: float = 15.0) -> Dict[str, str]:
    try:
        response = httpx.get(
            XAI_OAUTH_DISCOVERY_URL,
            headers={"Accept": "application/json"},
            timeout=timeout_seconds,
        )
    except Exception as exc:
        raise XaiOAuthError(
            f"xAI OIDC discovery failed: {exc}",
            code="xai_discovery_failed",
        ) from exc
    if response.status_code != 200:
        raise XaiOAuthError(
            f"xAI OIDC discovery status {response.status_code}",
            code="xai_discovery_failed",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise XaiOAuthError(
            "xAI OIDC discovery not a JSON object",
            code="xai_discovery_incomplete",
        )
    authorization_endpoint = str(payload.get("authorization_endpoint") or "").strip()
    token_endpoint = str(payload.get("token_endpoint") or "").strip()
    if not authorization_endpoint or not token_endpoint:
        raise XaiOAuthError(
            "xAI OIDC discovery missing endpoints",
            code="xai_discovery_incomplete",
        )
    validate_oauth_endpoint(authorization_endpoint, field="authorization_endpoint")
    validate_oauth_endpoint(token_endpoint, field="token_endpoint")
    return {
        "authorization_endpoint": authorization_endpoint,
        "token_endpoint": token_endpoint,
    }


def refresh_xai_oauth_pure(
    refresh_token: str,
    *,
    token_endpoint: str = "",
    timeout_seconds: float = DEFAULT_REFRESH_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise XaiOAuthError(
            "xAI OAuth missing refresh_token. Re-auth with `hermes model`.",
            code="xai_auth_missing_refresh_token",
            relogin_required=True,
        )
    endpoint = token_endpoint.strip() or oauth_discovery(timeout_seconds)["token_endpoint"]
    validate_oauth_endpoint(endpoint, field="token_endpoint")
    timeout = httpx.Timeout(max(5.0, float(timeout_seconds)))
    with httpx.Client(timeout=timeout, headers={"Accept": "application/json"}) as client:
        response = client.post(
            endpoint,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "client_id": XAI_OAUTH_CLIENT_ID,
                "refresh_token": refresh_token,
            },
        )
    if response.status_code != 200:
        detail = response.text.strip()
        if response.status_code == 403:
            raise XaiOAuthError(
                "xAI token refresh HTTP 403 (tier/API not authorized for this OAuth account). "
                "Set a static XAI_API_KEY instead."
                + (f" Response: {detail}" if detail else ""),
                code="xai_oauth_tier_denied",
                relogin_required=False,
            )
        raise XaiOAuthError(
            "xAI token refresh failed." + (f" Response: {detail}" if detail else ""),
            code="xai_refresh_failed",
            relogin_required=response.status_code in {400, 401},
        )
    try:
        payload = response.json()
    except Exception as exc:
        raise XaiOAuthError(
            f"xAI token refresh invalid JSON: {exc}",
            code="xai_refresh_invalid_json",
        ) from exc
    if not isinstance(payload, dict):
        raise XaiOAuthError(
            "xAI token refresh response not an object",
            code="xai_refresh_invalid_response",
            relogin_required=True,
        )
    refreshed_access = str(payload.get("access_token") or "").strip()
    if not refreshed_access:
        raise XaiOAuthError(
            "xAI token refresh missing access_token",
            code="xai_refresh_missing_access_token",
            relogin_required=True,
        )
    return {
        "access_token": refreshed_access,
        "refresh_token": str(payload.get("refresh_token") or refresh_token).strip(),
        "id_token": str(payload.get("id_token") or "").strip(),
        "expires_in": payload.get("expires_in"),
        "token_type": str(payload.get("token_type") or "Bearer").strip() or "Bearer",
        "last_refresh": datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def _persist_tokens(
    auth_file: Path,
    auth_store: Dict[str, Any],
    *,
    tokens: Dict[str, Any],
    discovery: Optional[Dict[str, Any]] = None,
    redirect_uri: str = "",
    last_refresh: Optional[str] = None,
    auth_mode: str = "oauth_device_code",
) -> None:
    providers = auth_store.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        auth_store["providers"] = providers
    state = dict(providers.get("xai-oauth") or {})
    state["tokens"] = tokens
    state["last_refresh"] = last_refresh or datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    state["auth_mode"] = auth_mode or state.get("auth_mode") or "oauth_device_code"
    if discovery:
        # Merge discovery keys; keep authorization_endpoint if present
        old_disc = dict(state.get("discovery") or {})
        old_disc.update(discovery)
        state["discovery"] = old_disc
    if redirect_uri:
        state["redirect_uri"] = redirect_uri
    # Do NOT flip active_provider (Hermes refresh path set_active=False)
    providers["xai-oauth"] = state
    _atomic_save_auth_store(auth_file, auth_store)


def _is_terminal_refresh_error(exc: XaiOAuthError) -> bool:
    if exc.code in {"xai_oauth_tier_denied"}:
        return True
    return bool(exc.relogin_required)


def resolve_xai_oauth_runtime_credentials(
    *,
    hermes_home: Optional[Path] = None,
    force_refresh: bool = False,
    refresh_if_expiring: bool = True,
    refresh_skew_seconds: Optional[int] = None,
    timeout_seconds: float = DEFAULT_REFRESH_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Return {api_key, base_url, source, last_refresh} — Hermes-compatible shape."""
    auth_file = auth_file_path(hermes_home)
    with _thread_lock:
        # Fast path without lock if token still good
        store = _load_auth_store(auth_file)
        state = _xai_state_from_store(store)
        if not state:
            raise XaiOAuthError(
                "No xAI OAuth credentials in Hermes auth store. "
                "Run `hermes model` and select xAI Grok OAuth.",
                code="xai_auth_missing",
                relogin_required=True,
            )
        tokens = dict(state.get("tokens") or {})
        access_token = str(tokens.get("access_token") or "").strip()
        refresh_token = str(tokens.get("refresh_token") or "").strip()
        if not access_token or not refresh_token:
            raise XaiOAuthError(
                "xAI OAuth state missing access/refresh token. Re-auth with `hermes model`.",
                code="xai_auth_invalid_shape",
                relogin_required=True,
            )

        discovery = dict(state.get("discovery") or {})
        token_endpoint = str(discovery.get("token_endpoint") or "").strip()
        redirect_uri = str(state.get("redirect_uri") or "").strip()
        auth_mode = str(state.get("auth_mode") or "oauth_device_code")

        effective_skew = (
            int(refresh_skew_seconds)
            if refresh_skew_seconds is not None
            else proactive_refresh_skew_seconds(access_token)
        )
        should_refresh = bool(force_refresh)
        if (not should_refresh) and refresh_if_expiring:
            should_refresh = access_token_is_expiring(access_token, effective_skew)

        if should_refresh:
            lock_timeout = max(AUTH_LOCK_TIMEOUT_SECONDS, float(timeout_seconds) + 5.0)
            with _auth_store_lock(auth_file, timeout_seconds=lock_timeout):
                # Re-read under lock (another process may have refreshed)
                store = _load_auth_store(auth_file)
                state = _xai_state_from_store(store) or {}
                tokens = dict(state.get("tokens") or {})
                access_token = str(tokens.get("access_token") or "").strip()
                refresh_token = str(tokens.get("refresh_token") or "").strip()
                discovery = dict(state.get("discovery") or {})
                token_endpoint = str(discovery.get("token_endpoint") or "").strip()
                redirect_uri = str(state.get("redirect_uri") or "").strip()
                auth_mode = str(state.get("auth_mode") or auth_mode)

                effective_skew = (
                    int(refresh_skew_seconds)
                    if refresh_skew_seconds is not None
                    else proactive_refresh_skew_seconds(access_token)
                )
                still_need = bool(force_refresh)
                if (not still_need) and refresh_if_expiring:
                    still_need = access_token_is_expiring(access_token, effective_skew)

                if still_need:
                    if not token_endpoint:
                        token_endpoint = oauth_discovery(timeout_seconds)[
                            "token_endpoint"
                        ]
                    try:
                        refreshed = refresh_xai_oauth_pure(
                            refresh_token,
                            token_endpoint=token_endpoint,
                            timeout_seconds=timeout_seconds,
                        )
                    except XaiOAuthError as exc:
                        if _is_terminal_refresh_error(exc):
                            # Quarantine dead tokens (Hermes behavior)
                            try:
                                q_tokens = dict(tokens)
                                q_tokens.pop("access_token", None)
                                q_tokens.pop("refresh_token", None)
                                q_state = dict(state)
                                q_state["tokens"] = q_tokens
                                q_state["last_auth_error"] = {
                                    "provider": "xai-oauth",
                                    "code": exc.code,
                                    "message": str(exc),
                                    "reason": "runtime_refresh_failure",
                                    "relogin_required": True,
                                    "at": datetime.now(timezone.utc).isoformat(),
                                }
                                providers = store.setdefault("providers", {})
                                if isinstance(providers, dict):
                                    providers["xai-oauth"] = q_state
                                    _atomic_save_auth_store(auth_file, store)
                            except Exception as save_exc:
                                log.debug(
                                    "xAI OAuth: failed to quarantine tokens: %s",
                                    save_exc,
                                )
                        raise

                    updated_tokens = dict(tokens)
                    updated_tokens["access_token"] = refreshed["access_token"]
                    updated_tokens["refresh_token"] = refreshed["refresh_token"]
                    if refreshed.get("id_token"):
                        updated_tokens["id_token"] = refreshed["id_token"]
                    if refreshed.get("expires_in") is not None:
                        updated_tokens["expires_in"] = refreshed["expires_in"]
                    if refreshed.get("token_type"):
                        updated_tokens["token_type"] = refreshed["token_type"]

                    _persist_tokens(
                        auth_file,
                        store,
                        tokens=updated_tokens,
                        discovery={"token_endpoint": token_endpoint},
                        redirect_uri=redirect_uri,
                        last_refresh=refreshed["last_refresh"],
                        auth_mode=auth_mode,
                    )
                    access_token = updated_tokens["access_token"]
                    log.info(
                        "xAI OAuth: refreshed access token (wrote auth store %s)",
                        auth_file,
                    )
                else:
                    log.debug("xAI OAuth: another process already refreshed; using store")

        base_url = DEFAULT_XAI_OAUTH_BASE_URL
        env_base = (
            os.getenv("HERMES_XAI_BASE_URL", "").strip().rstrip("/")
            or os.getenv("XAI_BASE_URL", "").strip().rstrip("/")
        )
        if env_base:
            try:
                parsed = urlparse(env_base)
                host = (parsed.hostname or "").lower()
                if parsed.scheme == "https" and (
                    host == "x.ai" or host.endswith(".x.ai")
                ):
                    base_url = env_base
                else:
                    log.warning(
                        "Ignoring non-xAI XAI_BASE_URL override %r", env_base
                    )
            except Exception:
                pass

        return {
            "provider": "xai-oauth",
            "base_url": base_url,
            "api_key": access_token,
            "source": "hermes-auth-store",
            "last_refresh": (state or {}).get("last_refresh"),
            "auth_mode": "oauth_device_code",
        }
