"""Service for SOS chat functionality"""
from typing import List, Dict, Optional
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
    
    async def chat(
        self,
        user_id: int,
        help_type: Optional[str] = None,
        custom_text: Optional[str] = None,
        message: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, any]:
        """
        Handle SOS chat dialog.
        Returns dict with reply, is_finished, and updated conversation_history.
        """
        # Get user and personalization
        user_repo = UserRepository(self.session)
        user = await user_repo.get_by_id(user_id)
        if not user:
            raise RuntimeError(f"User not found for user_id={user_id}")
        
        personalized_prompt = await user_repo.get_personalized_prompt(user_id) or "Нет персонализации."
        
        # Get current question context
        question_text = await self.get_current_question_context(user_id) or "Вопрос не найден."
        
        # Load SOS system prompt
        sos_system_prompt = await PromptRepository.load_sos_prompt()
        
        # Build conversation context
        conversation_history = conversation_history or []
        
        # Initialize conversation if this is the first message
        if not conversation_history:
            # Build initial prompt based on help type
            help_type_prompts = {
                "question": f"Пользователь не понимает вопрос: {question_text}. Помоги разобраться.",
                "memory": f"Пользователь не может вспомнить ситуацию для вопроса: {question_text}. Помоги вспомнить.",
                "formulation": f"Пользователь застрял и не может сформулировать ответ на вопрос: {question_text}. Помоги сформулировать.",
                "support": f"Пользователю тяжело работать над вопросом: {question_text}. Окажи поддержку.",
                "custom": f"Пользователь просит помощи: {custom_text or 'не указано'}. Контекст вопроса: {question_text}."
            }
            
            initial_prompt = help_type_prompts.get(help_type or "support", help_type_prompts["support"])
            
            conversation_history = [
                {"role": "system", "content": f"{sos_system_prompt}\n\nПерсонализация: {personalized_prompt}\n\n{initial_prompt}"}
            ]
        
        # Add user message if provided
        if message:
            conversation_history.append({"role": "user", "content": message})
        
        # Call OpenAI
        provider = OpenAI()
        
        # Convert conversation history to messages format
        messages = []
        for msg in conversation_history:
            if msg["role"] == "system":
                messages.append({"role": "system", "content": msg["content"]})
            elif msg["role"] == "user":
                messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                messages.append({"role": "assistant", "content": msg["content"]})
        
        # Generate response using OpenAI provider
        # Build context-like structure for provider
        from assistant.context import Context
        from assistant.assistant import Assistant
        from assistant.response import Response
        
        # Create a simple context for SOS chat
        assistant = Assistant(
            system_prompt=sos_system_prompt,
            personalized_prompt=personalized_prompt,
            helper_prompt=""
        )
        
        # Get last user message
        last_user_msg = message if message else (conversation_history[-1]["content"] if conversation_history and conversation_history[-1]["role"] == "user" else "")
        
        # Build context
        context = Context(
            assistant=assistant,
            message=last_user_msg,
            last_messages=[]  # We'll handle history differently
        )
        
        # Call provider
        response: Response = await provider.respond(context)
        reply_text = response.message
        
        # Add assistant response to history
        conversation_history.append({"role": "assistant", "content": reply_text})
        
        # Determine if conversation is finished
        # Simple heuristic: if reply is long or contains certain phrases, consider it finished
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

