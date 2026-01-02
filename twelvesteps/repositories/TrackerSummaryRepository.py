"""Repository for TrackerSummary operations"""
from datetime import date
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from db.models import TrackerSummary


class TrackerSummaryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_and_date(self, user_id: int, summary_date: date) -> Optional[TrackerSummary]:
        """Get TrackerSummary for a user by date"""
        stmt = select(TrackerSummary).where(
            TrackerSummary.user_id == user_id,
            TrackerSummary.date == summary_date
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest(self, user_id: int) -> Optional[TrackerSummary]:
        """Get latest TrackerSummary for a user"""
        stmt = (
            select(TrackerSummary)
            .where(TrackerSummary.user_id == user_id)
            .order_by(desc(TrackerSummary.date))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_summaries_for_period(
        self,
        user_id: int,
        start_date: date,
        end_date: date
    ) -> List[TrackerSummary]:
        """
        stmt = (
            select(TrackerSummary)
            .where(
                and_(
                    TrackerSummary.user_id == user_id,
                    TrackerSummary.date >= start_date,
                    TrackerSummary.date <= end_date
                )
            )
            .order_by(TrackerSummary.date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_last_n_summaries(
        self,
        user_id: int,
        limit: int = 7
    ) -> List[TrackerSummary]:
        """
        stmt = (
            select(TrackerSummary)
            .where(TrackerSummary.user_id == user_id)
            .order_by(desc(TrackerSummary.date))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_or_update(
        self,
        user_id: int,
        thinking: Optional[list] = None,
        feeling: Optional[list] = None,
        behavior: Optional[list] = None,
        relationships: Optional[list] = None,
        health: Optional[list] = None,
        summary_date: Optional[date] = None,
    ) -> TrackerSummary:
        """Create or update TrackerSummary for a user"""
        if summary_date is None:
            from datetime import date as date_class
            summary_date = date_class.today()

        existing = await self.get_by_user_and_date(user_id, summary_date)

        if existing:
            if thinking is not None:
                existing.thinking = thinking
            if feeling is not None:
                existing.feeling = feeling
            if behavior is not None:
                existing.behavior = behavior
            if relationships is not None:
                existing.relationships = relationships
            if health is not None:
                existing.health = health
            return existing
        else:
            new_summary = TrackerSummary(
                user_id=user_id,
                thinking=thinking,
                feeling=feeling,
                behavior=behavior,
                relationships=relationships,
                health=health,
                date=summary_date,
            )
            self.session.add(new_summary)
            return new_summary

