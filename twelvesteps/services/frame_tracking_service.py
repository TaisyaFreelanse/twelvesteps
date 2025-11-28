"""Service for managing FrameTracking operations"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import FrameTracking
from repositories.FrameTrackingRepository import FrameTrackingRepository


class FrameTrackingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = FrameTrackingRepository(session)
        self.min_to_confirm = 3  # Default minimum repetitions to confirm a frame
    
    async def get_tracking(self, user_id: int) -> Optional[FrameTracking]:
        """Get FrameTracking for a user"""
        return await self.repo.get_by_user_id(user_id)
    
    async def get_or_create_tracking(self, user_id: int) -> FrameTracking:
        """Get existing FrameTracking or create a new one"""
        tracking = await self.repo.get_by_user_id(user_id)
        if not tracking:
            tracking = await self.repo.create_or_update(
                user_id=user_id,
                tracking={"repetition_count": {}, "min_to_confirm": self.min_to_confirm}
            )
            await self.session.commit()
            await self.session.refresh(tracking)
        return tracking
    
    async def add_candidate(
        self,
        user_id: int,
        frame_content: str,
        frame_data: Optional[Dict[str, Any]] = None
    ) -> FrameTracking:
        """
        Add a frame candidate.
        If it reaches min_to_confirm repetitions, moves it to confirmed.
        """
        tracking = await self.get_or_create_tracking(user_id)
        
        if not tracking.candidates:
            tracking.candidates = []
        if not tracking.tracking:
            tracking.tracking = {"repetition_count": {}, "min_to_confirm": self.min_to_confirm}
        
        repetition_count = tracking.tracking.get("repetition_count", {})
        min_to_confirm = tracking.tracking.get("min_to_confirm", self.min_to_confirm)
        
        # Check if frame already exists in candidates
        candidate_found = False
        for candidate in tracking.candidates:
            if isinstance(candidate, dict) and candidate.get("content") == frame_content:
                candidate_found = True
                # Increment count
                if frame_content not in repetition_count:
                    repetition_count[frame_content] = 0
                repetition_count[frame_content] += 1
                break
        
        if not candidate_found:
            # Add new candidate
            candidate_entry = {
                "content": frame_content,
                "data": frame_data or {},
                "first_seen": None  # Can be set to timestamp if needed
            }
            tracking.candidates.append(candidate_entry)
            repetition_count[frame_content] = 1
        
        # Check if should be confirmed
        if repetition_count.get(frame_content, 0) >= min_to_confirm:
            # Move to confirmed
            if not tracking.confirmed:
                tracking.confirmed = []
            
            # Check if not already confirmed
            confirmed_contents = [
                c.get("content") if isinstance(c, dict) else str(c)
                for c in tracking.confirmed
            ]
            
            if frame_content not in confirmed_contents:
                confirmed_entry = {
                    "content": frame_content,
                    "data": frame_data or {},
                    "confirmed_at": None  # Can be set to timestamp if needed
                }
                tracking.confirmed.append(confirmed_entry)
                
                # Remove from candidates
                tracking.candidates = [
                    c for c in tracking.candidates
                    if (isinstance(c, dict) and c.get("content") != frame_content)
                    or (not isinstance(c, dict) and str(c) != frame_content)
                ]
        
        tracking.tracking["repetition_count"] = repetition_count
        await self.session.commit()
        await self.session.refresh(tracking)
        return tracking
    
    async def detect_archetypes(
        self,
        user_id: int
    ) -> List[str]:
        """
        Detect archetypes based on patterns in confirmed frames.
        Returns list of detected archetypes (victim, rescuer, judge, etc.)
        """
        tracking = await self.get_or_create_tracking(user_id)
        
        if not tracking.confirmed:
            return []
        
        archetypes = []
        confirmed_contents = []
        
        for frame in tracking.confirmed:
            if isinstance(frame, dict):
                content = frame.get("content", "")
            else:
                content = str(frame)
            confirmed_contents.append(content.lower())
        
        # Simple pattern detection (can be enhanced with ML/NLP)
        all_text = " ".join(confirmed_contents)
        
        # Victim archetype patterns
        victim_patterns = ["жертва", "меня обидели", "несправедливо", "я не виноват"]
        if any(pattern in all_text for pattern in victim_patterns):
            archetypes.append("victim")
        
        # Rescuer archetype patterns
        rescuer_patterns = ["помогаю", "спасаю", "нужно помочь", "должен помочь"]
        if any(pattern in all_text for pattern in rescuer_patterns):
            archetypes.append("rescuer")
        
        # Judge archetype patterns
        judge_patterns = ["осуждаю", "неправильно", "должен", "обязан", "виноват"]
        if any(pattern in all_text for pattern in judge_patterns):
            archetypes.append("judge")
        
        # Persecutor archetype patterns
        persecutor_patterns = ["наказать", "виноват", "должен ответить"]
        if any(pattern in all_text for pattern in persecutor_patterns):
            archetypes.append("persecutor")
        
        # Update tracking
        tracking.archetypes = list(set(archetypes))  # Remove duplicates
        await self.session.commit()
        await self.session.refresh(tracking)
        
        return archetypes
    
    async def detect_meta_flags(
        self,
        user_id: int
    ) -> List[str]:
        """
        Detect meta flags: loop_detected, frame_shift, identity_conflict.
        Returns list of detected flags.
        """
        tracking = await self.get_or_create_tracking(user_id)
        
        flags = []
        
        if not tracking.confirmed:
            return flags
        
        # Check for loops (repeated similar frames)
        if len(tracking.confirmed) >= 3:
            recent_contents = [
                c.get("content", "") if isinstance(c, dict) else str(c)
                for c in tracking.confirmed[-3:]
            ]
            # Simple check: if last 3 frames are very similar
            if len(set(recent_contents)) == 1:
                flags.append("loop_detected")
        
        # Check for frame_shift (sudden change in frame type)
        if len(tracking.confirmed) >= 2:
            # This is a simplified check - can be enhanced
            # Compare last two frames for significant differences
            flags.append("frame_shift")  # Placeholder - implement actual logic
        
        # Check for identity_conflict (conflicting self-perceptions)
        # This would require more sophisticated analysis
        # Placeholder for now
        if len(tracking.confirmed) >= 5:
            flags.append("identity_conflict")  # Placeholder
        
        # Update tracking
        tracking.meta_flags = list(set(flags))  # Remove duplicates
        await self.session.commit()
        await self.session.refresh(tracking)
        
        return flags
    
    async def set_min_to_confirm(
        self,
        user_id: int,
        min_count: int
    ) -> FrameTracking:
        """Set minimum repetitions required to confirm a frame"""
        tracking = await self.get_or_create_tracking(user_id)
        
        if not tracking.tracking:
            tracking.tracking = {"repetition_count": {}, "min_to_confirm": min_count}
        else:
            tracking.tracking["min_to_confirm"] = min_count
        
        await self.session.commit()
        await self.session.refresh(tracking)
        return tracking

