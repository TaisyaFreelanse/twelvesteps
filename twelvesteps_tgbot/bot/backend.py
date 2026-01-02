"""Backend communication helpers: HTTP client, token cache, and shared utilities."""

from __future__ import annotations

from datetime import datetime

import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
from pydantic import BaseModel

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


    async def get_next_step(self, access_token: str) -> Dict[str, Any]:
        return await self._request("GET", "/steps/next", token=access_token)

    async def submit_step_answer(
        self,
        access_token: str,
        text: str,
        is_template_format: bool = False,
        skip_validation: bool = False
    ) -> Tuple[bool, Optional[str]]:
        url = f"{self.base_url}/steps/answer"
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "text": text,
            "is_template_format": is_template_format,
            "skip_validation": skip_validation
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    return True, None
                elif response.status == 400:
                    try:
                        error_data = await response.json()
                        error_message = error_data.get("detail", "Ошибка при сохранении ответа")
                        return False, error_message
                    except Exception:
                        return False, "Нет активного вопроса. Нажми /steps"
                else:
                    response.raise_for_status()
                    return False, "Ошибка сервера"

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

    async def get_current_question_id(self, access_token: str) -> Dict[str, Any]:
        """Get question_id from active Tail"""
        return await self._request("GET", "/steps/current/question-id", token=access_token)

    async def get_last_answered_question_id(self, access_token: str) -> Dict[str, Any]:
        """Get question_id from the last answered question"""
        return await self._request("GET", "/steps/last-answered/question-id", token=access_token)

    async def get_previous_answer(self, access_token: str, question_id: int) -> Dict[str, Any]:
        """Get previous answer for a question"""
        return await self._request("GET", f"/steps/question/{question_id}/previous", token=access_token)

    async def get_example_answers(self, access_token: str, question_id: int, limit: int = 5) -> Dict[str, Any]:
        """Get example answers for a question from other users"""
        return await self._request("GET", f"/steps/question/{question_id}/examples?limit={limit}", token=access_token)

    async def switch_to_question(self, access_token: str, question_id: int) -> Dict[str, Any]:
        """Switch to a specific question"""
        return await self._request("POST", "/steps/switch-question", token=access_token, json={"question_id": question_id})

    async def get_steps_list(self, access_token: str) -> Dict[str, Any]:
        """Get list of all steps"""
        return await self._request("GET", "/steps/list", token=access_token)

    async def switch_step(self, access_token: str, step_id: int) -> Dict[str, Any]:
        """Switch to a specific step"""
        return await self._request("POST", "/steps/switch", token=access_token, json={"step_id": step_id})

    async def get_question_detail(self, access_token: str, question_id: int) -> Dict[str, Any]:
        """Get question details"""
        return await self._request("GET", f"/steps/question/{question_id}", token=access_token)


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


    async def get_profile_sections(self, access_token: str) -> Dict[str, Any]:
        """Get all profile sections"""
        return await self._request("GET", "/profile/sections", token=access_token)

    async def get_section_detail(self, access_token: str, section_id: int) -> Dict[str, Any]:
        """Get section details with questions"""
        return await self._request("GET", f"/profile/sections/{section_id}", token=access_token)

    async def get_user_answers_for_section(self, access_token: str, section_id: int) -> Dict[str, Any]:
        """Get user's answers for questions in a section"""
        return await self._request("GET", f"/profile/sections/{section_id}/answers", token=access_token)

    async def submit_profile_answer(
        self, access_token: str, section_id: int, question_id: Optional[int], answer_text: str
    ) -> Dict[str, Any]:
        """Submit answer to a profile question (question_id can be None for generated questions)"""
        payload = {"answer_text": answer_text}
        if question_id is not None:
            payload["question_id"] = question_id
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

    async def submit_general_free_text(
        self, access_token: str, text: str
    ) -> Dict[str, Any]:
        """Submit general free text (without section_id) - will be distributed across sections"""
        payload = {"text": text, "section_id": None}
        return await self._request(
            "POST", "/profile/free-text", token=access_token, json=payload
        )

    async def get_free_text_history(
        self, access_token: str
    ) -> Dict[str, Any]:
        """Get all free text entries (history) for the user"""
        return await self._request(
            "GET", "/profile/free-text/history", token=access_token
        )

    async def get_section_history(
        self, access_token: str, section_id: int, limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get history of entries for a specific section"""
        url = f"/profile/sections/{section_id}/history"
        if limit:
            url += f"?limit={limit}"
        return await self._request("GET", url, token=access_token)

    async def create_section_data_entry(
        self,
        access_token: str,
        section_id: int,
        content: str,
        subblock_name: Optional[str] = None,
        entity_type: Optional[str] = None,
        importance: Optional[float] = 1.0,
        is_core_personality: bool = False,
        tags: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new entry in a section (manual addition)"""
        payload = {
            "content": content,
            "subblock_name": subblock_name,
            "entity_type": entity_type,
            "importance": importance,
            "is_core_personality": is_core_personality,
            "tags": tags
        }
        return await self._request(
            "POST", f"/profile/sections/{section_id}/data", token=access_token, json=payload
        )

    async def update_section_data_entry(
        self,
        access_token: str,
        data_id: int,
        content: Optional[str] = None,
        subblock_name: Optional[str] = None,
        entity_type: Optional[str] = None,
        importance: Optional[float] = None,
        is_core_personality: Optional[bool] = None,
        tags: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an existing entry"""
        payload = {}
        if content is not None:
            payload["content"] = content
        if subblock_name is not None:
            payload["subblock_name"] = subblock_name
        if entity_type is not None:
            payload["entity_type"] = entity_type
        if importance is not None:
            payload["importance"] = importance
        if is_core_personality is not None:
            payload["is_core_personality"] = is_core_personality
        if tags is not None:
            payload["tags"] = tags

        return await self._request(
            "PUT", f"/profile/section-data/{data_id}", token=access_token, json=payload
        )

    async def delete_section_data_entry(
        self, access_token: str, data_id: int
    ) -> Dict[str, Any]:
        """Delete an entry"""
        return await self._request(
            "DELETE", f"/profile/section-data/{data_id}", token=access_token
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


    async def get_templates(self, access_token: str) -> Dict[str, Any]:
        """Get all available templates"""
        return await self._request("GET", "/steps/templates", token=access_token)

    async def set_active_template(self, access_token: str, template_id: Optional[int] = None) -> Dict[str, Any]:
        """Set active template (None to reset to default)"""
        payload = {"template_id": template_id}
        return await self._request("PATCH", "/me/template", token=access_token, json=payload)


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
        extended_timeout = aiohttp.ClientTimeout(total=180)
        url = f"{self.base_url}/sos/chat"
        headers: Dict[str, str] = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        async with aiohttp.ClientSession(timeout=extended_timeout) as session:
            async with session.post(url, headers=headers, json=payload) as response:
                response.raise_for_status()
                return await response.json()

    async def get_sos_message(self, telegram_id: int | str) -> str:
        payload = {"telegram_id": str(telegram_id)}
        data = await self._request("POST", "/sos", json=payload)
        return data["reply"]


    async def thanks(self, telegram_id: int | str, debug: bool = False) -> ChatResponse:
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


    async def create_gratitude(self, access_token: str, text: str) -> dict:
        """Создать новую благодарность"""
        return await self._request(
            "POST",
            "/gratitudes",
            token=access_token,
            json={"text": text}
        )

    async def get_gratitudes(self, access_token: str, page: int = 1, page_size: int = 20) -> dict:
        """Получить список благодарностей"""
        return await self._request(
            "GET",
            f"/gratitudes?page={page}&page_size={page_size}",
            token=access_token
        )


    async def start_step10_analysis(
        self, token: str, analysis_date: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Начать или продолжить самоанализ по 10 шагу"""
        try:
            payload = {}
            if analysis_date:
                payload["analysis_date"] = analysis_date

            data = await self._request(
                "POST",
                "/step10/start",
                token=token,
                json=payload
            )
            return data
        except Exception as e:
            logger.error(f"Failed to start step10 analysis: {e}")
            return None

    async def submit_step10_answer(
        self, token: str, question_number: int, answer: str, analysis_date: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Сохранить ответ на вопрос самоанализа"""
        try:
            payload = {
                "question_number": question_number,
                "answer": answer
            }
            if analysis_date:
                payload["analysis_date"] = analysis_date

            data = await self._request(
                "POST",
                "/step10/submit",
                token=token,
                json=payload
            )
            return data
        except Exception as e:
            logger.error(f"Failed to submit step10 answer: {e}")
            return None

    async def pause_step10_analysis(
        self, token: str, analysis_date: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Поставить самоанализ на паузу"""
        try:
            payload = {}
            if analysis_date:
                payload["analysis_date"] = analysis_date

            data = await self._request(
                "POST",
                "/step10/pause",
                token=token,
                json=payload
            )
            return data
        except Exception as e:
            logger.error(f"Failed to pause step10 analysis: {e}")
            return None

    async def get_step10_progress(
        self, token: str, analysis_date: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Получить текущий прогресс самоанализа"""
        try:
            params = {}
            if analysis_date:
                params["analysis_date"] = analysis_date

            data = await self._request(
                "GET",
                "/step10/progress",
                token=token,
                params=params
            )
            return data
        except Exception as e:
            logger.error(f"Failed to get step10 progress: {e}")
            return None


    async def start_template_progress(
        self, token: str, step_id: int, question_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        try:
            data = await self._request(
                "POST",
                "/template-progress/start",
                token=token,
                json={"step_id": step_id, "question_id": question_id}
            )
            return data
        except Exception as exc:
            logger.exception("Failed to start template progress: %s", exc)
            return None

    async def submit_template_field(
        self, token: str, step_id: int, question_id: int, value: str
    ) -> Optional[Dict[str, Any]]:
        try:
            data = await self._request(
                "POST",
                "/template-progress/submit",
                token=token,
                json={"step_id": step_id, "question_id": question_id, "value": value}
            )
            return data
        except Exception as exc:
            logger.exception("Failed to submit template field: %s", exc)
            return None

    async def pause_template_progress(
        self, token: str, step_id: int, question_id: int
    ) -> Optional[Dict[str, Any]]:
        try:
            data = await self._request(
                "POST",
                "/template-progress/pause",
                token=token,
                json={"step_id": step_id, "question_id": question_id}
            )
            return data
        except Exception as exc:
            logger.exception("Failed to pause template progress: %s", exc)
            return None

    async def get_template_progress(
        self, token: str, step_id: int, question_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        try:
            data = await self._request(
                "GET",
                f"/template-progress/current?step_id={step_id}&question_id={question_id}",
                token=token
            )
            return data
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                return None
            raise
        except Exception as exc:
            logger.exception("Failed to get template progress: %s", exc)
            return None

    async def cancel_template_progress(
        self, token: str, step_id: int, question_id: int
    ) -> bool:
        """
        try:
            await self._request(
                "DELETE",
                f"/template-progress/cancel?step_id={step_id}&question_id={question_id}",
                token=token
            )
            return True
        except Exception as exc:
            logger.exception("Failed to cancel template progress: %s", exc)
            return False

    async def get_template_fields_info(self, token: str) -> Optional[Dict[str, Any]]:
        """
        try:
            data = await self._request(
                "GET",
                "/template-progress/fields-info",
                token=token
            )
            return data
        except Exception as exc:
            logger.exception("Failed to get template fields info: %s", exc)
            return None



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
    except Exception as exc:
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
    except Exception as exc:
        logger.exception("Failed to update profile for %s: %s", key, exc)
        return
    if updated:
        USER_CACHE[key] = updated



async def process_step_message(
    telegram_id: int,
    text: str,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    skip_validation: bool = False
) -> Dict[str, Any]:
    token = await get_or_fetch_token(telegram_id, username, first_name)
    if not token:
        return None

    success, error_message = await BACKEND_CLIENT.submit_step_answer(
        token, text, is_template_format=False, skip_validation=skip_validation
    )

    if success:
        return await BACKEND_CLIENT.get_next_step(token)
    elif error_message:
        return {"error": True, "message": error_message}

    return None


async def get_current_step_question(
    telegram_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    token = await get_or_fetch_token(telegram_id, username, first_name)
    if not token:
        return None
    return await BACKEND_CLIENT.get_next_step(token)



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
    payload = {"telegram_id": str(telegram_id), "message": text, "debug": debug}
    timeout = aiohttp.ClientTimeout(total=120)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(BACKEND_CHAT_URL, json=payload) as response:
            response.raise_for_status()
            try:
                data = await response.json()
            except aiohttp.ContentTypeError:
                raw = await response.text()
                return ChatResponse(reply=raw, log=None)

    reply = None
    log = None

    if isinstance(data, dict):
        for key in ("reply", "response", "message", "text", "answer"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                reply = value
                break

        if reply is None:
            reply = json.dumps(data, ensure_ascii=False, indent=2)

        if "log" in data and data["log"]:
            try:
                log = Log(**data["log"])
            except Exception:
                pass

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