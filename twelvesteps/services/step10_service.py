"""Service for Step 10 daily analysis"""
from typing import Dict, Any, Optional
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
import json
import aiofiles

from repositories.Step10DailyAnalysisRepository import Step10DailyAnalysisRepository
from db.models import Step10AnalysisStatus, User


class Step10Service:
    def __init__(self, session: AsyncSession):
        self.repo = Step10DailyAnalysisRepository(session)
        self.session = session
    
    @staticmethod
    async def load_questions() -> list:
        """Загрузить список из 10 вопросов из JSON файла"""
        try:
            async with aiofiles.open("./llm/prompts/step10_questions.json", "r", encoding="utf-8") as f:
                content = await f.read()
                data = json.loads(content)
                return data.get("questions", [])
        except Exception:
            # Fallback: возвращаем вопросы встроенные
            return [
                {"number": 1, "text": "Где я сегодня почувствовал внутреннее напряжение, тревогу, раздражение, боль?", "subtext": "(Что запомнилось эмоционально?)"},
                {"number": 2, "text": "Какие старые модели поведения проявились?", "subtext": "(Контроль, избегание, обида, изоляция, злость, жалость к себе…)"},
                {"number": 3, "text": "Что я подумал / сделал, о чём жалею или что хочется пересмотреть?"},
                {"number": 4, "text": "Нанёс ли я кому-то или себе вред — действием, словом, бездействием, тональностью?"},
                {"number": 5, "text": "Был ли я честен в своих словах, мотивах и реакциях?"},
                {"number": 6, "text": "Повторялись ли сегодня старые чувства, мысли, действия, зацикленности?"},
                {"number": 7, "text": "Где я подавлял чувства или избегал ситуации?"},
                {"number": 8, "text": "Просил ли я о помощи? Или пытался всё потянуть один?"},
                {"number": 9, "text": "Применил ли я сегодня какие-то духовные принципы (честность, смирение, доверие, служение)? Где — да, где — нет?"},
                {"number": 10, "text": "За что я сегодня благодарен? Или наоборот — что особенно \"застряло\" во мне?"}
            ]
    
    async def start_analysis(
        self, user_id: int, analysis_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Начать или продолжить самоанализ.
        
        Returns:
            dict с информацией:
            - analysis_id: ID анализа
            - status: статус
            - current_question: текущий вопрос (1-10)
            - question_data: данные текущего вопроса
            - progress_summary: описание прогресса
            - is_resumed: True если возобновлен с паузы
        """
        if analysis_date is None:
            analysis_date = date.today()
        
        # Проверяем, есть ли незавершенный анализ за вчера
        yesterday = date.fromordinal(analysis_date.toordinal() - 1)
        yesterday_analysis = await self.repo.get_active_analysis(user_id, yesterday)
        
        is_resumed = False
        if yesterday_analysis and yesterday_analysis.status == Step10AnalysisStatus.PAUSED:
            # Если вчера был незавершенный анализ, предлагаем продолжить его
            # Но для нового дня создаем новый
            pass
        
        analysis = await self.repo.get_or_create_analysis(user_id, analysis_date)
        
        if analysis.status == Step10AnalysisStatus.PAUSED:
            await self.repo.resume_analysis(analysis)
            is_resumed = True
        
        questions = await self.load_questions()
        current_q = analysis.current_question
        
        # Находим данные текущего вопроса
        question_data = None
        for q in questions:
            if q["number"] == current_q:
                question_data = q
                break
        
        if not question_data:
            question_data = questions[0] if questions else None
        
        progress_summary = self.repo.get_progress_summary(analysis)
        
        return {
            "analysis_id": analysis.id,
            "status": analysis.status.value,
            "current_question": analysis.current_question,
            "question_data": question_data,
            "progress_summary": progress_summary,
            "is_resumed": is_resumed,
            "is_complete": analysis.status == Step10AnalysisStatus.COMPLETED
        }
    
    async def submit_answer(
        self, user_id: int, question_number: int, answer: str,
        analysis_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Сохранить ответ на вопрос.
        
        Returns:
            dict с информацией:
            - success: True если сохранено
            - next_question: следующий вопрос (1-10) или None
            - next_question_data: данные следующего вопроса
            - is_complete: True если все вопросы заполнены
            - progress_summary: описание прогресса
        """
        if analysis_date is None:
            analysis_date = date.today()
        
        analysis = await self.repo.get_active_analysis(user_id, analysis_date)
        
        if not analysis:
            return {"success": False, "error": "Самоанализ не найден. Начни заново."}
        
        if analysis.status == Step10AnalysisStatus.COMPLETED:
            return {"success": False, "error": "Самоанализ уже завершён."}
        
        # Сохраняем ответ
        result = await self.repo.save_answer(analysis, question_number, answer)
        
        questions = await self.load_questions()
        next_question_data = None
        
        if result["next_question"]:
            for q in questions:
                if q["number"] == result["next_question"]:
                    next_question_data = q
                    break
        
        return {
            "success": True,
            "next_question": result["next_question"],
            "next_question_data": next_question_data,
            "is_complete": result["is_complete"],
            "progress_summary": result["progress_summary"]
        }
    
    async def pause_analysis(
        self, user_id: int, analysis_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """Поставить самоанализ на паузу"""
        if analysis_date is None:
            analysis_date = date.today()
        
        analysis = await self.repo.get_active_analysis(user_id, analysis_date)
        
        if not analysis:
            return {"success": False, "error": "Самоанализ не найден."}
        
        await self.repo.pause_analysis(analysis)
        progress_summary = self.repo.get_progress_summary(analysis)
        
        questions = await self.load_questions()
        current_q_data = None
        for q in questions:
            if q["number"] == analysis.current_question:
                current_q_data = q
                break
        
        return {
            "success": True,
            "status": "PAUSED",
            "progress_summary": progress_summary,
            "current_question": analysis.current_question,
            "question_data": current_q_data,
            "resume_info": f"Ты остановился на вопросе {analysis.current_question}. При следующем входе сможешь продолжить."
        }
    
    async def get_analysis_progress(
        self, user_id: int, analysis_date: Optional[date] = None
    ) -> Optional[Dict[str, Any]]:
        """Получить текущий прогресс самоанализа"""
        if analysis_date is None:
            analysis_date = date.today()
        
        analysis = await self.repo.get_active_analysis(user_id, analysis_date)
        
        if not analysis:
            return None
        
        questions = await self.load_questions()
        current_q_data = None
        for q in questions:
            if q["number"] == analysis.current_question:
                current_q_data = q
                break
        
        return {
            "analysis_id": analysis.id,
            "status": analysis.status.value,
            "current_question": analysis.current_question,
            "question_data": current_q_data,
            "progress_summary": self.repo.get_progress_summary(analysis),
            "answers": analysis.answers,
            "is_complete": analysis.status == Step10AnalysisStatus.COMPLETED
        }

