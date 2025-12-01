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
            # Question has step_id field
            return active_tail.question.step_id
        return None
    
    async def build_sos_prompt(self, help_type: str, step_number: int, question_text: str) -> Optional[str]:
        """
        Build specialized SOS prompt based on help type using knowledge base.
        
        Supported types:
        - 'direction': Помоги понять куда смотреть (replaces 'memory')
        - 'question': Не понимаю вопрос
        - 'support': Просто тяжело — нужна поддержка
        """
        # Load template based on help type
        if help_type == "direction" or help_type == "memory":
            template = await PromptRepository.load_sos_direction_prompt()
            # Fallback to old memory prompt if direction not found
            if not template:
                template = await PromptRepository.load_sos_memory_prompt()
        elif help_type == "question":
            template = await PromptRepository.load_sos_question_prompt()
        elif help_type == "support":
            template = await PromptRepository.load_sos_support_prompt()
        else:
            return None
        
        if not template:
            return None
        
        # For 'support' type, no need for knowledge base - return as is
        if help_type == "support":
            return template
        
        # Load knowledge for this step (for direction and question types)
        step_knowledge = await PromptRepository.get_step_knowledge(step_number)
        
        # Format typical situations as bullet list
        typical_situations = "\n".join([f"• {s}" for s in step_knowledge.get("typical_situations", [])])
        
        # Format guiding areas as bullet list  
        guiding_areas = "\n".join([f"• {a}" for a in step_knowledge.get("guiding_areas", [])])
        
        # Format keywords
        keywords = ", ".join(step_knowledge.get("keywords", []))
        
        # Replace placeholders
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
        
        # Get current step number for knowledge base
        step_number = await self.get_current_step_number(user_id) or 1
        
        # Load SOS system prompt
        sos_system_prompt = await PromptRepository.load_sos_prompt()
        
        # Build conversation context
        conversation_history = conversation_history or []
        
        # Initialize conversation if this is the first message
        if not conversation_history:
            # Try to build specialized prompt for known SOS types
            specialized_prompt = None
            
            # Map old type names to new ones for backwards compatibility
            effective_type = help_type
            if help_type == "memory":
                effective_type = "direction"  # 'memory' renamed to 'direction'
            
            # Try to load specialized prompt
            if effective_type in ["direction", "question", "support"]:
                specialized_prompt = await self.build_sos_prompt(effective_type, step_number, question_text)
            
            if specialized_prompt:
                # Use specialized prompt with knowledge base
                if effective_type == "support":
                    # Support type doesn't need personalization context
                    system_content = specialized_prompt
                else:
                    system_content = f"{specialized_prompt}\n\n## ПЕРСОНАЛИЗАЦИЯ ПОЛЬЗОВАТЕЛЯ\n{personalized_prompt}"
            else:
                # Fallback to generic prompts for custom type or if specialized prompt not found
                help_type_prompts = {
                    "formulation": f"Пользователь застрял и не может сформулировать ответ на вопрос: {question_text}. Помоги сформулировать.",
                    "custom": f"Пользователь просит помощи: {custom_text or 'не указано'}. Контекст вопроса: {question_text}."
                }
                
                initial_prompt = help_type_prompts.get(help_type or "custom", help_type_prompts["custom"])
                system_content = f"{sos_system_prompt}\n\nПерсонализация: {personalized_prompt}\n\n{initial_prompt}"
            
            conversation_history = [
                {"role": "system", "content": system_content}
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
        
        # Get the actual system prompt used (from conversation history)
        actual_system_prompt = conversation_history[0]["content"] if conversation_history else sos_system_prompt
        
        # Create a simple context for SOS chat
        assistant = Assistant(
            system_prompt=actual_system_prompt,
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

