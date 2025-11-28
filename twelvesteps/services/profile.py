from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.ProfileRepository import ProfileRepository
from db.models import (
    ProfileSection,
    ProfileSectionData,
    ProfileQuestion,
    ProfileAnswer,
)
from llm.openai_provider import OpenAI


class ProfileService:
    def __init__(self, session: AsyncSession):
        self.repo = ProfileRepository(session)
        self.session = session

    async def get_all_sections(self, user_id: Optional[int] = None) -> List[ProfileSection]:
        """Get all sections available to user"""
        return await self.repo.get_all_sections(user_id)

    async def get_section_detail(
        self, section_id: int, user_id: Optional[int] = None
    ) -> Optional[ProfileSection]:
        """Get section with questions and check if user has data"""
        section = await self.repo.get_section_by_id(section_id)
        if not section:
            return None

        # Check if user has data for this section
        if user_id:
            data = await self.repo.get_section_data(user_id, section_id)
            # This will be used in the response schema
            section.has_data = data is not None

        return section

    async def save_answer(
        self, user_id: int, question_id: int, answer_text: str
    ) -> Tuple[ProfileAnswer, Optional[ProfileQuestion]]:
        """
        Save answer to a question and suggest next question based on answer.
        Returns (answer, next_question)
        """
        answer = await self.repo.save_answer(user_id, question_id, answer_text)
        
        # Get section_id from question
        from sqlalchemy import select
        query = select(ProfileQuestion).where(ProfileQuestion.id == question_id)
        result = await self.session.execute(query)
        question = result.scalar_one_or_none()
        
        if question:
            # Get next question based on answer
            next_question = await self.get_next_question_for_section(
                user_id, question.section_id, answer_text
            )
            return answer, next_question
        
        return answer, None

    async def save_free_text(
        self, user_id: int, section_id: Optional[int], text: str
    ) -> ProfileSectionData:
        """Save free text. If section_id is None, it's a general free text"""
        # For general free text, we might need special handling later
        # For now, if section_id is None, we'll need to create a special section or handle differently
        # But according to spec, general free text should be distributed across sections
        # For now, we'll require section_id
        if section_id is None:
            raise ValueError("section_id is required for free text")
        
        return await self.repo.save_free_text(user_id, section_id, text)

    async def create_custom_section(
        self, user_id: int, name: str, icon: Optional[str] = None
    ) -> ProfileSection:
        """Create a custom section for user"""
        return await self.repo.create_custom_section(user_id, name, icon)

    async def update_section(
        self, section_id: int, name: Optional[str] = None,
        icon: Optional[str] = None, order_index: Optional[int] = None
    ) -> Optional[ProfileSection]:
        """Update a custom section"""
        return await self.repo.update_section(section_id, name, icon, order_index)

    async def delete_section(self, section_id: int, user_id: int) -> bool:
        """Delete a custom section (only custom sections owned by user)"""
        return await self.repo.delete_section(section_id, user_id)

    async def get_section_summary(
        self, user_id: int, section_id: int
    ) -> dict:
        """Get summary for a section"""
        return await self.repo.get_section_summary(user_id, section_id)

    def split_long_message(self, text: str, max_length: int = 4096) -> List[str]:
        """
        Split long message into chunks preserving context.
        Tries to split at sentence boundaries when possible.
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        
        for para in paragraphs:
            # If paragraph itself is too long, split by sentences
            if len(para) > max_length:
                sentences = para.split('. ')
                for i, sentence in enumerate(sentences):
                    if i < len(sentences) - 1:
                        sentence += '. '
                    
                    if len(current_chunk) + len(sentence) > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = sentence
                        else:
                            # Single sentence is too long, split by words
                            words = sentence.split()
                            for word in words:
                                if len(current_chunk) + len(word) + 1 > max_length:
                                    if current_chunk:
                                        chunks.append(current_chunk.strip())
                                        current_chunk = word
                                    else:
                                        # Single word is too long, force split
                                        chunks.append(word[:max_length])
                                        current_chunk = word[max_length:]
                                else:
                                    current_chunk += (' ' if current_chunk else '') + word
                    else:
                        current_chunk += sentence
            else:
                # Check if adding paragraph would exceed limit
                if len(current_chunk) + len(para) + 2 > max_length:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = para
                    else:
                        chunks.append(para)
                else:
                    current_chunk += ('\n\n' if current_chunk else '') + para
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    async def get_next_question_for_section(
        self, user_id: int, section_id: int, last_answer: Optional[str] = None
    ) -> Optional[ProfileQuestion]:
        """
        Get next question for a section based on FSM logic.
        If last_answer is provided, uses LLM to suggest the most relevant next question.
        Otherwise, returns the first unanswered question.
        """
        section = await self.repo.get_section_by_id(section_id)
        if not section:
            return None
        
        questions = section.questions
        if not questions:
            return None
        
        # Get user's answers for this section
        user_answers = await self.repo.get_user_answers_for_section(user_id, section_id)
        answered_question_ids = {ans.question_id for ans in user_answers}
        
        # Find unanswered questions
        unanswered = [q for q in questions if q.id not in answered_question_ids]
        
        if not unanswered:
            return None  # All questions answered
        
        # If no last_answer provided, return first unanswered question
        if not last_answer:
            return unanswered[0]
        
        # Use LLM to suggest next question based on answer
        try:
            next_question = await self._suggest_next_question(
                section, unanswered, last_answer
            )
            return next_question
        except Exception as e:
            # Fallback to first unanswered question if LLM fails
            print(f"[ProfileService] Error suggesting next question: {e}")
            return unanswered[0]

    async def _suggest_next_question(
        self,
        section: ProfileSection,
        unanswered_questions: List[ProfileQuestion],
        last_answer: str
    ) -> ProfileQuestion:
        """
        Use LLM to suggest the most relevant next question based on the user's answer.
        """
        llm = OpenAI()
        
        # Build prompt for question suggestion
        questions_text = "\n".join([
            f"{i+1}. [ID: {q.id}] {q.question_text}"
            for i, q in enumerate(unanswered_questions)
        ])
        
        system_prompt = f"""Ты помогаешь определить, какой следующий вопрос задать пользователю в разделе "{section.name}".

Пользователь только что ответил на вопрос. На основе его ответа выбери наиболее подходящий следующий вопрос из списка.

Верни только номер вопроса (1, 2, 3 и т.д.) без дополнительного текста."""

        user_prompt = f"""Раздел: {section.name}

Ответ пользователя:
{last_answer}

Доступные вопросы:
{questions_text}

Какой вопрос задать следующим? Верни только номер."""

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # Use OpenAI to get suggestion
            from openai import AsyncOpenAI
            import os
            from dotenv import load_dotenv
            load_dotenv()
            
            async with AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) as client:
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    max_tokens=10,
                    temperature=0.3,
                )
            
            suggestion = response.choices[0].message.content.strip()
            # Extract number from response
            try:
                question_num = int(''.join(filter(str.isdigit, suggestion)))
                if 1 <= question_num <= len(unanswered_questions):
                    return unanswered_questions[question_num - 1]
            except ValueError:
                pass
            
            # Fallback to first question
            return unanswered_questions[0]
            
        except Exception as e:
            print(f"[ProfileService._suggest_next_question] Error: {e}")
            return unanswered_questions[0]

    async def get_fsm_state(
        self, user_id: int, section_id: int
    ) -> dict:
        """
        Get current FSM state for a section:
        - current_question_id: ID of current question (if any)
        - answered_count: number of answered questions
        - total_questions: total questions in section
        - is_complete: whether all questions are answered
        """
        section = await self.repo.get_section_by_id(section_id)
        if not section:
            return {
                "current_question_id": None,
                "answered_count": 0,
                "total_questions": 0,
                "is_complete": False,
            }
        
        questions = section.questions
        user_answers = await self.repo.get_user_answers_for_section(user_id, section_id)
        answered_question_ids = {ans.question_id for ans in user_answers}
        
        # Get current question (first unanswered)
        unanswered = [q for q in questions if q.id not in answered_question_ids]
        current_question = unanswered[0] if unanswered else None
        
        return {
            "current_question_id": current_question.id if current_question else None,
            "answered_count": len(answered_question_ids),
            "total_questions": len(questions),
            "is_complete": len(unanswered) == 0,
        }

