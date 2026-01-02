"""Service for SOS chat functionality"""
from typing import List, Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.models import Tail, TailType, User
from repositories.UserRepository import UserRepository
from repositories.PromptRepository import PromptRepository
from llm.openai_provider import OpenAI


class SosService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_current_question_context(self, user_id: int) -> Optional[str]:
        """Get current step question text for context"""
        stmt = select(Tail).options(selectinload(Tail.question)).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        )
        result = await self.session.execute(stmt)
        active_tail = result.scalars().first()

        if active_tail and active_tail.question:
            return active_tail.question.text
        return None

    async def get_current_step_number(self, user_id: int) -> Optional[int]:
        """Get current step number for the user"""
        stmt = select(Tail).options(selectinload(Tail.question)).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        )
        result = await self.session.execute(stmt)
        active_tail = result.scalars().first()

        if active_tail and active_tail.question:
            return active_tail.question.step_id
        return None

    async def _get_user_context(self, user_id: int) -> Optional[str]:
        """Extract user context (HALT, time of day, cravings, etc.) from session context"""
        try:
            from repositories.SessionContextRepository import SessionContextRepository
            from db.models import SessionType

            session_context_repo = SessionContextRepository(self.session)
            active_context = await session_context_repo.get_active_context(user_id)

            if active_context and active_context.context_data:
                context_parts = []
                context_data = active_context.context_data

                halt_states = []
                if context_data.get("hungry"):
                    halt_states.append("голод")
                if context_data.get("angry"):
                    halt_states.append("злость")
                if context_data.get("lonely"):
                    halt_states.append("одиночество")
                if context_data.get("tired"):
                    halt_states.append("усталость")

                if halt_states:
                    context_parts.append(f"HALT: {', '.join(halt_states)}")

                from datetime import datetime
                current_hour = datetime.now().hour
                if 6 <= current_hour < 12:
                    context_parts.append("утро")
                elif 12 <= current_hour < 18:
                    context_parts.append("день")
                elif 18 <= current_hour < 22:
                    context_parts.append("вечер")
                else:
                    context_parts.append("ночь")

                if context_data.get("craving") or context_data.get("urge"):
                    context_parts.append("тяга")

                if context_parts:
                    return ", ".join(context_parts)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to extract user context: {e}")

        return None

    async def build_sos_prompt(self, help_type: str, step_number: int, question_text: str, user_context: Optional[str] = None, time_window: str = "за последние 72 часа") -> Optional[str]:
        """Build SOS prompt based on help type."""
        if help_type == "direction" or help_type == "memory":
            template = await PromptRepository.load_sos_direction_prompt()
            if not template:
                template = await PromptRepository.load_sos_memory_prompt()
        elif help_type == "question":
            template = await PromptRepository.load_sos_question_prompt()
        elif help_type == "support":
            template = await PromptRepository.load_sos_support_prompt()
        elif help_type == "examples":
            template = await PromptRepository.load_sos_examples_prompt()
        else:
            return None

        if not template:
            return None

        if help_type == "support":
            return template

        if help_type == "examples":
            prompt = template.replace("{{step_number}}", str(step_number))
            prompt = prompt.replace("{{step_question}}", question_text)
            prompt = prompt.replace("{{time_window}}", time_window)
            prompt = prompt.replace("{{user_context}}", user_context or "не указано")
            return prompt

        step_knowledge = await PromptRepository.get_step_knowledge(step_number)

        typical_situations = "\n".join([f"• {s}" for s in step_knowledge.get("typical_situations", [])])

        guiding_areas = "\n".join([f"• {a}" for a in step_knowledge.get("guiding_areas", [])])

        keywords = ", ".join(step_knowledge.get("keywords", []))

        prompt = template.replace("{{step_number}}", str(step_number))
        prompt = prompt.replace("{{step_name}}", step_knowledge.get("name", f"Шаг {step_number}"))
        prompt = prompt.replace("{{step_essence}}", step_knowledge.get("essence", ""))
        prompt = prompt.replace("{{step_keywords}}", keywords)
        prompt = prompt.replace("{{question_text}}", question_text)
        prompt = prompt.replace("{{typical_situations}}", typical_situations)
        prompt = prompt.replace("{{guiding_areas}}", guiding_areas)

        return prompt

    async def chat(
        self,
        user_id: int,
        help_type: Optional[str] = None,
        custom_text: Optional[str] = None,
        message: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, any]:
        """Handle SOS chat conversation."""
        user_repo = UserRepository(self.session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            raise RuntimeError(f"User not found for user_id={user_id}")

        personalized_prompt = await user_repo.get_personalized_prompt(user_id) or "Нет персонализации."

        question_text = await self.get_current_question_context(user_id) or "Вопрос не найден."

        step_number = await self.get_current_step_number(user_id) or 1

        sos_system_prompt = await PromptRepository.load_sos_prompt()

        conversation_history = conversation_history or []

        if not conversation_history:
            specialized_prompt = None

            effective_type = help_type
            if help_type == "memory":
                effective_type = "direction"

            if effective_type in ["direction", "question", "support", "examples"]:
                user_context = await self._get_user_context(user_id)
                time_window = "за последние 72 часа"
                specialized_prompt = await self.build_sos_prompt(
                    effective_type, step_number, question_text,
                    user_context=user_context, time_window=time_window
                )

            if specialized_prompt:
                if effective_type == "support":
                    system_content = specialized_prompt
                else:
                    system_content = f"{specialized_prompt}\n\n## ПЕРСОНАЛИЗАЦИЯ ПОЛЬЗОВАТЕЛЯ\n{personalized_prompt}"
            else:
                help_type_prompts = {
                    "formulation": f"Пользователь застрял и не может сформулировать ответ на вопрос: {question_text}. Помоги сформулировать.",
                    "custom": f"Пользователь просит помощи: {custom_text or 'не указано'}. Контекст вопроса: {question_text}."
                }

                initial_prompt = help_type_prompts.get(help_type or "custom", help_type_prompts["custom"])
                system_content = f"{sos_system_prompt}\n\nПерсонализация: {personalized_prompt}\n\n{initial_prompt}"

            conversation_history = [
                {"role": "system", "content": system_content}
            ]

        if message:
            conversation_history.append({"role": "user", "content": message})

        provider = OpenAI()

        messages = []
        for msg in conversation_history:
            if msg["role"] == "system":
                messages.append({"role": "system", "content": msg["content"]})
            elif msg["role"] == "user":
                messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                messages.append({"role": "assistant", "content": msg["content"]})

        from assistant.context import Context
        from assistant.assistant import Assistant
        from assistant.response import Response

        actual_system_prompt = conversation_history[0]["content"] if conversation_history else sos_system_prompt

        assistant = Assistant(
            system_prompt=actual_system_prompt,
            personalized_prompt=personalized_prompt,
            helper_prompt=""
        )

        last_user_msg = message if message else (conversation_history[-1]["content"] if conversation_history and conversation_history[-1]["role"] == "user" else "")

        context = Context(
            assistant=assistant,
            message=last_user_msg,
            last_messages=[]
        )

        response: Response = await provider.respond(context)
        reply_text = response.message

        conversation_history.append({"role": "assistant", "content": reply_text})

        is_finished = (
            len(reply_text) > 200 or
            "заверш" in reply_text.lower() or
            "удачи" in reply_text.lower() or
            "успех" in reply_text.lower()
        )

        return {
            "reply": reply_text,
            "is_finished": is_finished,
            "conversation_history": conversation_history
        }

