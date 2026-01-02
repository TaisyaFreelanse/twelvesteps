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
    user_repo = UserRepository(session)
    personalized_prompt = await user_repo.get_personalized_prompt(user_id) or ""

    from sqlalchemy import select
    from db.models import User
    user_stmt = select(User).where(User.id == user_id)
    user_result = await session.execute(user_stmt)
    user = user_result.scalar_one_or_none()

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

    profile_summary = "=== ИНФОРМАЦИЯ ИЗ ПРОФИЛЯ ПОЛЬЗОВАТЕЛЯ (ТОЧНЫЕ ОТВЕТЫ) ===\n\n"

    max_version_subq = (
        select(
            ProfileAnswer.question_id,
            func.max(ProfileAnswer.version).label('max_version')
        )
        .where(ProfileAnswer.user_id == user_id)
        .group_by(ProfileAnswer.question_id)
    ).subquery()

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
            desc(ProfileSectionData.is_core_personality),
            desc(ProfileSectionData.importance),
            desc(ProfileSectionData.created_at)
        )
    )
    free_text_data_result = await session.execute(free_text_data_stmt)
    free_text_data = free_text_data_result.all()

    if free_text_data:
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

            for subblock_name, entries in section_info['subblocks'].items():
                entries.sort(key=lambda e: (
                    not e['is_core_personality'],
                    -(e['importance'] or 1.0),
                    -(e['created_at'].timestamp() if e['created_at'] else 0)
                ))

                current_entries = []
                historical_entries = []

                if entries:
                    current_entries = [entries[0]]
                    historical_entries = entries[1:]

                if subblock_name != "general":
                    profile_summary += f"  • {subblock_name}"
                    if entries[0].get('entity_type'):
                        profile_summary += f" ({entries[0]['entity_type']})"
                    profile_summary += ":\n"

                    if current_entries:
                        entry = current_entries[0]
                        content = entry['content']
                        profile_summary += f"    Сейчас: {content}"
                        if entry.get('is_core_personality'):
                            profile_summary += " [ядро личности]"
                        if entry.get('tags'):
                            profile_summary += f" [теги: {entry['tags']}]"
                        profile_summary += "\n"

                    if historical_entries:
                        historical_sorted = sorted(
                            historical_entries[:2],
                            key=lambda e: (not e.get('is_core_personality'), -(e.get('importance') or 1.0))
                        )
                        if len(historical_sorted) == 1:
                            entry = historical_sorted[0]
                            profile_summary += f"    Ранее: {entry['content']}"
                            if entry.get('is_core_personality'):
                                profile_summary += " [ядро личности]"
                            profile_summary += "\n"
                        elif len(historical_sorted) > 1:
                            profile_summary += "    Ранее: "
                            historical_texts = []
                            for entry in historical_sorted:
                                historical_texts.append(entry['content'])
                            profile_summary += ", ".join(historical_texts)
                            if any(e.get('is_core_personality') for e in historical_sorted):
                                profile_summary += " [ядро личности]"
                            profile_summary += "\n"

                        if len(historical_entries) > 2:
                            profile_summary += f"    ... и ещё {len(historical_entries) - 2} исторических записей\n"
                else:
                    for entry in entries[:3]:
                        content = entry['content']
                        profile_summary += f"  - {content}"
                        if entry.get('is_core_personality'):
                            profile_summary += " [ядро личности]"
                        if entry.get('tags'):
                            profile_summary += f" [теги: {entry['tags']}]"
                        profile_summary += "\n"

                    if len(entries) > 3:
                        profile_summary += f"  ... и ещё {len(entries) - 3} записей\n"

    if not profile_answers and not free_text_data:
        profile_summary += "Пользователь еще не заполнил профиль.\n\n"

    steps_summary = "=== ОТВЕТЫ ПО ШАГАМ (РАБОТА ПО ПРОГРАММЕ) ===\n\n"

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

    step10_summary = "=== ЕЖЕДНЕВНЫЙ САМОАНАЛИЗ (ШАГ 10) ===\n\n"

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

    chat_summary = "=== ИНФОРМАЦИЯ ИЗ ОБЫЧНОГО ОБЩЕНИЯ ===\n\n"

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
        chat_summary += "Ключевые темы и информация из общения с пользователем:\n\n"
        for content, created_at in chat_messages[:10]:
            if content and len(content.strip()) > 10:
                content_preview = content[:200] + "..." if len(content) > 200 else content
                chat_summary += f"- {content_preview}\n"
        chat_summary += "\n"
    else:
        chat_summary += "Пользователь еще не общался в обычном режиме.\n\n"

    complete_profile = f"{onboarding_summary}\n{profile_summary}\n\n{steps_summary}\n\n{gratitudes_summary}\n\n{step10_summary}\n\n{chat_summary}"

"""

    if personalized_prompt:
        personalized_prompt = re.sub(
            r'=== ИНСТРУКЦИЯ ДЛЯ БОТА.*?===.*?(?=\n\n===|\Z)',
            '',
            personalized_prompt,
            flags=re.DOTALL
        ).strip()

        new_prompt_text = f"{personalized_prompt}\n\n{instruction}\n\n{complete_profile}"
    else:
        new_prompt_text = f"{instruction}\n\n{complete_profile}"

    stmt = (
        update(User)
        .where(User.id == user_id)
        .values(personal_prompt=new_prompt_text)
    )
    await session.execute(stmt)
    await session.commit()

