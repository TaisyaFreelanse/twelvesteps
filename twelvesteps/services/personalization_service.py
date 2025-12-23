"""Service for building personalized prompt from all user answers."""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, desc
from db.models import (
    User, ProfileAnswer, ProfileQuestion, ProfileSection, ProfileSectionData,
    StepAnswer, Question, Step, Message, SenderRole, Gratitude,
    Step10DailyAnalysis, Step10AnalysisStatus
)
from repositories.UserRepository import UserRepository


async def update_personalized_prompt_from_all_answers(session: AsyncSession, user_id: int) -> None:
    """
    Build complete personalized prompt from ALL user answers:
    - Onboarding data (display_name, program_experience, sobriety_date)
    - Profile answers (from "Рассказать о себе")
    - Step answers (from work on steps)
    - Regular chat messages (from everyday conversations)
    
    This creates a complete picture of the user's character for personalization.
    The bot adapts and remembers personality from ALL interactions, not just profile filling.
    """
    user_repo = UserRepository(session)
    personalized_prompt = await user_repo.get_personalized_prompt(user_id) or ""
    
    # Get user data for onboarding info
    from sqlalchemy import select
    from db.models import User
    user_stmt = select(User).where(User.id == user_id)
    user_result = await session.execute(user_stmt)
    user = user_result.scalar_one_or_none()
    
    # Remove old sections if exist
    import re
    personalized_prompt = re.sub(
        r'=== ДАННЫЕ ОНБОРДИНГА.*?===.*?(?=\n\n===|\Z)',
        '',
        personalized_prompt,
        flags=re.DOTALL
    ).strip()
    personalized_prompt = re.sub(
        r'=== ИНФОРМАЦИЯ ИЗ ПРОФИЛЯ.*?===.*?(?=\n\n===|\Z)',
        '',
        personalized_prompt,
        flags=re.DOTALL
    ).strip()
    personalized_prompt = re.sub(
        r'=== ОТВЕТЫ ПО ШАГАМ.*?===.*?(?=\n\n===|\Z)',
        '',
        personalized_prompt,
        flags=re.DOTALL
    ).strip()
    personalized_prompt = re.sub(
        r'=== БЛАГОДАРНОСТИ.*?===.*?(?=\n\n===|\Z)',
        '',
        personalized_prompt,
        flags=re.DOTALL
    ).strip()
    personalized_prompt = re.sub(
        r'=== ЕЖЕДНЕВНЫЙ САМОАНАЛИЗ.*?===.*?(?=\n\n===|\Z)',
        '',
        personalized_prompt,
        flags=re.DOTALL
    ).strip()
    personalized_prompt = re.sub(
        r'=== ИНФОРМАЦИЯ ИЗ ОБЫЧНОГО ОБЩЕНИЯ.*?===.*?(?=\n\n===|\Z)',
        '',
        personalized_prompt,
        flags=re.DOTALL
    ).strip()
    
    # ============================================================
    # 0. COLLECT ONBOARDING DATA
    # ============================================================
    onboarding_summary = "=== ДАННЫЕ ОНБОРДИНГА (СТАРТОВАЯ ИНФОРМАЦИЯ) ===\n\n"
    
    if user:
        if user.display_name:
            onboarding_summary += f"Имя: {user.display_name}\n"
        
        if user.program_experience:
            experience_map = {
                "NEWBIE": "Новичок",
                "SOME_EXPERIENCE": "Есть немного опыта",
                "LONG_TERM": "Бывалый / Давно в программе"
            }
            experience_display = experience_map.get(user.program_experience, user.program_experience)
            onboarding_summary += f"Опыт работы с программой: {experience_display}\n"
        
        if user.sobriety_date:
            onboarding_summary += f"Дата трезвости: {user.sobriety_date}\n"
        
        if not user.display_name and not user.program_experience and not user.sobriety_date:
            onboarding_summary += "Пользователь еще не прошел онбординг.\n"
    else:
        onboarding_summary += "Пользователь не найден.\n"
    
    onboarding_summary += "\n"
    
    # ============================================================
    # 1. COLLECT PROFILE ANSWERS
    # ============================================================
    profile_summary = "=== ИНФОРМАЦИЯ ИЗ ПРОФИЛЯ ПОЛЬЗОВАТЕЛЯ (ТОЧНЫЕ ОТВЕТЫ) ===\n\n"
    
    # Subquery to get max version per question
    max_version_subq = (
        select(
            ProfileAnswer.question_id,
            func.max(ProfileAnswer.version).label('max_version')
        )
        .where(ProfileAnswer.user_id == user_id)
        .group_by(ProfileAnswer.question_id)
    ).subquery()
    
    # Get all profile answers with latest versions
    profile_answers_stmt = (
        select(
            ProfileAnswer.answer_text,
            ProfileQuestion.question_text,
            ProfileSection.name.label('section_name'),
            ProfileSection.order_index
        )
        .join(ProfileQuestion, ProfileAnswer.question_id == ProfileQuestion.id)
        .join(ProfileSection, ProfileQuestion.section_id == ProfileSection.id)
        .join(
            max_version_subq,
            (ProfileAnswer.question_id == max_version_subq.c.question_id) &
            (ProfileAnswer.version == max_version_subq.c.max_version)
        )
        .where(ProfileAnswer.user_id == user_id)
        .order_by(ProfileSection.order_index, ProfileQuestion.id)
    )
    profile_answers_result = await session.execute(profile_answers_stmt)
    profile_answers = profile_answers_result.all()
    
    # Track sections we've processed
    processed_sections = set()
    current_section = None
    
    if profile_answers:
        for answer_text, question_text, section_name, _ in profile_answers:
            if current_section != section_name:
                if current_section is not None:
                    profile_summary += "\n"
                profile_summary += f"[{section_name}]\n"
                current_section = section_name
                processed_sections.add(section_name)
            profile_summary += f"Вопрос: {question_text}\n"
            profile_summary += f"Ответ: {answer_text}\n\n"
    
    # Also collect free text data (ProfileSectionData) for each section
    # Get all entries with metadata, ordered by importance and recency
    free_text_data_stmt = (
        select(
            ProfileSectionData.content,
            ProfileSectionData.subblock_name,
            ProfileSectionData.entity_type,
            ProfileSectionData.importance,
            ProfileSectionData.is_core_personality,
            ProfileSectionData.tags,
            ProfileSectionData.created_at,
            ProfileSection.name.label('section_name'),
            ProfileSection.order_index
        )
        .join(ProfileSection, ProfileSectionData.section_id == ProfileSection.id)
        .where(ProfileSectionData.user_id == user_id)
        .order_by(
            ProfileSection.order_index,
            desc(ProfileSectionData.is_core_personality),  # Core personality first
            desc(ProfileSectionData.importance),  # Then by importance
            desc(ProfileSectionData.created_at)  # Then by recency
        )
    )
    free_text_data_result = await session.execute(free_text_data_stmt)
    free_text_data = free_text_data_result.all()
    
    if free_text_data:
        # Group by section and subblock for better aggregation
        section_data_map = {}
        for row in free_text_data:
            content, subblock_name, entity_type, importance, is_core, tags, created_at, section_name, order_idx = row
            if not content or len(content.strip()) == 0:
                continue
            
            if section_name not in section_data_map:
                section_data_map[section_name] = {
                    'order_index': order_idx,
                    'subblocks': {}
                }
            
            # Group by subblock if exists
            subblock_key = subblock_name or "general"
            if subblock_key not in section_data_map[section_name]['subblocks']:
                section_data_map[section_name]['subblocks'][subblock_key] = []
            
            section_data_map[section_name]['subblocks'][subblock_key].append({
                'content': content,
                'entity_type': entity_type,
                'importance': importance,
                'is_core_personality': is_core,
                'tags': tags,
                'created_at': created_at
            })
        
        # Build summary with aggregation
        sorted_sections = sorted(section_data_map.items(), key=lambda x: x[1]['order_index'])
        
        for section_name, section_info in sorted_sections:
            if section_name not in processed_sections:
                if current_section is not None:
                    profile_summary += "\n"
                profile_summary += f"[{section_name}]\n"
                current_section = section_name
                processed_sections.add(section_name)
            elif current_section != section_name:
                if current_section is not None:
                    profile_summary += "\n"
                current_section = section_name
            
            # Aggregate entries by subblock
            for subblock_name, entries in section_info['subblocks'].items():
                # Sort entries: core personality first, then by importance and recency
                entries.sort(key=lambda e: (
                    not e['is_core_personality'],
                    -(e['importance'] or 1.0),
                    -(e['created_at'].timestamp() if e['created_at'] else 0)
                ))
                
                # For each subblock, aggregate information
                if subblock_name != "general":
                    profile_summary += f"  • {subblock_name}"
                    if entries[0].get('entity_type'):
                        profile_summary += f" ({entries[0]['entity_type']})"
                    profile_summary += ":\n"
                
                # Include most important/recent entries (limit to top 3 per subblock)
                for entry in entries[:3]:
                    content = entry['content']
                    if subblock_name == "general":
                        profile_summary += f"  - {content}"
                    else:
                        profile_summary += f"    {content}"
                    
                    # Add metadata if significant
                    if entry.get('is_core_personality'):
                        profile_summary += " [ядро личности]"
                    if entry.get('tags'):
                        profile_summary += f" [теги: {entry['tags']}]"
                    profile_summary += "\n"
                
                # If there are more entries, summarize
                if len(entries) > 3:
                    profile_summary += f"    ... и ещё {len(entries) - 3} записей\n"
    
    if not profile_answers and not free_text_data:
        profile_summary += "Пользователь еще не заполнил профиль.\n\n"
    
    # ============================================================
    # 2. COLLECT STEP ANSWERS
    # ============================================================
    steps_summary = "=== ОТВЕТЫ ПО ШАГАМ (РАБОТА ПО ПРОГРАММЕ) ===\n\n"
    
    # Get all step answers with questions and steps
    step_answers_stmt = (
        select(
            StepAnswer.answer_text,
            Question.text.label('question_text'),
            Step.index.label('step_number'),
            Step.title.label('step_title'),
            StepAnswer.created_at
        )
        .join(Question, StepAnswer.question_id == Question.id)
        .join(Step, StepAnswer.step_id == Step.id)
        .where(StepAnswer.user_id == user_id)
        .order_by(Step.index, Question.id, StepAnswer.created_at)
    )
    step_answers_result = await session.execute(step_answers_stmt)
    step_answers = step_answers_result.all()
    
    if step_answers:
        current_step = None
        for answer_text, question_text, step_number, step_title, created_at in step_answers:
            if current_step != step_number:
                if current_step is not None:
                    steps_summary += "\n"
                step_title_display = step_title or f"Шаг {step_number}"
                steps_summary += f"[{step_title_display} (Шаг {step_number})]\n"
                current_step = step_number
            steps_summary += f"Вопрос: {question_text}\n"
            steps_summary += f"Ответ: {answer_text}\n\n"
    else:
        steps_summary += "Пользователь еще не начал работу по шагам.\n\n"
    
    # ============================================================
    # 3. COLLECT GRATITUDES
    # ============================================================
    gratitudes_stmt = (
        select(Gratitude.text, Gratitude.created_at)
        .where(Gratitude.user_id == user_id)
        .order_by(desc(Gratitude.created_at))
        .limit(20)
    )
    gratitudes_result = await session.execute(gratitudes_stmt)
    gratitudes = gratitudes_result.all()
    
    gratitudes_summary = "=== БЛАГОДАРНОСТИ ===\n\n"
    if gratitudes:
        gratitudes_summary += "Записи благодарностей пользователя:\n"
        for text, created_at in gratitudes:
            gratitudes_summary += f"- {text}\n"
    else:
        gratitudes_summary += "Пользователь еще не записывал благодарности.\n\n"
    
    # ============================================================
    # 4. COLLECT STEP 10 DAILY ANALYSIS (self-analysis)
    # ============================================================
    step10_summary = "=== ЕЖЕДНЕВНЫЙ САМОАНАЛИЗ (ШАГ 10) ===\n\n"
    
    # Get recent Step 10 analyses (last 10 completed analyses)
    step10_analyses_stmt = (
        select(Step10DailyAnalysis)
        .where(
            Step10DailyAnalysis.user_id == user_id,
            Step10DailyAnalysis.status == Step10AnalysisStatus.COMPLETED
        )
        .order_by(desc(Step10DailyAnalysis.analysis_date))
        .limit(10)
    )
    step10_analyses_result = await session.execute(step10_analyses_stmt)
    step10_analyses = step10_analyses_result.scalars().all()
    
    if step10_analyses:
        step10_summary += "Записи ежедневного самоанализа:\n\n"
        for analysis in step10_analyses:
            # Format analysis data from answers JSON
            if analysis.answers:
                date_str = analysis.analysis_date.strftime("%d.%m.%Y") if analysis.analysis_date else ""
                step10_summary += f"[{date_str}]\n"
                for answer_entry in analysis.answers:
                    q_num = answer_entry.get("question_number", 0)
                    answer_text = answer_entry.get("answer", "")
                    if answer_text:
                        step10_summary += f"Вопрос {q_num}: {answer_text}\n"
                step10_summary += "\n"
    else:
        step10_summary += "Пользователь еще не проходил ежедневный самоанализ.\n\n"
    
    # ============================================================
    # 5. COLLECT REGULAR CHAT MESSAGES (from everyday conversations)
    # ============================================================
    chat_summary = "=== ИНФОРМАЦИЯ ИЗ ОБЫЧНОГО ОБЩЕНИЯ ===\n\n"
    
    # Get recent user messages (last 20 messages from user, not bot)
    chat_messages_stmt = (
        select(Message.content, Message.created_at)
        .where(
            Message.user_id == user_id,
            Message.sender_role == SenderRole.user
        )
        .order_by(desc(Message.created_at))
        .limit(20)
    )
    chat_messages_result = await session.execute(chat_messages_stmt)
    chat_messages = chat_messages_result.all()
    
    if chat_messages:
        # Extract key information from messages (summarize, don't list all)
        chat_summary += "Ключевые темы и информация из общения с пользователем:\n\n"
        # Take most recent and important messages
        for content, created_at in chat_messages[:10]:  # Last 10 messages
            if content and len(content.strip()) > 10:  # Skip very short messages
                # Truncate long messages
                content_preview = content[:200] + "..." if len(content) > 200 else content
                chat_summary += f"- {content_preview}\n"
        chat_summary += "\n"
    else:
        chat_summary += "Пользователь еще не общался в обычном режиме.\n\n"
    
    # ============================================================
    # 6. BUILD COMPLETE PERSONALIZED PROMPT
    # ============================================================
    # Combine all information: onboarding -> profile -> steps -> gratitudes -> step10 -> chat
    complete_profile = f"{onboarding_summary}\n{profile_summary}\n\n{steps_summary}\n\n{gratitudes_summary}\n\n{step10_summary}\n\n{chat_summary}"
    
    # Add instruction for bot
    instruction = """=== ИНСТРУКЦИЯ ДЛЯ БОТА ===
Используй ВСЮ информацию о пользователе для:
1. Понимания личности пользователя, его фонов, паттернов поведения
2. Построения персонализированных ответов на основе ВСЕХ взаимодействий
3. Цитирования точных ответов когда пользователь спрашивает: "Да, я помню твой ответ: [EXACT ANSWER]"
4. Связывания информации между разными разделами для построения полной картины
5. Адаптации терапевтического подхода под тип человека

ВАЖНО:
- Бот должен адаптироваться и запоминать личность из ВСЕХ взаимодействий, не только из профиля
- Если пользователь просто общается без заполнения профиля - бот все равно запоминает и подстраивается
- Мягко намекай, что заполнение профиля поможет лучше понять пользователя, но НЕ требуй этого
- Используй информацию из обычного общения для построения картины личности

Все ответы и сообщения пользователя важны для построения общей картины его личности и жизненного опыта.
"""
    
    # Build final prompt
    if personalized_prompt:
        # Remove old instruction if exists
        personalized_prompt = re.sub(
            r'=== ИНСТРУКЦИЯ ДЛЯ БОТА.*?===.*?(?=\n\n===|\Z)',
            '',
            personalized_prompt,
            flags=re.DOTALL
        ).strip()
        
        new_prompt_text = f"{personalized_prompt}\n\n{instruction}\n\n{complete_profile}"
    else:
        new_prompt_text = f"{instruction}\n\n{complete_profile}"
    
    # Save to database
    stmt = (
        update(User)
        .where(User.id == user_id)
        .values(personal_prompt=new_prompt_text)
    )
    await session.execute(stmt)
    await session.commit()  # Commit to ensure prompt is saved

