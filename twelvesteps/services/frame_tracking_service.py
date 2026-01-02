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
        self.min_to_confirm = 3

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
        """Add a candidate frame to tracking."""
        tracking = await self.get_or_create_tracking(user_id)

        if not tracking.candidates:
            tracking.candidates = []
        if not tracking.tracking:
            tracking.tracking = {"repetition_count": {}, "min_to_confirm": self.min_to_confirm}

        repetition_count = tracking.tracking.get("repetition_count", {})
        min_to_confirm = tracking.tracking.get("min_to_confirm", self.min_to_confirm)

        candidate_found = False
        for candidate in tracking.candidates:
            if isinstance(candidate, dict) and candidate.get("content") == frame_content:
                candidate_found = True
                if frame_content not in repetition_count:
                    repetition_count[frame_content] = 0
                repetition_count[frame_content] += 1
                break

        if not candidate_found:
            candidate_entry = {
                "content": frame_content,
                "data": frame_data or {},
                "first_seen": None
            }
            tracking.candidates.append(candidate_entry)
            repetition_count[frame_content] = 1

        if repetition_count.get(frame_content, 0) >= min_to_confirm:
            if not tracking.confirmed:
                tracking.confirmed = []

            confirmed_contents = [
                c.get("content") if isinstance(c, dict) else str(c)
                for c in tracking.confirmed
            ]

            if frame_content not in confirmed_contents:
                confirmed_entry = {
                    "content": frame_content,
                    "data": frame_data or {},
                    "confirmed_at": None
                }
                tracking.confirmed.append(confirmed_entry)

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

        all_text = " ".join(confirmed_contents)

        victim_patterns = ["жертва", "меня обидели", "несправедливо", "я не виноват"]
        if any(pattern in all_text for pattern in victim_patterns):
            archetypes.append("victim")

        rescuer_patterns = ["помогаю", "спасаю", "нужно помочь", "должен помочь"]
        if any(pattern in all_text for pattern in rescuer_patterns):
            archetypes.append("rescuer")

        judge_patterns = ["осуждаю", "неправильно", "должен", "обязан", "виноват"]
        if any(pattern in all_text for pattern in judge_patterns):
            archetypes.append("judge")

        persecutor_patterns = ["наказать", "виноват", "должен ответить"]
        if any(pattern in all_text for pattern in persecutor_patterns):
            archetypes.append("persecutor")

        tracking.archetypes = list(set(archetypes))
        await self.session.commit()
        await self.session.refresh(tracking)

        return archetypes

    async def detect_meta_flags(
        self,
        user_id: int
    ) -> List[str]:
        """
        tracking = await self.get_or_create_tracking(user_id)

        flags = []

        if not tracking.confirmed:
            return flags

        if len(tracking.confirmed) >= 3:
            recent_contents = [
                c.get("content", "") if isinstance(c, dict) else str(c)
                for c in tracking.confirmed[-3:]
            ]
            if len(set(recent_contents)) == 1:
                flags.append("loop_detected")

        if len(tracking.confirmed) >= 2:
            flags.append("frame_shift")

        if len(tracking.confirmed) >= 5:
            flags.append("identity_conflict")

        tracking.meta_flags = list(set(flags))
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

