"""Repository for FrameTracking operations"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import FrameTracking


class FrameTrackingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> Optional[FrameTracking]:
        """Get FrameTracking for a user"""
        stmt = select(FrameTracking).where(FrameTracking.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_or_update(
        self,
        user_id: int,
        confirmed: Optional[list] = None,
        candidates: Optional[list] = None,
        tracking: Optional[dict] = None,
        archetypes: Optional[list] = None,
        meta_flags: Optional[list] = None,
    ) -> FrameTracking:
        """Create or update FrameTracking for a user"""
        existing = await self.get_by_user_id(user_id)

        if existing:
            if confirmed is not None:
                existing.confirmed = confirmed
            if candidates is not None:
                existing.candidates = candidates
            if tracking is not None:
                existing.tracking = tracking
            if archetypes is not None:
                existing.archetypes = archetypes
            if meta_flags is not None:
                existing.meta_flags = meta_flags
            return existing
        else:
            new_tracking = FrameTracking(
                user_id=user_id,
                confirmed=confirmed,
                candidates=candidates,
                tracking=tracking,
                archetypes=archetypes,
                meta_flags=meta_flags,
            )
            self.session.add(new_tracking)
            return new_tracking

