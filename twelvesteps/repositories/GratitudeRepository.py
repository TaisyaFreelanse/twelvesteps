"""Repository for Gratitude entries"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from db.models import Gratitude


class GratitudeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, user_id: int, text: str) -> Gratitude:
        """Создать новую благодарность"""
        gratitude = Gratitude(
            user_id=user_id,
            text=text
        )
        self.session.add(gratitude)
        await self.session.commit()
        await self.session.refresh(gratitude)
        return gratitude
    
    async def get_user_gratitudes(
        self, 
        user_id: int, 
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Gratitude]:
        """Получить список благодарностей пользователя, отсортированных по дате (новые сначала)"""
        stmt = select(Gratitude).where(
            Gratitude.user_id == user_id
        ).order_by(desc(Gratitude.created_at))
        
        if limit:
            stmt = stmt.limit(limit).offset(offset)
        
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def get_count(self, user_id: int) -> int:
        """Получить количество благодарностей пользователя"""
        from sqlalchemy import func
        stmt = select(func.count(Gratitude.id)).where(
            Gratitude.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

