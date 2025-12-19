from datetime import datetime
from typing import Optional, Union

# Update imports to match your models exactly
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Step, Question, StepAnswer, UserStep, 
    Tail, TailType, StepProgressStatus, User, AnswerTemplate
)
import json

class StepFlowService:
    # Минимальное количество символов для ответа на вопрос (защита от случайного пропуска)
    MIN_ANSWER_LENGTH = 50  # минимум 50 символов
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_current_step_info(self, user_id: int) -> Optional[dict]:
        """Get current step information including step number"""
        from sqlalchemy.orm import selectinload
        
        # Find current step in progress
        stmt_user_step = select(UserStep).where(
            UserStep.user_id == user_id,
            UserStep.status == StepProgressStatus.IN_PROGRESS
        )
        
        result = await self.session.execute(stmt_user_step)
        current_user_step = result.scalars().first()
        
        if not current_user_step:
            # Try to initialize next step
            current_user_step = await self._initialize_next_step(user_id)
            if not current_user_step:
                return None
        
        # Get step by step_id
        stmt_step = select(Step).where(Step.id == current_user_step.step_id)
        result_step = await self.session.execute(stmt_step)
        step = result_step.scalars().first()
        
        if not step:
            return None
        
        # Get total number of steps
        stmt_total = select(Step).order_by(Step.index.desc()).limit(1)
        result_total = await self.session.execute(stmt_total)
        last_step = result_total.scalars().first()
        total_steps = last_step.index if last_step else 12  # Default to 12 if no steps found
        
        # Get answered questions count for current step
        stmt_answered = select(StepAnswer).where(
            StepAnswer.user_id == user_id,
            StepAnswer.step_id == current_user_step.step_id
        )
        result_answered = await self.session.execute(stmt_answered)
        answered_count = len(result_answered.scalars().all())
        
        # Get total questions count for current step
        stmt_questions = select(Question).where(Question.step_id == current_user_step.step_id)
        result_questions = await self.session.execute(stmt_questions)
        total_questions = len(result_questions.scalars().all())
        
        return {
            "step_id": step.id,
            "step_number": step.index,
            "step_title": step.title,
            "step_description": step.description,
            "total_steps": total_steps,
            "answered_questions": answered_count,
            "total_questions": total_questions,
            "status": current_user_step.status.value
        }
    
    async def get_all_steps(self) -> list[dict]:
        """Get list of all steps"""
        stmt = select(Step).order_by(Step.index)
        result = await self.session.execute(stmt)
        steps = result.scalars().all()
        
        return [{"id": s.id, "number": s.index} for s in steps]
    
    async def get_step_questions(self, step_id: int) -> list[dict]:
        """Get list of questions for a step"""
        stmt = select(Question).where(Question.step_id == step_id).order_by(Question.id)
        result = await self.session.execute(stmt)
        questions = result.scalars().all()
        
        # Ensure id and text are not None
        return [
            {"id": int(q.id), "text": str(q.text) if q.text else ""} 
            for q in questions 
            if q.id is not None
        ]
    
    async def save_draft(self, user_id: int, draft_text: str) -> bool:
        """Save draft answer in Tail.payload without closing Tail"""
        import logging
        logger = logging.getLogger(__name__)
        
        stmt = select(Tail).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        )
        result = await self.session.execute(stmt)
        active_tail = result.scalars().first()
        
        logger.info(f"save_draft for user {user_id}: active_tail={active_tail is not None}")
        
        if not active_tail:
            logger.warning(f"No active tail found for user {user_id} to save draft")
            return False
        
        # Update payload with draft
        # IMPORTANT: For JSON fields, we need to create a new dict or use flag_modified
        # to ensure SQLAlchemy tracks the change
        if active_tail.payload is None:
            active_tail.payload = {}
        
        # Create a new dict to ensure SQLAlchemy tracks the change
        new_payload = dict(active_tail.payload) if active_tail.payload else {}
        new_payload["draft"] = draft_text
        new_payload["draft_saved_at"] = datetime.now().isoformat()
        active_tail.payload = new_payload
        
        # Explicitly mark the field as modified for JSON columns
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(active_tail, "payload")
        
        logger.info(f"Saving draft to tail {active_tail.id}, payload keys: {list(active_tail.payload.keys())}")
        
        # Flush to ensure changes are staged before commit
        await self.session.flush()
        
        # Commit the transaction
        await self.session.commit()
        logger.info(f"Committed draft save for tail {active_tail.id}")
        
        # Verify it was saved by re-fetching
        await self.session.refresh(active_tail)
        saved_draft = active_tail.payload.get("draft") if active_tail.payload else None
        logger.info(f"Draft saved verification for user {user_id}, tail {active_tail.id}: saved_draft length={len(saved_draft) if saved_draft else 0}, payload keys: {list(active_tail.payload.keys()) if active_tail.payload else 'None'}")
        
        return True
    
    async def get_previous_answer(self, user_id: int, question_id: int) -> Optional[str]:
        """Get previous answer for a question if exists"""
        stmt = select(StepAnswer).where(
            StepAnswer.user_id == user_id,
            StepAnswer.question_id == question_id
        ).order_by(desc(StepAnswer.version)).limit(1)
        
        result = await self.session.execute(stmt)
        previous_answer = result.scalars().first()
        
        if previous_answer:
            return previous_answer.answer_text
        return None
    
    async def get_active_tail_draft(self, user_id: int) -> Optional[str]:
        """Get draft from active Tail if exists"""
        import logging
        logger = logging.getLogger(__name__)
        
        stmt = select(Tail).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        )
        result = await self.session.execute(stmt)
        active_tail = result.scalars().first()
        
        logger.info(f"get_active_tail_draft for user {user_id}: active_tail={active_tail is not None}, tail_id={active_tail.id if active_tail else None}")
        
        if active_tail:
            # Refresh to get latest data from database
            await self.session.refresh(active_tail)
            logger.info(f"Active tail found: id={active_tail.id}, payload type={type(active_tail.payload)}, payload={active_tail.payload}")
            
            if active_tail.payload and "draft" in active_tail.payload:
                draft_value = active_tail.payload["draft"]
                logger.info(f"Draft found in payload: length={len(draft_value) if draft_value else 0}")
                return draft_value
            else:
                payload_keys = list(active_tail.payload.keys()) if active_tail.payload else None
                logger.warning(f"No draft in payload for user {user_id}, tail_id={active_tail.id}, payload keys: {payload_keys}")
        else:
            logger.warning(f"No active tail found for user {user_id}")
        
        return None
    
    async def get_example_answers(self, question_id: int, user_id: int, limit: int = 5) -> list[dict]:
        """Get example answers for a question from other users (anonymized)"""
        from sqlalchemy import func
        
        # Get random answers from other users for this question
        # Exclude current user's answers
        stmt = (
            select(StepAnswer)
            .where(
                StepAnswer.question_id == question_id,
                StepAnswer.user_id != user_id
            )
            .order_by(func.random())
            .limit(limit)
        )
        
        result = await self.session.execute(stmt)
        answers = result.scalars().all()
        
        # Return anonymized examples (just the text, no user info)
        examples = []
        for answer in answers:
            # Truncate long answers to first 200 characters for preview
            answer_text = answer.answer_text
            if len(answer_text) > 200:
                answer_text = answer_text[:200] + "..."
            examples.append({
                "text": answer_text,
                "preview": answer_text[:100] + "..." if len(answer_text) > 100 else answer_text
            })
        
        return examples
    
    async def get_active_question_id(self, user_id: int) -> Optional[int]:
        """Get question_id from active Tail if exists"""
        stmt = select(Tail).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        )
        result = await self.session.execute(stmt)
        active_tail = result.scalars().first()
        
        if active_tail and active_tail.step_question_id:
            return active_tail.step_question_id
        return None
    
    async def get_last_answered_question_id(self, user_id: int) -> Optional[int]:
        """Get question_id from the last answered question (last closed Tail)"""
        stmt = (
            select(Tail)
            .where(
                Tail.user_id == user_id,
                Tail.tail_type == TailType.STEP_QUESTION,
                Tail.is_closed == True
            )
            .order_by(desc(Tail.closed_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        last_tail = result.scalars().first()
        
        if last_tail and last_tail.step_question_id:
            return last_tail.step_question_id
        return None
    
    async def switch_to_question(self, user_id: int, question_id: int) -> Optional[str]:
        """Switch to a specific question, also switching step if needed"""
        # First, get the question to find which step it belongs to
        stmt_question = select(Question).where(Question.id == question_id)
        result_q = await self.session.execute(stmt_question)
        question = result_q.scalars().first()
        
        if not question:
            return None
        
        target_step_id = question.step_id
        
        # Get current step
        stmt_user_step = select(UserStep).where(
            UserStep.user_id == user_id,
            UserStep.status == StepProgressStatus.IN_PROGRESS
        )
        result = await self.session.execute(stmt_user_step)
        current_user_step = result.scalars().first()
        
        # If question is in a different step, we need to switch steps
        if not current_user_step or current_user_step.step_id != target_step_id:
            # Close current step if exists (mark as not started to pause it)
            if current_user_step:
                current_user_step.status = StepProgressStatus.NOT_STARTED
            
            # Check if user already has a record for target step
            stmt_target_step = select(UserStep).where(
                UserStep.user_id == user_id,
                UserStep.step_id == target_step_id
            )
            result_target = await self.session.execute(stmt_target_step)
            target_user_step = result_target.scalars().first()
            
            if target_user_step:
                # Reactivate existing user step
                target_user_step.status = StepProgressStatus.IN_PROGRESS
            else:
                # Create new user step
                target_user_step = UserStep(
                    user_id=user_id,
                    step_id=target_step_id,
                    status=StepProgressStatus.IN_PROGRESS,
                    started_at=datetime.now()
                )
                self.session.add(target_user_step)
        
        # Close current tail if exists
        stmt_tail = select(Tail).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        )
        result_tail = await self.session.execute(stmt_tail)
        current_tail = result_tail.scalars().first()
        
        if current_tail:
            current_tail.is_closed = True
            current_tail.closed_at = datetime.now()
        
        # Create new tail for selected question
        new_tail = Tail(
            user_id=user_id,
            tail_type=TailType.STEP_QUESTION,
            step_id=target_step_id,
            step_question_id=question_id,
            is_closed=False,
            payload={}
        )
        self.session.add(new_tail)
        await self.session.commit()
        
        return question.text

    async def get_next_question_for_user(self, user_id: int) -> Union[str, None]:
        """
        Determines the user's current progress, finds the next unanswered question,
        creates a 'Tail' record to track the state, and returns the question text.
        Returns None if all steps are completed.
        """
        
        # 1. Check if there is already an open TAIL (User hasn't answered yet)
        stmt_tail = select(Tail).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        ).options(selectinload(Tail.question))
        
        result_tail = await self.session.execute(stmt_tail)
        active_tail = result_tail.scalars().first()

        # If found, return the existing question text
        # IMPORTANT: Don't create a new Tail if one already exists, even if question is not loaded
        # This preserves the draft in payload
        if active_tail:
            if active_tail.question:
                return active_tail.question.text
            else:
                # Question not loaded, but Tail exists - fetch question text manually
                if active_tail.step_question_id:
                    stmt_q = select(Question).where(Question.id == active_tail.step_question_id)
                    result_q = await self.session.execute(stmt_q)
                    question = result_q.scalars().first()
                    if question:
                        return question.text
                # If we can't get question text, still return existing Tail's question_id
                # to prevent creating a new Tail that would overwrite the draft
                return None  # Will be handled by caller

        # 2. Determine Current Step (Find IN_PROGRESS)
        stmt_user_step = select(UserStep).where(
            UserStep.user_id == user_id,
            UserStep.status == StepProgressStatus.IN_PROGRESS
        )
        result_step = await self.session.execute(stmt_user_step)
        current_user_step = result_step.scalars().first()

        # If no step is in progress, initialize the next one
        if not current_user_step:
            current_user_step = await self._initialize_next_step(user_id)
            if not current_user_step:
                return None  # All steps finished

        # 3. Find the next unanswered question in this step
        next_question = await self._find_next_unanswered_question(
            user_id, current_user_step.step_id
        )

        # 4. If no questions left in this step, complete it and recurse
        if not next_question:
            await self._complete_step(current_user_step)
            return await self.get_next_question_for_user(user_id)

        # 5. Create a new TAIL record
        new_tail = Tail(
            user_id=user_id,
            tail_type=TailType.STEP_QUESTION,
            step_id=current_user_step.step_id,
            step_question_id=next_question.id,
            is_closed=False,
            payload={}
        )
        self.session.add(new_tail)
        await self.session.commit()

        return next_question.text

    def validate_answer_length(self, answer_text: str, is_template_format: bool = False) -> tuple[bool, str]:
        """
        Validates that answer meets minimum length requirement.
        Returns (is_valid, error_message).
        
        According to requirements:
        "можно поставить на строку ограничение в символах, чтоб нечаянно не получилось пропустить вопрос по ошибке"
        """
        if is_template_format:
            # For template format, check total content length
            try:
                template_data = json.loads(answer_text)
                # Calculate total text length in template
                total_length = 0
                for key, value in template_data.items():
                    if isinstance(value, str):
                        total_length += len(value)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str):
                                total_length += len(item)
                            elif isinstance(item, dict):
                                for v in item.values():
                                    if isinstance(v, str):
                                        total_length += len(v)
                
                if total_length < self.MIN_ANSWER_LENGTH:
                    return False, f"⚠️ Ответ слишком короткий ({total_length} символов). Минимум: {self.MIN_ANSWER_LENGTH} символов. Пожалуйста, раскрой ответ подробнее."
            except json.JSONDecodeError:
                # If not valid JSON, check plain text length
                if len(answer_text.strip()) < self.MIN_ANSWER_LENGTH:
                    return False, f"⚠️ Ответ слишком короткий ({len(answer_text.strip())} символов). Минимум: {self.MIN_ANSWER_LENGTH} символов. Пожалуйста, раскрой ответ подробнее."
        else:
            # Plain text answer
            if len(answer_text.strip()) < self.MIN_ANSWER_LENGTH:
                return False, f"⚠️ Ответ слишком короткий ({len(answer_text.strip())} символов). Минимум: {self.MIN_ANSWER_LENGTH} символов.\n\nРаскрой ответ подробнее - это поможет глубже проработать вопрос."
        
        return True, ""
    
    async def save_user_answer(self, user_id: int, answer_text: str, is_template_format: bool = False, skip_validation: bool = False) -> tuple[bool, str]:
        """
        Checks for an open Tail, validates answer length, saves the answer, and closes the Tail.
        If is_template_format is True, answer_text should be a JSON string with template structure.
        Otherwise, it's treated as plain text.
        
        Returns: (success: bool, error_message: str)
        - (True, "") on success
        - (False, error_message) on failure
        """
        # 1. Find the active TAIL
        stmt = select(Tail).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        )
        result = await self.session.execute(stmt)
        active_tail = result.scalars().first()

        if not active_tail:
            return False, "Нет активного вопроса. Нажми /steps, чтобы начать."

        # 2. Validate answer length (unless skipped)
        if not skip_validation:
            is_valid, error_msg = self.validate_answer_length(answer_text, is_template_format)
            if not is_valid:
                return False, error_msg

        # 3. Get user and active template
        stmt_user = select(User).where(User.id == user_id)
        result_user = await self.session.execute(stmt_user)
        user = result_user.scalars().first()
        
        # 4. Process answer text based on template
        final_answer_text = answer_text
        
        if is_template_format:
            # Answer is already in template format (JSON string)
            # Validate it's valid JSON
            try:
                template_data = json.loads(answer_text)
                # Store as formatted JSON string
                final_answer_text = json.dumps(template_data, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                # If not valid JSON, treat as plain text
                final_answer_text = answer_text
        elif user and user.active_template_id:
            # User has active template, check if answer might be structured
            # For now, we save as-is, but could add logic to detect template structure
            # This is handled in the bot when user fills by template
            final_answer_text = answer_text

        # 5. Create the Answer record
        new_answer = StepAnswer(
            user_id=user_id,
            step_id=active_tail.step_id,
            question_id=active_tail.step_question_id,
            answer_text=final_answer_text,
            version=1
        )
        self.session.add(new_answer)

        # 6. Close the Tail
        active_tail.is_closed = True
        active_tail.closed_at = datetime.now()

        # 7. IMPORTANT: Update personalized prompt with ALL answers (profile + steps)
        # This builds a complete picture of the user's character
        # Note: update_personalized_prompt_from_all_answers commits internally
        from services.personalization_service import update_personalized_prompt_from_all_answers
        await update_personalized_prompt_from_all_answers(self.session, user_id)
        
        return True, ""
    
    async def get_current_step_questions(self, user_id: int) -> list[dict]:
        """Get list of questions for current step"""
        # Get current step
        stmt_user_step = select(UserStep).where(
            UserStep.user_id == user_id,
            UserStep.status == StepProgressStatus.IN_PROGRESS
        )
        result = await self.session.execute(stmt_user_step)
        current_user_step = result.scalars().first()
        
        if not current_user_step:
            return []
        
        # Get questions for current step
        return await self.get_step_questions(current_user_step.step_id)

    # --- Helper Methods ---

    async def _initialize_next_step(self, user_id: int) -> Optional[UserStep]:
        """
        Finds the last completed step, determines the next index, 
        and creates a new UserStep record.
        """
        # Find the highest index completed by the user
        # FIX: Changed Step.number -> Step.index
        stmt_last = select(Step).join(UserStep).where(
            UserStep.user_id == user_id,
            UserStep.status == StepProgressStatus.COMPLETED
        ).order_by(desc(Step.index)).limit(1)
        
        result_last = await self.session.execute(stmt_last)
        last_step = result_last.scalars().first()

        # If user has completed steps, next is +1. If not, start at 1.
        # FIX: Changed .number -> .index
        next_index = 1 if not last_step else last_step.index + 1

        # Find the Step definition from DB
        # FIX: Changed Step.number -> Step.index
        stmt_next_step_def = select(Step).where(Step.index == next_index)
        result_def = await self.session.execute(stmt_next_step_def)
        next_step_def = result_def.scalars().first()

        if not next_step_def:
            return None  # No more steps exist in DB

        # Create new UserStep
        new_user_step = UserStep(
            user_id=user_id,
            step_id=next_step_def.id,
            status=StepProgressStatus.IN_PROGRESS,
            started_at=datetime.now()
        )
        self.session.add(new_user_step)
        await self.session.commit()
        return new_user_step

    async def _find_next_unanswered_question(self, user_id: int, step_id: int) -> Optional[Question]:
        """
        Finds the first question in the step that hasn't been answered.
        """
        # Get all questions for step
        # FIX: Changed Question.order -> Question.id (or whatever sorting logic you prefer)
        stmt_questions = select(Question).where(
            Question.step_id == step_id
        ).order_by(Question.id)
        
        # Get all existing answers for step
        stmt_answers = select(StepAnswer.question_id).where(
            StepAnswer.user_id == user_id,
            StepAnswer.step_id == step_id
        )

        res_q = await self.session.execute(stmt_questions)
        questions = res_q.scalars().all()

        res_a = await self.session.execute(stmt_answers)
        answered_ids = set(res_a.scalars().all())

        for q in questions:
            if q.id not in answered_ids:
                return q
        
        return None

    async def _complete_step(self, user_step: UserStep):
        """Marks a user step as completed."""
        user_step.status = StepProgressStatus.COMPLETED
        user_step.completed_at = datetime.now()
        await self.session.commit()