"""Backend communication helpers: HTTP client, token cache, and shared utilities."""

from __future__ import annotations

from datetime import datetime

import json
import logging
from typing import Any, Dict, Optional, Tuple, Union

import aiohttp
from pydantic import BaseModel

# Ensure these are defined in your bot/config.py
from bot.config import BACKEND_API_BASE, BACKEND_CHAT_URL

logger = logging.getLogger(__name__)


class BackendClient:
    """Simple wrapper around aiohttp for the REST endpoints."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=20)

    async def _request(
        self,
        method: str,
        path: str,
        token: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Internal helper to make requests to the base API URL."""
        url = f"{self.base_url}{path}"
        headers: Dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.request(method, url, headers=headers, **kwargs) as response:
                response.raise_for_status()
                return await response.json()

    async def auth_telegram(
        self,
        telegram_id: str,
        username: Optional[str],
        first_name: Optional[str],
    ) -> Tuple[Dict[str, Any], bool, str]:
        payload = {
            "telegram_id": telegram_id,
            "username": username,
            "first_name": first_name,
        }
        data = await self._request("POST", "/auth/telegram", json=payload)
        return data["user"], data["is_new"], data["access_token"]

    async def update_me(
        self,
        access_token: str,
        display_name: Optional[str] = None,
        program_experience: Optional[str] = None,
        sobriety_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if display_name:
            payload["display_name"] = display_name
        if program_experience:
            payload["program_experience"] = program_experience
        if sobriety_date:
            payload["sobriety_date"] = sobriety_date
        if not payload:
            return {}
        return await self._request("PATCH", "/me", token=access_token, json=payload)

    async def get_status(self, access_token: str) -> Dict[str, Any]:
        return await self._request("GET", "/status", token=access_token)

    # --- Steps Functionality ---

    async def get_next_step(self, access_token: str) -> Dict[str, Any]:
        """
        Fetches the next question in the step flow.
        Returns: Dict with keys 'message' (str) and 'is_completed' (bool).
        """
        return await self._request("GET", "/steps/next", token=access_token)

    async def submit_step_answer(self, access_token: str, text: str) -> bool:
        """
        Attempts to submit an answer for the current active step.
        Returns: True if answer was saved, False if no active question was found (400).
        Raises: aiohttp.ClientResponseError for other errors (500, 401, etc).
        """
        try:
            await self._request("POST", "/steps/answer", token=access_token, json={"text": text})
            return True
        except aiohttp.ClientResponseError as e:
            # API returns 400 if there is no active "Tail" (question) to answer
            if e.status == 400:
                return False
            raise e

    # --- SOS Functionality ---

    async def get_sos_message(self, telegram_id: int | str) -> str:
        """
        Calls POST /sos to get a helpful hint based on user context.
        """
        payload = {"telegram_id": str(telegram_id)}
        # We use _request to handle base_url, json headers, and error raising automatically
        data = await self._request("POST", "/sos", json=payload)
        return data["reply"]


# ---------------------------------------------------------------------------
# GLOBAL STATE & HELPERS
# ---------------------------------------------------------------------------

BACKEND_CLIENT = BackendClient(base_url=BACKEND_API_BASE)
TOKEN_STORE: Dict[str, str] = {}
USER_CACHE: Dict[str, Dict[str, Any]] = {}


async def get_or_fetch_token(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
) -> Optional[str]:
    """Return stored token or authenticate to fetch a fresh one."""
    key = str(telegram_id)
    cached = TOKEN_STORE.get(key)
    if cached:
        return cached
    try:
        user, _, token = await BACKEND_CLIENT.auth_telegram(
            telegram_id=key,
            username=username,
            first_name=first_name,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unable to fetch token for %s: %s", key, exc)
        return None
    TOKEN_STORE[key] = token
    USER_CACHE[key] = user
    return token


async def update_user_profile(
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
    display_name: Optional[str] = None,
    program_experience: Optional[str] = None,
    sobriety_date: Optional[str] = None,
) -> None:
    """Upload partial profile updates to the backend."""
    key = str(telegram_id)
    token = TOKEN_STORE.get(key)
    if not token:
        token = await get_or_fetch_token(telegram_id, username, first_name)
    if not token:
        return

    try:
        updated = await BACKEND_CLIENT.update_me(
            access_token=token,
            display_name=display_name,
            program_experience=program_experience,
            sobriety_date=sobriety_date,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to update profile for %s: %s", key, exc)
        return
    if updated:
        USER_CACHE[key] = updated


# --- Step Logic Helpers ---

async def process_step_message(
    telegram_id: int,
    text: str,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Logic:
    1. Try to submit the user's text as an answer to an active step.
    2. If successful: Fetch and return the NEXT question/status.
    3. If failed (was not an answer): Return None (caller should use legacy chat).
    """
    token = await get_or_fetch_token(telegram_id, username, first_name)
    if not token:
        return None

    # 1. Try to submit answer
    was_answer = await BACKEND_CLIENT.submit_step_answer(token, text)

    if was_answer:
        # 2. If it was an answer, get the immediate next prompt
        return await BACKEND_CLIENT.get_next_step(token)
    
    return None


async def get_current_step_question(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Just fetches the current pending question without submitting an answer.
    Useful for commands like /steps or /continue_steps.
    """
    token = await get_or_fetch_token(telegram_id, username, first_name)
    if not token:
        return None
    return await BACKEND_CLIENT.get_next_step(token)


# --- Chat & Models (Legacy/Direct Chat) ---

class Log(BaseModel):
    classification_result: str
    blocks_used: str
    plan : str
    prompt_changes : Optional[str]
    timestamp: Optional[datetime] = None

class ChatResponse(BaseModel):
    reply: str
    log : Optional[Log]


async def call_legacy_chat(telegram_id: int, text: str, debug: bool) -> Union[str, ChatResponse]:
    """
    Calls the dedicated chat endpoint (separate from main API if configured).
    """
    payload = {"telegram_id": str(telegram_id), "message": text, "debug": debug}
    timeout = aiohttp.ClientTimeout(total=20)

    # Note: Using a fresh session here in case BACKEND_CHAT_URL is different base
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(BACKEND_CHAT_URL, json=payload) as response:
            response.raise_for_status()
            try:
                data = await response.json()
            except aiohttp.ContentTypeError:
                # If backend sent raw text instead of JSON
                raw = await response.text()
                return ChatResponse(reply=raw, log=None)

    reply = None
    log = None

    if isinstance(data, dict):
        # Look for standard text fields
        for key in ("reply", "response", "message", "text", "answer"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                reply = value
                break

        # Fallback: dump the whole dict
        if reply is None:
            reply = json.dumps(data, ensure_ascii=False, indent=2)

        # Extract log if present
        if "log" in data and data["log"]:
            try:
                log = Log(**data["log"])
            except Exception:
                pass  # Ignore log parsing errors

        return ChatResponse(reply=reply, log=log)

    elif isinstance(data, list):
        return json.dumps(data, ensure_ascii=False, indent=2)

    else:
        return str(data)


def get_display_name(user: Dict[str, Any]) -> str:
    return (
        user.get("display_name")
        or user.get("first_name")
        or user.get("username")
        or "друг"
    )