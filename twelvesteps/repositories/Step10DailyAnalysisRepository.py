"""Repository for Step 10 daily analysis tracking"""
from typing import Optional, List
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from db.models import Step10DailyAnalysis, Step10AnalysisStatus


class Step10DailyAnalysisRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_active_analysis(
        self, user_id: int, analysis_date: Optional[date] = None
    ) -> Optional[Step10DailyAnalysis]:
        """Получить активный самоанализ для пользователя на указанную дату (или сегодня)"""
        if analysis_date is None:
            analysis_date = date.today()
        
        stmt = select(Step10DailyAnalysis).where(
            and_(
                Step10DailyAnalysis.user_id == user_id,
                Step10DailyAnalysis.analysis_date == analysis_date,
                Step10DailyAnalysis.status.in_([
                    Step10AnalysisStatus.IN_PROGRESS,
                    Step10AnalysisStatus.PAUSED
                ])
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
    
    async def get_any_analysis(
        self, user_id: int, analysis_date: Optional[date] = None
    ) -> Optional[Step10DailyAnalysis]:
        """Получить любой самоанализ для пользователя на указанную дату (включая COMPLETED)"""
        if analysis_date is None:
            analysis_date = date.today()
        
        stmt = select(Step10DailyAnalysis).where(
            and_(
                Step10DailyAnalysis.user_id == user_id,
                Step10DailyAnalysis.analysis_date == analysis_date
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
    
    async def get_or_create_analysis(
        self, user_id: int, analysis_date: Optional[date] = None
    ) -> Step10DailyAnalysis:
        """Получить или создать самоанализ для пользователя на указанную дату"""
        if analysis_date is None:
            analysis_date = date.today()
        
        # Сначала ищем существующий
        analysis = await self.get_any_analysis(user_id, analysis_date)
        
        if analysis:
            # Если был COMPLETED — сбрасываем для нового заполнения
            if analysis.status == Step10AnalysisStatus.COMPLETED:
                analysis.status = Step10AnalysisStatus.IN_PROGRESS
                analysis.current_question = 1
                analysis.answers = []
                analysis.completed_at = None
                analysis.updated_at = datetime.utcnow()
                self.session.add(analysis)
                await self.session.flush()
            elif analysis.status == Step10AnalysisStatus.PAUSED:
                # Возобновляем с паузы
                analysis.status = Step10AnalysisStatus.IN_PROGRESS
                analysis.paused_at = None
                analysis.updated_at = datetime.utcnow()
                self.session.add(analysis)
                await self.session.flush()
            return analysis
        
        # Создаём новый
        analysis = Step10DailyAnalysis(
            user_id=user_id,
            analysis_date=analysis_date,
            status=Step10AnalysisStatus.IN_PROGRESS,
            current_question=1,
            answers=[]
        )
        self.session.add(analysis)
        await self.session.flush()
        
        return analysis
    
    async def save_answer(
        self, analysis: Step10DailyAnalysis, question_number: int, answer: str
    ) -> dict:
        """
        Сохранить ответ на вопрос и вернуть информацию о следующем шаге.
        
        Returns:
            dict с ключами:
            - next_question: следующий вопрос (1-10) или None если завершено
            - is_complete: True если все 10 вопросов заполнены
            - progress_summary: текстовое описание прогресса
        """
        answers = analysis.answers or []
        
        # Обновляем или добавляем ответ
        answer_found = False
        for i, ans in enumerate(answers):
            if ans.get("question_number") == question_number:
                answers[i]["answer"] = answer
                answers[i]["answered_at"] = datetime.utcnow().isoformat()
                answer_found = True
                break
        
        if not answer_found:
            answers.append({
                "question_number": question_number,
                "answer": answer,
                "answered_at": datetime.utcnow().isoformat()
            })
        
        analysis.answers = answers
        
        # Определяем следующий вопрос
        next_question = None
        is_complete = False
        
        if question_number < 10:
            next_question = question_number + 1
            analysis.current_question = next_question
        else:
            # Все 10 вопросов заполнены
            is_complete = True
            analysis.status = Step10AnalysisStatus.COMPLETED
            analysis.completed_at = datetime.utcnow()
            analysis.current_question = 10
        
        analysis.updated_at = datetime.utcnow()
        self.session.add(analysis)
        await self.session.flush()
        
        progress_summary = self.get_progress_summary(analysis)
        
        return {
            "next_question": next_question,
            "is_complete": is_complete,
            "progress_summary": progress_summary
        }
    
    async def pause_analysis(self, analysis: Step10DailyAnalysis) -> Step10DailyAnalysis:
        """Поставить самоанализ на паузу"""
        analysis.status = Step10AnalysisStatus.PAUSED
        analysis.paused_at = datetime.utcnow()
        analysis.updated_at = datetime.utcnow()
        
        self.session.add(analysis)
        await self.session.flush()
        
        return analysis
    
    async def resume_analysis(self, analysis: Step10DailyAnalysis) -> Step10DailyAnalysis:
        """Возобновить самоанализ с паузы"""
        analysis.status = Step10AnalysisStatus.IN_PROGRESS
        analysis.paused_at = None
        analysis.updated_at = datetime.utcnow()
        
        self.session.add(analysis)
        await self.session.flush()
        
        return analysis
    
    def get_progress_summary(self, analysis: Step10DailyAnalysis) -> str:
        """Получить текстовое описание прогресса"""
        answers = analysis.answers or []
        answered_count = len(answers)
        
        if analysis.status == Step10AnalysisStatus.COMPLETED:
            return f"✅ Самоанализ за {analysis.analysis_date.strftime('%d.%m.%Y')} завершён: {answered_count}/10 вопросов"
        
        if analysis.status == Step10AnalysisStatus.PAUSED:
            return f"⏸ Самоанализ на паузе: {answered_count}/10 вопросов. Остановился на вопросе {analysis.current_question}"
        
        return f"📝 Прогресс: {answered_count}/10 вопросов. Текущий вопрос: {analysis.current_question}"
    
    def format_analysis_for_saving(self, analysis: Step10DailyAnalysis) -> str:
        """Форматировать заполненный самоанализ для сохранения"""
        answers = analysis.answers or []
        result_parts = []
        
        result_parts.append(f"📘 Ежедневный самоанализ (10 шаг) — {analysis.analysis_date.strftime('%d.%m.%Y')}\n")
        
        # Сортируем ответы по номеру вопроса
        sorted_answers = sorted(answers, key=lambda x: x.get("question_number", 0))
        
        for ans in sorted_answers:
            q_num = ans.get("question_number", 0)
            answer_text = ans.get("answer", "")
            result_parts.append(f"{q_num}. {answer_text}\n")
        
        return "\n".join(result_parts)

