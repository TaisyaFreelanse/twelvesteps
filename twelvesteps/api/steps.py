from datetime import datetime
from typing import Optional, Union

# Update imports to match your models exactly
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    Step, Question, StepAnswer, UserStep, 
    Tail, TailType, StepProgressStatus
)

class StepFlowService:
    def __init__(self, session: AsyncSession):
        self.session = session

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
        if active_tail and active_tail.question:
            return active_tail.question.text

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

    async def save_user_answer(self, user_id: int, answer_text: str) -> bool:
        """
        Checks for an open Tail, saves the answer, and closes the Tail.
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
            return False

        # 2. Create the Answer record
        new_answer = StepAnswer(
            user_id=user_id,
            step_id=active_tail.step_id,
            question_id=active_tail.step_question_id,
            answer_text=answer_text,
            version=1
        )
        self.session.add(new_answer)

        # 3. Close the Tail
        active_tail.is_closed = True
        active_tail.closed_at = datetime.now()

        await self.session.commit()
        return True

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