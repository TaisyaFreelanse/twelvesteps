from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    User as UserModel,
    UserStep,
    Step,
    Tail,
    TailType,
    StepProgressStatus
)


DEFAULT_STEP_STATUS = "NOT_STARTED"


class StatusService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_status_for_user(self, user: UserModel) -> dict[str, Any]:
        """Get the status for a specific user."""
        user_id = user.id

        stmt_user_step = select(UserStep).where(
            UserStep.user_id == user_id,
            UserStep.status == StepProgressStatus.IN_PROGRESS
        )
        result_user_step = await self.session.execute(stmt_user_step)
        current_user_step = result_user_step.scalars().first()

        current_step = None
        current_step_status = DEFAULT_STEP_STATUS

        if current_user_step:
            stmt_step = select(Step).where(Step.id == current_user_step.step_id)
            result_step = await self.session.execute(stmt_step)
            step = result_step.scalars().first()

            if step:
                current_step = step.index
                current_step_status = current_user_step.status.value

        open_step_question = None

        stmt_open_tail = select(Tail).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        ).options(selectinload(Tail.question), selectinload(Tail.step))

        result_open_tail = await self.session.execute(stmt_open_tail)
        open_tail = result_open_tail.scalars().first()

        if open_tail and open_tail.step_question_id and open_tail.step_id:
            open_step_question = {
                "step_id": open_tail.step_id,
                "question_id": open_tail.step_question_id
            }

        stmt_all_tails = select(Tail).where(
            Tail.user_id == user_id,
            Tail.is_closed == False
        ).order_by(Tail.created_at.desc())

        result_all_tails = await self.session.execute(stmt_all_tails)
        all_tails = result_all_tails.scalars().all()

        tails = []
        for tail in all_tails:
            tails.append({
                "id": tail.id,
                "type": tail.tail_type.value,
                "payload": tail.payload
            })

        return {
            "current_step": current_step,
            "current_step_status": current_step_status,
            "open_step_question": open_step_question,
            "tails": tails,
        }
