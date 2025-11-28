"""Backend communication helpers: HTTP client, token cache, and shared utilities."""

from __future__ import annotations

from datetime import datetime

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

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

    async def submit_step_answer(self, access_token: str, text: str, is_template_format: bool = False) -> bool:
        """
        Attempts to submit an answer for the current active step.
        Returns: True if answer was saved, False if no active question was found (400).
        Raises: aiohttp.ClientResponseError for other errors (500, 401, etc).
        """
        try:
            await self._request(
                "POST", 
                "/steps/answer", 
                token=access_token, 
                json={"text": text, "is_template_format": is_template_format}
            )
            return True
        except aiohttp.ClientResponseError as e:
            # API returns 400 if there is no active "Tail" (question) to answer
            if e.status == 400:
                return False
            raise e

    async def get_current_step_info(self, access_token: str) -> Dict[str, Any]:
        """Get current step information with progress indicators"""
        return await self._request("GET", "/steps/current", token=access_token)
    
    async def get_step_detail(self, access_token: str, step_id: int) -> Dict[str, Any]:
        """Get detailed information about a step"""
        return await self._request("GET", f"/steps/{step_id}/detail", token=access_token)

    async def get_all_steps(self, access_token: str) -> Dict[str, Any]:
        """Get list of all steps"""
        return await self._request("GET", "/steps/list", token=access_token)

    async def get_step_questions(self, access_token: str, step_id: int) -> Dict[str, Any]:
        """Get list of questions for a step"""
        return await self._request("GET", f"/steps/{step_id}/questions", token=access_token)

    async def get_current_step_questions(self, access_token: str) -> Dict[str, Any]:
        """Get list of questions for current step"""
        return await self._request("GET", "/steps/current/questions", token=access_token)

    async def save_draft(self, access_token: str, draft_text: str) -> Dict[str, Any]:
        """Save draft answer"""
        return await self._request("POST", "/steps/draft", token=access_token, json={"draft_text": draft_text})

    async def get_draft(self, access_token: str) -> Dict[str, Any]:
        """Get draft from active Tail"""
        return await self._request("GET", "/steps/draft", token=access_token)

    async def get_previous_answer(self, access_token: str, question_id: int) -> Dict[str, Any]:
        """Get previous answer for a question"""
        return await self._request("GET", f"/steps/question/{question_id}/previous", token=access_token)

    async def switch_to_question(self, access_token: str, question_id: int) -> Dict[str, Any]:
        """Switch to a specific question"""
        return await self._request("POST", "/steps/switch-question", token=access_token, json={"question_id": question_id})

    # --- Steps Settings Functionality ---

    async def get_steps_settings(self, access_token: str) -> Dict[str, Any]:
        """Get current steps settings"""
        return await self._request("GET", "/steps/settings", token=access_token)

    async def update_steps_settings(
        self, 
        access_token: str,
        active_template_id: Optional[int] = None,
        reminders_enabled: Optional[bool] = None,
        reminder_time: Optional[str] = None,
        reminder_days: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Update steps settings"""
        payload = {}
        if active_template_id is not None:
            payload["active_template_id"] = active_template_id
        if reminders_enabled is not None:
            payload["reminders_enabled"] = reminders_enabled
        if reminder_time is not None:
            payload["reminder_time"] = reminder_time
        if reminder_days is not None:
            payload["reminder_days"] = reminder_days
        
        return await self._request("PUT", "/steps/settings", token=access_token, json=payload)

    # --- SOS Functionality ---

    async def get_profile_sections(self, access_token: str) -> Dict[str, Any]:
        """Get all profile sections"""
        return await self._request("GET", "/profile/sections", token=access_token)

    async def get_section_detail(self, access_token: str, section_id: int) -> Dict[str, Any]:
        """Get section details with questions"""
        return await self._request("GET", f"/profile/sections/{section_id}", token=access_token)

    async def submit_profile_answer(
        self, access_token: str, section_id: int, question_id: int, answer_text: str
    ) -> Dict[str, Any]:
        """Submit answer to a profile question"""
        payload = {"question_id": question_id, "answer_text": answer_text}
        return await self._request(
            "POST", f"/profile/sections/{section_id}/answer", token=access_token, json=payload
        )

    async def submit_free_text(
        self, access_token: str, section_id: int, text: str
    ) -> Dict[str, Any]:
        """Submit free text for a section"""
        payload = {"text": text}
        return await self._request(
            "POST", f"/profile/sections/{section_id}/free-text", token=access_token, json=payload
        )

    async def create_custom_section(
        self, access_token: str, name: str, icon: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a custom profile section"""
        payload = {"name": name, "icon": icon}
        return await self._request(
            "POST", "/profile/sections/custom", token=access_token, json=payload
        )

    async def get_section_summary(self, access_token: str, section_id: int) -> Dict[str, Any]:
        """Get summary for a section"""
        return await self._request(
            "GET", f"/profile/sections/{section_id}/summary", token=access_token
        )

    async def update_section(
        self, access_token: str, section_id: int, name: Optional[str] = None,
        icon: Optional[str] = None, order_index: Optional[int] = None
    ) -> Dict[str, Any]:
        """Update a custom section"""
        payload = {}
        if name is not None:
            payload["name"] = name
        if icon is not None:
            payload["icon"] = icon
        if order_index is not None:
            payload["order_index"] = order_index
        return await self._request(
            "PUT", f"/profile/sections/{section_id}", token=access_token, json=payload
        )

    async def delete_section(self, access_token: str, section_id: int) -> Dict[str, Any]:
        """Delete a custom section"""
        return await self._request(
            "DELETE", f"/profile/sections/{section_id}", token=access_token
        )

    # --- Answer Template Functionality ---

    async def get_templates(self, access_token: str) -> Dict[str, Any]:
        """Get all available templates"""
        return await self._request("GET", "/steps/templates", token=access_token)

    async def set_active_template(self, access_token: str, template_id: Optional[int] = None) -> Dict[str, Any]:
        """Set active template (None to reset to default)"""
        payload = {"template_id": template_id}
        return await self._request("PATCH", "/me/template", token=access_token, json=payload)

    # --- SOS Chat Functionality ---

    async def get_sos_message(self, telegram_id: int) -> str:
        """Get SOS help message (legacy method)"""
        response = await self._request("POST", "/sos", json={"telegram_id": telegram_id})
        return response.get("reply", "")

    async def sos_chat(
        self, 
        access_token: str, 
        help_type: Optional[str] = None,
        custom_text: Optional[str] = None,
        message: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Start or continue SOS chat dialog"""
        payload = {
            "help_type": help_type,
            "custom_text": custom_text,
            "message": message,
            "conversation_history": conversation_history or []
        }
        return await self._request("POST", "/sos/chat", token=access_token, json=payload)

    async def get_sos_message(self, telegram_id: int | str) -> str:
        """
        Calls POST /sos to get a helpful hint based on user context.
        """
        payload = {"telegram_id": str(telegram_id)}
        # We use _request to handle base_url, json headers, and error raising automatically
        data = await self._request("POST", "/sos", json=payload)
        return data["reply"]

    # --- Thanks and Day Commands ---

    async def thanks(self, telegram_id: int | str, debug: bool = False) -> ChatResponse:
        """
        Calls POST /thanks to get a support and motivation message.
        """
        payload = {"telegram_id": str(telegram_id), "debug": debug}
        data = await self._request("POST", "/thanks", json=payload)
        
        reply = data.get("reply", "")
        log_data = data.get("log")
        log = None
        if log_data:
            try:
                log = Log(**log_data)
            except Exception:
                pass
        
        return ChatResponse(reply=reply, log=log)

    async def day(self, telegram_id: int | str, debug: bool = False) -> ChatResponse:
        """
        Calls POST /day to get an analysis and reflection message.
        """
        payload = {"telegram_id": str(telegram_id), "debug": debug}
        data = await self._request("POST", "/day", json=payload)
        
        reply = data.get("reply", "")
        log_data = data.get("log")
        log = None
        if log_data:
            try:
                log = Log(**log_data)
            except Exception:
                pass
        
        return ChatResponse(reply=reply, log=log)


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

    # 1. Try to submit answer (default is_template_format=False for plain text)
    was_answer = await BACKEND_CLIENT.submit_step_answer(token, text, is_template_format=False)

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