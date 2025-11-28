"""Service for steps settings management"""
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.models import User, AnswerTemplate
from repositories.UserRepository import UserRepository


class StepsSettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
    
    async def get_settings(self, user_id: int) -> Dict[str, Any]:
        """Get current steps settings for user"""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise RuntimeError(f"User not found for user_id={user_id}")
        
        active_template_id = user.active_template_id
        active_template_name = None
        
        if active_template_id:
            stmt = select(AnswerTemplate).where(AnswerTemplate.id == active_template_id)
            result = await self.session.execute(stmt)
            template = result.scalars().first()
            if template:
                active_template_name = template.name
        
        # For now, reminders are not implemented in User model
        # We can add them later as JSON field or separate table
        # For now, return defaults
        return {
            "active_template_id": active_template_id,
            "active_template_name": active_template_name,
            "reminders_enabled": False,
            "reminder_time": None,
            "reminder_days": []
        }
    
    async def update_settings(
        self, 
        user_id: int, 
        active_template_id: Optional[int] = None,
        reminders_enabled: Optional[bool] = None,
        reminder_time: Optional[str] = None,
        reminder_days: Optional[list] = None
    ) -> Dict[str, Any]:
        """Update steps settings for user"""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise RuntimeError(f"User not found for user_id={user_id}")
        
        # Update active template if provided
        if active_template_id is not None:
            # Verify template exists and belongs to user or is AUTHOR
            stmt = select(AnswerTemplate).where(AnswerTemplate.id == active_template_id)
            result = await self.session.execute(stmt)
            template = result.scalars().first()
            
            if not template:
                raise ValueError(f"Template with id {active_template_id} not found")
            
            # Check if template is AUTHOR or belongs to user
            from db.models import TemplateType
            if template.template_type != TemplateType.AUTHOR and template.user_id != user_id:
                raise ValueError("You can only use your own templates or author template")
            
            user.active_template_id = active_template_id
        
        # For now, reminders are not stored in User model
        # This can be added later as JSON field or separate table
        # For now, we just acknowledge the request
        
        await self.session.commit()
        
        # Return updated settings
        return await self.get_settings(user_id)

