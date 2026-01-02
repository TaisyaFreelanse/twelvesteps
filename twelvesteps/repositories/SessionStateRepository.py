"""Repository for SessionState operations"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import SessionState


class SessionStateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> Optional[SessionState]:
        """Get SessionState for a user"""
        stmt = select(SessionState).where(SessionState.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_or_update(
        self,
        user_id: int,
        recent_messages: Optional[list] = None,
        daily_snapshot: Optional[dict] = None,
        active_blocks: Optional[list] = None,
        pending_topics: Optional[list] = None,
        group_signals: Optional[list] = None,
    ) -> SessionState:
        """Create or update SessionState for a user"""
        existing = await self.get_by_user_id(user_id)

        if existing:
            if recent_messages is not None:
                existing.recent_messages = recent_messages
            if daily_snapshot is not None:
                existing.daily_snapshot = daily_snapshot
            if active_blocks is not None:
                existing.active_blocks = active_blocks
            if pending_topics is not None:
                existing.pending_topics = pending_topics
            if group_signals is not None:
                existing.group_signals = group_signals
            return existing
        else:
            new_state = SessionState(
                user_id=user_id,
                recent_messages=recent_messages,
                daily_snapshot=daily_snapshot,
                active_blocks=active_blocks,
                pending_topics=pending_topics,
                group_signals=group_signals,
            )
            self.session.add(new_state)
            return new_state

