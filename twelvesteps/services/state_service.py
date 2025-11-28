"""Service for managing SessionState operations"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import SessionState
from repositories.SessionStateRepository import SessionStateRepository


class StateService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = SessionStateRepository(session)
    
    async def get_state(self, user_id: int) -> Optional[SessionState]:
        """Get SessionState for a user"""
        return await self.repo.get_by_user_id(user_id)
    
    async def get_or_create_state(self, user_id: int) -> SessionState:
        """Get existing SessionState or create a new one"""
        state = await self.repo.get_by_user_id(user_id)
        if not state:
            state = await self.repo.create_or_update(user_id=user_id)
            await self.session.commit()
            await self.session.refresh(state)
        return state
    
    async def update_daily_snapshot(
        self,
        user_id: int,
        emotions: Optional[List[str]] = None,
        triggers: Optional[List[str]] = None,
        actions: Optional[List[str]] = None,
        health: Optional[Dict[str, Any]] = None,
    ) -> SessionState:
        """
        Update daily_snapshot based on classification.
        Merges new data with existing snapshot.
        """
        state = await self.get_or_create_state(user_id)
        
        current_snapshot = state.daily_snapshot or {}
        
        if emotions is not None:
            current_snapshot["emotions"] = emotions
        if triggers is not None:
            current_snapshot["triggers"] = triggers
        if actions is not None:
            current_snapshot["actions"] = actions
        if health is not None:
            current_snapshot["health"] = health
        
        state.daily_snapshot = current_snapshot
        await self.session.commit()
        await self.session.refresh(state)
        return state
    
    async def update_active_blocks(
        self,
        user_id: int,
        blocks: List[str],
        merge: bool = True
    ) -> SessionState:
        """
        Update active_blocks.
        If merge=True, adds to existing blocks. Otherwise replaces.
        """
        state = await self.get_or_create_state(user_id)
        
        if merge and state.active_blocks:
            # Merge with existing, avoiding duplicates
            existing = set(state.active_blocks)
            new_blocks = list(existing.union(set(blocks)))
            state.active_blocks = new_blocks
        else:
            state.active_blocks = blocks
        
        await self.session.commit()
        await self.session.refresh(state)
        return state
    
    async def add_pending_topic(
        self,
        user_id: int,
        topic: str
    ) -> SessionState:
        """Add a topic to pending_topics"""
        state = await self.get_or_create_state(user_id)
        
        if not state.pending_topics:
            state.pending_topics = []
        
        if topic not in state.pending_topics:
            state.pending_topics.append(topic)
        
        await self.session.commit()
        await self.session.refresh(state)
        return state
    
    async def remove_pending_topic(
        self,
        user_id: int,
        topic: str
    ) -> SessionState:
        """Remove a topic from pending_topics"""
        state = await self.get_or_create_state(user_id)
        
        if state.pending_topics and topic in state.pending_topics:
            state.pending_topics.remove(topic)
        
        await self.session.commit()
        await self.session.refresh(state)
        return state
    
    async def add_group_signal(
        self,
        user_id: int,
        signal: str
    ) -> SessionState:
        """Add a signal to group_signals"""
        state = await self.get_or_create_state(user_id)
        
        if not state.group_signals:
            state.group_signals = []
        
        if signal not in state.group_signals:
            state.group_signals.append(signal)
        
        await self.session.commit()
        await self.session.refresh(state)
        return state
    
    async def add_recent_message(
        self,
        user_id: int,
        text: str,
        tags: Optional[List[str]] = None
    ) -> SessionState:
        """
        Add a message to recent_messages with timestamp and tags.
        Keeps only last N messages (default 20).
        """
        state = await self.get_or_create_state(user_id)
        
        if not state.recent_messages:
            state.recent_messages = []
        
        message_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "text": text,
            "tags": tags or []
        }
        
        state.recent_messages.append(message_entry)
        
        # Keep only last 20 messages
        if len(state.recent_messages) > 20:
            state.recent_messages = state.recent_messages[-20:]
        
        await self.session.commit()
        await self.session.refresh(state)
        return state

