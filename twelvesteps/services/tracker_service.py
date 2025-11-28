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
        
        Args:
            user_id: User ID
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            
        Returns:
            List of TrackerSummary records
        """
        return await self.repo.get_summaries_for_period(user_id, start_date, end_date)
    
    async def get_last_week_summaries(self, user_id: int) -> List[TrackerSummary]:
        """Get summaries for the last 7 days."""
        end = date.today()
        start = end - timedelta(days=7)
        return await self.repo.get_summaries_for_period(user_id, start, end)
    
    async def aggregate_by_category(
        self,
        user_id: int,
        start_date: date,
        end_date: date
    ) -> Dict[str, List[str]]:
        """
        Aggregate data by category for a period.
        Combines all entries from multiple days into single lists per category.
        
        Args:
            user_id: User ID
            start_date: Start date
            end_date: End date
            
        Returns:
            Dict with keys: thinking, feeling, behavior, relationships, health
            Each contains a list of unique entries from the period
        """
        summaries = await self.repo.get_summaries_for_period(user_id, start_date, end_date)
        
        result: Dict[str, List[str]] = {
            "thinking": [],
            "feeling": [],
            "behavior": [],
            "relationships": [],
            "health": []
        }
        
        # Aggregate all entries, keeping unique values
        for summary in summaries:
            for category in result.keys():
                values = getattr(summary, category, None) or []
                for value in values:
                    if value and value not in result[category]:
                        result[category].append(value)
        
        return result
    
    async def get_trends(
        self,
        user_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Analyze trends over the specified number of days.
        
        Args:
            user_id: User ID
            days: Number of days to analyze
            
        Returns:
            Dict with trend analysis including:
            - most_common: Most frequently mentioned items per category
            - daily_counts: Number of entries per day
            - categories_filled: Which categories have data
        """
        end = date.today()
        start = end - timedelta(days=days)
        summaries = await self.repo.get_summaries_for_period(user_id, start, end)
        
        # Count occurrences of each item
        from collections import Counter
        category_counters: Dict[str, Counter] = {
            "thinking": Counter(),
            "feeling": Counter(),
            "behavior": Counter(),
            "relationships": Counter(),
            "health": Counter()
        }
        
        daily_counts = []
        for summary in summaries:
            day_count = 0
            for category in category_counters.keys():
                values = getattr(summary, category, None) or []
                for value in values:
                    if value:
                        category_counters[category][value] += 1
                        day_count += 1
            daily_counts.append({
                "date": summary.date.isoformat(),
                "count": day_count
            })
        
        # Get most common items per category
        most_common = {}
        for category, counter in category_counters.items():
            most_common[category] = counter.most_common(5)
        
        # Which categories have data
        categories_filled = {
            category: len(counter) > 0
            for category, counter in category_counters.items()
        }
        
        return {
            "period_days": days,
            "summaries_count": len(summaries),
            "most_common": most_common,
            "daily_counts": daily_counts,
            "categories_filled": categories_filled
        }

