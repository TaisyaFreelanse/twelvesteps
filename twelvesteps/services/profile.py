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
        try:
            section = await self.repo.get_section_by_id(section_id)
            if not section:
                return None

            # Check if user has data for this section
            if user_id:
                try:
                    data = await self.repo.get_section_data(user_id, section_id)
                    # This will be used in the response schema
                    section.has_data = data is not None
                except Exception as e:
                    # If there's an error checking data (e.g., migration not applied),
                    # just set has_data to False and continue
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Error checking section data for user {user_id}, section {section_id}: {e}")
                    section.has_data = False

            return section
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in get_section_detail for section_id={section_id}, user_id={user_id}: {e}")
            raise

    async def save_answer(
        self, user_id: int, question_id: int, answer_text: str
    ) -> Tuple[ProfileAnswer, Optional[ProfileQuestion]]:
        """
        Save answer to a question and suggest next question based on answer.
        Returns (answer, next_question)
        """
        answer = await self.repo.save_answer(user_id, question_id, answer_text)
        
        # Ensure the answer is flushed so it's visible in subsequent queries
        await self.session.flush()
        
        # Get section_id from question
        from sqlalchemy import select
        query = select(ProfileQuestion).where(ProfileQuestion.id == question_id)
        result = await self.session.execute(query)
        question = result.scalar_one_or_none()
        
        if question:
            # Get next question based on answer
            # Refresh session to ensure we see the newly saved answer
            await self.session.refresh(answer)
            next_question = await self.get_next_question_for_section(
                user_id, question.section_id, answer_text
            )
            return answer, next_question
        
        return answer, None

    async def save_free_text(
        self, 
        user_id: int, 
        section_id: Optional[int], 
        text: str,
        subblock_name: Optional[str] = None,
        entity_type: Optional[str] = None,
        importance: Optional[float] = 1.0,
        is_core_personality: bool = False,
        tags: Optional[str] = None
    ) -> ProfileSectionData:
        """Save free text as a new entry (history). If section_id is None, it's a general free text"""
        if section_id is None:
            raise ValueError("section_id is required for free text")
        
        return await self.repo.save_free_text(
            user_id=user_id,
            section_id=section_id,
            content=text,
            subblock_name=subblock_name,
            entity_type=entity_type,
            importance=importance,
            is_core_personality=is_core_personality,
            tags=tags
        )
    
    async def get_section_data_history(
        self, user_id: int, section_id: int, limit: Optional[int] = None
    ) -> List[ProfileSectionData]:
        """Get history of entries for a section"""
        return await self.repo.get_section_data_history(user_id, section_id, limit)
    
    async def get_section_data_by_subblock(
        self, user_id: int, section_id: int, subblock_name: str
    ) -> List[ProfileSectionData]:
        """Get all entries for a specific subblock"""
        return await self.repo.get_section_data_by_subblock(user_id, section_id, subblock_name)

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
        If all basic questions are answered, generates a follow-up question using LLM.
        Otherwise, returns the first unanswered basic question or suggests next based on answer.
        
        Limits follow-up questions to maximum 2 per section to prevent infinite loops.
        """
        section = await self.repo.get_section_by_id(section_id)
        if not section:
            return None
        
        questions = section.questions
        if not questions:
            return None
        
        # Get user's answers for this section
        # Note: get_user_answers_for_section returns all versions, but we only need unique question_ids
        user_answers = await self.repo.get_user_answers_for_section(user_id, section_id)
        # Get unique question IDs that have been answered (any version counts as answered)
        answered_question_ids = {ans.question_id for ans in user_answers}
        
        # Find unanswered questions
        unanswered = [q for q in questions if q.id not in answered_question_ids]
        
        # Debug logging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[ProfileService.get_next_question_for_section] Section {section_id}: "
                   f"Total questions: {len(questions)}, "
                   f"Answered: {len(answered_question_ids)}, "
                   f"Unanswered: {len(unanswered)}, "
                   f"Has last_answer: {last_answer is not None}")
        
        # If all basic questions are answered, check if we should generate follow-up question
        if not unanswered and last_answer:
            # Check how many generated questions (free text entries) already exist for this section
            # This prevents infinite loops of follow-up questions
            section_data = await self.repo.get_section_data(user_id, section_id)
            generated_count = 0
            if section_data and section_data.content:
                # Count how many times "[Сгенерированный вопрос]" appears in content
                # Each generated question is saved with this marker
                content = section_data.content
                generated_count = content.count("[Сгенерированный вопрос]")
            
            # Limit to maximum 1 follow-up question per section to prevent infinite loops
            MAX_FOLLOW_UP_QUESTIONS = 1
            if generated_count >= MAX_FOLLOW_UP_QUESTIONS:
                return None  # Already generated enough follow-up questions
            
            try:
                follow_up_question = await self._generate_follow_up_question(
                    user_id, section, last_answer
                )
                return follow_up_question
            except Exception as e:
                print(f"[ProfileService] Error generating follow-up question: {e}")
                return None  # All questions answered, no follow-up generated
        
        if not unanswered:
            return None  # All questions answered, but no last_answer to generate follow-up
        
        # If no last_answer provided, return first unanswered question
        if not last_answer:
            return unanswered[0] if unanswered else None
        
        # For mini-survey mode, just return next unanswered question in order
        # Don't use LLM suggestion to avoid delays and potential failures
        # Simply return the first unanswered question
        if unanswered:
            return unanswered[0]
        
        # This should not happen if we have unanswered questions
        return None

    async def _suggest_next_question(
        self,
        section: ProfileSection,
        unanswered_questions: List[ProfileQuestion],
        last_answer: str
    ) -> ProfileQuestion:
        """
        Use LLM to suggest the most relevant next question based on the user's answer.
        This is used when there are still unanswered basic questions.
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
    
    async def _generate_follow_up_question(
        self,
        user_id: int,
        section: ProfileSection,
        last_answer: str
    ) -> Optional[ProfileQuestion]:
        """
        Generate a follow-up question after all basic questions are answered.
        Uses the profile_next_question prompt to create a contextual question.
        Returns a temporary ProfileQuestion object (with id=-1 to indicate it's generated).
        """
        from repositories.PromptRepository import PromptRepository
        from db.models import ProfileQuestion
        
        # Load the prompt
        prompt_template = await PromptRepository.load_profile_next_question_prompt()
        if not prompt_template:
            return None
        
        # Get all answers for this section
        user_answers = await self.repo.get_user_answers_for_section(user_id, section.id)
        
        # Build context: all answers in this section
        answers_text = ""
        for answer in user_answers:
            # Get question text
            from sqlalchemy import select
            query = select(ProfileQuestion).where(ProfileQuestion.id == answer.question_id)
            result = await self.session.execute(query)
            question = result.scalar_one_or_none()
            if question:
                answers_text += f"Вопрос: {question.question_text}\n"
                answers_text += f"Ответ: {answer.answer_text}\n\n"
        
        # Get personalized prompt for user context
        from repositories.UserRepository import UserRepository
        user_repo = UserRepository(self.session)
        personalized_prompt = await user_repo.get_personalized_prompt(user_id) or "Нет персонализации."
        
        # Get frames related to this section (simplified - just use personalized prompt)
        # In future, could query Frame table for section-related frames
        
        # Replace placeholders in prompt
        prompt = prompt_template.replace("[НАЗВАНИЕ_БЛОКА]", section.name)
        
        # Build full prompt
        full_prompt = f"""{prompt}

## КОНТЕКСТ БЛОКА "{section.name}"

### Все ответы в этом блоке:
{answers_text}

### Последний ответ:
{last_answer}

### Общее ядро личности:
{personalized_prompt[:1000]}...

### Уже заданные вопросы в этом блоке:
{chr(10).join([f"- {q.question_text}" for q in section.questions])}

---

Сформулируй уточняющий вопрос (или верни пустую строку, если не нужен)."""

        try:
            from openai import AsyncOpenAI
            import os
            from dotenv import load_dotenv
            load_dotenv()
            
            async with AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY")) as client:
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Ты помогаешь формулировать уточняющие вопросы для психологического профиля."},
                        {"role": "user", "content": full_prompt}
                    ],
                    max_tokens=150,
                    temperature=0.7,
                )
            
            generated_question = response.choices[0].message.content.strip()
            
            # If empty or too short, return None
            if not generated_question or len(generated_question) < 10:
                return None
            
            # Create a temporary ProfileQuestion object
            # Use id=-1 to indicate it's a generated question (not from DB)
            temp_question = ProfileQuestion(
                id=-1,  # Special ID for generated questions
                section_id=section.id,
                question_text=generated_question,
                order_index=999,  # High order to indicate it's after basic questions
                is_optional=True
            )
            return temp_question
            
        except Exception as e:
            print(f"[ProfileService._generate_follow_up_question] Error: {e}")
            return None

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

