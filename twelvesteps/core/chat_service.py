from typing import List

from sqlalchemy import select, update

from api.schemas import ChatResponse, Log
from assistant.assistant import Assistant
from assistant.context import Context
from core.bot import Bot
from db.database import async_session_factory
from db.models import Frame as FrameModel, SenderRole, User
from llm.openai_provider import ClassificationResult, OpenAI
from repositories import MessageRepository, PromptRepository, UserRepository
from repositories.FrameRepository import FrameRepository

# ... [Helper functions: classification_to_string, _extract_blocks_from_parts, _build_helper_prompt remain unchanged] ...
def classification_to_string(result: ClassificationResult) -> str:
    lines = []
    for idx, part in enumerate(result.parts, 1):
        blocks = ", ".join(part.blocks) if part.blocks else "нет блоков"
        lines.append(f"{idx}. '{part.part}' | Эмоция: {part.emotion} | Важность: {part.importance} | Блоки: {blocks}")
    return "\n".join(lines)

def _extract_blocks_from_parts(parts) -> List[str]:
    blocks: list[str] = []
    if not parts or not getattr(parts, "parts", None):
        return blocks

    for part in parts.parts:
        for block in getattr(part, "blocks", []) or []:
            if block and block not in blocks:
                blocks.append(block)
    return blocks

def _build_helper_prompt(frames: List[FrameModel]) -> str:
    if not frames:
        return ""

    lines: list[str] = [
        "Контекст: важные события и состояния пользователя, которые стоит учитывать при ответе:"
    ]
    for frame in frames:
        if not frame.content:
            continue
        emotion = frame.emotion or "эмоция не указана"
        weight = int(frame.weight or 0)
        lines.append(f"- ({emotion}, важность {weight}) {frame.content}")
    return "\n".join(lines)


async def handle_chat(telegram_id: int | str, message: str, debug: bool) -> str:
    telegram_id_value = str(telegram_id)
    
    # 1. Найти или создать пользователя и получить текущий промпт
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.find_or_create_user_by_telegram_id(telegram_id=telegram_id_value)
        if not user:
            raise RuntimeError(f"Unable to locate or create user with telegram_id={telegram_id}")

        user_id = user.id
        # Load the current personalized prompt
        personalized_prompt = await user_repo.get_personalized_prompt(user_id) or ""

    # 2. Классификация (Existing logic)
    provider = OpenAI()
    parts = await provider.classify(message)
    blocks_in_message = _extract_blocks_from_parts(parts)
    
    async with async_session_factory() as session:
        frame_repo = FrameRepository(session)
        if parts and getattr(parts, "parts", None):
            for part in parts.parts:
                block_titles = getattr(part, "blocks", []) or []
                if not block_titles:
                    continue
                await frame_repo.add_frame(
                    content=part.part,
                    emotion=part.emotion,
                    weight=part.importance,
                    user_id=user_id,
                    block_titles=block_titles,
                )

        relevant_frames = await frame_repo.get_relevant_frames(
            user_id=user_id,
            block_titles=blocks_in_message,
            limit=5,
        )
        await session.commit()

    # 3. Подготовка промптов (Existing logic)
    system_prompt = await PromptRepository.load_system_prompt()
    helper_prompt = _build_helper_prompt(relevant_frames)

    # 4. Загрузка истории (Existing logic)
    async with async_session_factory() as session:
        msg_repo = MessageRepository(session)
        last_messages = await msg_repo.get_last_messages(user_id)

    # Create Assistant and Context objects
    assistant = Assistant(system_prompt, personalized_prompt, helper_prompt)
    context = Context(message, last_messages, assistant)
    context.relevant_frames = relevant_frames
    
    # ==================================================================================
    # 5. NEW: PERSONALIZATION ANALYZER & UPDATE LOGIC
    # ==================================================================================
    
    # Run the analyzer to see if the profile needs updating
    analysis_result = await provider.analyze_profile(context)
    log_update_info = "Update needed: False"
    
    if analysis_result.update_needed:
        # Rewrite the prompt with new info
        new_prompt_text = await provider.update_personalized_prompt(context, analysis_result.extracted_info)
        
        log_update_info = f"Update needed: True. Info: {analysis_result.extracted_info}"
        
        # A. Update the Context immediately so the Bot uses the new profile NOW
        context.assistant.personalized_prompt = new_prompt_text
        
        # B. Update the Database so it is remembered for next time
        async with async_session_factory() as session:
            # Direct SQLAlchemy update since we have the user_id
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(personal_prompt=new_prompt_text)
            )
            await session.execute(stmt)
            await session.commit()
            
            if debug:
                print(f"[Profile Updated] ID: {user_id} | New Info: {analysis_result.extracted_info}")

    # ==================================================================================
    
    # 6. Получить ответ бота (Using potentially updated context)
    bot = Bot(provider)
    response = await bot.chat(context)

    log = Log(
        classification_result=classification_to_string(parts),
        blocks_used=str(f"использованые блоки: {blocks_in_message}\n{helper_prompt}\n---\n{log_update_info}"),
        plan=response.plan,
        prompt_changes=None
    )

    if analysis_result.update_needed:
        log.prompt_changes = str(analysis_result)

    # 7. Сохранить сообщения (Existing logic)
    async with async_session_factory() as session:
        msg_repo = MessageRepository(session)
        try:
            await msg_repo.add_message(message, SenderRole.user, user_id)
            await msg_repo.add_message(response.message, SenderRole.assistant, user_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return ChatResponse(reply=response.message, log=log)

from sqlalchemy.orm import selectinload
# Ensure these imports are present
from db.models import Tail, TailType, SenderRole

async def handle_sos(telegram_id: int | str) -> str:
    telegram_id_value = str(telegram_id)

    async with async_session_factory() as session:
        # 1. Find User and Personalization
        user_repo = UserRepository(session)
        user = await user_repo.find_or_create_user_by_telegram_id(telegram_id=telegram_id_value)
        
        if not user:
            raise RuntimeError(f"User not found for telegram_id={telegram_id}")
            
        user_id = user.id
        personalized_prompt = await user_repo.get_personalized_prompt(user_id) or "Нет персонализации."

        # 2. Determine the Question
        # Priority 1: Check if there is an active "Step Question" in the Tail
        stmt = select(Tail).options(selectinload(Tail.question)).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        )
        result = await session.execute(stmt)
        active_tail = result.scalars().first()

        question_text = "Вопрос не найден."

        if active_tail and active_tail.question:
            question_text = active_tail.question.text

        # 3. Load SOS System Prompt
        sos_system_prompt = await PromptRepository.load_sos_prompt()

    # 4. Call Provider to generate example
    provider = OpenAI()
    
    answer = await provider.generate_sos_response(
        system_prompt=sos_system_prompt,
        question=question_text,
        personalization=personalized_prompt
    )

    return answer