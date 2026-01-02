"""Repository for QAStatus operations"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import QAStatus


class QAStatusRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> Optional[QAStatus]:
        """Get QAStatus for a user"""
        stmt = select(QAStatus).where(QAStatus.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_or_update(
        self,
        user_id: int,
        last_prompt_included: Optional[bool] = None,
        trace_ok: Optional[bool] = None,
        open_threads: Optional[int] = None,
        rebuild_required: Optional[bool] = None,
    ) -> QAStatus:
        """Create or update QAStatus for a user"""
        existing = await self.get_by_user_id(user_id)

        if existing:
            if last_prompt_included is not None:
                existing.last_prompt_included = last_prompt_included
            if trace_ok is not None:
                existing.trace_ok = trace_ok
            if open_threads is not None:
                existing.open_threads = open_threads
            if rebuild_required is not None:
                existing.rebuild_required = rebuild_required
            return existing
        else:
            new_status = QAStatus(
                user_id=user_id,
                last_prompt_included=last_prompt_included,
                trace_ok=trace_ok,
                open_threads=open_threads,
                rebuild_required=rebuild_required,
            )
            self.session.add(new_status)
            return new_status

