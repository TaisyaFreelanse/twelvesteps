"""Repository for UserMeta operations"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import UserMeta


class UserMetaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: int) -> Optional[UserMeta]:
        """Get UserMeta for a user (one-to-one relationship)"""
        stmt = select(UserMeta).where(UserMeta.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_or_update(
        self,
        user_id: int,
        metasloy_signals: Optional[list] = None,
        prompt_revision_history: Optional[int] = None,
        time_zone: Optional[str] = None,
        language: Optional[str] = None,
        data_flags: Optional[dict] = None,
    ) -> UserMeta:
        """Create or update UserMeta for a user"""
        existing = await self.get_by_user_id(user_id)

        if existing:
            if metasloy_signals is not None:
                existing.metasloy_signals = metasloy_signals
            if prompt_revision_history is not None:
                existing.prompt_revision_history = prompt_revision_history
            if time_zone is not None:
                existing.time_zone = time_zone
            if language is not None:
                existing.language = language
            if data_flags is not None:
                existing.data_flags = data_flags
            return existing
        else:
            new_meta = UserMeta(
                user_id=user_id,
                metasloy_signals=metasloy_signals,
                prompt_revision_history=prompt_revision_history,
                time_zone=time_zone,
                language=language,
                data_flags=data_flags,
            )
            self.session.add(new_meta)
            return new_meta

