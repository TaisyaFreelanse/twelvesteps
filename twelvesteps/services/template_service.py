from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.AnswerTemplateRepository import AnswerTemplateRepository
from repositories.TemplateProgressRepository import TemplateProgressRepository, TEMPLATE_FIELDS, MIN_SITUATIONS
from db.models import AnswerTemplate, User, TemplateProgress, TemplateProgressStatus


class TemplateService:
    def __init__(self, session: AsyncSession):
        self.repo = AnswerTemplateRepository(session)
        self.progress_repo = TemplateProgressRepository(session)
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
    
    # ============================================================
    # TEMPLATE PROGRESS METHODS (FSM для пошагового заполнения)
    # ============================================================
    
    async def start_template_filling(
        self, user_id: int, step_id: int, question_id: int
    ) -> Dict[str, Any]:
        """
        Начать или продолжить заполнение шаблона для вопроса.
        
        Returns:
            dict с информацией о текущем состоянии:
            - progress_id: ID прогресса
            - status: статус (IN_PROGRESS, PAUSED, COMPLETED)
            - current_field: текущее поле для заполнения
            - current_situation: номер текущей ситуации (1-3)
            - field_info: информация о поле (name, description, min_items)
            - progress_summary: текстовое описание прогресса
            - is_resumed: True если возобновлен с паузы
        """
        progress = await self.progress_repo.get_or_create_progress(
            user_id, step_id, question_id
        )
        
        is_resumed = False
        if progress.status == TemplateProgressStatus.PAUSED:
            await self.progress_repo.resume_progress(progress)
            is_resumed = True
        
        field_info = self.progress_repo.get_current_field_info(progress)
        progress_summary = self.progress_repo.get_progress_summary(progress)
        
        return {
            "progress_id": progress.id,
            "status": progress.status.value,
            "current_field": progress.current_field,
            "current_situation": progress.current_situation,
            "field_info": field_info,
            "progress_summary": progress_summary,
            "is_resumed": is_resumed,
            "is_complete": progress.status == TemplateProgressStatus.COMPLETED
        }
    
    async def submit_field_value(
        self, user_id: int, step_id: int, question_id: int, value: str
    ) -> Dict[str, Any]:
        """
        Сохранить значение текущего поля и получить следующее.
        
        Returns:
            dict с информацией:
            - success: True если сохранено
            - next_field: следующее поле (или None если завершено)
            - field_info: информация о следующем поле
            - current_situation: номер текущей ситуации
            - is_situation_complete: True если ситуация завершена
            - is_all_situations_complete: True если все ситуации завершены
            - ready_for_conclusion: True если готов к финальному выводу
            - is_complete: True если весь шаблон завершен
            - progress_summary: текстовое описание прогресса
            - formatted_answer: отформатированный ответ (если is_complete)
        """
        progress = await self.progress_repo.get_active_progress(
            user_id, step_id, question_id
        )
        
        if not progress:
            return {"success": False, "error": "Прогресс не найден. Начни заполнение шаблона заново."}
        
        if progress.status == TemplateProgressStatus.COMPLETED:
            return {"success": False, "error": "Шаблон уже заполнен."}
        
        current_field = progress.current_field
        
        # Если это финальный вывод
        if current_field == "conclusion":
            await self.progress_repo.save_conclusion(progress, value)
            formatted_answer = self.progress_repo.format_template_for_saving(progress)
            
            return {
                "success": True,
                "next_field": None,
                "is_complete": True,
                "progress_summary": self.progress_repo.get_progress_summary(progress),
                "formatted_answer": formatted_answer
            }
        
        # Валидация для feelings_before (минимум 3 чувства)
        if current_field == "feelings_before":
            feelings = [f.strip() for f in value.replace('\n', ',').split(',') if f.strip()]
            if len(feelings) < 3:
                return {
                    "success": False,
                    "error": f"Нужно указать минимум 3 чувства. Ты указал: {len(feelings)}. Напиши ещё.",
                    "validation_error": True
                }
        
        # Сохраняем значение и получаем следующее поле
        result = await self.progress_repo.save_field_value(progress, current_field, value)
        
        # Получаем информацию о следующем поле
        field_info = self.progress_repo.get_current_field_info(progress)
        progress_summary = self.progress_repo.get_progress_summary(progress)
        
        return {
            "success": True,
            "next_field": result["next_field"],
            "field_info": field_info,
            "current_situation": result["current_situation"],
            "is_situation_complete": result["is_situation_complete"],
            "is_all_situations_complete": result["is_all_situations_complete"],
            "ready_for_conclusion": result["ready_for_conclusion"],
            "is_complete": result.get("is_complete", False),
            "progress_summary": progress_summary
        }
    
    async def pause_template_filling(
        self, user_id: int, step_id: int, question_id: int
    ) -> Dict[str, Any]:
        """
        Поставить заполнение шаблона на паузу.
        
        Returns:
            dict с информацией о сохранённом прогрессе
        """
        progress = await self.progress_repo.get_active_progress(
            user_id, step_id, question_id
        )
        
        if not progress:
            return {"success": False, "error": "Прогресс не найден."}
        
        await self.progress_repo.pause_progress(progress)
        progress_summary = self.progress_repo.get_progress_summary(progress)
        field_info = self.progress_repo.get_current_field_info(progress)
        
        return {
            "success": True,
            "status": "PAUSED",
            "progress_summary": progress_summary,
            "resume_info": f"Ты остановился на Ситуации {progress.current_situation} — поле '{field_info.get('name', progress.current_field)}'"
        }
    
    async def get_template_progress(
        self, user_id: int, step_id: int, question_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Получить текущий прогресс по шаблону.
        
        Returns:
            dict с информацией о прогрессе или None если не найден
        """
        progress = await self.progress_repo.get_active_progress(
            user_id, step_id, question_id
        )
        
        if not progress:
            return None
        
        field_info = self.progress_repo.get_current_field_info(progress)
        progress_summary = self.progress_repo.get_progress_summary(progress)
        
        return {
            "progress_id": progress.id,
            "status": progress.status.value,
            "current_field": progress.current_field,
            "current_situation": progress.current_situation,
            "field_info": field_info,
            "progress_summary": progress_summary,
            "situations": progress.situations,
            "conclusion": progress.conclusion,
            "is_complete": progress.status == TemplateProgressStatus.COMPLETED
        }
    
    async def cancel_template_filling(
        self, user_id: int, step_id: int, question_id: int
    ) -> Dict[str, Any]:
        """Отменить заполнение шаблона"""
        progress = await self.progress_repo.get_active_progress(
            user_id, step_id, question_id
        )
        
        if not progress:
            return {"success": False, "error": "Прогресс не найден."}
        
        await self.progress_repo.cancel_progress(progress)
        
        return {"success": True, "status": "CANCELLED"}
    
    def get_template_fields_info(self) -> List[Dict[str, Any]]:
        """Получить информацию о полях шаблона"""
        return TEMPLATE_FIELDS
    
    def get_min_situations(self) -> int:
        """Получить минимальное количество ситуаций"""
        return MIN_SITUATIONS

