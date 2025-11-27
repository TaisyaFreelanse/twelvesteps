from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User as UserModel


DEFAULT_STEP_STATUS = "NOT_STARTED"


class StatusService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_status_for_user(self, user: UserModel) -> dict[str, Any]:
        # Placeholder implementation until Step/Question/Tail models exist.
        return {
            "current_step": None,
            "current_step_status": DEFAULT_STEP_STATUS,
            "open_step_question": None,
            "tails": [],
        }
