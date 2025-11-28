from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    ProfileSection,
    ProfileSectionData,
    ProfileQuestion,
    ProfileAnswer,
)


class ProfileRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all_sections(self, user_id: Optional[int] = None) -> List[ProfileSection]:
        """Get all sections (standard + user's custom sections if user_id provided)"""
        query = select(ProfileSection).where(
            (ProfileSection.is_custom == False) | (ProfileSection.user_id == user_id)
        ).order_by(ProfileSection.order_index)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_section_by_id(self, section_id: int) -> Optional[ProfileSection]:
        """Get section by ID with questions"""
        query = select(ProfileSection).options(
            selectinload(ProfileSection.questions)
        ).where(ProfileSection.id == section_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_section_questions(self, section_id: int) -> List[ProfileQuestion]:
        """Get all questions for a section"""
        query = select(ProfileQuestion).where(
            ProfileQuestion.section_id == section_id
        ).order_by(ProfileQuestion.order_index)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_custom_section(
        self, user_id: int, name: str, icon: Optional[str] = None
    ) -> ProfileSection:
        """Create a custom section for user"""
        # Get max order_index for user's custom sections
        query = select(func.max(ProfileSection.order_index)).where(
            ProfileSection.user_id == user_id
        )
        result = await self.db.execute(query)
        max_order = result.scalar() or 0

        section = ProfileSection(
            name=name,
            icon=icon,
            is_custom=True,
            user_id=user_id,
            order_index=max_order + 1,
        )
        self.db.add(section)
        await self.db.flush()
        return section

    async def update_section(
        self, section_id: int, name: Optional[str] = None,
        icon: Optional[str] = None, order_index: Optional[int] = None
    ) -> Optional[ProfileSection]:
        """Update section (only custom sections can be updated)"""
        section = await self.get_section_by_id(section_id)
        if not section or not section.is_custom:
            return None

        if name is not None:
            section.name = name
        if icon is not None:
            section.icon = icon
        if order_index is not None:
            section.order_index = order_index

        self.db.add(section)
        await self.db.flush()
        return section

    async def delete_section(self, section_id: int, user_id: int) -> bool:
        """Delete a custom section (only custom sections owned by user can be deleted)"""
        section = await self.get_section_by_id(section_id)
        if not section:
            return False
        
        # Only custom sections owned by the user can be deleted
        if not section.is_custom or section.user_id != user_id:
            return False
        
        await self.db.delete(section)
        await self.db.flush()
        return True

    async def save_answer(
        self, user_id: int, question_id: int, answer_text: str
    ) -> ProfileAnswer:
        """Save or update answer to a question"""
        # Get latest version
        query = select(func.max(ProfileAnswer.version)).where(
            ProfileAnswer.user_id == user_id,
            ProfileAnswer.question_id == question_id
        )
        result = await self.db.execute(query)
        max_version = result.scalar() or 0

        answer = ProfileAnswer(
            user_id=user_id,
            question_id=question_id,
            answer_text=answer_text,
            version=max_version + 1,
        )
        self.db.add(answer)
        await self.db.flush()
        return answer

    async def save_free_text(
        self, user_id: int, section_id: int, content: str
    ) -> ProfileSectionData:
        """Save free text data for a section"""
        # Check if data exists
        query = select(ProfileSectionData).where(
            ProfileSectionData.user_id == user_id,
            ProfileSectionData.section_id == section_id
        )
        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            existing.content = content
            self.db.add(existing)
            await self.db.flush()
            return existing
        else:
            data = ProfileSectionData(
                user_id=user_id,
                section_id=section_id,
                content=content,
            )
            self.db.add(data)
            await self.db.flush()
            return data

    async def get_section_data(
        self, user_id: int, section_id: int
    ) -> Optional[ProfileSectionData]:
        """Get user's data for a section"""
        query = select(ProfileSectionData).where(
            ProfileSectionData.user_id == user_id,
            ProfileSectionData.section_id == section_id
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_answers_for_section(
        self, user_id: int, section_id: int
    ) -> List[ProfileAnswer]:
        """Get all user's answers for questions in a section"""
        query = select(ProfileAnswer).join(ProfileQuestion).where(
            ProfileAnswer.user_id == user_id,
            ProfileQuestion.section_id == section_id
        ).order_by(ProfileAnswer.question_id, ProfileAnswer.version.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_section_summary(
        self, user_id: int, section_id: int
    ) -> dict:
        """Get summary statistics for a section"""
        # Count questions
        questions_query = select(func.count(ProfileQuestion.id)).where(
            ProfileQuestion.section_id == section_id
        )
        questions_result = await self.db.execute(questions_query)
        questions_count = questions_result.scalar() or 0

        # Count answers (latest versions only)
        answers_query = select(func.count(ProfileAnswer.id.distinct())).join(
            ProfileQuestion
        ).where(
            ProfileAnswer.user_id == user_id,
            ProfileQuestion.section_id == section_id
        )
        answers_result = await self.db.execute(answers_query)
        answers_count = answers_result.scalar() or 0

        # Get last updated
        last_updated_query = select(func.max(ProfileAnswer.created_at)).join(
            ProfileQuestion
        ).where(
            ProfileAnswer.user_id == user_id,
            ProfileQuestion.section_id == section_id
        )
        last_updated_result = await self.db.execute(last_updated_query)
        last_updated = last_updated_result.scalar()

        # Get section name
        section = await self.get_section_by_id(section_id)
        section_name = section.name if section else ""

        return {
            "section_id": section_id,
            "section_name": section_name,
            "questions_count": questions_count,
            "answers_count": answers_count,
            "last_updated": last_updated,
        }

