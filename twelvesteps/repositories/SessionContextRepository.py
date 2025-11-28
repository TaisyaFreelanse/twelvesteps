"""Repository for SessionContext operations"""
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from db.models import SessionContext, SessionType, User


class SessionContextRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_or_update_context(
        self,
        user_id: int,
        session_type: SessionType,
        context_data: Dict[str, Any]
    ) -> SessionContext:
        """Create or update session context for a user"""
        # Check if context exists
        stmt = select(SessionContext).where(
            SessionContext.user_id == user_id,
            SessionContext.session_type == session_type
        )
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        
        if existing:
            # Update existing context
            existing.context_data = context_data
            existing.updated_at = datetime.utcnow()
            return existing
        else:
            # Create new context
            new_context = SessionContext(
                user_id=user_id,
                session_type=session_type,
                context_data=context_data
            )
            self.session.add(new_context)
            return new_context
    
    async def get_active_context(
        self,
        user_id: int,
        session_type: Optional[SessionType] = None
    ) -> Optional[SessionContext]:
        """Get active session context for a user"""
        stmt = select(SessionContext).where(
            SessionContext.user_id == user_id
        )
        
        if session_type:
            stmt = stmt.where(SessionContext.session_type == session_type)
        else:
            # Get most recent context
            stmt = stmt.order_by(SessionContext.updated_at.desc())
        
        result = await self.session.execute(stmt)
        return result.scalars().first()
    
    async def delete_context(
        self,
        user_id: int,
        session_type: Optional[SessionType] = None
    ) -> bool:
        """Delete session context for a user"""
        stmt = delete(SessionContext).where(
            SessionContext.user_id == user_id
        )
        
        if session_type:
            stmt = stmt.where(SessionContext.session_type == session_type)
        
        result = await self.session.execute(stmt)
        return result.rowcount > 0
    
    async def update_context_data(
        self,
        user_id: int,
        session_type: SessionType,
        context_data: Dict[str, Any]
    ) -> Optional[SessionContext]:
        """Update context data for existing session"""
        stmt = select(SessionContext).where(
            SessionContext.user_id == user_id,
            SessionContext.session_type == session_type
        )
        result = await self.session.execute(stmt)
        context = result.scalars().first()
        
        if context:
            context.context_data = context_data
            context.updated_at = datetime.utcnow()
            return context
        
        return None

