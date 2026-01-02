from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AnswerTemplate, TemplateType, User


class AnswerTemplateRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_templates(self, user_id: Optional[int] = None) -> List[AnswerTemplate]:
        """Get all templates (author templates + user's custom templates)"""
        query = select(AnswerTemplate).where(
            (AnswerTemplate.template_type == TemplateType.AUTHOR) |
            (AnswerTemplate.user_id == user_id)
        ).order_by(AnswerTemplate.template_type, AnswerTemplate.created_at)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_template_by_id(self, template_id: int) -> Optional[AnswerTemplate]:
        """Get template by ID"""
        query = select(AnswerTemplate).where(AnswerTemplate.id == template_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_author_template(self) -> Optional[AnswerTemplate]:
        """Get the default author template"""
        query = select(AnswerTemplate).where(
            AnswerTemplate.template_type == TemplateType.AUTHOR
        ).limit(1)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create_template(
        self, user_id: int, name: str, structure: dict
    ) -> AnswerTemplate:
        """Create a custom template for user"""
        template = AnswerTemplate(
            user_id=user_id,
            name=name,
            template_type=TemplateType.CUSTOM,
            structure=structure,
        )
        self.db.add(template)
        await self.db.flush()
        return template

    async def update_template(
        self, template_id: int, user_id: int, name: Optional[str] = None,
        structure: Optional[dict] = None
    ) -> Optional[AnswerTemplate]:
        """Update a custom template (only user's own templates can be updated)"""
        template = await self.get_template_by_id(template_id)
        if not template:
            return None

        if template.template_type != TemplateType.CUSTOM or template.user_id != user_id:
            return None

        if name is not None:
            template.name = name
        if structure is not None:
            template.structure = structure

        self.db.add(template)
        await self.db.flush()
        return template

    async def delete_template(self, template_id: int, user_id: int) -> bool:
        """Delete a custom template (only user's own templates can be deleted)"""
        template = await self.get_template_by_id(template_id)
        if not template:
            return False

        if template.template_type != TemplateType.CUSTOM or template.user_id != user_id:
            return False

        await self.db.delete(template)
        await self.db.flush()
        return True

