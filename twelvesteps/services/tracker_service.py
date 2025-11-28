"""Service for managing TrackerSummary operations"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import TrackerSummary
from repositories.TrackerSummaryRepository import TrackerSummaryRepository


class TrackerService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = TrackerSummaryRepository(session)
    
    async def get_summary(
        self,
        user_id: int,
        summary_date: Optional[date] = None
    ) -> Optional[TrackerSummary]:
        """Get tracker summary for a user by date or latest"""
        if summary_date:
            return await self.repo.get_by_user_and_date(user_id, summary_date)
        else:
            return await self.repo.get_latest(user_id)
    
    async def create_or_update_summary(
        self,
        user_id: int,
        thinking: Optional[List[str]] = None,
        feeling: Optional[List[str]] = None,
        behavior: Optional[List[str]] = None,
        relationships: Optional[List[str]] = None,
        health: Optional[List[str]] = None,
        summary_date: Optional[date] = None,
    ) -> TrackerSummary:
        """Create or update tracker summary for a user"""
        if summary_date is None:
            summary_date = date.today()
        
        summary = await self.repo.create_or_update(
            user_id=user_id,
            thinking=thinking,
            feeling=feeling,
            behavior=behavior,
            relationships=relationships,
            health=health,
            summary_date=summary_date,
        )
        await self.session.commit()
        await self.session.refresh(summary)
        return summary
    
    async def add_to_category(
        self,
        user_id: int,
        category: str,
        value: str,
        summary_date: Optional[date] = None
    ) -> TrackerSummary:
        """
        Add a value to a specific category (thinking, feeling, behavior, relationships, health).
        Creates summary if it doesn't exist.
        """
        if summary_date is None:
            summary_date = date.today()
        
        summary = await self.repo.get_by_user_and_date(user_id, summary_date)
        
        if not summary:
            # Create new summary
            summary = await self.repo.create_or_update(
                user_id=user_id,
                summary_date=summary_date
            )
        
        # Get current list for category
        current_list = getattr(summary, category, None) or []
        
        # Add value if not already present
        if value not in current_list:
            current_list.append(value)
            setattr(summary, category, current_list)
        
        await self.session.commit()
        await self.session.refresh(summary)
        return summary
    
    async def generate_summary_from_data(
        self,
        user_id: int,
        data: Dict[str, Any],
        summary_date: Optional[date] = None
    ) -> TrackerSummary:
        """
        Generate tracker_summary from aggregated data.
        Data should contain keys: thinking, feeling, behavior, relationships, health
        """
        if summary_date is None:
            summary_date = date.today()
        
        summary = await self.repo.create_or_update(
            user_id=user_id,
            thinking=data.get("thinking"),
            feeling=data.get("feeling"),
            behavior=data.get("behavior"),
            relationships=data.get("relationships"),
            health=data.get("health"),
            summary_date=summary_date,
        )
        await self.session.commit()
        await self.session.refresh(summary)
        return summary
    
    async def get_summaries_for_period(
        self,
        user_id: int,
        start_date: date,
        end_date: date
    ) -> List[TrackerSummary]:
        """
        Get tracker summaries for a period.
        Note: This requires adding a method to repository.
        """
        # For now, return empty list - can be enhanced with repository method
        # This would require adding a query method to TrackerSummaryRepository
        return []
    
    async def aggregate_by_category(
        self,
        user_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, List[str]]:
        """
        Aggregate data by category for a period.
        Returns dict with keys: thinking, feeling, behavior, relationships, health
        """
        # This would require implementing get_summaries_for_period first
        # For now, return empty dict
        return {
            "thinking": [],
            "feeling": [],
            "behavior": [],
            "relationships": [],
            "health": []
        }

