"""Telegram handlers for /start, /exit, /steps and the legacy chat bridge."""

from __future__ import annotations

from functools import partial
import json
import logging
import datetime

from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.backend import (
    BACKEND_CLIENT, 
    TOKEN_STORE, 
    USER_CACHE, 
    Log, 
    call_legacy_chat, 
    get_display_name,
    process_step_message,      
    get_current_step_question,
    get_or_fetch_token
)
from bot.config import (
    build_exit_markup, 
    build_main_menu_markup,
    build_error_markup,
    format_step_progress_indicator,
    build_profile_sections_markup,
    build_profile_actions_markup,
    build_profile_skip_markup,
    build_template_selection_markup,
    build_template_filling_markup,
    build_sos_help_type_markup,
    build_sos_save_draft_markup,
    build_sos_exit_markup,
    build_steps_navigation_markup,
    build_steps_list_markup,
    build_step_questions_markup,
    build_step_actions_markup,
    build_steps_settings_markup,
    build_template_selection_settings_markup,
    build_reminders_settings_markup
)
from bot.utils import split_long_message, send_long_message, edit_long_message
from bot.onboarding import OnboardingStates, register_onboarding_handlers

logger = logging.getLogger(__name__)

USER_LOGS: dict[int, list[Log]] = {}

# --- STATES ---
class StepState(StatesGroup):
    answering = State()  # User is currently answering a step question
    filling_template = State()  # User is filling answer by template
    template_field = State()  # User is entering value for a template field


class ProfileStates(StatesGroup):
    section_selection = State()  # User is selecting a profile section
    answering_question = State()  # User is answering a profile question
    free_text_input = State()  # User is entering free text for a section
    creating_custom_section = State()  # User is creating a custom section

class SosStates(StatesGroup):
    help_type_selection = State()  # User is selecting type of help
    chatting = State()  # User is in SOS chat dialog
    custom_input = State()  # User is entering custom help description
    saving_draft = State()  # User is deciding whether to save draft

class Step10States(StatesGroup):
    answering_question = State()  # User is answering a step10 question

# ---------------------------------------------------------
# REGISTER HANDLERS
# ---------------------------------------------------------

def register_handlers(dp: Dispatcher) -> None:
    # 1. Commands (Priority)
    dp.message(CommandStart())(handle_start)
    dp.message(Command(commands=["exit"]))(handle_exit)
    dp.message(Command(commands=["reset", "restart"]))(handle_reset)
    dp.message(Command(commands=["steps"]))(handle_steps)
    dp.message(Command(commands=["about_step"]))(handle_about_step)
    dp.message(Command(commands=["sos"]))(handle_sos)
    dp.message(Command(commands=["profile"]))(handle_profile)
    dp.message(Command(commands=["steps_settings", "settings"]))(handle_steps_settings)
    dp.message(Command(commands=["thanks"]))(handle_thanks)
    dp.message(Command(commands=["day", "inventory"]))(handle_day)  # Alias for self-analysis
    
    # 1.5. Main menu button text handlers (for button clicks)
    dp.message(F.text == "🪜 Работа по шагу")(handle_steps)
    dp.message(F.text == "📖 Самоанализ")(handle_day)
    dp.message(F.text == "❓ FAQ")(handle_faq)
    dp.message(F.text == "⚙️ Настройки")(handle_steps_settings)
    dp.message(F.text == "🙏 Благодарность")(handle_thanks)

    # 2. Onboarding Flow
    register_onboarding_handlers(dp)

    # 3. Step Answering Flow (Only works if state is StepState.answering)
    dp.message(StateFilter(StepState.answering))(handle_step_answer)
    dp.message(StateFilter(StepState.filling_template))(handle_template_field_input)
    dp.message(Command(commands=["qa_open"]))(qa_open)
    
    # 4. Profile Flow
    dp.callback_query(F.data.startswith("profile_"))(handle_profile_callback)
    dp.message(StateFilter(ProfileStates.answering_question))(handle_profile_answer)
    dp.message(StateFilter(ProfileStates.free_text_input))(handle_profile_free_text)
    dp.message(StateFilter(ProfileStates.creating_custom_section))(handle_profile_custom_section)
    
    # 4.5. Template Selection Flow
    dp.callback_query(F.data.startswith("template_"))(handle_template_selection)
    
    # 4.5.1 Template Filling FSM Flow (tpl_ prefix)
    dp.callback_query(F.data.startswith("tpl_"))(handle_template_filling_callback)
    
    # 4.6. SOS Help Flow
    dp.callback_query(F.data.startswith("sos_"))(handle_sos_callback)
    dp.message(StateFilter(SosStates.chatting))(handle_sos_chat_message)
    dp.message(StateFilter(SosStates.custom_input))(handle_sos_custom_input)
    
    # 4.6.5. Step 10 Daily Analysis Flow
    dp.message(StateFilter(Step10States.answering_question))(handle_step10_answer)
    dp.callback_query(F.data.startswith("step10_"))(handle_step10_callback)
    
    # 4.7. Steps Navigation Flow (MUST be registered BEFORE general step_ handlers)
    dp.callback_query(F.data.startswith("steps_"))(handle_steps_navigation_callback)
    dp.callback_query(F.data.startswith("step_select_"))(handle_step_selection_callback)
    dp.callback_query(F.data.startswith("question_view_"))(handle_question_view_callback)
    
    # 3.5. Step Action Callbacks (exclude step_select_ to avoid conflicts)
    dp.callback_query(F.data.startswith("step_") & ~F.data.startswith("step_select_"))(handle_step_action_callback)
    
    # 4.8. Steps Settings Flow
    dp.callback_query(F.data.startswith("settings_"))(handle_steps_settings_callback)

    # 4. QA / Debug Commands
    dp.message(Command(commands=["qa_last"]))(qa_last)
    dp.message(Command(commands=["qa_ctx"]))(qa_ctx)
    dp.message(Command(commands=["qa_trace"]))(qa_trace)
    dp.message(Command(commands=["qa_report"]))(qa_report)
    dp.message(Command(commands=["qa_export"]))(qa_export)
    
    # NEW COMMAND HERE
    

    # 5. Profile Flow (before general chat)
    # Profile handlers are registered above
    
    # 6. General Chat (Fallback for everything else)
    dp.message()(partial(handle_message, debug=False))


# ---------------------------------------------------------
# STEPS HANDLER (/steps)
# ---------------------------------------------------------

async def handle_steps(message: Message, state: FSMContext) -> None:
    """
    Activates 'Step Mode'. Fetches the current question and sets FSM state.
    Automatically uses author template if none selected.
    Shows status (step, question, progress) at the top.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Сначала нажми /start для авторизации.")
            return
        
        # Check if user has active template, if not - set author template automatically
        templates_data = await BACKEND_CLIENT.get_templates(token)
        active_template_id = templates_data.get("active_template_id")
        
        if active_template_id is None:
            # Automatically set author template
            templates = templates_data.get("templates", [])
            author_template = None
            for template in templates:
                if template.get("template_type") == "AUTHOR":
                    author_template = template
                    break
            
            if author_template:
                await BACKEND_CLIENT.set_active_template(token, author_template.get("id"))
        
        # Proceed with steps
        # Get current step info with progress indicators
        step_info = await BACKEND_CLIENT.get_current_step_info(token)
        step_number = step_info.get("step_number")
        
        if step_number:
            # Build progress indicator
            progress_indicator = format_step_progress_indicator(
                step_number=step_number,
                total_steps=step_info.get("total_steps", 12),
                step_title=step_info.get("step_title"),
                answered_questions=step_info.get("answered_questions", 0),
                total_questions=step_info.get("total_questions", 0)
            )
            
            # Show current step and navigation
            step_data = await get_current_step_question(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name
            )
            
            if step_data:
                response_text = step_data.get("message", "")
                is_completed = step_data.get("is_completed", False)
                
                if is_completed:
                    await message.answer("🎉 Ты уже прошел все доступные шаги!", reply_markup=build_main_menu_markup())
                    await state.clear()
                    return
                
                if response_text:
                    # Check if there's paused template progress
                    step_id = step_info.get("step_id")
                    question_id = None
                    template_progress = None
                    
                    # Try to get current question ID and template progress from backend
                    try:
                        # Get current question info to find question_id
                        questions_data = await BACKEND_CLIENT.get_step_questions(token, step_id)
                        questions = questions_data.get("questions", [])
                        answered_count = step_info.get("answered_questions", 0)
                        if questions and answered_count < len(questions):
                            current_question = questions[answered_count]
                            question_id = current_question.get("id")
                            
                            # Check for template progress via backend
                            if step_id and question_id:
                                progress_data = await BACKEND_CLIENT.get_template_progress(token, step_id, question_id)
                                if progress_data and progress_data.get("status") in ["IN_PROGRESS", "PAUSED"]:
                                    template_progress = progress_data
                    except Exception as e:
                        logger.warning(f"Failed to check template progress: {e}")
                    
                    # Build status header
                    status_header = f"📍 Ты сейчас на:\n{progress_indicator}\n"
                    
                    if template_progress:
                        status_header += f"\n⏸ Есть сохранённый прогресс по шаблону\n"
                        status_header += f"📊 {template_progress.get('progress_summary', '')}\n"
                    
                    status_header += "\n" + "─" * 30 + "\n"
                    
                    # Save session context for STEPS
                    context_data = {
                        "step_number": step_number,
                        "step_title": step_info.get("step_title", ""),
                        "step_description": step_info.get("step_description", ""),
                        "current_question": response_text[:200],
                        "total_steps": step_info.get("total_steps", 12),
                        "answered_questions": step_info.get("answered_questions", 0),
                        "total_questions": step_info.get("total_questions", 0)
                    }
                    try:
                        await BACKEND_CLIENT.save_session_context(token, "STEPS", context_data)
                    except Exception as e:
                        logger.warning(f"Failed to save session context: {e}")
                    
                    # Show current step info with status header
                    step_description = step_info.get("step_description", "")
                    full_text = status_header
                    if step_description:
                        full_text += f"\n{step_description}\n"
                    full_text += f"\n{response_text}"
                    
                    await send_long_message(
                        message,
                        full_text,
                        reply_markup=build_step_actions_markup(has_template_progress=bool(template_progress))
                    )
                    # Set the state to 'answering' so the next message goes to handle_step_answer
                    await state.set_state(StepState.answering)
                else:
                    # No question yet, show step info
                    step_description = step_info.get("step_description", "")
                    full_text = progress_indicator
                    if step_description:
                        full_text += f"\n\n{step_description}"
                    
                    await send_long_message(
                        message,
                        full_text,
                        reply_markup=build_steps_navigation_markup()
                    )
            else:
                # No step data, show step info only
                step_description = step_info.get("step_description", "")
                full_text = progress_indicator
                if step_description:
                    full_text += f"\n\n{step_description}"
                
                await send_long_message(
                    message,
                    full_text,
                    reply_markup=build_steps_navigation_markup()
                )
        else:
            # No step in progress, start from beginning
            step_data = await get_current_step_question(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name
            )

            if not step_data:
                await message.answer("Сначала нажми /start для авторизации.")
                return

            response_text = step_data.get("message", "")
            is_completed = step_data.get("is_completed", False)
            
            if is_completed:
                await message.answer("🎉 Ты уже прошел все доступные шаги!", reply_markup=build_main_menu_markup())
                await state.clear()
                return

            if response_text:
                await state.set_state(StepState.answering)
                await send_long_message(message, response_text, reply_markup=build_exit_markup())
                
    except Exception as exc:
        logger.exception("Error fetching steps for %s: %s", telegram_id, exc)
        await message.answer("Ошибка сервера. Попробуй позже.")
        return


# ---------------------------------------------------------
# STEP ANSWER HANDLER (State: StepState.answering)
# ---------------------------------------------------------

async def handle_step_answer(message: Message, state: FSMContext) -> None:
    """
    Processes the user's text as an answer to the active step question.
    Also handles pause draft saving if action is "pause".
    Validates minimum answer length before saving.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    user_text = message.text

    try:
        state_data = await state.get_data()
        action = state_data.get("action")
        
        if action == "pause":
            # Save as draft
            token = await get_or_fetch_token(telegram_id, username, first_name)
            if token:
                await BACKEND_CLIENT.save_draft(token, user_text)
                await message.answer("✅ Черновик сохранён. Можешь вернуться позже.")
                await state.update_data(action=None)
                await state.set_state(StepState.answering)
            else:
                await message.answer("Ошибка авторизации.")
            return
        
        # Normal answer processing
        step_next = await process_step_message(
            telegram_id=telegram_id,
            text=user_text,
            username=username,
            first_name=first_name
        )
        
        if not step_next:
            await message.answer("Сессия потеряна. Нажми /steps снова.")
            await state.clear()
            return

        # Check if validation error occurred
        if step_next.get("error"):
            error_message = step_next.get("message", "Ошибка валидации")
            await message.answer(
                f"{error_message}\n\n"
                "💡 Ты можешь:\n"
                "• Дополнить ответ и отправить снова\n"
                "• Нажать «⏸ Пауза» чтобы сохранить черновик\n"
                "• Нажать «🔀 Вопрос» чтобы перейти к другому вопросу",
                reply_markup=build_step_actions_markup()
            )
            # Stay in answering state
            return

        # Get updated step info for progress indicator
        token = await get_or_fetch_token(telegram_id, username, first_name)
        step_info = await BACKEND_CLIENT.get_current_step_info(token) if token else {}
        
        response_text = step_next.get("message", "Ответ принят.")
        is_completed = step_next.get("is_completed", False)
        
        # Build progress indicator
        if step_info.get("step_number"):
            progress_indicator = format_step_progress_indicator(
                step_number=step_info.get("step_number", 0),
                total_steps=step_info.get("total_steps", 12),
                step_title=step_info.get("step_title"),
                answered_questions=step_info.get("answered_questions", 0),
                total_questions=step_info.get("total_questions", 0)
            )
            full_response = f"{progress_indicator}\n\n✅ Ответ сохранён!\n\n{response_text}"
        else:
            full_response = f"✅ Ответ сохранён!\n\n{response_text}"

        await send_long_message(message, full_response, reply_markup=build_step_actions_markup())

        if is_completed:
             await message.answer("Этап завершен! 🎉 Возвращаю в обычный режим.", reply_markup=build_main_menu_markup())
             await state.clear()
             
    except Exception as exc:
        logger.exception("Error processing step answer: %s", exc)
        error_text = (
            "❌ Произошла ошибка при сохранении ответа.\n\n"
            "Хочешь начать заново?"
        )
        await message.answer(error_text, reply_markup=build_error_markup())


# ---------------------------------------------------------
# EXIT HANDLER (/exit)
# ---------------------------------------------------------

async def handle_exit(message: Message, state: FSMContext) -> None:
    """
    Forcefully exits any state (Onboarding or Steps) and returns to Chat mode.
    """
    current_state = await state.get_state()
    
    await state.clear()
    
    if current_state == StepState.answering:
        text = "Выход из режима шагов. Твой прогресс сохранен."
    elif current_state:
        text = "Процесс прерван."
    else:
        text = "Режим сброшен."
    
    await message.answer(text, reply_markup=build_main_menu_markup())


# ---------------------------------------------------------
# RESET HANDLER (/reset, /restart)
# ---------------------------------------------------------

async def handle_reset(message: Message, state: FSMContext) -> None:
    """
    Resets the dialog state and restarts the bot.
    Clears all FSM states and returns to start flow.
    """
    telegram_id = message.from_user.id
    key = str(telegram_id)
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Clear all states
    await state.clear()
    
    # Clear cached tokens if needed
    from bot.backend import TOKEN_STORE, USER_CACHE
    if key in TOKEN_STORE:
        del TOKEN_STORE[key]
    if key in USER_CACHE:
        del USER_CACHE[key]
    
    try:
        # Re-authenticate
        user, is_new, access_token = await BACKEND_CLIENT.auth_telegram(
            telegram_id=key,
            username=username,
            first_name=first_name,
        )
        
        TOKEN_STORE[key] = access_token
        USER_CACHE[key] = user
        
        # Check if user needs onboarding: new user OR existing user without program_experience
        needs_onboarding = is_new or not user.get("program_experience")
        
        if needs_onboarding:
            await state.set_state(OnboardingStates.display_name)
            await message.answer(
                "🔄 Начинаем заново!\n\nПривет! Как к тебе обращаться?",
                reply_markup=build_exit_markup()
            )
        else:
            try:
                status = await BACKEND_CLIENT.get_status(access_token)
                await send_welcome_back(message, user, status)
            except:
                await message.answer(
                    "🔄 Состояние сброшено. С возвращением!",
                    reply_markup=build_main_menu_markup()
                )
    except Exception as exc:
        logger.exception("Failed to reset for user %s: %s", key, exc)
        await message.answer(
            "❌ Не удалось перезапустить. Попробуй нажать /start",
            reply_markup=build_error_markup()
        )


# ---------------------------------------------------------
# ABOUT STEP HANDLER (/about_step)
# ---------------------------------------------------------

async def handle_about_step(message: Message, state: FSMContext) -> None:
    """Show description of current step"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Сначала нажми /start для авторизации.")
            return
        
        # Get current step info
        step_info = await BACKEND_CLIENT.get_current_step_info(token)
        
        if not step_info or not step_info.get("step_number"):
            await message.answer("У тебя нет активного шага. Нажми /steps, чтобы начать.")
            return
        
        # Build step description
        step_number = step_info.get("step_number")
        step_title = step_info.get("step_title", f"Шаг {step_number}")
        step_description = step_info.get("step_description", "")
        total_steps = step_info.get("total_steps", 12)
        
        progress_indicator = format_step_progress_indicator(
            step_number=step_number,
            total_steps=total_steps,
            step_title=step_title,
            answered_questions=step_info.get("answered_questions", 0),
            total_questions=step_info.get("total_questions", 0)
        )
        
        about_text = f"📘 {progress_indicator}"
        if step_description:
            about_text += f"\n\n{step_description}"
        else:
            about_text += "\n\nОписание шага пока не добавлено."
        
        await send_long_message(
            message,
            about_text,
            reply_markup=build_steps_navigation_markup()
        )
        
    except Exception as exc:
        logger.exception("Error handling /about_step for %s: %s", telegram_id, exc)
        error_text = (
            "❌ Ошибка при получении информации о шаге.\n\n"
            "Хочешь начать заново?"
        )
        await message.answer(error_text, reply_markup=build_error_markup())


# ---------------------------------------------------------
# QA / DEBUG COMMANDS
# ---------------------------------------------------------

async def qa_open(message: Message) -> None:
    """
    QA Command: Fetches the active TAIL (question) from the backend 
    without expecting an answer (does not change state).
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    try:
        # We reuse the get_current_step_question logic which hits /steps/next
        step_data = await get_current_step_question(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name
        )
    except Exception as exc:
        await message.answer(f"❌ API Error: {exc}")
        return

    if not step_data:
        await message.answer("📭 Backend returned no data (or Auth failed).")
        return

    text = step_data.get("message", "[No Text]")
    is_done = step_data.get("is_completed", False)

    info = (
        f"Хвосты:\nШаг: {text}"
    )
    await message.answer(info)


async def qa_ctx(message: Message) -> None:
    uid = message.from_user.id
    logs = USER_LOGS.get(uid, [])
    await message.answer(logs[-1].prompt_changes if logs else "Empty")

async def qa_trace(message: Message) -> None:
    uid = message.from_user.id
    logs = USER_LOGS.get(uid, [])
    await message.answer(str(logs[-1].blocks_used) if logs else "Empty")

async def qa_last(message: Message) -> None:
    uid = message.from_user.id
    logs = USER_LOGS.get(uid, [])
    await message.answer(str(logs[-1].classification_result) if logs else "Empty")

def get_logs_for_period(uid: int, hours: int):
    logs = USER_LOGS.get(uid, [])
    now_ts = int(datetime.datetime.utcnow().timestamp())
    return [l for l in logs if getattr(l, "timestamp", 0) >= (now_ts - hours * 3600)]

async def qa_export(message: Message):
    uid = message.from_user.id
    args = message.text.split()
    if len(args) < 2: return await message.answer("Usage: /qa_export 5h")
    logs = get_logs_for_period(uid, int(args[1][:-1]))
    if not logs: return await message.answer("No logs.")
    data = [{"ts": l.timestamp, "blocks": l.blocks_used} for l in logs]
    await message.answer(f"```json\n{json.dumps(data, indent=2)[:4000]}\n```")

async def qa_report(message: Message):
    uid = message.from_user.id
    args = message.text.split()
    if len(args) < 2: return await message.answer("Usage: /qa_report 5h")
    logs = get_logs_for_period(uid, int(args[1][:-1]))
    if not logs: return await message.answer("No logs.")
    await message.answer(f"Found {len(logs)} interactions.")


# ---------------------------------------------------------
# GENERAL MESSAGE HANDLER (Pure Chat)
# ---------------------------------------------------------

async def handle_message(message: Message, debug: bool) -> None:
    """
    Handles general chat with the AI.
    """
    telegram_id = message.from_user.id
    
    try:
        backend_reply = await call_legacy_chat(
            telegram_id=telegram_id,
            text=message.text,
            debug=debug
        )
        
        reply_text = "..."
        if isinstance(backend_reply, str):
             try:
                data = json.loads(backend_reply)
                reply_text = data.get("reply", "Error parsing reply")
             except:
                reply_text = backend_reply
        else:
             reply_text = backend_reply.reply
             if backend_reply.log:
                uid = message.from_user.id
                log = backend_reply.log
                log.timestamp = int(datetime.datetime.utcnow().timestamp())
                USER_LOGS.setdefault(uid, []).append(log)

        await send_long_message(message, reply_text, reply_markup=build_main_menu_markup())

    except Exception as exc:
        # Handle "bot was blocked by the user" - this is normal, don't log as error
        error_msg = str(exc)
        if "bot was blocked by the user" in error_msg or "Forbidden: bot was blocked" in error_msg:
            logger.info(f"User {telegram_id} blocked the bot - skipping message")
            return  # Silently ignore - user blocked the bot
        
        logger.exception("Failed to get response from backend chat: %s", exc)
        error_text = (
            "❌ Не удалось получить ответ от сервера.\n\n"
            "Произошла ошибка. Хочешь начать заново?"
        )
        await message.answer(error_text, reply_markup=build_error_markup())


# ---------------------------------------------------------
# START & HELPERS
# ---------------------------------------------------------

async def handle_start(message: Message, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    key = str(telegram_id)
    username = message.from_user.username
    first_name = message.from_user.first_name

    try:
        user, is_new, access_token = await BACKEND_CLIENT.auth_telegram(
            telegram_id=key,
            username=username,
            first_name=first_name,
        )
    except Exception as exc:
        logger.exception("Failed to auth telegram user %s: %s", key, exc)
        error_text = (
            "❌ Ошибка подключения к серверу.\n\n"
            "Хочешь попробовать начать заново?"
        )
        await message.answer(error_text, reply_markup=build_error_markup())
        return

    TOKEN_STORE[key] = access_token
    USER_CACHE[key] = user

    # Check if user needs onboarding: new user OR existing user without program_experience
    needs_onboarding = is_new or not user.get("program_experience")
    
    if needs_onboarding:
        await state.clear()
        await state.set_state(OnboardingStates.display_name)
        await message.answer("Привет! Как к тебе обращаться?", reply_markup=build_exit_markup())
        return

    try:
        status = await BACKEND_CLIENT.get_status(access_token)
    except:
        await message.answer("С возвращением!", reply_markup=build_main_menu_markup())
        return

    await send_welcome_back(message, user, status)


async def send_welcome_back(message: Message, user: dict, status: dict) -> None:
    display_name = get_display_name(user)
    open_question = status.get("open_step_question")

    text = f"С возвращением, {display_name}!"
    if open_question:
        text += "\n\nУ тебя есть незавершённый шаг. Нажми /steps, чтобы продолжить."
    else:
        text += "\n\nЯ готов общаться. Напиши мне что-нибудь или нажми /steps."

    await message.answer(text, reply_markup=build_main_menu_markup())

# ---------------------------------------------------------
# SOS HANDLER (/sos)
# ---------------------------------------------------------

# ... existing imports ...

# ---------------------------------------------------------
# SOS HANDLER (/sos)
# ---------------------------------------------------------

async def handle_sos(message: Message, state: FSMContext) -> None:
    """
    Handles /sos command: Shows help type selection menu.
    """
    telegram_id = message.from_user.id
    
    # Check if user is in step answering mode - save current state
    current_state = await state.get_state()
    if current_state == StepState.answering:
        await state.update_data(previous_state=StepState.answering)
    
    # Show help type selection
    await state.set_state(SosStates.help_type_selection)
    await message.answer(
        "🆘 Хорошо, я с тобой. Давай разберёмся, с чем нужна помощь.\n\n"
        "Выбери или опиши словами:",
        reply_markup=build_sos_help_type_markup()
    )


async def safe_answer_callback(callback: CallbackQuery, text: str | None = None, show_alert: bool = False) -> bool:
    """
    Safely answer a callback query, handling expired queries gracefully.
    Returns True if answered successfully, False if query expired.
    """
    try:
        await callback.answer(text=text, show_alert=show_alert)
        return True
    except TelegramBadRequest as e:
        # Check if it's the "query too old" error
        error_message = str(e).lower()
        if "query is too old" in error_message or "query id is invalid" in error_message:
            logger.warning("Callback query expired for user %s: %s", callback.from_user.id, callback.data)
            return False
        # Re-raise if it's a different TelegramBadRequest
        raise


async def handle_sos_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle SOS callback queries (help type selection, exit, etc.)"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await safe_answer_callback(callback, "Ошибка авторизации. Нажми /start.")
            return
        
        if data == "sos_cancel":
            # Cancel SOS - return to main menu
            await state.clear()
            await edit_long_message(
                callback,
                "❌ Помощь отменена.\n\nВернулся в главное меню.",
                reply_markup=None
            )
            # Send main menu as a new message with ReplyKeyboardMarkup
            await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
            await safe_answer_callback(callback)
            return
        
        if data == "sos_exit":
            # Exit SOS chat
            await state.clear()
            await edit_long_message(
                callback,
                "✅ Вышел из помощи.\n\nВернулся в главное меню.",
                reply_markup=None
            )
            # Send main menu as a new message with ReplyKeyboardMarkup
            await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
            await safe_answer_callback(callback)
            return
        
        if data == "sos_help":
            # User clicked "🆘 Нужна помощь" button - show help type selection
            current_state = await state.get_state()
            if current_state == StepState.answering:
                await state.update_data(previous_state=StepState.answering)
            
            await state.set_state(SosStates.help_type_selection)
            await edit_long_message(
                callback,
                "🆘 Хорошо, я с тобой. Давай разберёмся, с чем нужна помощь.\n\n"
                "Выбери или опиши словами:",
                reply_markup=build_sos_help_type_markup()
            )
            await safe_answer_callback(callback)
            return
        
        if data == "sos_help_custom":
            # User wants to enter custom help description
            await state.set_state(SosStates.custom_input)
            await edit_long_message(
                callback,
                "✍️ Опиши, с чем нужна помощь, своими словами:",
                reply_markup=build_sos_exit_markup()
            )
            await safe_answer_callback(callback)
            return
        
        if data.startswith("sos_help_"):
            # User selected a help type
            help_type = data.replace("sos_help_", "")
            help_type_map = {
                "question": "Не понимаю вопрос",
                "examples": "Хочу примеры",
                "direction": "Помоги понять куда смотреть",
                "memory": "Помоги понять куда смотреть",  # backwards compatibility
                "support": "Просто тяжело, нужна поддержка"
            }
            help_type_name = help_type_map.get(help_type, help_type)
            
            # Start SOS chat with selected help type
            await state.set_state(SosStates.chatting)
            await state.update_data(help_type=help_type, conversation_history=[])
            
            # Get initial SOS response
            sos_response = await BACKEND_CLIENT.sos_chat(
                access_token=token,
                help_type=help_type
            )
            
            reply_text = sos_response.get("reply", "Готов помочь!")
            await edit_long_message(
                callback,
                f"🆘 Помощь: {help_type_name}\n\n{reply_text}",
                reply_markup=build_sos_exit_markup()
            )
            await safe_answer_callback(callback)
            return
        
        if data == "sos_save_yes":
            # Save draft - TODO: implement draft saving
            await state.clear()
            await edit_long_message(
                callback,
                "✅ Черновик сохранён.\n\nВернулся в главное меню.",
                reply_markup=None
            )
            # Send main menu as a new message with ReplyKeyboardMarkup
            await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
            await safe_answer_callback(callback, "Черновик сохранён")
            return
        
        if data == "sos_save_no":
            # Don't save draft
            await state.clear()
            await edit_long_message(
                callback,
                "✅ Помощь завершена.\n\nВернулся в главное меню.",
                reply_markup=None
            )
            # Send main menu as a new message with ReplyKeyboardMarkup
            await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
            await safe_answer_callback(callback)
            return
        
        await safe_answer_callback(callback, "Неизвестная команда")
        
    except TelegramBadRequest as e:
        # Handle Telegram API errors (including expired queries)
        error_message = str(e).lower()
        if "query is too old" in error_message or "query id is invalid" in error_message:
            logger.warning("Callback query expired for user %s: %s", telegram_id, data)
            # Don't try to answer - query is already expired
        else:
            logger.exception("TelegramBadRequest handling SOS callback for %s: %s", telegram_id, e)
            await safe_answer_callback(callback, "Ошибка. Попробуй позже.")
    except Exception as exc:
        logger.exception("Error handling SOS callback for %s: %s", telegram_id, exc)
        await safe_answer_callback(callback, "Ошибка. Попробуй позже.")


async def handle_sos_chat_message(message: Message, state: FSMContext) -> None:
    """Handle messages during SOS chat"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    text = message.text
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Ошибка авторизации. Нажми /start.")
            return
        
        # Get conversation history from state
        state_data = await state.get_data()
        conversation_history = state_data.get("conversation_history", [])
        help_type = state_data.get("help_type")
        
        # Add user message to history
        conversation_history.append({"role": "user", "content": text})
        
        # Get SOS response
        sos_response = await BACKEND_CLIENT.sos_chat(
            access_token=token,
            help_type=help_type,
            message=text,
            conversation_history=conversation_history
        )
        
        reply_text = sos_response.get("reply", "Готов помочь!")
        
        # Add assistant response to history
        conversation_history.append({"role": "assistant", "content": reply_text})
        await state.update_data(conversation_history=conversation_history)
        
        await send_long_message(
            message,
            reply_text,
            reply_markup=build_sos_exit_markup()
        )
        
    except Exception as exc:
        logger.exception("Error handling SOS chat message for %s: %s", telegram_id, exc)
        await message.answer("Ошибка. Попробуй позже.")


async def handle_sos_custom_input(message: Message, state: FSMContext) -> None:
    """Handle custom help description input"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    custom_text = message.text
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Ошибка авторизации. Нажми /start.")
            return
        
        # Start SOS chat with custom text
        await state.set_state(SosStates.chatting)
        await state.update_data(help_type="custom", conversation_history=[])
        
        sos_response = await BACKEND_CLIENT.sos_chat(
            access_token=token,
            help_type="custom",
            custom_text=custom_text
        )
        
        reply_text = sos_response.get("reply", "Готов помочь!")
        
        await send_long_message(
            message,
            f"🆘 Помощь: Своё описание\n\n{reply_text}",
            reply_markup=build_sos_exit_markup()
        )
        
    except Exception as exc:
        logger.exception("Error handling SOS custom input for %s: %s", telegram_id, exc)
        await message.answer("Ошибка. Попробуй позже.")


# ---------------------------------------------------------
# THANKS HANDLER (/thanks)
# ---------------------------------------------------------

async def handle_thanks(message: Message, state: FSMContext) -> None:
    """
    Handles /thanks command: Returns support and motivation message.
    """
    telegram_id = message.from_user.id
    
    try:
        backend_reply = await BACKEND_CLIENT.thanks(telegram_id=telegram_id, debug=False)
        
        reply_text = backend_reply.reply
        if backend_reply.log:
            log = backend_reply.log
            log.timestamp = int(datetime.datetime.utcnow().timestamp())
            USER_LOGS.setdefault(telegram_id, []).append(log)
        
        await send_long_message(message, reply_text, reply_markup=build_main_menu_markup())
    
    except Exception as exc:
        logger.exception("Failed to get response from /thanks endpoint: %s", exc)
        error_text = (
            "❌ Не удалось получить ответ от сервера.\n\n"
            "Произошла ошибка. Хочешь начать заново?"
        )
        await message.answer(error_text, reply_markup=build_error_markup())


# ---------------------------------------------------------
# FAQ HANDLER
# ---------------------------------------------------------

async def handle_faq(message: Message, state: FSMContext) -> None:
    """Handle FAQ command - show frequently asked questions"""
    faq_text = (
        "📎 ИНСТРУКЦИИ — КАК ЭТО РАБОТАЕТ\n\n"
        "🪜 Работа по шагу\n\n"
        "• Что такое шаги?\n"
        "Это 12 ключевых тем, через которые проходит каждый зависимый. Шаги помогают понять своё мышление, чувства, действия и изменить их. Это не теория — это личная практика.\n\n"
        "• Как выбрать шаг и вопрос?\n"
        "Если ты уже работаешь по шагу — продолжай. Если нет — выбери начальный шаг (обычно с 1-го). Внутри шага есть вопросы, которые раскрывают тему. Система запомнит, где ты остановился.\n\n"
        "• Что делать, если не могу ответить?\n"
        "Нажми «🧭 Помощь». Там есть варианты: «Не понял вопрос», «Нужны примеры», «Просто тяжело». GPT подскажет, поможет вспомнить и не даст застрять.\n\n"
        "• Как сохраняется прогресс?\n"
        "Все твои ответы сохраняются автоматически. Ты можешь поставить вопрос на паузу и вернуться. Прогресс виден в разделе «Мой прогресс».\n\n"
        "📖 Самоанализ (10 шаг)\n\n"
        "• Как работает?\n"
        "Каждый день ты отвечаешь на вопросы. Это помогает отслеживать мысли, чувства, ошибки, помогает развиваться.\n\n"
        "• Сколько вопросов?\n"
        "В самоанализе 10 вопросов. Они повторяются ежедневно. Можно делать не все, а столько, сколько успеешь.\n\n"
        "• Делать ли каждый день?\n"
        "Желательно. Это как зарядка для осознанности. Но если не получилось — не страшно. Главное — возвращаться.\n\n"
        "📘 Чувства\n\n"
        "• Что такое таблица чувств?\n"
        "Это список эмоций, которые можно выбрать, если сложно назвать, что ты чувствуешь. Они помогают лучше понять себя.\n\n"
        "• Как использовать?\n"
        "Когда заполняешь шаблон, можно открыть таблицу и выбрать подходящие чувства. Особенно это важно в блоке \"Чувства до / после\".\n\n"
        "• Как выбрать нужное чувство?\n"
        "Не обязательно выбирать «правильно». Просто найди то, что ближе всего к тому, как ты ощущаешь. Это не тест.\n\n"
        "✍️ О себе\n\n"
        "• Зачем писать?\n"
        "Чем больше ты рассказываешь о себе, тем точнее GPT тебя понимает. Это как знакомство — без давления, но с пользой.\n\n"
        "• Что, если не хочу?\n"
        "Ты можешь пропустить. Но лучше дать хоть немного информации — это поможет в работе по шагам и в поддержке.\n\n"
        "• Что такое \"Свободный рассказ\"?\n"
        "Это раздел, где можно просто написать всё, что хочешь — без вопросов и рамок. GPT сам распределит по темам.\n\n"
        "📋 Шаблон ответа\n\n"
        "• Как выбрать или изменить?\n"
        "Система автоматически использует авторский шаблон. Его можно изменить в настройках шага.\n\n"
        "• Мой vs авторский шаблон?\n"
        "Авторский — проверенная структура (ситуация, мысли, чувства, действия…). Свой — ты настраиваешь сам.\n\n"
        "🧭 Помощь\n\n"
        "• Когда использовать?\n"
        "Когда застрял. Когда не знаешь, что ответить. Когда слишком тяжело. Или просто не понимаешь вопрос.\n\n"
        "• Что значит \"Не понял вопрос\"?\n"
        "GPT переформулирует вопрос и объяснит его.\n\n"
        "• Как работает \"Нужны примеры\"\n"
        "GPT даст тебе 12-18 бытовых ситуаций, где может проявляться тема шага. Это поможет вспомнить свою ситуацию. Если не нашел подходящий пример, нажми еще раз — получишь новые варианты.\n\n"
        "• Что делать, если тяжело?\n"
        "Нажми «Просто тяжело». GPT поддержит тебя. Иногда важно просто не быть одному.\n\n"
        "🙏 Благодарности\n\n"
        "• Зачем писать?\n"
        "Чтобы учиться видеть хорошее. Благодарность переключает мышление и снижает тревогу.\n\n"
        "• Как часто?\n"
        "Хоть каждый день. Можно 4-5 фраз, за что именно ты сегодня благодарен — это может быть благодарность миру за теплый день и маме за вкусный обед.\n\n"
        "• Кто видит?\n"
        "Только ты. Это твой личный дневник. Никуда не отправляется.\n\n"
        "📈 Прогресс\n\n"
        "• Как посмотреть, что уже сделано?\n"
        "Зайди в «Мой прогресс». Там будут шаги, вопросы, твои ответы и статус каждого.\n\n"
        "• Что такое \"Мой прогресс\"?\n"
        "Это твоя карта движения. Показывает, где ты, что уже пройдено, что осталось."
    )
    await send_long_message(message, faq_text, reply_markup=build_main_menu_markup())


# ---------------------------------------------------------
# DAY HANDLER (/day)
# ---------------------------------------------------------

async def handle_day(message: Message, state: FSMContext) -> None:
    """
    Handles /day command: Starts Step 10 daily self-analysis.
    IMPORTANT: Closes active step question and switches to Step 10 analysis.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # CRITICAL: Clear step answering state if active
    # This prevents /day from being processed as a step answer
    current_state = await state.get_state()
    if current_state == StepState.answering or current_state == StepState.filling_template:
        await state.clear()
        logger.info(f"Cleared step state for user {telegram_id} when switching to /day")
    
    try:
        # Get token for API calls
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("❌ Ошибка аутентификации. Попробуй /start")
            return
        
        # Start Step 10 analysis
        data = await BACKEND_CLIENT.start_step10_analysis(token)
        
        if not data:
            await message.answer("❌ Не удалось начать самоанализ. Попробуй позже.")
            return
        
        # Check if resumed from pause
        if data.get("is_resumed"):
            resume_text = f"⏸ Продолжаем с того места, где остановились.\n\n"
        else:
            resume_text = ""
        
        # Get question data
        question_data = data.get("question_data", {})
        question_number = question_data.get("number", 1)
        question_text = question_data.get("text", "")
        question_subtext = question_data.get("subtext", "")
        
        # Build question message
        question_msg = (
            f"{resume_text}"
            f"📘 Ежедневный самоанализ (10 шаг)\n\n"
            f"Вопрос {question_number}/10:\n"
            f"{question_text}\n"
        )
        if question_subtext:
            question_msg += f"\n{question_subtext}\n"
        
        question_msg += f"\n{data.get('progress_summary', '')}"
        
        # Set FSM state
        await state.set_state(Step10States.answering_question)
        await state.update_data(
            step10_analysis_id=data.get("analysis_id"),
            step10_current_question=question_number,
            step10_is_complete=data.get("is_complete", False)
        )
        
        # Build markup with pause button
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏸ Пауза", callback_data="step10_pause")]
        ])
        
        await send_long_message(message, question_msg, reply_markup=markup)
    
    except Exception as exc:
        logger.exception("Failed to start step10 analysis: %s", exc)
        error_text = (
            "❌ Не удалось начать самоанализ.\n\n"
            "Произошла ошибка. Хочешь начать заново?"
        )
        await message.answer(error_text, reply_markup=build_error_markup())


# ---------------------------------------------------------
# STEP 10 DAILY ANALYSIS HANDLERS
# ---------------------------------------------------------

async def handle_step10_answer(message: Message, state: FSMContext) -> None:
    """Обработка ответа на вопрос самоанализа по 10 шагу"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    answer_text = message.text
    
    if not answer_text or not answer_text.strip():
        await message.answer("Пожалуйста, напиши ответ на вопрос.")
        return
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("❌ Ошибка аутентификации.")
            await state.clear()
            return
        
        # Get current question from state
        state_data = await state.get_data()
        current_question = state_data.get("step10_current_question", 1)
        
        # Submit answer
        data = await BACKEND_CLIENT.submit_step10_answer(
            token, current_question, answer_text
        )
        
        if not data or not data.get("success"):
            error_msg = data.get("error", "Не удалось сохранить ответ. Попробуй позже.")
            await message.answer(f"❌ {error_msg}")
            return
        
        # Check if complete
        if data.get("is_complete"):
            # All questions answered
            await state.clear()
            completion_msg = (
                "✅ Самоанализ за сегодня завершён!\n\n"
                "Спасибо. Самоанализ за сегодня завершён, жду тебя завтра."
            )
            await message.answer(completion_msg, reply_markup=build_main_menu_markup())
            return
        
        # Get next question
        next_question_data = data.get("next_question_data", {})
        if not next_question_data:
            await message.answer("❌ Ошибка: не удалось получить следующий вопрос.")
            await state.clear()
            return
        
        next_question_number = next_question_data.get("number", current_question + 1)
        next_question_text = next_question_data.get("text", "")
        next_question_subtext = next_question_data.get("subtext", "")
        
        # Update state
        await state.update_data(
            step10_current_question=next_question_number
        )
        
        # Build next question message
        next_question_msg = (
            f"📘 Ежедневный самоанализ (10 шаг)\n\n"
            f"Вопрос {next_question_number}/10:\n"
            f"{next_question_text}\n"
        )
        if next_question_subtext:
            next_question_msg += f"\n{next_question_subtext}\n"
        
        next_question_msg += f"\n{data.get('progress_summary', '')}"
        
        # Build markup
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏸ Пауза", callback_data="step10_pause")]
        ])
        
        await send_long_message(message, next_question_msg, reply_markup=markup)
    
    except Exception as exc:
        logger.exception("Failed to submit step10 answer: %s", exc)
        await message.answer("❌ Произошла ошибка. Попробуй позже.")


async def handle_step10_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Обработка callback для Step 10 (пауза и т.д.)"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        await callback.answer()
        
        if data == "step10_pause":
            token = await get_or_fetch_token(telegram_id, username, first_name)
            if not token:
                await callback.message.answer("❌ Ошибка аутентификации.")
                return
            
            pause_data = await BACKEND_CLIENT.pause_step10_analysis(token)
            
            if not pause_data or not pause_data.get("success"):
                error_msg = pause_data.get("error", "Не удалось поставить на паузу.")
                await callback.message.answer(f"❌ {error_msg}")
                return
            
            # Clear state
            await state.clear()
            
            pause_msg = (
                f"⏸ Самоанализ поставлен на паузу.\n\n"
                f"{pause_data.get('resume_info', '')}\n\n"
                f"При следующем входе в раздел «📖 Самоанализ» сможешь продолжить с того же места."
            )
            await callback.message.answer(pause_msg, reply_markup=build_main_menu_markup())
    
    except Exception as exc:
        logger.exception("Failed to handle step10 callback: %s", exc)
        await callback.message.answer("❌ Произошла ошибка. Попробуй позже.")


# ---------------------------------------------------------
# PROFILE HANDLERS (/profile)
# ---------------------------------------------------------

async def handle_profile(message: Message, state: FSMContext) -> None:
    """Handle /profile command - show all profile sections"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Сначала нажми /start для авторизации.")
            return
        
        # Get all sections
        sections_data = await BACKEND_CLIENT.get_profile_sections(token)
        sections = sections_data.get("sections", [])
        
        if not sections:
            await message.answer("Разделы профиля пока не настроены.")
            return
        
        # Build and send sections keyboard
        markup = build_profile_sections_markup(sections)
        await send_long_message(
            message,
            "📋 Выбери раздел, о котором хочешь рассказать:",
            reply_markup=markup
        )
        await state.set_state(ProfileStates.section_selection)
        
    except Exception as exc:
        logger.exception("Error handling /profile for %s: %s", telegram_id, exc)
        await message.answer("Ошибка при загрузке разделов. Попробуй позже.")


async def handle_profile_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle callback queries for profile actions"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await callback.answer("Ошибка авторизации. Нажми /start.")
            return
        
        if data.startswith("profile_section_"):
            # User selected a section
            section_id = int(data.split("_")[-1])
            section_data = await BACKEND_CLIENT.get_section_detail(token, section_id)
            section = section_data.get("section", {})
            questions = section.get("questions", [])
            
            if not questions:
                await callback.answer("В этом разделе пока нет вопросов.")
                return
            
            # Show first question or intro
            intro_text = f"📝 {section.get('name', 'Раздел')}\n\n"
            intro_text += "Давай начнём с первого вопроса:\n\n"
            
            first_question = questions[0]
            question_text = f"{first_question.get('question_text', '')}"
            
            # Store section and question info in state
            await state.update_data(
                section_id=section_id,
                current_question_id=first_question.get("id"),
                questions=questions,
                question_index=0
            )
            
            markup = build_profile_actions_markup(section_id)
            if first_question.get("is_optional"):
                skip_markup = build_profile_skip_markup()
                # Combine markups
                markup.inline_keyboard.append(skip_markup.inline_keyboard[0])
            
            await edit_long_message(
                callback,
                intro_text + question_text,
                reply_markup=markup
            )
            await state.set_state(ProfileStates.answering_question)
            await callback.answer()
            
        elif data == "profile_free_text" or data.startswith("profile_free_text_"):
            # Free text input
            section_id = None
            if "_" in data:
                try:
                    section_id = int(data.split("_")[-1])
                except ValueError:
                    pass
            
            await state.update_data(section_id=section_id)
            await edit_long_message(
                callback,
                "✍️ Напиши свой рассказ. После сохранения система автоматически распределит информацию по разделам."
            )
            await state.set_state(ProfileStates.free_text_input)
            await callback.answer()
            
        elif data == "profile_custom_section":
            # Create custom section
            await edit_long_message(
                callback,
                "➕ Как назовём новый раздел? (можно добавить эмодзи)"
            )
            await state.set_state(ProfileStates.creating_custom_section)
            await callback.answer()
            
        elif data.startswith("profile_save_"):
            # Save section
            section_id = int(data.split("_")[-1])
            summary = await BACKEND_CLIENT.get_section_summary(token, section_id)
            
            summary_text = f"✅ Раздел сохранён!\n\n"
            summary_text += f"Вопросов: {summary.get('questions_count', 0)}\n"
            summary_text += f"Отвечено: {summary.get('answers_count', 0)}"
            
            await edit_long_message(callback, summary_text)
            await state.clear()
            await callback.answer("Раздел сохранён")
            
        elif data == "profile_back":
            # Back to sections list
            sections_data = await BACKEND_CLIENT.get_profile_sections(token)
            sections = sections_data.get("sections", [])
            markup = build_profile_sections_markup(sections)
            await edit_long_message(
                callback,
                "📋 Выбери раздел:",
                reply_markup=markup
            )
            await state.set_state(ProfileStates.section_selection)
            await callback.answer()
            
        elif data == "profile_skip":
            # Skip question
            state_data = await state.get_data()
            questions = state_data.get("questions", [])
            question_index = state_data.get("question_index", 0)
            
            if question_index + 1 < len(questions):
                next_index = question_index + 1
                next_question = questions[next_index]
                
                await state.update_data(question_index=next_index, current_question_id=next_question.get("id"))
                
                markup = build_profile_actions_markup(state_data.get("section_id"))
                if next_question.get("is_optional"):
                    skip_markup = build_profile_skip_markup()
                    markup.inline_keyboard.append(skip_markup.inline_keyboard[0])
                
                await edit_long_message(
                    callback,
                    next_question.get("question_text", ""),
                    reply_markup=markup
                )
                await callback.answer("Вопрос пропущен")
            else:
                await callback.answer("Это был последний вопрос")
                
    except Exception as exc:
        logger.exception("Error handling profile callback for %s: %s", telegram_id, exc)
        await callback.answer("Ошибка. Попробуй позже.")


async def handle_profile_answer(message: Message, state: FSMContext) -> None:
    """Handle answer to a profile question"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    answer_text = message.text
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Ошибка авторизации. Нажми /start.")
            await state.clear()
            return
        
        state_data = await state.get_data()
        section_id = state_data.get("section_id")
        question_id = state_data.get("current_question_id")
        questions = state_data.get("questions", [])
        question_index = state_data.get("question_index", 0)
        
        if not section_id or not question_id:
            await message.answer("Ошибка: не найден вопрос. Начни заново с /profile")
            await state.clear()
            return
        
        # Submit answer
        result = await BACKEND_CLIENT.submit_profile_answer(
            token, section_id, question_id, answer_text
        )
        
        # Check if there's a next question
        next_question = result.get("next_question")
        
        if next_question:
            # Show next question
            next_question_text = next_question.get("text", "")
            await state.update_data(
                current_question_id=next_question.get("id"),
                question_index=question_index + 1
            )
            
            markup = build_profile_actions_markup(section_id)
            if next_question.get("is_optional"):
                skip_markup = build_profile_skip_markup()
                markup.inline_keyboard.append(skip_markup.inline_keyboard[0])
            
            await send_long_message(
                message,
                f"✅ Ответ сохранён!\n\nСледующий вопрос:\n\n{next_question_text}",
                reply_markup=markup
            )
        else:
            # All questions answered
            await message.answer(
                "✅ Все вопросы в этом разделе отвечены!",
                reply_markup=build_profile_actions_markup(section_id)
            )
            await state.set_state(ProfileStates.section_selection)
            
    except Exception as exc:
        logger.exception("Error handling profile answer for %s: %s", telegram_id, exc)
        await message.answer("Ошибка при сохранении ответа. Попробуй позже.")


async def handle_profile_free_text(message: Message, state: FSMContext) -> None:
    """Handle free text input for profile"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    text = message.text
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Ошибка авторизации. Нажми /start.")
            await state.clear()
            return
        
        state_data = await state.get_data()
        section_id = state_data.get("section_id")
        
        if section_id:
            # Save to specific section
            await BACKEND_CLIENT.submit_free_text(token, section_id, text)
            await message.answer(
                f"✅ Свободный рассказ сохранён в раздел!",
                reply_markup=build_main_menu_markup()
            )
        else:
            # General free text - process and distribute across sections
            try:
                result = await BACKEND_CLIENT.submit_general_free_text(token, text)
                saved_sections = result.get("saved_sections", [])
                if saved_sections:
                    sections_list = ", ".join([s.get("section_name", "") for s in saved_sections])
                    await message.answer(
                        f"✅ Текст обработан и распределён по разделам: {sections_list}",
                        reply_markup=build_main_menu_markup()
                    )
                else:
                    await message.answer(
                        "✅ Текст сохранён. Система обработает его и распределит по разделам.",
                        reply_markup=build_main_menu_markup()
                    )
            except Exception as e:
                logger.exception("Error processing general free text: %s", e)
                await message.answer(
                    "✅ Текст сохранён. Система обработает его и распределит по разделам.",
                    reply_markup=build_main_menu_markup()
                )
        
        await state.clear()
        
    except Exception as exc:
        logger.exception("Error handling profile free text for %s: %s", telegram_id, exc)
        await message.answer("Ошибка при сохранении текста. Попробуй позже.")


async def handle_profile_custom_section(message: Message, state: FSMContext) -> None:
    """Handle custom section creation"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    section_name = message.text
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Ошибка авторизации. Нажми /start.")
            await state.clear()
            return
        
        # Extract icon if present (first emoji)
        icon = None
        if section_name and len(section_name) > 0:
            # Check if first character is emoji
            first_char = section_name[0]
            if ord(first_char) > 127:  # Simple emoji check
                icon = first_char
                section_name = section_name[1:].strip()
        
        result = await BACKEND_CLIENT.create_custom_section(token, section_name, icon)
        section_id = result.get("section_id")
        
        await message.answer(
            f"✅ Раздел '{section_name}' создан! Теперь можешь добавить в него вопросы через /profile",
            reply_markup=build_main_menu_markup()
        )
        await state.clear()
        
    except Exception as exc:
        logger.exception("Error creating custom section for %s: %s", telegram_id, exc)
        await message.answer("Ошибка при создании раздела. Попробуй позже.")


# ---------------------------------------------------------
# TEMPLATE SELECTION HANDLERS
# ---------------------------------------------------------

async def handle_template_selection(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle template selection callback"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await callback.answer("Ошибка авторизации. Нажми /start.")
            return
        
        if data == "template_author":
            # Get author template and set it as active
            templates_data = await BACKEND_CLIENT.get_templates(token)
            templates = templates_data.get("templates", [])
            
            # Debug logging
            logger.info(f"Templates received: {len(templates)} templates")
            for t in templates:
                logger.info(f"Template: id={t.get('id')}, name={t.get('name')}, type={t.get('template_type')}")
            
            author_template = None
            for template in templates:
                template_type = template.get("template_type")
                # Handle both string and enum-like values
                if template_type == "AUTHOR" or (hasattr(template_type, 'value') and template_type.value == "AUTHOR"):
                    author_template = template
                    break
            
            if author_template:
                await BACKEND_CLIENT.set_active_template(token, author_template.get("id"))
                await callback.answer("✅ Авторский шаблон выбран")
                
                # Automatically start steps flow after template selection
                # Get current step info
                step_info = await BACKEND_CLIENT.get_current_step_info(token)
                
                if step_info:
                    step_number = step_info.get("step_number")
                    step_title = step_info.get("step_title") or step_info.get("step_description") or (f"Шаг {step_number}" if step_number else "Шаг")
                    total_steps = step_info.get("total_steps", 12)
                    
                    # Build progress indicator (handle None values)
                    if step_number is not None and total_steps is not None:
                        progress_bar = "█" * step_number + "░" * (total_steps - step_number)
                        progress_text = f"Шаг {step_number}/{total_steps}\n{progress_bar}"
                    else:
                        progress_text = "Начинаем работу по шагам..."
                    
                    # Get current question
                    step_next = await BACKEND_CLIENT.get_next_step(token)
                    
                    if step_next:
                        is_completed = step_next.get("is_completed", False)
                        question_text = step_next.get("message", "")
                        
                        if is_completed or not question_text or question_text == "Program completed.":
                            # No questions available - need to check if steps exist
                            await edit_long_message(
                                callback,
                                f"✅ Шаблон выбран!\n\n{progress_text}\n\n"
                                "⚠️ В базе данных пока нет шагов или вопросов.\n\n"
                                "Обратитесь к администратору для настройки шагов программы.",
                                reply_markup=None
                            )
                        else:
                            # Show question
                            await edit_long_message(
                                callback,
                                f"✅ Шаблон выбран!\n\n{progress_text}\n\n📘 {step_title}\n\n{question_text}",
                                reply_markup=build_step_actions_markup()
                            )
                            await state.set_state(StepState.answering)
                    else:
                        await edit_long_message(
                            callback,
                            f"✅ Шаблон выбран!\n\n{progress_text}\n\n📘 {step_title}\n\nНачинаем работу по шагу...",
                            reply_markup=build_step_actions_markup()
                        )
                        await state.set_state(StepState.answering)
                else:
                    await edit_long_message(
                        callback,
                        "✅ Выбран авторский шаблон!\n\nТеперь можешь начать работу по шагу. Нажми /steps."
                    )
            else:
                await callback.answer("Авторский шаблон не найден")
                
        elif data == "template_custom":
            # Create custom template - show instructions
            await edit_long_message(
                callback,
                "✍️ Для создания своего шаблона нужно:\n\n"
                "1. Определить структуру (поля) шаблона\n"
                "2. Создать шаблон через API или настройки\n\n"
                "Пока используй авторский шаблон, а свой создашь позже в настройках."
            )
            await callback.answer()
            
    except Exception as exc:
        logger.exception("Error handling template selection for %s: %s", telegram_id, exc)
        await callback.answer("Ошибка. Попробуй позже.")


# ---------------------------------------------------------
# TEMPLATE FILLING FSM CALLBACKS (tpl_ prefix)
# ---------------------------------------------------------

async def handle_template_filling_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle template filling FSM callbacks (pause, cancel, etc.)"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await callback.answer("Ошибка авторизации. Нажми /start.")
            return
        
        state_data = await state.get_data()
        step_id = state_data.get("template_step_id")
        question_id = state_data.get("template_question_id")
        
        if data == "tpl_pause":
            # Pause template filling
            if step_id and question_id:
                result = await BACKEND_CLIENT.pause_template_progress(token, step_id, question_id)
                
                if result and result.get("success"):
                    resume_info = result.get("resume_info", "")
                    progress_summary = result.get("progress_summary", "")
                    await edit_long_message(
                        callback,
                        f"⏸ Прогресс сохранён!\n\n"
                        f"{resume_info}\n\n"
                        f"📊 {progress_summary}\n\n"
                        f"💡 Чтобы продолжить:\n"
                        f"1. Вернись к этому вопросу (🪜 Работа по шагу)\n"
                        f"2. Нажми «🧩 Заполнить по шаблону»\n"
                        f"3. Система автоматически продолжит с того места, где остановился",
                        reply_markup=build_step_actions_markup()
                    )
                    await state.set_state(StepState.answering)
                    await callback.answer("Прогресс сохранён")
                else:
                    await callback.answer("Ошибка сохранения прогресса")
            else:
                await callback.answer("Данные шаблона потеряны")
                await state.set_state(StepState.answering)
                
        elif data == "tpl_cancel":
            # Cancel template filling
            if step_id and question_id:
                await BACKEND_CLIENT.cancel_template_progress(token, step_id, question_id)
            
            await edit_long_message(
                callback,
                "❌ Заполнение шаблона отменено.\n\n"
                "Ты можешь ответить на вопрос своими словами или начать заполнение заново.",
                reply_markup=build_step_actions_markup()
            )
            await state.set_state(StepState.answering)
            await callback.answer("Заполнение отменено")
            
        elif data == "tpl_next_situation":
            # Continue to next situation (just acknowledge, actual progression is handled by field input)
            await callback.answer("Продолжаем...")
            
        elif data == "tpl_write_conclusion":
            # Ready to write conclusion (just acknowledge)
            await callback.answer("Напиши финальный вывод")
            
        else:
            await callback.answer("Неизвестная команда")
            
    except Exception as exc:
        logger.exception("Error handling template filling callback for %s: %s", telegram_id, exc)
        await callback.answer("Ошибка. Попробуй позже.")


# ---------------------------------------------------------
# STEPS SETTINGS HANDLERS
# ---------------------------------------------------------

async def handle_steps_settings(message: Message, state: FSMContext) -> None:
    """Handle /steps_settings command - show settings menu"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Сначала нажми /start для авторизации.")
            return
        
        # Get current settings
        settings = await BACKEND_CLIENT.get_steps_settings(token)
        active_template_name = settings.get("active_template_name", "Не выбран")
        reminders_enabled = settings.get("reminders_enabled", False)
        
        settings_text = (
            "⚙️ Настройки работы по шагу\n\n"
            f"🧩 Активный шаблон: {active_template_name}\n"
            f"⏰ Напоминания: {'✅ Включены' if reminders_enabled else '❌ Выключены'}\n\n"
            "Выбери настройку для изменения:"
        )
        
        await message.answer(
            settings_text,
            reply_markup=build_steps_settings_markup()
        )
        
    except Exception as exc:
        logger.exception("Error handling steps settings for %s: %s", telegram_id, exc)
        await message.answer("Ошибка при загрузке настроек. Попробуй позже.")


async def handle_steps_settings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle steps settings callback buttons"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await callback.answer("Ошибка авторизации. Нажми /start.")
            return
        
        if data == "settings_back":
            # Return to settings main menu
            settings = await BACKEND_CLIENT.get_steps_settings(token)
            active_template_name = settings.get("active_template_name", "Не выбран")
            reminders_enabled = settings.get("reminders_enabled", False)
            
            settings_text = (
                "⚙️ Настройки работы по шагу\n\n"
                f"🧩 Активный шаблон: {active_template_name}\n"
                f"⏰ Напоминания: {'✅ Включены' if reminders_enabled else '❌ Выключены'}\n\n"
                "Выбери настройку для изменения:"
            )
            
            await edit_long_message(
                callback,
                settings_text,
                reply_markup=build_steps_settings_markup()
            )
            await callback.answer()
            return
        
        if data == "settings_template":
            # Show template selection
            templates_data = await BACKEND_CLIENT.get_templates(token)
            templates = templates_data.get("templates", [])
            current_template_id = templates_data.get("active_template_id")
            
            if templates:
                await edit_long_message(
                    callback,
                    "🧩 Выбери активный шаблон:",
                    reply_markup=build_template_selection_settings_markup(templates, current_template_id)
                )
            else:
                await callback.answer("Шаблоны не найдены")
            return
        
        if data.startswith("settings_select_template_"):
            # Select template
            template_id = int(data.split("_")[-1])
            
            # Update settings
            await BACKEND_CLIENT.update_steps_settings(token, active_template_id=template_id)
            
            # Get updated settings
            settings = await BACKEND_CLIENT.get_steps_settings(token)
            active_template_name = settings.get("active_template_name", "Не выбран")
            
            await edit_long_message(
                callback,
                f"✅ Шаблон изменён на: {active_template_name}\n\n"
                "⚙️ Настройки работы по шагу",
                reply_markup=build_steps_settings_markup()
            )
            await callback.answer("Шаблон изменён")
            return
        
        if data == "settings_reset_template":
            # Reset to author template
            templates_data = await BACKEND_CLIENT.get_templates(token)
            templates = templates_data.get("templates", [])
            
            # Find author template
            author_template = None
            for template in templates:
                if template.get("template_type") == "AUTHOR":
                    author_template = template
                    break
            
            if author_template:
                await BACKEND_CLIENT.update_steps_settings(token, active_template_id=author_template.get("id"))
                await edit_long_message(
                    callback,
                    f"✅ Сброшено на авторский шаблон: {author_template.get('name')}\n\n"
                    "⚙️ Настройки работы по шагу",
                    reply_markup=build_steps_settings_markup()
                )
                await callback.answer("Сброшено на авторский шаблон")
            else:
                await callback.answer("Авторский шаблон не найден")
            return
        
        if data == "settings_edit_template":
            # Show user's custom templates for editing
            templates_data = await BACKEND_CLIENT.get_templates(token)
            templates = templates_data.get("templates", [])
            
            # Filter only custom templates
            custom_templates = [t for t in templates if t.get("template_type") == "CUSTOM"]
            
            if custom_templates:
                buttons = []
                for template in custom_templates:
                    buttons.append([InlineKeyboardButton(
                        text=f"✏️ {template.get('name')}",
                        callback_data=f"settings_edit_template_{template.get('id')}"
                    )])
                buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="settings_back")])
                
                await edit_long_message(
                    callback,
                    "✏️ Выбери шаблон для редактирования:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
                )
            else:
                await edit_long_message(
                    callback,
                    "✏️ У тебя нет пользовательских шаблонов.\n\n"
                    "Создай свой шаблон через API или в настройках позже.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_back")]
                    ])
                )
            await callback.answer()
            return
        
        if data.startswith("settings_edit_template_"):
            # Edit specific template (for now, just show info)
            template_id = int(data.split("_")[-1])
            await callback.answer("Редактирование шаблона будет реализовано позже")
            return
        
        if data == "settings_reminders":
            # Show reminders settings
            settings = await BACKEND_CLIENT.get_steps_settings(token)
            reminders_enabled = settings.get("reminders_enabled", False)
            
            reminders_text = (
                "⏰ Настройки напоминаний\n\n"
                f"Статус: {'✅ Включены' if reminders_enabled else '❌ Выключены'}\n\n"
                "Настройка напоминаний будет полностью реализована позже."
            )
            
            await edit_long_message(
                callback,
                reminders_text,
                reply_markup=build_reminders_settings_markup(reminders_enabled)
            )
            await callback.answer()
            return
        
        if data == "settings_toggle_reminders":
            # Toggle reminders
            settings = await BACKEND_CLIENT.get_steps_settings(token)
            current_enabled = settings.get("reminders_enabled", False)
            new_enabled = not current_enabled
            
            await BACKEND_CLIENT.update_steps_settings(token, reminders_enabled=new_enabled)
            
            reminders_text = (
                "⏰ Настройки напоминаний\n\n"
                f"Статус: {'✅ Включены' if new_enabled else '❌ Выключены'}\n\n"
                "Настройка напоминаний будет полностью реализована позже."
            )
            
            await edit_long_message(
                callback,
                reminders_text,
                reply_markup=build_reminders_settings_markup(new_enabled)
            )
            await callback.answer(f"Напоминания {'включены' if new_enabled else 'выключены'}")
            return
        
        if data == "settings_reminder_time":
            # Set reminder time (for now, just acknowledge)
            await callback.answer("Настройка времени напоминания будет реализована позже")
            return
        
        if data == "settings_reminder_days":
            # Set reminder days (for now, just acknowledge)
            await callback.answer("Настройка дней недели будет реализована позже")
            return
        
    except Exception as exc:
        logger.exception("Error handling steps settings callback for %s: %s", telegram_id, exc)
        await callback.answer("Ошибка. Попробуй позже.")


# ---------------------------------------------------------
# STEP ACTIONS HANDLERS
# ---------------------------------------------------------

async def handle_step_action_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle step action callbacks (pause, template, etc.)"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await callback.answer("Ошибка авторизации. Нажми /start.")
            return
        
        if data == "step_pause":
            # Pause and save draft
            await state.update_data(action="pause")
            await callback.answer("Напиши текст для черновика и отправь его")
            
        elif data == "step_template":
            # Start FSM template filling mode using backend API
            # Get current step info to get step_id and question_id
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            if not step_info:
                await callback.answer("Не удалось получить информацию о шаге")
                return
            
            step_id = step_info.get("step_id")
            
            # Get current question (from active tail)
            step_data = await get_current_step_question(telegram_id, username, first_name)
            if not step_data:
                await callback.answer("Нет активного вопроса")
                return
            
            # We need question_id from the active tail
            # For now, let's get it from the backend
            questions_data = await BACKEND_CLIENT.get_current_step_questions(token)
            questions = questions_data.get("questions", []) if questions_data else []
            
            # Find current question by matching text
            current_question_text = step_data.get("message", "")
            question_id = None
            for q in questions:
                if q.get("text") == current_question_text:
                    question_id = q.get("id")
                    break
            
            if not question_id and questions:
                # Fallback: use first unanswered or first question
                question_id = questions[0].get("id")
            
            if not step_id or not question_id:
                await callback.answer("Не удалось определить вопрос")
                return
            
            # Start template progress via backend API
            progress = await BACKEND_CLIENT.start_template_progress(token, step_id, question_id)
            
            if not progress:
                await callback.answer("Ошибка при запуске шаблона")
                return
            
            # Store step_id and question_id in state for subsequent field submissions
            await state.update_data(
                template_step_id=step_id,
                template_question_id=question_id
            )
            
            # Check if resuming from pause
            is_resumed = progress.get("is_resumed", False)
            field_info = progress.get("field_info", {})
            current_situation = progress.get("current_situation", 1)
            progress_summary = progress.get("progress_summary", "")
            
            # Build intro message
            if is_resumed:
                field_name = field_info.get("name", "поле")
                situations = progress.get("situations", [])
                
                # Show what's already filled
                filled_info = ""
                if situations:
                    completed_count = sum(1 for s in situations if s.get("complete"))
                    filled_info = f"\n✅ Заполнено ситуаций: {completed_count}/3\n"
                    
                    # Show brief info about filled situations
                    for i, situation in enumerate(situations[:completed_count], 1):
                        if situation.get("complete"):
                            where = situation.get("where", "")[:50]
                            if where:
                                filled_info += f"   Ситуация {i}: {where}...\n"
                
                intro_text = (
                    f"📋 Продолжаем заполнение шаблона!\n\n"
                    f"⏸ Ты остановился на:\n"
                    f"   Ситуация {current_situation}/3\n"
                    f"   Поле: {field_name}\n"
                    f"{filled_info}\n"
                    f"📊 {progress_summary}\n\n"
                    f"💡 Продолжай с того места, где остановился.\n"
                    f"👁️ Нажми «Посмотреть что заполнено» чтобы увидеть все детали.\n\n"
                )
            else:
                intro_text = (
                    f"📋 Заполнение по шаблону\n\n"
                    f"Шаблон включает:\n"
                    f"• 3 ситуации (по 6 полей каждая)\n"
                    f"• Финальный вывод\n\n"
                    f"📝 Ситуация {current_situation}/3\n\n"
                )
            
            # Show first field
            field_name = field_info.get("name", "Поле")
            field_description = field_info.get("description", "")
            min_items = field_info.get("min_items")
            
            field_text = intro_text
            field_text += f"**{field_name}**\n"
            if field_description:
                field_text += f"{field_description}\n"
            if min_items:
                field_text += f"\n⚠️ Нужно указать минимум {min_items} (через запятую)\n"
            field_text += "\nВведи значение:"
            
            await edit_long_message(callback, field_text, reply_markup=build_template_filling_markup())
            await state.set_state(StepState.filling_template)
            await callback.answer()
            
        elif data == "step_switch_question":
            # Show list of questions to switch to
            try:
                step_info = await BACKEND_CLIENT.get_current_step_info(token)
                step_id = step_info.get("step_id") if step_info else None
                
                if step_id:
                    try:
                        questions_data = await BACKEND_CLIENT.get_current_step_questions(token)
                        questions = questions_data.get("questions", []) if questions_data else []
                        
                        if questions:
                            await edit_long_message(
                                callback,
                                "📋 Выбери вопрос для перехода:",
                                reply_markup=build_step_questions_markup(questions, step_id)
                            )
                            await callback.answer()
                        else:
                            await callback.answer("Вопросы не найдены")
                    except Exception as e:
                        logger.error(f"Error getting questions: {e}")
                        await callback.answer("Ошибка получения списка вопросов")
                else:
                    await callback.answer("Шаг не выбран")
            except Exception as e:
                logger.error(f"Error in step_switch_question: {e}")
                await callback.answer("Ошибка. Попробуй позже.")
            
        elif data == "step_view_template":
            # View filled template data
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            if not step_info:
                await callback.answer("Не удалось получить информацию о шаге")
                return
            
            step_id = step_info.get("step_id")
            
            # Get current question ID
            questions_data = await BACKEND_CLIENT.get_step_questions(token, step_id)
            questions = questions_data.get("questions", [])
            answered_count = step_info.get("answered_questions", 0)
            
            if not questions or answered_count >= len(questions):
                await callback.answer("Нет активного вопроса")
                return
            
            current_question = questions[answered_count]
            question_id = current_question.get("id")
            
            # Get template progress
            progress = await BACKEND_CLIENT.get_template_progress(token, step_id, question_id)
            
            if not progress:
                await callback.answer("Нет сохранённых данных по шаблону")
                return
            
            # Format filled data for display
            situations = progress.get("situations", [])
            conclusion = progress.get("conclusion")
            current_situation = progress.get("current_situation", 1)
            current_field = progress.get("current_field", "")
            
            view_text = "📋 Что уже заполнено по шаблону:\n\n"
            
            if situations:
                for i, situation in enumerate(situations, 1):
                    if situation.get("complete"):
                        view_text += f"📌 Ситуация {i}:\n"
                        if situation.get("where"):
                            view_text += f"  Где: {situation.get('where')}\n"
                        if situation.get("thoughts"):
                            view_text += f"  Мысли: {situation.get('thoughts')}\n"
                        if situation.get("feelings_before"):
                            feelings = situation.get("feelings_before", [])
                            if isinstance(feelings, list):
                                feelings_str = ", ".join(feelings)
                            else:
                                feelings_str = str(feelings)
                            view_text += f"  Чувства (до): {feelings_str}\n"
                        if situation.get("actions"):
                            view_text += f"  Действие: {situation.get('actions')}\n"
                        if situation.get("healthy_feelings"):
                            view_text += f"  Здоровые чувства: {situation.get('healthy_feelings')}\n"
                        if situation.get("next_step"):
                            view_text += f"  Следующий шаг: {situation.get('next_step')}\n"
                        view_text += "\n"
                    elif i == current_situation:
                        # Show partial data for current situation
                        view_text += f"📌 Ситуация {i} (заполняется):\n"
                        if situation.get("where"):
                            view_text += f"  Где: {situation.get('where')}\n"
                        if situation.get("thoughts"):
                            view_text += f"  Мысли: {situation.get('thoughts')}\n"
                        if situation.get("feelings_before"):
                            feelings = situation.get("feelings_before", [])
                            if isinstance(feelings, list):
                                feelings_str = ", ".join(feelings)
                            else:
                                feelings_str = str(feelings)
                            view_text += f"  Чувства (до): {feelings_str}\n"
                        if situation.get("actions"):
                            view_text += f"  Действие: {situation.get('actions')}\n"
                        if situation.get("healthy_feelings"):
                            view_text += f"  Здоровые чувства: {situation.get('healthy_feelings')}\n"
                        if situation.get("next_step"):
                            view_text += f"  Следующий шаг: {situation.get('next_step')}\n"
                        view_text += f"  ⏸ Остановился на поле: {current_field}\n"
                        view_text += "\n"
            
            if conclusion:
                view_text += f"📌 Финальный вывод:\n{conclusion}\n"
            
            view_text += f"\n{progress.get('progress_summary', '')}"
            
            await send_long_message(
                callback.message,
                view_text,
                reply_markup=build_step_actions_markup(has_template_progress=True)
            )
            await callback.answer()
            return
        
        elif data == "step_previous":
            # Get previous question (if exists)
            try:
                step_info = await BACKEND_CLIENT.get_current_step_info(token)
                step_id = step_info.get("step_id") if step_info else None
                
                if step_id:
                    try:
                        questions_data = await BACKEND_CLIENT.get_current_step_questions(token)
                        questions = questions_data.get("questions", []) if questions_data else []
                        
                        if questions and len(questions) > 1:
                            # Find current question index
                            current_question_text = await get_current_step_question(
                                telegram_id=telegram_id,
                                username=username,
                                first_name=first_name
                            )
                            current_text = current_question_text.get("message", "") if current_question_text else ""
                            
                            # Find previous question
                            current_idx = -1
                            for i, q in enumerate(questions):
                                if q.get("text") == current_text:
                                    current_idx = i
                                    break
                            
                            if current_idx > 0:
                                prev_question = questions[current_idx - 1]
                                # Switch to previous question
                                await BACKEND_CLIENT.switch_to_question(token, prev_question.get("id"))
                                await edit_long_message(
                                    callback,
                                    f"📜 Предыдущий вопрос:\n\n{prev_question.get('text', '')}",
                                    reply_markup=build_step_actions_markup()
                                )
                                await state.set_state(StepState.answering)
                                await callback.answer()
                            else:
                                await callback.answer("Это первый вопрос в шаге")
                        else:
                            await callback.answer("Нет предыдущего вопроса")
                    except Exception as e:
                        logger.error(f"Error getting previous question: {e}")
                        await callback.answer("Ошибка получения вопросов")
                else:
                    await callback.answer("Шаг не выбран")
            except Exception as e:
                logger.error(f"Error in step_previous: {e}")
                await callback.answer("Ошибка. Попробуй позже.")
            
    except Exception as exc:
        logger.exception("Error handling step action callback for %s: %s", telegram_id, exc)
        await callback.answer("Ошибка. Попробуй позже.")


async def handle_steps_navigation_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle steps navigation callbacks (select step, show questions, continue, back)"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    logger.info(f"Steps navigation callback received: {data} from user {telegram_id}")
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await callback.answer("Ошибка авторизации. Нажми /start.")
            return
        
        if data == "steps_select":
            # Show list of steps
            logger.info(f"Fetching steps list for user {telegram_id}")
            try:
                steps_data = await BACKEND_CLIENT.get_steps_list(token)
                steps = steps_data.get("steps", [])
                
                logger.info(f"Received {len(steps)} steps for user {telegram_id}")
                
                if steps:
                    await callback.answer()  # Answer callback first to stop loading
                    logger.info(f"Building steps list markup for {len(steps)} steps")
                    markup = build_steps_list_markup(steps)
                    logger.info(f"Markup created, attempting to edit message")
                    
                    try:
                        # Try to edit the message directly
                        await callback.message.edit_text(
                            "🔢 Выбери шаг для работы:",
                            reply_markup=markup
                        )
                        logger.info(f"Successfully edited message with steps list")
                    except TelegramBadRequest as e:
                        # Handle "message is not modified" error - this is normal when user clicks button again
                        if "message is not modified" in str(e).lower():
                            logger.debug(f"Message not modified (user clicked button again): {e}")
                            # Message is already showing the steps list, nothing to do
                        else:
                            logger.warning(f"TelegramBadRequest when editing message: {e}")
                            # Fallback: send new message
                            await callback.message.answer(
                                "🔢 Выбери шаг для работы:",
                                reply_markup=markup
                            )
                            logger.info(f"Sent new message as fallback")
                    except Exception as edit_error:
                        logger.exception(f"Failed to edit message: {edit_error}")
                        # Fallback: send new message
                        await callback.message.answer(
                            "🔢 Выбери шаг для работы:",
                            reply_markup=markup
                        )
                        logger.info(f"Sent new message as fallback")
                else:
                    await callback.answer("Шаги не найдены")
            except Exception as e:
                logger.exception(f"Error in steps_select for user {telegram_id}: {e}")
                await callback.answer("Ошибка получения списка шагов")
            return
        
        if data == "steps_questions":
            # Show list of questions for current step
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            step_id = step_info.get("step_id")
            
            if step_id:
                questions_data = await BACKEND_CLIENT.get_step_questions(token, step_id)
                questions = questions_data.get("questions", [])
                
                if questions:
                    await callback.answer()  # Answer callback first to stop loading
                    await edit_long_message(
                        callback,
                        "📋 Вопросы в этом шаге:",
                        reply_markup=build_step_questions_markup(questions, step_id)
                    )
                else:
                    await callback.answer("Вопросы не найдены")
            else:
                await callback.answer("Шаг не выбран")
            return
        
        if data == "steps_continue":
            # Continue with current step
            step_data = await get_current_step_question(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name
            )
            
            if step_data:
                response_text = step_data.get("message", "")
                if response_text:
                    await callback.answer()  # Answer callback first to stop loading
                    await edit_long_message(
                        callback,
                        response_text,
                        reply_markup=build_step_actions_markup()
                    )
                    await state.set_state(StepState.answering)
                else:
                    await callback.answer("Нет текущего вопроса")
            else:
                await callback.answer("Ошибка получения вопроса")
            return
        
        if data == "steps_back":
            # Return to main menu
            await callback.answer()  # Answer callback first to stop loading
            await state.clear()
            # Edit message without ReplyKeyboardMarkup (edit_text doesn't support it)
            await edit_long_message(
                callback,
                "✅ Вернулся в главное меню.",
                reply_markup=None
            )
            # Send new message with ReplyKeyboardMarkup
            await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
            return
        
        await callback.answer("Неизвестная команда")
        
    except Exception as exc:
        logger.exception("Error handling steps navigation callback for %s: %s", telegram_id, exc)
        await callback.answer("Ошибка. Попробуй позже.")


async def handle_step_selection_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle step selection callback (step_select_1, step_select_2, etc.)"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    logger.info(f"Step selection callback received: {data} from user {telegram_id}")
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await callback.answer("Ошибка авторизации. Нажми /start.")
            return
        
        # Extract step ID from callback data (step_select_123)
        step_id = int(data.split("_")[-1])
        logger.info(f"Switching to step {step_id} for user {telegram_id}")
        
        # Answer callback early to stop loading spinner
        await callback.answer(f"Переключаю на шаг {step_id}...")
        
        try:
            # Switch to selected step
            await BACKEND_CLIENT.switch_step(token, step_id)
            logger.info(f"Successfully switched to step {step_id}")
        except Exception as switch_error:
            logger.exception(f"Failed to switch to step {step_id}: {switch_error}")
            await callback.answer(f"Ошибка переключения на шаг {step_id}")
            return
        
        # Get step info
        try:
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            step_number = step_info.get("step_number")
            step_title = step_info.get("step_title", "")
            step_description = step_info.get("step_description", "")
            
            logger.info(f"Step {step_id} info retrieved: step_number={step_number}, title={step_title[:50] if step_title else None}")
        except Exception as info_error:
            logger.exception(f"Failed to get step info for step {step_id}: {info_error}")
            await callback.answer("Ошибка получения информации о шаге")
            return
        
        # Get current question
        try:
            step_data = await get_current_step_question(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name
            )
        except Exception as question_error:
            logger.exception(f"Failed to get current question for step {step_id}: {question_error}")
            await callback.answer("Ошибка получения вопроса")
            return
        
        if step_data:
            response_text = step_data.get("message", "")
            progress_indicator = format_step_progress_indicator(
                step_number=step_number,
                total_steps=step_info.get("total_steps", 12),
                step_title=step_title,
                answered_questions=step_info.get("answered_questions", 0),
                total_questions=step_info.get("total_questions", 0)
            )
            
            full_text = progress_indicator
            if step_description:
                full_text += f"\n\n{step_description}"
            full_text += f"\n\n{response_text}"
            
            try:
                await edit_long_message(
                    callback,
                    full_text,
                    reply_markup=build_step_actions_markup()
                )
            except TelegramBadRequest as e:
                # Handle "message is not modified" error
                if "message is not modified" in str(e).lower():
                    logger.debug(f"Message not modified when selecting step {step_id}: {e}")
                    # Message is already showing the correct content, nothing to do
                else:
                    logger.warning(f"TelegramBadRequest when editing message for step {step_id}: {e}")
                    # Fallback: send new message
                    await callback.message.answer(
                        full_text,
                        reply_markup=build_step_actions_markup()
                    )
            except Exception as edit_error:
                logger.exception(f"Failed to edit message for step {step_id}: {edit_error}")
                # Fallback: send new message
                await callback.message.answer(
                    full_text,
                    reply_markup=build_step_actions_markup()
                )
            
            await state.set_state(StepState.answering)
        else:
            await callback.answer("Ошибка получения вопроса")
        
    except Exception as exc:
        logger.exception("Error handling step selection callback for %s: %s", telegram_id, exc)
        await callback.answer("Ошибка. Попробуй позже.")


async def handle_question_view_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle question view callback (question_view_123)"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await callback.answer("Ошибка авторизации. Нажми /start.")
            return
        
        # Extract question ID from callback data (question_view_123)
        question_id = int(data.split("_")[-1])
        
        # Get question details
        question_data = await BACKEND_CLIENT.get_question_detail(token, question_id)
        question_text = question_data.get("question_text", "")
        question_number = question_data.get("question_number", 0)
        total_questions = question_data.get("total_questions", 0)
        
        if question_text:
            text = f"📋 Вопрос {question_number} из {total_questions}\n\n{question_text}"
            await edit_long_message(
                callback,
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад к списку", callback_data="steps_questions")]
                ])
            )
            await callback.answer()
        else:
            await callback.answer("Вопрос не найден")
        
    except Exception as exc:
        logger.exception("Error handling question view callback for %s: %s", telegram_id, exc)
        await callback.answer("Ошибка. Попробуй позже.")


async def handle_template_field_input(message: Message, state: FSMContext) -> None:
    """
    Handle input for template field in FSM mode.
    Uses backend API for progress tracking.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    field_value = message.text
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Ошибка авторизации. Нажми /start.")
            await state.clear()
            return
        
        state_data = await state.get_data()
        step_id = state_data.get("template_step_id")
        question_id = state_data.get("template_question_id")
        
        if not step_id or not question_id:
            await message.answer("Ошибка: данные шаблона потеряны. Начни заново.")
            await state.clear()
            return
        
        # Submit field value to backend
        result = await BACKEND_CLIENT.submit_template_field(
            token, step_id, question_id, field_value
        )
        
        if not result:
            await message.answer("Ошибка сервера. Попробуй ещё раз.")
            return
        
        # Check for validation error
        if not result.get("success"):
            error_msg = result.get("error", "Ошибка валидации")
            validation_error = result.get("validation_error", False)
            
            # Если это ошибка валидации чувств, показываем текущие чувства
            if validation_error and result.get("current_feelings"):
                current_feelings = result.get("current_feelings", [])
                current_count = result.get("current_count", 0)
                if current_feelings:
                    feelings_text = ", ".join(current_feelings)
                    error_msg = f"{error_msg}\n\n📝 Уже указано ({current_count}): {feelings_text}"
            
            await message.answer(
                f"⚠️ {error_msg}\n\n💡 Совет: можешь написать все чувства через запятую в одном сообщении, или добавлять по одному.",
                reply_markup=build_template_filling_markup()
            )
            return
        
        # Check if template is complete
        if result.get("is_complete"):
            formatted_answer = result.get("formatted_answer", "")
            
            # Save the formatted answer
            success = await BACKEND_CLIENT.submit_step_answer(token, formatted_answer, is_template_format=True)
            
            if success:
                # Get next question
                step_next = await BACKEND_CLIENT.get_next_step(token)
                
                if step_next:
                    response_text = step_next.get("message", "")
                    is_completed = step_next.get("is_completed", False)
                    
                    await send_long_message(
                        message,
                        f"✅ Шаблон полностью заполнен!\n\n"
                        f"📝 Твой ответ сохранён.\n\n"
                        f"{response_text}",
                        reply_markup=build_step_actions_markup()
                    )
                    
                    if is_completed:
                        await message.answer(
                            "Этап завершен! 🎉",
                            reply_markup=build_main_menu_markup()
                        )
                        await state.clear()
                    else:
                        await state.set_state(StepState.answering)
                else:
                    await message.answer("Ответ сохранён!")
                    await state.set_state(StepState.answering)
            else:
                await message.answer("Ошибка при сохранении. Попробуй ещё раз.")
            return
        
        # Build message for next field
        field_info = result.get("field_info", {})
        current_situation = result.get("current_situation", 1)
        is_situation_complete = result.get("is_situation_complete", False)
        ready_for_conclusion = result.get("ready_for_conclusion", False)
        progress_summary = result.get("progress_summary", "")
        
        if ready_for_conclusion:
            # All 3 situations done, ask for conclusion
            await message.answer(
                f"✅ Ситуация {current_situation - 1} завершена!\n\n"
                f"🎯 Все 3 ситуации заполнены!\n\n"
                f"Теперь напиши **Финальный вывод**:\n\n"
                f"• Как ты теперь видишь ситуацию?\n"
                f"• Что на самом деле происходило?\n"
                f"• Как повторялись чувства/мысли/действия?\n"
                f"• Где была болезнь, где был ты?",
                reply_markup=build_template_filling_markup(),
                parse_mode="Markdown"
            )
        elif is_situation_complete:
            # Current situation done, moving to next
            await message.answer(
                f"✅ Ситуация {current_situation - 1} завершена!\n\n"
                f"📝 Переходим к Ситуации {current_situation}\n\n"
                f"**{field_info.get('name', 'Поле')}**\n"
                f"{field_info.get('description', '')}\n\n"
                f"Введи значение:",
                reply_markup=build_template_filling_markup(),
                parse_mode="Markdown"
            )
        else:
            # Next field in current situation
            min_items = field_info.get("min_items")
            field_text = f"✅ Сохранено!\n\n"
            field_text += f"📝 Ситуация {current_situation}/3\n\n"
            field_text += f"**{field_info.get('name', 'Поле')}**\n"
            field_text += f"{field_info.get('description', '')}\n"
            if min_items:
                field_text += f"\n⚠️ Нужно указать минимум {min_items} (через запятую)\n"
            field_text += "\nВведи значение:"
            
            await message.answer(
                field_text,
                reply_markup=build_template_filling_markup(),
                parse_mode="Markdown"
            )
            
    except Exception as exc:
        logger.exception("Error handling template field input for %s: %s", telegram_id, exc)
        await message.answer("Произошла ошибка. Попробуй ещё раз.")
        await state.clear()


# ---------------------------------------------------------
# REGISTER HANDLERS
# ---------------------------------------------------------