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
    dp.message(F.text == "🆘 Помощь (SOS)")(handle_sos)
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
    
    # 4.6. SOS Help Flow
    dp.callback_query(F.data.startswith("sos_"))(handle_sos_callback)
    dp.message(StateFilter(SosStates.chatting))(handle_sos_chat_message)
    dp.message(StateFilter(SosStates.custom_input))(handle_sos_custom_input)
    
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
    Checks if user has selected a template, if not - shows template selection.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Сначала нажми /start для авторизации.")
            return
        
        # Check if user has active template
        templates_data = await BACKEND_CLIENT.get_templates(token)
        active_template_id = templates_data.get("active_template_id")
        
        # If no active template, show template selection
        if active_template_id is None:
            await message.answer(
                "📋 Перед началом работы выбери шаблон для ответов:\n\n"
                "🧩 Авторский шаблон — структурированный шаблон с полями\n"
                "✍️ Свой шаблон — создай свой формат ответов\n\n"
                "Можно изменить позже в настройках.",
                reply_markup=build_template_selection_markup()
            )
            return
        
        # User has template, proceed with steps
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
                    # Save session context for STEPS
                    context_data = {
                        "step_number": step_number,
                        "step_title": step_info.get("step_title", ""),
                        "step_description": step_info.get("step_description", ""),
                        "current_question": response_text[:200],  # First 200 chars of question
                        "total_steps": step_info.get("total_steps", 12),
                        "answered_questions": step_info.get("answered_questions", 0),
                        "total_questions": step_info.get("total_questions", 0)
                    }
                    try:
                        await BACKEND_CLIENT.save_session_context(token, "STEPS", context_data)
                    except Exception as e:
                        logger.warning(f"Failed to save session context: {e}")
                    
                    # Show current step info with progress indicator
                    step_description = step_info.get("step_description", "")
                    full_text = progress_indicator
                    if step_description:
                        full_text += f"\n\n{step_description}"
                    full_text += f"\n\n{response_text}"
                    
                    await send_long_message(
                        message,
                        full_text,
                        reply_markup=build_step_actions_markup()
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
# DAY HANDLER (/day)
# ---------------------------------------------------------

async def handle_day(message: Message, state: FSMContext) -> None:
    """
    Handles /day command: Returns analysis and reflection message.
    IMPORTANT: Clears step answering state to prevent /day from being treated as step answer.
    """
    telegram_id = message.from_user.id
    
    # CRITICAL: Clear step answering state if active
    # This prevents /day from being processed as a step answer
    current_state = await state.get_state()
    if current_state == StepState.answering or current_state == StepState.filling_template:
        await state.clear()
        logger.info(f"Cleared step state for user {telegram_id} when switching to /day")
    
    try:
        backend_reply = await BACKEND_CLIENT.day(telegram_id=telegram_id, debug=False)
        
        reply_text = backend_reply.reply
        if backend_reply.log:
            log = backend_reply.log
            log.timestamp = int(datetime.datetime.utcnow().timestamp())
            USER_LOGS.setdefault(telegram_id, []).append(log)
        
        await send_long_message(message, reply_text, reply_markup=build_main_menu_markup())
    
    except Exception as exc:
        logger.exception("Failed to get response from /day endpoint: %s", exc)
        error_text = (
            "❌ Не удалось получить ответ от сервера.\n\n"
            "Произошла ошибка. Хочешь начать заново?"
        )
        await message.answer(error_text, reply_markup=build_error_markup())


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
            # Start template filling mode
            # Get active template
            templates_data = await BACKEND_CLIENT.get_templates(token)
            active_template_id = templates_data.get("active_template_id")
            
            if not active_template_id:
                await callback.answer("Сначала выбери шаблон в настройках")
                return
            
            # Find active template
            templates = templates_data.get("templates", [])
            active_template = None
            for template in templates:
                if template.get("id") == active_template_id:
                    active_template = template
                    break
            
            if not active_template:
                await callback.answer("Шаблон не найден")
                return
            
            # Get template structure
            structure = active_template.get("structure", {})
            
            # Convert structure dict to fields list if needed
            # Structure can be either:
            # 1. Dict with "fields" key: {"fields": [{"name": "...", "description": "..."}]}
            # 2. Dict with field keys: {"situation": "Ситуация", "thoughts": "Мысли", ...}
            # 3. Dict with detailed structure: {"situation": {"label": "...", "description": "...", "order": 1}, ...}
            # 4. Complex author template: {"version": 2, "header": {...}, "situations": {...}, ...}
            if "fields" in structure:
                fields = structure.get("fields", [])
            elif "header" in structure or "situations" in structure:
                # Complex author template format v2
                # Extract fields from header and situations.item_structure
                fields = []
                
                # Process header fields
                header = structure.get("header", {})
                for field_key, field_data in header.items():
                    if isinstance(field_data, dict) and not field_data.get("auto_fill"):
                        fields.append({
                            "key": f"header_{field_key}",
                            "name": field_data.get("label", field_key),
                            "description": field_data.get("description", ""),
                            "type": "header"
                        })
                
                # Process situations item structure
                situations = structure.get("situations", {})
                item_structure = situations.get("item_structure", {})
                if item_structure:
                    sorted_items = sorted(item_structure.items(), key=lambda x: x[1].get("order", 999) if isinstance(x[1], dict) else 999)
                    for field_key, field_data in sorted_items:
                        if isinstance(field_data, dict):
                            fields.append({
                                "key": f"situation_{field_key}",
                                "name": field_data.get("label", field_key),
                                "description": field_data.get("description", ""),
                                "example": field_data.get("example", ""),
                                "type": "situation"
                            })
                
                # Process conclusion
                conclusion = structure.get("conclusion", {})
                if isinstance(conclusion, dict) and conclusion.get("label"):
                    fields.append({
                        "key": "conclusion",
                        "name": conclusion.get("label", "Вывод"),
                        "description": conclusion.get("description", ""),
                        "type": "conclusion",
                        "optional": conclusion.get("optional", False)
                    })
            else:
                # Convert dict structure to fields list
                fields = []
                # Check if structure has detailed format (with label/description) or simple format
                # Skip non-dict values (like version: 2)
                dict_values = [(k, v) for k, v in structure.items() if isinstance(v, dict)]
                if dict_values:
                    sample_key, sample_value = dict_values[0]
                    if "label" in sample_value:
                        # Detailed format: {"situation": {"label": "...", "description": "...", "order": 1}}
                        sorted_items = sorted(dict_values, key=lambda x: x[1].get("order", 999))
                        for field_key, field_data in sorted_items:
                            fields.append({
                                "key": field_key,
                                "name": field_data.get("label", field_key),
                                "description": field_data.get("description", ""),
                                "min_items": field_data.get("min_items")
                            })
                
                # Also handle simple string values
                for field_key, field_label in structure.items():
                    # Skip non-field entries (like min_items, max_items, version, etc.)
                    if isinstance(field_label, (int, float, bool)):
                        continue
                    if isinstance(field_label, str):
                        fields.append({
                            "key": field_key,
                            "name": field_label,
                            "description": ""
                        })
            
            if not fields:
                await callback.answer("В шаблоне нет полей")
                return
            
            # Store template info in state
            await state.update_data(
                template_id=active_template_id,
                template_fields=fields,
                current_field_index=0,
                template_values={}
            )
            
            # Show first field
            first_field = fields[0]
            # Support both formats: {"name": "..."} or {"key": "...", "name": "..."}
            field_key = first_field.get("key") or first_field.get("name", "field_0")
            field_name = first_field.get("name", field_key)
            field_description = first_field.get("description", "")
            
            field_text = f"📋 Заполнение по шаблону\n\n"
            field_text += f"**{field_name}**\n"
            if field_description:
                field_text += f"{field_description}\n"
            min_items = first_field.get("min_items")
            if min_items:
                field_text += f"\n⚠️ Важно: нужно указать минимум {min_items} элемента(ов).\n"
            field_text += "\nВведи значение:"
            
            await edit_long_message(callback, field_text)
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
            
        elif data == "step_add_more":
            # Allow user to add more to current answer (reopen current question)
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            step_id = step_info.get("step_id")
            
            if step_id:
                # Get current question again
                step_data = await get_current_step_question(
                    telegram_id=telegram_id,
                    username=username,
                    first_name=first_name
                )
                
                if step_data:
                    response_text = step_data.get("message", "")
                    if response_text:
                        await edit_long_message(
                            callback,
                            f"➕ Добавь ещё к ответу:\n\n{response_text}",
                            reply_markup=build_step_actions_markup()
                        )
                        await state.set_state(StepState.answering)
                        await callback.answer("Можешь дополнить ответ")
                    else:
                        await callback.answer("Нет текущего вопроса")
                else:
                    await callback.answer("Ошибка получения вопроса")
            else:
                await callback.answer("Шаг не выбран")
            
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
    """Handle input for template field"""
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
        template_fields = state_data.get("template_fields", [])
        current_field_index = state_data.get("current_field_index", 0)
        template_values = state_data.get("template_values", {})
        
        if not template_fields or current_field_index >= len(template_fields):
            await message.answer("Ошибка: данные шаблона потеряны. Начни заново.")
            await state.clear()
            return
        
        # Save current field value
        current_field = template_fields[current_field_index]
        # Support both formats: {"name": "..."} or {"key": "...", "name": "..."}
        field_key = current_field.get("key") or current_field.get("name", f"field_{current_field_index}")
        field_name = current_field.get("name", field_key)
        template_values[field_key] = field_value
        
        # Check if there are more fields
        next_field_index = current_field_index + 1
        
        if next_field_index < len(template_fields):
            # Show next field
            next_field = template_fields[next_field_index]
            # Support both formats
            next_field_key = next_field.get("key") or next_field.get("name", "field")
            next_field_name = next_field.get("name", next_field_key)
            next_field_description = next_field.get("description", "")
            next_min_items = next_field.get("min_items")
            
            field_text = f"✅ Сохранено: {field_name}\n\n"
            field_text += f"**{next_field_name}**\n"
            if next_field_description:
                field_text += f"{next_field_description}\n"
            if next_min_items:
                field_text += f"\n⚠️ Важно: нужно указать минимум {next_min_items} элемента(ов).\n"
            field_text += "\nВведи значение:"
            
            await send_long_message(message, field_text)
            await state.update_data(
                current_field_index=next_field_index,
                template_values=template_values
            )
        else:
            # All fields filled, combine into JSON and submit
            import json
            combined_answer = json.dumps(template_values, ensure_ascii=False, indent=2)
            
            # Submit answer with template format flag
            success = await BACKEND_CLIENT.submit_step_answer(token, combined_answer, is_template_format=True)
            
            if success:
                # Get next question
                step_next = await BACKEND_CLIENT.get_next_step(token)
                
                if step_next:
                    response_text = step_next.get("message", "Ответ сохранён!")
                    is_completed = step_next.get("is_completed", False)
                    
                    await send_long_message(
                        message,
                        f"✅ Ответ по шаблону сохранён!\n\n{response_text}",
                        reply_markup=build_step_actions_markup()
                    )
                    
                    if is_completed:
                        await message.answer(
                            "Этап завершен! 🎉 Возвращаю в обычный режим.",
                            reply_markup=build_main_menu_markup()
                        )
                        await state.clear()
                    else:
                        await state.set_state(StepState.answering)
                else:
                    await message.answer("Ответ сохранён, но не удалось получить следующий вопрос.")
                    await state.clear()
            else:
                await message.answer("Ошибка при сохранении ответа. Попробуй ещё раз.")
                await state.clear()
            
    except Exception as exc:
        logger.exception("Error handling template field input for %s: %s", telegram_id, exc)
        await message.answer("Произошла ошибка. Попробуй ещё раз.")
        await state.clear()


# ---------------------------------------------------------
# REGISTER HANDLERS
# ---------------------------------------------------------