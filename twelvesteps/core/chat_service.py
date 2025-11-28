from typing import List, Dict, Any
from datetime import datetime
import json

from sqlalchemy import select, update
from openai import AsyncOpenAI

from api.schemas import ChatResponse, Log
from assistant.assistant import Assistant
from assistant.context import Context
from core.bot import Bot
from db.database import async_session_factory
from db.models import Frame as FrameModel, SenderRole, User
from llm.openai_provider import ClassificationResult, OpenAI
from repositories import MessageRepository, PromptRepository, UserRepository
from repositories.FrameRepository import FrameRepository
from services.vector_store import VectorStoreService
from services.profile import ProfileService

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
        
        # Load active session context (STEPS, DAY, or CHAT)
        from repositories.SessionContextRepository import SessionContextRepository
        from db.models import SessionType
        
        session_context_repo = SessionContextRepository(session)
        active_context = await session_context_repo.get_active_context(user_id)
        
        # Build session context prompt if exists
        session_context_prompt = ""
        if active_context and active_context.context_data:
            context_data = active_context.context_data
            if active_context.session_type == SessionType.STEPS:
                step_number = context_data.get("step_number")
                step_title = context_data.get("step_title", "")
                current_question = context_data.get("current_question", "")
                session_context_prompt = (
                    f"\n\n[Контекст текущей сессии: Работа по шагам]\n"
                    f"Пользователь сейчас работает над шагом {step_number}"
                )
                if step_title:
                    session_context_prompt += f": {step_title}"
                if current_question:
                    session_context_prompt += f"\nТекущий вопрос: {current_question}"
                session_context_prompt += "\nУчитывай этот контекст при ответе."
            elif active_context.session_type == SessionType.DAY:
                day_context = context_data.get("day_context", "")
                session_context_prompt = (
                    f"\n\n[Контекст текущей сессии: Анализ дня]\n"
                    f"{day_context}\n"
                    f"Учитывай этот контекст при ответе."
                )
            elif active_context.session_type == SessionType.CHAT:
                chat_context = context_data.get("chat_context", "")
                if chat_context:
                    session_context_prompt = (
                        f"\n\n[Контекст текущей сессии: Чат]\n"
                        f"{chat_context}\n"
                        f"Учитывай этот контекст при ответе."
                    )

    # 2. Классификация (Existing logic)
    provider = OpenAI()
    parts = await provider.classify(message)
    blocks_in_message = _extract_blocks_from_parts(parts)
    
    async with async_session_factory() as session:
        frame_repo = FrameRepository(session)
        vector_store = VectorStoreService()
        openai_client = AsyncOpenAI()
        
        if parts and getattr(parts, "parts", None):
            for part in parts.parts:
                block_titles = getattr(part, "blocks", []) or []
                if not block_titles:
                    continue
                
                # Save frame to database
                frame = await frame_repo.add_frame(
                    content=part.part,
                    emotion=part.emotion,
                    weight=part.importance,
                    user_id=user_id,
                    block_titles=block_titles,
                    thinking_frame=getattr(part, "thinking_frame", None),
                    level_of_mind=getattr(part, "level_of_mind", None),
                    memory_type=getattr(part, "memory_type", None),
                    target_block=getattr(part, "target_block", None),
                    action=getattr(part, "action", None),
                    strategy_hint=getattr(part, "strategy_hint", None),
                )
                
                # Create embedding and save to vector store
                try:
                    embedding_response = await openai_client.embeddings.create(
                        model="text-embedding-3-small",
                        input=part.part
                    )
                    embedding = embedding_response.data[0].embedding
                    
                    # Save to vector store (synchronous operation)
                    vector_store.add_frame_embedding(
                        frame_id=frame.id,
                        content=part.part,
                        embedding=embedding,
                        metadata={
                            "user_id": user_id,
                            "emotion": part.emotion,
                            "blocks": ",".join(block_titles),
                            "thinking_frame": getattr(part, "thinking_frame", "") or "",
                            "memory_type": getattr(part, "memory_type", "") or "",
                        }
                    )
                except Exception as e:
                    # Log error but don't fail the request
                    if debug:
                        print(f"[handle_chat] Error creating embedding for frame {frame.id}: {e}")

        # Get frames by blocks (existing method)
        block_based_frames = await frame_repo.get_relevant_frames(
            user_id=user_id,
            block_titles=blocks_in_message,
            limit=5,
        )
        
        # Semantic search for frames and GPT-SELF core
        semantic_frames = []
        core_context = ""
        try:
            # Create embedding for the message
            embedding_response = await openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=message
            )
            query_embedding = embedding_response.data[0].embedding
            
            # Search in frames (synchronous call)
            semantic_results = vector_store.search_frames(
                query_embedding=query_embedding,
                user_id=user_id,
                limit=5
            )
            
            # Get frame IDs from results
            if semantic_results.get("ids") and len(semantic_results["ids"][0]) > 0:
                semantic_frame_ids = [int(frame_id) for frame_id in semantic_results["ids"][0]]
                semantic_frames = await frame_repo.get_frames_by_ids(semantic_frame_ids)
            
            # Search GPT-SELF core for relevant strategies (synchronous call)
            if vector_store.get_core_count() > 0:
                core_results = vector_store.search_core(
                    query_embedding=query_embedding,
                    limit=3
                )
                
                # Build core context from results
                if core_results.get("documents") and len(core_results["documents"][0]) > 0:
                    core_chunks = core_results["documents"][0]
                    core_context = "\n\n[Контекст из ядра GPT-SELF]:\n" + "\n---\n".join(core_chunks)
                    if debug:
                        print(f"[handle_chat] Found {len(core_chunks)} relevant core chunks")
                        
        except Exception as e:
            # Log error but don't fail the request
            if debug:
                print(f"[handle_chat] Error in semantic search: {e}")
        
        # Combine and deduplicate frames
        all_frame_ids = set()
        relevant_frames = []
        
        # Add block-based frames
        for frame in block_based_frames:
            if frame.id not in all_frame_ids:
                relevant_frames.append(frame)
                all_frame_ids.add(frame.id)
        
        # Add semantic frames (avoid duplicates)
        for frame in semantic_frames:
            if frame.id not in all_frame_ids:
                relevant_frames.append(frame)
                all_frame_ids.add(frame.id)
        
        # Sort by weight and limit
        relevant_frames.sort(key=lambda f: f.weight or 0, reverse=True)
        relevant_frames = relevant_frames[:5]
        
        await session.commit()

    # 3. Подготовка промптов (Existing logic)
    system_prompt = await PromptRepository.load_system_prompt()
    helper_prompt = _build_helper_prompt(relevant_frames)
    
    # Add GPT-SELF core context if available
    if 'core_context' in locals() and core_context:
        helper_prompt = f"{helper_prompt}\n{core_context}" if helper_prompt else core_context

    # 4. Загрузка истории (Existing logic)
    async with async_session_factory() as session:
        msg_repo = MessageRepository(session)
        last_messages = await msg_repo.get_last_messages(user_id)

    # Create Assistant and Context objects
    # Append session context to personalized prompt if exists
    full_personalized_prompt = personalized_prompt
    if 'session_context_prompt' in locals() and session_context_prompt:
        full_personalized_prompt = f"{personalized_prompt}\n{session_context_prompt}"
    
    assistant = Assistant(system_prompt, full_personalized_prompt, helper_prompt)
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
    
    # IMPORTANT: Always update personalized prompt with ALL answers (onboarding + profile + steps)
    # This ensures the bot has a complete picture of the user from ALL their answers
    async with async_session_factory() as session:
        from services.personalization_service import update_personalized_prompt_from_all_answers
        await update_personalized_prompt_from_all_answers(session, user_id)

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


async def handle_thanks(telegram_id: int | str, debug: bool) -> str:
    """
    Handle /thanks command - express support, motivation, and gratitude.
    Different from /day - focuses on support rather than analysis.
    """
    telegram_id_value = str(telegram_id)
    
    # 1. Найти или создать пользователя
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.find_or_create_user_by_telegram_id(telegram_id=telegram_id_value)
        if not user:
            raise RuntimeError(f"Unable to locate or create user with telegram_id={telegram_id}")

        user_id = user.id
        personalized_prompt = await user_repo.get_personalized_prompt(user_id) or ""
        
        # Check last command to avoid duplication
        from repositories.SessionContextRepository import SessionContextRepository
        from db.models import SessionType
        
        session_context_repo = SessionContextRepository(session)
        last_context = await session_context_repo.get_active_context(user_id, SessionType.CHAT)
        
        # Check if last command was /thanks (avoid duplicate responses)
        if last_context and last_context.context_data:
            last_command = last_context.context_data.get("last_command")
            if last_command == "/thanks":
                # Return a variation to avoid exact duplication
                variation_prompts = [
                    "Спасибо, что делишься благодарностью! Это важная часть выздоровления.",
                    "Твоя благодарность вдохновляет! Продолжай в том же духе.",
                    "Рад слышать о твоей благодарности. Это показывает твой рост."
                ]
                import random
                return ChatResponse(reply=random.choice(variation_prompts), log=None)
        
        # Save current command in context
        await session_context_repo.create_or_update_context(
            user_id,
            SessionType.CHAT,
            {"last_command": "/thanks", "command_timestamp": datetime.utcnow().isoformat()}
        )
        await session.commit()

    # 2. Load thanks-specific prompt
    thanks_prompt_json = await PromptRepository.load_thanks_prompt()
    thanks_prompt_data = json.loads(thanks_prompt_json)
    thanks_system_prompt = thanks_prompt_data.get("content", "")

    # 3. Get relevant frames for context
    async with async_session_factory() as session:
        frame_repo = FrameRepository(session)
        relevant_frames = await frame_repo.get_relevant_frames(
            user_id=user_id,
            block_titles=[],
            limit=3,
        )
        await session.commit()

    # 4. Prepare prompts
    helper_prompt = _build_helper_prompt(relevant_frames)
    
    # 5. Load message history
    async with async_session_factory() as session:
        msg_repo = MessageRepository(session)
        last_messages = await msg_repo.get_last_messages(user_id, amount=5)

    # 6. Create Assistant and Context
    assistant = Assistant(thanks_system_prompt, personalized_prompt, helper_prompt)
    context = Context("", last_messages, assistant)  # Empty message for /thanks
    context.relevant_frames = relevant_frames

    # 7. Generate response
    provider = OpenAI()
    bot = Bot(provider)
    response = await bot.chat(context)

    # 8. Save messages
    async with async_session_factory() as session:
        msg_repo = MessageRepository(session)
        try:
            await msg_repo.add_message("/thanks", SenderRole.user, user_id)
            await msg_repo.add_message(response.message, SenderRole.assistant, user_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    log = Log(
        classification_result="Command: /thanks",
        blocks_used=str(f"использованные блоки: {helper_prompt}"),
        plan=response.plan,
        prompt_changes=None
    )

    return ChatResponse(reply=response.message, log=log)


async def handle_day(telegram_id: int | str, debug: bool) -> str:
    """
    Handle /day command - analyze current state, ask questions, provide reflection.
    Different from /thanks - focuses on analysis rather than support.
    
    IMPORTANT: Closes any active step Tail and switches session context to DAY
    to prevent /day from being treated as a step answer.
    """
    telegram_id_value = str(telegram_id)
    
    # 1. Найти или создать пользователя
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.find_or_create_user_by_telegram_id(telegram_id=telegram_id_value)
        if not user:
            raise RuntimeError(f"Unable to locate or create user with telegram_id={telegram_id}")

        user_id = user.id
        personalized_prompt = await user_repo.get_personalized_prompt(user_id) or ""
        
        # CRITICAL: Close any active step Tail to prevent /day from being saved as step answer
        from db.models import Tail, TailType
        from sqlalchemy import select
        from datetime import datetime
        
        active_tail_stmt = select(Tail).where(
            Tail.user_id == user_id,
            Tail.tail_type == TailType.STEP_QUESTION,
            Tail.is_closed == False
        )
        tail_result = await session.execute(active_tail_stmt)
        active_tail = tail_result.scalars().first()
        
        if active_tail:
            active_tail.is_closed = True
            active_tail.closed_at = datetime.utcnow()
            if debug:
                print(f"[handle_day] Closed active Tail {active_tail.id} for user {user_id}")
        
        # Switch session context to DAY
        from repositories.SessionContextRepository import SessionContextRepository
        from db.models import SessionType
        
        session_context_repo = SessionContextRepository(session)
        
        # Check last command to avoid duplication
        last_context = await session_context_repo.get_active_context(user_id, SessionType.CHAT)
        
        # Check if last command was /day (avoid duplicate responses)
        if last_context and last_context.context_data:
            last_command = last_context.context_data.get("last_command")
            if last_command == "/day":
                # Return a variation to avoid exact duplication
                variation_prompts = [
                    "Как дела сегодня? Что нового происходит в твоей жизни?",
                    "Расскажи, как проходит твой день. Что ты чувствуешь?",
                    "Давай поговорим о твоем текущем состоянии. Что на душе?"
                ]
                import random
                await session.commit()
                return ChatResponse(reply=random.choice(variation_prompts), log=None)
        
        # Switch to DAY context (this overrides any STEPS context)
        await session_context_repo.create_or_update_context(
            user_id,
            SessionType.DAY,
            {
                "last_command": "/day",
                "command_timestamp": datetime.utcnow().isoformat(),
                "day_context": "Пользователь использует команду /day для анализа текущего состояния"
            }
        )
        await session.commit()

    # 2. Load day-specific prompt
    day_prompt_json = await PromptRepository.load_day_prompt()
    day_prompt_data = json.loads(day_prompt_json)
    day_system_prompt = day_prompt_data.get("content", "")

    # 3. Get relevant frames for context
    async with async_session_factory() as session:
        frame_repo = FrameRepository(session)
        relevant_frames = await frame_repo.get_relevant_frames(
            user_id=user_id,
            block_titles=[],
            limit=5,
        )
        await session.commit()

    # 4. Prepare prompts
    helper_prompt = _build_helper_prompt(relevant_frames)
    
    # 5. Load message history
    async with async_session_factory() as session:
        msg_repo = MessageRepository(session)
        last_messages = await msg_repo.get_last_messages(user_id, amount=5)

    # 6. Create Assistant and Context
    assistant = Assistant(day_system_prompt, personalized_prompt, helper_prompt)
    context = Context("", last_messages, assistant)  # Empty message for /day
    context.relevant_frames = relevant_frames

    # 7. Generate response
    provider = OpenAI()
    bot = Bot(provider)
    response = await bot.chat(context)

    # 8. Save messages
    async with async_session_factory() as session:
        msg_repo = MessageRepository(session)
        try:
            await msg_repo.add_message("/day", SenderRole.user, user_id)
            await msg_repo.add_message(response.message, SenderRole.assistant, user_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    log = Log(
        classification_result="Command: /day",
        blocks_used=str(f"использованные блоки: {helper_prompt}"),
        plan=response.plan,
        prompt_changes=None
    )

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


async def process_profile_free_text(
    user_id: int,
    free_text: str,
    debug: bool = False
) -> Dict[str, Any]:
    """
    Process free text profile story and distribute information across profile sections.
    Uses analyze_profile to extract information and then distributes it to appropriate sections.
    
    Args:
        user_id: User ID
        free_text: Free text story from user
        debug: Debug mode flag
        
    Returns:
        Dict with status and information about processed sections
    """
    async with async_session_factory() as session:
        # 1. Get user and personalized prompt
        user_repo = UserRepository(session)
        # Get user by ID using select
        from sqlalchemy import select
        from db.models import User
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise RuntimeError(f"User not found with id={user_id}")
        
        personalized_prompt = await user_repo.get_personalized_prompt(user_id) or ""
        
        # 2. Get all profile sections
        profile_service = ProfileService(session)
        sections = await profile_service.get_all_sections(user_id)
        
        if not sections:
            return {
                "status": "error",
                "message": "No profile sections found"
            }
        
        # 3. Create context for analyze_profile
        system_prompt = await PromptRepository.load_system_prompt()
        assistant = Assistant(system_prompt, personalized_prompt, "")
        context = Context(free_text, [], assistant)
        
        # 4. Use analyze_profile to extract information
        provider = OpenAI()
        analysis_result = await provider.analyze_profile(context)
        
        if not analysis_result.update_needed or not analysis_result.extracted_info:
            return {
                "status": "no_info",
                "message": "No new information extracted from the text"
            }
        
        extracted_info = analysis_result.extracted_info
        
        # 5. Use LLM to distribute information across sections
        # Build section list for LLM
        section_names = [f"{s.name} (id: {s.id})" for s in sections]
        sections_text = "\n".join(section_names)
        
        distribution_prompt = f"""
You are a Profile Information Distributor.
Analyze the following text and determine which profile sections it belongs to.

Available sections:
{sections_text}

User's free text:
{free_text}

Extracted information:
{extracted_info}

For each relevant section, provide:
- section_id: The ID of the section
- content: The part of the text that belongs to this section

Return a JSON array with objects like:
[
    {{"section_id": 1, "content": "relevant text for section 1"}},
    {{"section_id": 3, "content": "relevant text for section 3"}}
]

If no sections are relevant, return an empty array [].
"""
        
        # Call LLM to distribute information
        import json
        from openai import AsyncOpenAI
        
        config = await provider.load_config("./llm/configs/openai_dynamic.json")
        
        async with AsyncOpenAI() as client:
            response = await client.chat.completions.create(
                model=config.get("model", "gpt-4o"),
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that distributes profile information to appropriate sections. Always return valid JSON."},
                    {"role": "user", "content": distribution_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=1000,
            )
            
            try:
                raw = response.choices[0].message.content
                # LLM might return {"sections": [...]} or just [...]
                data = json.loads(raw)
                if isinstance(data, dict) and "sections" in data:
                    distributions = data["sections"]
                elif isinstance(data, list):
                    distributions = data
                elif isinstance(data, dict):
                    # Try to find array in dict
                    for key, value in data.items():
                        if isinstance(value, list):
                            distributions = value
                            break
                    else:
                        distributions = []
                else:
                    distributions = []
            except Exception as e:
                if debug:
                    print(f"[process_profile_free_text] Error parsing distribution: {e} | Raw: {raw}")
                distributions = []
        
        # 6. Save information to sections
        saved_sections = []
        for dist in distributions:
            section_id = dist.get("section_id")
            content = dist.get("content", "")
            
            if not section_id or not content:
                continue
            
            # Verify section exists
            section = await profile_service.get_section_detail(section_id, user_id)
            if not section:
                if debug:
                    print(f"[process_profile_free_text] Section {section_id} not found")
                continue
            
            try:
                # Save to section
                section_data = await profile_service.save_free_text(
                    user_id,
                    section_id,
                    content
                )
                saved_sections.append({
                    "section_id": section_id,
                    "section_name": section.name,
                    "data_id": section_data.id
                })
            except Exception as e:
                if debug:
                    print(f"[process_profile_free_text] Error saving to section {section_id}: {e}")
                continue
        
        await session.commit()
        
        return {
            "status": "success",
            "message": f"Information distributed to {len(saved_sections)} section(s)",
            "saved_sections": saved_sections,
            "extracted_info": extracted_info
        }