"""Repository for template progress tracking"""
from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from db.models import TemplateProgress, TemplateProgressStatus


# Определение полей шаблона и их порядка
TEMPLATE_FIELDS = [
    {"key": "where", "name": "Где это произошло?", "description": "Контекст, место, время"},
    {"key": "thoughts", "name": "Что ты думал?", "description": "Мысль, установка, реакция ума"},
    {"key": "feelings_before", "name": "Чувства (до)", "description": "Минимум 3 чувства — из списка или своими словами", "min_items": 3},
    {"key": "actions", "name": "Что ты сделал?", "description": "Действие, без обобщений"},
    {"key": "healthy_feelings", "name": "Чувства от здоровой части", "description": "Принятие, ясность, уважение и т.д."},
    {"key": "next_step", "name": "Пути выхода / Следующий шаг", "description": "Конкретное действие + срок"},
]

FIELD_ORDER = [f["key"] for f in TEMPLATE_FIELDS]
MIN_SITUATIONS = 3


class TemplateProgressRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_active_progress(
        self, user_id: int, step_id: int, question_id: int
    ) -> Optional[TemplateProgress]:
        """Получить активный прогресс по шаблону для вопроса"""
        stmt = select(TemplateProgress).where(
            and_(
                TemplateProgress.user_id == user_id,
                TemplateProgress.step_id == step_id,
                TemplateProgress.question_id == question_id,
                TemplateProgress.status.in_([
                    TemplateProgressStatus.IN_PROGRESS,
                    TemplateProgressStatus.PAUSED
                ])
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
    
    async def get_or_create_progress(
        self, user_id: int, step_id: int, question_id: int
    ) -> TemplateProgress:
        """Получить или создать прогресс по шаблону"""
        progress = await self.get_active_progress(user_id, step_id, question_id)
        
        if not progress:
            progress = TemplateProgress(
                user_id=user_id,
                step_id=step_id,
                question_id=question_id,
                status=TemplateProgressStatus.IN_PROGRESS,
                current_situation=1,
                current_field="where",
                situations=[]
            )
            self.session.add(progress)
            await self.session.flush()
        
        return progress
    
    async def save_field_value(
        self, progress: TemplateProgress, field_key: str, value: str
    ) -> dict:
        """
        Сохранить значение поля и вернуть следующее поле.
        
        Returns:
            dict с ключами:
            - next_field: следующее поле для заполнения (или None если все заполнено)
            - current_situation: номер текущей ситуации
            - is_situation_complete: True если текущая ситуация завершена
            - is_all_situations_complete: True если все 3 ситуации завершены
            - ready_for_conclusion: True если готов к финальному выводу
            - is_complete: True если весь шаблон завершен
        """
        situations = progress.situations or []
        current_sit_idx = progress.current_situation - 1  # 0-based index
        
        # Убедимся что есть структура для текущей ситуации
        while len(situations) <= current_sit_idx:
            situations.append({
                "where": None,
                "thoughts": None,
                "feelings_before": None,
                "actions": None,
                "healthy_feelings": None,
                "next_step": None,
                "complete": False
            })
        
        current_situation = situations[current_sit_idx]
        
        # Сохраняем значение
        if field_key == "feelings_before":
            # Парсим чувства (разделенные запятой или новой строкой)
            feelings = [f.strip() for f in value.replace('\n', ',').split(',') if f.strip()]
            current_situation[field_key] = feelings
        else:
            current_situation[field_key] = value
        
        # Определяем следующее поле
        current_field_idx = FIELD_ORDER.index(field_key)
        next_field_idx = current_field_idx + 1
        
        result = {
            "next_field": None,
            "current_situation": progress.current_situation,
            "is_situation_complete": False,
            "is_all_situations_complete": False,
            "ready_for_conclusion": False,
            "is_complete": False
        }
        
        if next_field_idx < len(FIELD_ORDER):
            # Есть следующее поле в текущей ситуации
            next_field = FIELD_ORDER[next_field_idx]
            progress.current_field = next_field
            result["next_field"] = next_field
        else:
            # Текущая ситуация завершена
            current_situation["complete"] = True
            result["is_situation_complete"] = True
            
            if progress.current_situation < MIN_SITUATIONS:
                # Переход к следующей ситуации
                progress.current_situation += 1
                progress.current_field = "where"
                result["current_situation"] = progress.current_situation
                result["next_field"] = "where"
            else:
                # Все 3 ситуации заполнены
                result["is_all_situations_complete"] = True
                result["ready_for_conclusion"] = True
                progress.current_field = "conclusion"
                result["next_field"] = "conclusion"
        
        progress.situations = situations
        progress.updated_at = datetime.utcnow()
        
        self.session.add(progress)
        await self.session.flush()
        
        return result
    
    async def save_conclusion(self, progress: TemplateProgress, conclusion: str) -> bool:
        """Сохранить финальный вывод и завершить шаблон"""
        progress.conclusion = conclusion
        progress.status = TemplateProgressStatus.COMPLETED
        progress.completed_at = datetime.utcnow()
        progress.current_field = "done"
        
        self.session.add(progress)
        await self.session.flush()
        
        return True
    
    async def pause_progress(self, progress: TemplateProgress) -> TemplateProgress:
        """Поставить прогресс на паузу"""
        progress.status = TemplateProgressStatus.PAUSED
        progress.paused_at = datetime.utcnow()
        
        self.session.add(progress)
        await self.session.flush()
        
        return progress
    
    async def resume_progress(self, progress: TemplateProgress) -> TemplateProgress:
        """Возобновить прогресс"""
        progress.status = TemplateProgressStatus.IN_PROGRESS
        progress.paused_at = None
        
        self.session.add(progress)
        await self.session.flush()
        
        return progress
    
    async def cancel_progress(self, progress: TemplateProgress) -> TemplateProgress:
        """Отменить прогресс"""
        progress.status = TemplateProgressStatus.CANCELLED
        
        self.session.add(progress)
        await self.session.flush()
        
        return progress
    
    def get_current_field_info(self, progress: TemplateProgress) -> dict:
        """Получить информацию о текущем поле для заполнения"""
        if progress.current_field == "conclusion":
            return {
                "key": "conclusion",
                "name": "Финальный вывод",
                "description": "Как ты теперь видишь ситуацию? Что на самом деле происходило? Как повторялись чувства/мысли/действия? Где была болезнь, где был ты?",
                "is_conclusion": True
            }
        
        if progress.current_field == "done":
            return {
                "key": "done",
                "name": "Завершено",
                "description": "Шаблон полностью заполнен",
                "is_complete": True
            }
        
        # Находим информацию о поле
        for field in TEMPLATE_FIELDS:
            if field["key"] == progress.current_field:
                return {
                    **field,
                    "situation_number": progress.current_situation,
                    "is_conclusion": False,
                    "is_complete": False
                }
        
        # Fallback
        return {
            "key": progress.current_field,
            "name": progress.current_field,
            "description": "",
            "situation_number": progress.current_situation
        }
    
    def get_progress_summary(self, progress: TemplateProgress) -> str:
        """Получить текстовое описание прогресса"""
        situations = progress.situations or []
        completed_situations = sum(1 for s in situations if s.get("complete"))
        
        if progress.status == TemplateProgressStatus.COMPLETED:
            return f"✅ Шаблон заполнен полностью: {MIN_SITUATIONS} ситуации + вывод"
        
        if progress.current_field == "conclusion":
            return f"📝 Ситуации: {completed_situations}/{MIN_SITUATIONS} ✅\nОсталось: Финальный вывод"
        
        field_info = self.get_current_field_info(progress)
        field_name = field_info.get("name", progress.current_field)
        
        return f"📝 Ситуация {progress.current_situation}/{MIN_SITUATIONS}\nПоле: {field_name}"
    
    def format_template_for_saving(self, progress: TemplateProgress) -> str:
        """Форматировать заполненный шаблон для сохранения как ответ"""
        situations = progress.situations or []
        result_parts = []
        
        for i, situation in enumerate(situations, 1):
            if not situation.get("complete"):
                continue
            
            result_parts.append(f"📌 СИТУАЦИЯ {i}:")
            result_parts.append(f"  Где: {situation.get('where', '-')}")
            result_parts.append(f"  Мысли: {situation.get('thoughts', '-')}")
            
            feelings = situation.get('feelings_before', [])
            if isinstance(feelings, list):
                feelings_str = ', '.join(feelings)
            else:
                feelings_str = str(feelings)
            result_parts.append(f"  Чувства (до): {feelings_str}")
            
            result_parts.append(f"  Действие: {situation.get('actions', '-')}")
            result_parts.append(f"  Здоровые чувства: {situation.get('healthy_feelings', '-')}")
            result_parts.append(f"  Следующий шаг: {situation.get('next_step', '-')}")
            result_parts.append("")
        
        if progress.conclusion:
            result_parts.append("📌 ФИНАЛЬНЫЙ ВЫВОД:")
            result_parts.append(progress.conclusion)
        
        return "\n".join(result_parts)

