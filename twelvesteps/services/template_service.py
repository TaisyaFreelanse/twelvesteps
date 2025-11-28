from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.AnswerTemplateRepository import AnswerTemplateRepository
from db.models import AnswerTemplate, User


class TemplateService:
    def __init__(self, session: AsyncSession):
        self.repo = AnswerTemplateRepository(session)
        self.session = session

    async def get_all_templates(self, user_id: Optional[int] = None) -> List[AnswerTemplate]:
        """Get all templates available to user"""
        return await self.repo.get_all_templates(user_id)

    async def get_template_by_id(self, template_id: int) -> Optional[AnswerTemplate]:
        """Get template by ID"""
        return await self.repo.get_template_by_id(template_id)

    async def create_template(
        self, user_id: int, name: str, structure: dict
    ) -> AnswerTemplate:
        """Create a custom template for user"""
        return await self.repo.create_template(user_id, name, structure)

    async def update_template(
        self, template_id: int, user_id: int, name: Optional[str] = None,
        structure: Optional[dict] = None
    ) -> Optional[AnswerTemplate]:
        """Update a custom template"""
        return await self.repo.update_template(template_id, user_id, name, structure)

    async def delete_template(self, template_id: int, user_id: int) -> bool:
        """Delete a custom template"""
        return await self.repo.delete_template(template_id, user_id)

    async def set_active_template(self, user: User, template_id: Optional[int]) -> bool:
        """Set active template for user. None resets to default (author template)"""
        if template_id is None:
            # Reset to default (author template)
            user.active_template_id = None
            self.session.add(user)
            await self.session.flush()
            return True
        
        # Verify template exists and is available to user
        template = await self.repo.get_template_by_id(template_id)
        if not template:
            return False
        
        # Check if template is author template or user's custom template
        from db.models import TemplateType
        if template.template_type == TemplateType.AUTHOR or template.user_id == user.id:
            user.active_template_id = template_id
            self.session.add(user)
            await self.session.flush()
            return True
        
        return False

    async def get_active_template(self, user: User) -> Optional[AnswerTemplate]:
        """Get user's active template, or default author template if none set"""
        if user.active_template_id:
            template = await self.repo.get_template_by_id(user.active_template_id)
            if template:
                return template
        
        # Return default author template
        return await self.repo.get_author_template()

