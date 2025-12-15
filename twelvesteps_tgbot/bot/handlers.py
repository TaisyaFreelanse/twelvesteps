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
    build_step_answer_mode_markup,
    build_steps_settings_markup,
    build_template_selection_settings_markup,
    build_reminders_settings_markup,
    # New imports for Settings, Progress, Thanks, Feelings
    build_main_settings_markup,
    build_language_settings_markup,
    build_step_settings_markup,
    build_profile_settings_markup,
    build_about_me_main_markup,
    build_free_story_markup,
    build_mini_survey_markup,
    build_settings_steps_list_markup,
    build_settings_questions_list_markup,
    build_settings_select_step_for_question_markup,
    build_progress_step_markup,
    build_progress_main_markup,
    build_progress_view_answers_steps_markup,
    build_progress_view_answers_questions_markup,
    build_thanks_menu_markup,
    build_thanks_history_markup,
    build_feelings_categories_markup,
    build_feelings_list_markup,
    build_all_feelings_markup,
    build_feelings_category_markup,
    build_fears_markup,
    FEELINGS_CATEGORIES,
    FEARS_LIST,
    # FAQ/Instructions:
    build_faq_menu_markup,
    build_faq_section_markup,
    FAQ_SECTIONS
)
from bot.utils import split_long_message, send_long_message, edit_long_message
from bot.onboarding import OnboardingStates, register_onboarding_handlers

logger = logging.getLogger(__name__)

USER_LOGS: dict[int, list[Log]] = {}

# --- STATES ---
class StepState(StatesGroup):
    answering = State()  # User is currently answering a step question
    answer_mode = State()  # User is in answer mode (can save draft, edit, etc.)
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


class ThanksStates(StatesGroup):
    adding_entry = State()  # User is adding a gratitude entry


class AboutMeStates(StatesGroup):
    adding_entry = State()  # User is adding an entry to an about section


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
    dp.message(F.text == "📘 Чувства")(handle_feelings)
    dp.message(F.text == "🙏 Благодарности")(handle_thanks_menu)
    dp.message(F.text == "⚙️ Настройки")(handle_main_settings)
    dp.message(F.text == "📎 Инструкция")(handle_faq)

    # 2. Onboarding Flow
    register_onboarding_handlers(dp)

    # 3. Step Answering Flow (Only works if state is StepState.answering or StepState.answer_mode)
    dp.message(StateFilter(StepState.answering))(handle_step_answer)
    dp.message(StateFilter(StepState.answer_mode))(handle_step_answer_mode)
    dp.message(StateFilter(StepState.filling_template))(handle_template_field_input)
    dp.message(Command(commands=["qa_open"]))(qa_open)
    
    # 4. Profile Flow
    # IMPORTANT: More specific handlers must be registered BEFORE general ones
    # 4.9. Main Settings Flow (main_settings_ prefix) - register BEFORE profile_ to avoid conflicts
    dp.callback_query(F.data.startswith("main_settings_"))(handle_main_settings_callback)
    dp.callback_query(F.data.startswith("lang_"))(handle_language_callback)
    dp.callback_query(F.data.startswith("step_settings_"))(handle_step_settings_callback)
    dp.callback_query(F.data.startswith("profile_settings_"))(handle_profile_settings_callback)
    dp.callback_query(F.data.startswith("about_"))(handle_about_callback)
    
    # Now register general profile_ handler (after profile_settings_)
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
    dp.message(StateFilter(AboutMeStates.adding_entry))(handle_about_entry_input)
    
    # 4.10. Progress Flow
    dp.callback_query(F.data.startswith("progress_"))(handle_progress_callback)
    
    # 4.11. Thanks/Gratitude Flow
    dp.callback_query(F.data.startswith("thanks_"))(handle_thanks_callback)
    dp.message(StateFilter(ThanksStates.adding_entry))(handle_thanks_entry_input)
    
    # 4.12. Feelings Flow
    dp.callback_query(F.data.startswith("feelings_"))(handle_feelings_callback)
    dp.callback_query(F.data.startswith("feeling_"))(handle_feeling_selection_callback)
    
    # 4.13. FAQ/Instructions Flow
    dp.callback_query(F.data.startswith("faq_"))(handle_faq_callback)

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
                    
                    # Build compact status header
                    full_text = f"{progress_indicator}\n\n❔{response_text}"
                    
                    if template_progress:
                        full_text = f"{progress_indicator}\n\n⏸ Есть сохранённый прогресс по шаблону\n📊 {template_progress.get('progress_summary', '')}\n\n❔{response_text}"
                    
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
                    
                    # Store step description in state for toggle
                    await state.update_data(step_description=step_info.get("step_description", ""))
                    
                    await send_long_message(
                        message,
                        full_text,
                        reply_markup=build_step_actions_markup(has_template_progress=bool(template_progress), show_description=False)
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

async def handle_step_answer_mode(message: Message, state: FSMContext) -> None:
    """
    Handles text input in answer mode - supports draft saving, editing, and completion.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    user_text = message.text

    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Ошибка авторизации. Нажми /start.")
            await state.clear()
            return
        
        state_data = await state.get_data()
        action = state_data.get("action")
        
        if action == "save_draft":
            # Save as draft
                await BACKEND_CLIENT.save_draft(token, user_text)
            await state.update_data(action=None, current_draft=user_text)
            
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            step_data = await get_current_step_question(telegram_id, username, first_name)
            if step_data:
                response_text = step_data.get("message", "")
                progress_indicator = format_step_progress_indicator(
                    step_number=step_info.get("step_number"),
                    total_steps=step_info.get("total_steps", 12),
                    step_title=step_info.get("step_title"),
                    answered_questions=step_info.get("answered_questions", 0),
                    total_questions=step_info.get("total_questions", 0)
                )
                full_text = (
                    f"{progress_indicator}\n\n"
                    f"❔{response_text}\n\n"
                    f"📝 Поле для ответа:\n"
                    f"💾 Черновик сохранён: {user_text[:100]}{'...' if len(user_text) > 100 else ''}"
                )
                await message.answer(
                    "✅ Черновик сохранён!",
                    reply_markup=build_step_answer_mode_markup()
                )
            return
        
        if action == "edit_answer":
            # Edit previous answer - save as new answer
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
            
            if step_next.get("error"):
                error_message = step_next.get("message", "Ошибка валидации")
                await message.answer(
                    f"{error_message}\n\n"
                    "Попробуй ещё раз:",
                    reply_markup=build_step_answer_mode_markup()
                )
                return
            
            # Answer saved successfully
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            response_text = step_next.get("message", "Ответ обновлён.")
            is_completed = step_next.get("is_completed", False)
            
            if step_info.get("step_number"):
                progress_indicator = format_step_progress_indicator(
                    step_number=step_info.get("step_number", 0),
                    total_steps=step_info.get("total_steps", 12),
                    step_title=step_info.get("step_title"),
                    answered_questions=step_info.get("answered_questions", 0),
                    total_questions=step_info.get("total_questions", 0)
                )
                full_response = f"{progress_indicator}\n\n✅ Ответ обновлён!\n\n❔{response_text}"
            else:
                full_response = f"✅ Ответ обновлён!\n\n❔{response_text}"
            
            await send_long_message(message, full_response, reply_markup=build_step_actions_markup(show_description=False))
                await state.update_data(action=None)
                await state.set_state(StepState.answering)
            
            if is_completed:
                await message.answer("Этап завершен! 🎉 Возвращаю в обычный режим.", reply_markup=build_main_menu_markup())
                await state.clear()
            return
        
        if action == "complete":
            # Complete answer and move to next
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
            
            if step_next.get("error"):
                error_message = step_next.get("message", "Ошибка валидации")
                await message.answer(
                    f"{error_message}\n\n"
                    "Ответ должен быть достаточно подробным. Попробуй ещё раз:",
                    reply_markup=build_step_answer_mode_markup()
                )
                return
            
            # Answer completed successfully
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            response_text = step_next.get("message", "Ответ принят.")
            is_completed = step_next.get("is_completed", False)
            
            if step_info.get("step_number"):
                progress_indicator = format_step_progress_indicator(
                    step_number=step_info.get("step_number", 0),
                    total_steps=step_info.get("total_steps", 12),
                    step_title=step_info.get("step_title"),
                    answered_questions=step_info.get("answered_questions", 0),
                    total_questions=step_info.get("total_questions", 0)
                )
                full_response = f"{progress_indicator}\n\n✅ Ответ завершён и сохранён!\n\n❔{response_text}"
            else:
                full_response = f"✅ Ответ завершён и сохранён!\n\n❔{response_text}"
            
            await send_long_message(message, full_response, reply_markup=build_step_actions_markup(show_description=False))
            await state.update_data(action=None, current_draft="")
            await state.set_state(StepState.answering)
            
            if is_completed:
                await message.answer("Этап завершен! 🎉 Возвращаю в обычный режим.", reply_markup=build_main_menu_markup())
                await state.clear()
            return
        
        # Default: just save as draft if no action specified
        await BACKEND_CLIENT.save_draft(token, user_text)
        await state.update_data(current_draft=user_text)
        await message.answer(
            "💾 Текст сохранён как черновик.\n\n"
            "Используй кнопки для управления:",
            reply_markup=build_step_answer_mode_markup()
        )
        
    except Exception as exc:
        logger.exception("Error processing step answer mode: %s", exc)
        await message.answer("❌ Произошла ошибка. Попробуй ещё раз.")


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
        # Normal answer processing (direct submission without draft mode)
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
            full_response = f"{progress_indicator}\n\n✅ Ответ сохранён!\n\n❔{response_text}"
            
            # Store step description in state
            await state.update_data(step_description=step_info.get("step_description", ""))
        else:
            full_response = f"✅ Ответ сохранён!\n\n❔{response_text}"

        await send_long_message(message, full_response, reply_markup=build_step_actions_markup(show_description=False))

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
        
        if data == "sos_back":
            # Return to previous screen (step work or main menu)
            state_data = await state.get_data()
            previous_state = state_data.get("previous_state")
            current_state = await state.get_state()
            
            # Check if we were in step answering mode or currently in step answering
            if previous_state == StepState.answering or current_state == StepState.answering or str(previous_state) == str(StepState.answering):
                # Return to step work
                step_info = await BACKEND_CLIENT.get_current_step_info(token)
                if step_info:
                    step_data = await get_current_step_question(telegram_id, username, first_name)
                    if step_data:
                        response_text = step_data.get("message", "")
                        if response_text:
                            progress_indicator = format_step_progress_indicator(
                                step_number=step_info.get("step_number"),
                                total_steps=step_info.get("total_steps", 12),
                                step_title=step_info.get("step_title"),
                                answered_questions=step_info.get("answered_questions", 0),
                                total_questions=step_info.get("total_questions", 0)
                            )
                            full_text = f"{progress_indicator}\n\n{response_text}"
                            await edit_long_message(
                                callback,
                                full_text,
                                reply_markup=build_step_actions_markup()
                            )
                            await state.set_state(StepState.answering)
                            await safe_answer_callback(callback)
                            return
            
            # Default: return to main menu
            await state.clear()
            await edit_long_message(
                callback,
                "Главное меню:",
                reply_markup=None
            )
            await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
            await safe_answer_callback(callback)
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
                "question": "Не понял вопрос",
                "examples": "Хочу примеры",
                "direction": "Помоги понять куда смотреть",
                "memory": "Помоги понять куда смотреть",  # backwards compatibility
                "support": "Просто тяжело"
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
            
            # For "question" type, clean up the response - remove extra formatting
            if help_type == "question":
                # Remove "Простыми словами:", "Про что это:", "Можно понять как:" sections
                lines = reply_text.split("\n")
                cleaned_lines = []
                skip_until_empty = False
                for i, line in enumerate(lines):
                    if any(marker in line for marker in ["**Простыми словами:**", "**Про что это:**", "**Можно понять как:**", "Простыми словами:", "Про что это:", "Можно понять как:"]):
                        skip_until_empty = True
                        continue
                    if skip_until_empty and line.strip() == "":
                        skip_until_empty = False
                        continue
                    if not skip_until_empty:
                        cleaned_lines.append(line)
                reply_text = "\n".join(cleaned_lines).strip()
            
            # For "examples" type, ensure we show examples
            if help_type == "examples" and "пример" not in reply_text.lower() and "example" not in reply_text.lower():
                # If no examples in response, add a note
                reply_text += "\n\n💡 Если нужны конкретные примеры, напиши мне об этом."
            
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
# FEELINGS HANDLER
# ---------------------------------------------------------

async def handle_feelings(message: Message, state: FSMContext) -> None:
    """Handle Feelings button - show feelings categories menu"""
    # Show only menu with categories, no text
    await message.answer("📘 Чувства", reply_markup=build_all_feelings_markup())


async def handle_feelings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle feelings navigation callbacks"""
    data = callback.data
    
    if data == "feelings_back":
        # Return to main menu
        await callback.message.delete()
        await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
        await callback.answer()
        return
    
    if data == "feelings_categories":
        # Show all categories menu only
        await callback.message.edit_text("📘 Чувства", reply_markup=build_all_feelings_markup())
        await callback.answer()
        return
    
    if data.startswith("feelings_cat_"):
        category = data.replace("feelings_cat_", "")
        
        # Find the full category name
        full_category = None
        for cat_name in FEELINGS_CATEGORIES.keys():
            if cat_name == category or category in cat_name:
                full_category = cat_name
                break
        
        if full_category:
            # Show only category name, no feelings list
            await callback.message.edit_text(
                f"{full_category}",
                reply_markup=build_feelings_category_markup(full_category)
            )
        await callback.answer()
        return
    
    if data == "feelings_fears":
        # Show fears list
        fears_text = "⚠️ СТРАХИ\n\n" + "\n".join([f"• {fear}" for fear in FEARS_LIST])
        fears_text += "\n\n💡 Нажми на страх, чтобы скопировать:"
        
        await callback.message.edit_text(fears_text, reply_markup=build_fears_markup())
        await callback.answer()
        return
    
    if data == "feelings_noop":
        # Category header clicked - do nothing
        await callback.answer()
        return
    
    await callback.answer()


async def handle_feeling_selection_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle feeling selection - show the feeling for copying"""
    data = callback.data
    
    if data.startswith("feeling_copy_") or data.startswith("feeling_select_"):
        feeling = data.replace("feeling_copy_", "").replace("feeling_select_", "")
        
        # Show the feeling so user can copy it
        await callback.answer(f"💡 {feeling}", show_alert=True)
        return
    
    await callback.answer()


# ---------------------------------------------------------
# FAQ HANDLER (Инструкция)
# ---------------------------------------------------------

async def handle_faq(message: Message, state: FSMContext) -> None:
    """Handle FAQ command - show instructions menu"""
    faq_text = "📎 ИНСТРУКЦИИ — КАК ЭТО РАБОТАЕТ\n\nВыбери раздел для просмотра:"
    await message.answer(faq_text, reply_markup=build_faq_menu_markup())


async def handle_faq_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle FAQ/Instructions callbacks"""
    data = callback.data
    
    if data == "faq_back":
        # Return to main menu
        await callback.message.delete()
        await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
        await callback.answer()
        return
    
    if data == "faq_menu":
        # Return to FAQ menu
        faq_text = "📎 ИНСТРУКЦИИ — КАК ЭТО РАБОТАЕТ\n\nВыбери раздел для просмотра:"
        await callback.message.edit_text(faq_text, reply_markup=build_faq_menu_markup())
        await callback.answer()
        return
    
    if data.startswith("faq_section_"):
        section_name = data.replace("faq_section_", "")
        section_text = FAQ_SECTIONS.get(section_name)
        
        if section_text:
            await edit_long_message(
                callback,
                section_text,
                reply_markup=build_faq_section_markup()
            )
        else:
            await callback.answer("Раздел не найден")
        await callback.answer()
        return
    
    await callback.answer()


# ---------------------------------------------------------
# MAIN SETTINGS HANDLERS
# ---------------------------------------------------------

async def handle_main_settings(message: Message, state: FSMContext) -> None:
    """Handle main settings button - show settings menu"""
    settings_text = (
        "⚙️ Настройки\n\n"
        "Выбери раздел настроек:"
    )
    await message.answer(settings_text, reply_markup=build_main_settings_markup())


async def handle_main_settings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle main settings callbacks"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    if data == "main_settings_back":
        # Return to main menu
        await callback.message.delete()
        await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
        await callback.answer()
        return
    
    if data == "main_settings_reminders":
        # Show reminders settings
        await callback.message.edit_text(
            "🔔 Напоминания\n\n"
            "Настрой напоминания для регулярной практики.",
            reply_markup=build_reminders_settings_markup(reminders_enabled=False)
        )
        await callback.answer()
        return
    
    if data == "main_settings_language":
        # Show language settings
        await callback.message.edit_text(
            "🌐 Язык интерфейса\n\n"
            "Выбери язык:",
            reply_markup=build_language_settings_markup("ru")
        )
        await callback.answer()
        return
    
    if data == "main_settings_profile":
        # Show profile settings
        await callback.message.edit_text(
            "🪪 Мой профиль\n\n"
            "Настройки профиля:",
            reply_markup=build_profile_settings_markup()
        )
        await callback.answer()
        return
    
    if data == "main_settings_steps":
        # Show steps settings (templates and reminders)
        try:
            token = await get_or_fetch_token(telegram_id, username, first_name)
            if not token:
                await callback.answer("Ошибка авторизации")
                return
            
            # Get current settings
            settings = await BACKEND_CLIENT.get_steps_settings(token)
            active_template_name = settings.get("active_template_name", "Не выбран")
            reminders_enabled = settings.get("reminders_enabled", False)
            
            settings_text = (
                "⚙️ Настройки работы по шагу\n\n"
                f"⚙️ Активный шаблон: {active_template_name}\n"
                f"⏰ Напоминания: {'✅ Включены' if reminders_enabled else '❌ Выключены'}\n\n"
                "Выбери настройку для изменения:"
            )
            
            await callback.message.edit_text(
                settings_text,
                reply_markup=build_steps_settings_markup()
            )
        except Exception as e:
            logger.exception("Error loading steps settings: %s", e)
            await callback.answer("Ошибка загрузки настроек")
        await callback.answer()
        return
    
    await callback.answer()


async def handle_language_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle language selection"""
    data = callback.data
    
    if data == "lang_ru":
        await callback.message.edit_text(
            "🌐 Язык интерфейса\n\n"
            "✅ Выбран русский язык.",
            reply_markup=build_language_settings_markup("ru")
        )
        await callback.answer("Выбран русский язык")
        return
    
    if data == "lang_en":
        await callback.message.edit_text(
            "🌐 Interface Language\n\n"
            "✅ English selected.\n\n"
            "(English interface coming soon)",
            reply_markup=build_language_settings_markup("en")
        )
        await callback.answer("English selected (coming soon)")
        return
    
    await callback.answer()


async def handle_step_settings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle step-specific settings callbacks"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    if data == "step_settings_select_step":
        # Show list of steps to select
        try:
            token = await get_or_fetch_token(telegram_id, username, first_name)
            if token:
                steps_data = await BACKEND_CLIENT.get_all_steps(token)
                steps = steps_data.get("steps", []) if steps_data else []
                
                await callback.message.edit_text(
                    "🪜 Выбрать шаг вручную\n\n"
                    "Выбери номер шага:",
                    reply_markup=build_settings_steps_list_markup(steps)
                )
        except Exception as e:
            logger.exception("Error loading steps: %s", e)
            await callback.answer("Ошибка загрузки шагов")
        await callback.answer()
        return
    
    if data.startswith("step_settings_select_"):
        # User selected a step - switch to it
        try:
            step_id = int(data.split("_")[-1])
            token = await get_or_fetch_token(telegram_id, username, first_name)
            if token:
                result = await BACKEND_CLIENT.switch_step(token, step_id)
                if result:
                    await callback.message.edit_text(
                        f"✅ Переключено на шаг {step_id}\n\n"
                        "Теперь ты работаешь с этим шагом.",
                        reply_markup=build_step_settings_markup()
                    )
                else:
                    await callback.answer("Ошибка переключения шага")
        except Exception as e:
            logger.exception("Error switching step: %s", e)
            await callback.answer("Ошибка переключения шага")
        await callback.answer()
        return
    
    if data == "step_settings_select_question":
        # Show list of steps first, then questions
        try:
            token = await get_or_fetch_token(telegram_id, username, first_name)
            if token:
                steps_data = await BACKEND_CLIENT.get_all_steps(token)
                steps = steps_data.get("steps", []) if steps_data else []
                
                await callback.message.edit_text(
                    "🗂 Выбрать вопрос вручную\n\n"
                    "Сначала выбери шаг:",
                    reply_markup=build_settings_select_step_for_question_markup(steps)
                )
        except Exception as e:
            logger.exception("Error loading steps: %s", e)
            await callback.answer("Ошибка загрузки шагов")
        await callback.answer()
        return
    
    if data.startswith("step_settings_question_step_"):
        # User selected a step, now show questions
        try:
            step_id = int(data.split("_")[-1])
            token = await get_or_fetch_token(telegram_id, username, first_name)
            if token:
                questions_data = await BACKEND_CLIENT.get_step_questions(token, step_id)
                questions = questions_data.get("questions", []) if questions_data else []
                
                await callback.message.edit_text(
                    f"🗂 Выбрать вопрос вручную\n\n"
                    f"Шаг {step_id}\n"
                    "Выбери номер вопроса:",
                    reply_markup=build_settings_questions_list_markup(questions, step_id)
                )
        except Exception as e:
            logger.exception("Error loading questions: %s", e)
            await callback.answer("Ошибка загрузки вопросов")
        await callback.answer()
        return
    
    if data.startswith("step_settings_question_"):
        # User selected a question - switch to it
        try:
            question_id = int(data.split("_")[-1])
            token = await get_or_fetch_token(telegram_id, username, first_name)
            if token:
                result = await BACKEND_CLIENT.switch_to_question(token, question_id)
                if result:
                    await callback.message.edit_text(
                        f"✅ Переключено на вопрос {question_id}\n\n"
                        "Теперь ты работаешь с этим вопросом.",
                        reply_markup=build_step_settings_markup()
                    )
                else:
                    await callback.answer("Ошибка переключения вопроса")
        except Exception as e:
            logger.exception("Error switching question: %s", e)
            await callback.answer("Ошибка переключения вопроса")
        await callback.answer()
        return
    
    await callback.answer()


async def handle_profile_settings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle profile settings callbacks"""
    data = callback.data
    telegram_id = callback.from_user.id
    
    # #region agent log
    import json
    with open(r"c:\Users\Admin\Desktop\twelvesteps\twelvesteps\.cursor\debug.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": "A", "location": "handlers.py:1678", "message": "handle_profile_settings_callback called", "data": {"telegram_id": telegram_id, "callback_data": data}, "timestamp": __import__("time").time() * 1000}) + "\n")
    # #endregion
    
    try:
        # #region agent log
        with open(r"c:\Users\Admin\Desktop\twelvesteps\twelvesteps\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": "B", "location": "handlers.py:1681", "message": "Checking callback data", "data": {"data": data, "is_back": data == "profile_settings_back", "is_about": data == "profile_settings_about"}, "timestamp": __import__("time").time() * 1000}) + "\n")
        # #endregion
        
        if data == "profile_settings_back":
            # Back to main settings
            # #region agent log
            with open(r"c:\Users\Admin\Desktop\twelvesteps\twelvesteps\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": "C", "location": "handlers.py:1683", "message": "Handling profile_settings_back", "data": {}, "timestamp": __import__("time").time() * 1000}) + "\n")
            # #endregion
            await callback.message.edit_text(
                "⚙️ Настройки\n\n"
                "Выбери раздел настроек:",
                reply_markup=build_main_settings_markup()
            )
            await callback.answer()
            return
        
        if data == "profile_settings_about":
            # Show main menu for "Tell about yourself"
            # #region agent log
            with open(r"c:\Users\Admin\Desktop\twelvesteps\twelvesteps\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": "D", "location": "handlers.py:1693", "message": "Handling profile_settings_about", "data": {}, "timestamp": __import__("time").time() * 1000}) + "\n")
            # #endregion
            await callback.answer("Загружаю меню...")
            await callback.message.edit_text(
                "🪪 Расскажи о себе\n\n"
                "Выбери способ:",
                reply_markup=build_about_me_main_markup()
            )
            # #region agent log
            with open(r"c:\Users\Admin\Desktop\twelvesteps\twelvesteps\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": "D", "location": "handlers.py:1699", "message": "profile_settings_about completed successfully", "data": {}, "timestamp": __import__("time").time() * 1000}) + "\n")
            # #endregion
            return
        
        # #region agent log
        with open(r"c:\Users\Admin\Desktop\twelvesteps\twelvesteps\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": "E", "location": "handlers.py:1701", "message": "Unknown callback data, answering with default", "data": {"data": data}, "timestamp": __import__("time").time() * 1000}) + "\n")
        # #endregion
        await callback.answer()
    except Exception as e:
        # #region agent log
        with open(r"c:\Users\Admin\Desktop\twelvesteps\twelvesteps\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": "F", "location": "handlers.py:1703", "message": "Exception in handle_profile_settings_callback", "data": {"error": str(e), "error_type": type(e).__name__}, "timestamp": __import__("time").time() * 1000}) + "\n")
        # #endregion
        logger.exception("Error in handle_profile_settings_callback: %s", e)
        try:
            await callback.answer("Ошибка. Попробуй позже.")
        except:
            pass


async def handle_about_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle about me section callbacks"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        if data == "about_back":
            # #region agent log
            import json
            with open(r"c:\Users\Admin\Desktop\twelvesteps\twelvesteps\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId": "debug-session", "runId": "run1", "hypothesisId": "H", "location": "handlers.py:1725", "message": "Handling about_back", "data": {}, "timestamp": __import__("time").time() * 1000}) + "\n")
            # #endregion
            await callback.answer()
            await callback.message.edit_text(
                "🪪 Расскажи о себе\n\n"
                "Выбери способ:",
                reply_markup=build_about_me_main_markup()
            )
            return
        
        if data == "about_free_story":
            # Show free story section
            await callback.answer()
            await callback.message.edit_text(
                "✍️ Свободный рассказ\n\n"
                "Здесь ты можешь свободно рассказать о себе.",
                reply_markup=build_free_story_markup()
            )
            return
    
        if data == "about_add_free":
            # Add free story entry
            await callback.answer()
            await state.update_data(about_section="about_free")
            await state.set_state(AboutMeStates.adding_entry)
            
            await callback.message.edit_text(
                "✍️ Свободный рассказ\n\n"
                "Напиши то, что хочешь добавить:"
            )
            return
        
        if data == "about_history_free":
            # View free story history
            await callback.answer()
            try:
                token = await get_or_fetch_token(telegram_id, username, first_name)
                if token:
                    # TODO: Load history from backend
                    history_text = "🗃️ История\n\n(История пока пуста)"
                    await callback.message.edit_text(
                        history_text,
                        reply_markup=build_free_story_markup()
                    )
            except Exception as e:
                logger.exception("Error loading history: %s", e)
                await callback.message.edit_text(
                    "🗃️ История\n\n(История пока пуста)",
                    reply_markup=build_free_story_markup()
                )
            return
    
        if data == "about_mini_survey":
            # Start mini survey
            await callback.answer("Загружаю вопросы...")
            
            try:
                token = await get_or_fetch_token(telegram_id, username, first_name)
                if not token:
                    await callback.message.edit_text(
                        "❌ Ошибка авторизации. Нажми /start.",
                        reply_markup=build_about_me_main_markup()
                    )
                    return
                
                logger.info(f"Loading profile sections for user {telegram_id}")
                
                # Get first section with questions - optimize by getting only first section
                sections_data = await BACKEND_CLIENT.get_profile_sections(token)
                logger.info(f"Received sections_data: {sections_data}")
                
                sections = sections_data.get("sections", []) if sections_data else []
                logger.info(f"Found {len(sections)} sections")
                
                if not sections:
                    logger.warning("No sections found in response")
                    await callback.message.edit_text(
                        "👣 Пройти мини-опрос\n\n"
                        "Вопросы пока не доступны. Разделы не найдены.",
                        reply_markup=build_about_me_main_markup()
                    )
                    return
                
                # Get first section only (optimize - don't loop through all)
                first_section = sections[0] if sections else None
                if not first_section:
                    logger.warning("First section is None")
                    await callback.message.edit_text(
                        "👣 Пройти мини-опрос\n\n"
                        "Вопросы пока не доступны.",
                        reply_markup=build_about_me_main_markup()
                    )
                    return
                
                section_id = first_section.get("id")
                logger.info(f"Loading section detail for section_id={section_id}")
                
                # Get section detail for first section only
                section_detail = await BACKEND_CLIENT.get_section_detail(token, section_id)
                logger.info(f"Received section_detail: {section_detail}")
                
                section_info = section_detail.get("section", {}) if section_detail else {}
                questions = section_info.get("questions", [])
                logger.info(f"Found {len(questions)} questions in section {section_id}")
                
                if not questions:
                    logger.warning(f"No questions found in section {section_id}")
                    await callback.message.edit_text(
                        "👣 Пройти мини-опрос\n\n"
                        f"В разделе '{section_info.get('name', 'Неизвестный')}' пока нет вопросов.",
                        reply_markup=build_about_me_main_markup()
                    )
                    return
                
                first_question = questions[0]
                logger.info(f"First question: id={first_question.get('id')}, text={first_question.get('question_text', '')[:50]}...")
                
                # Store survey state
                await state.update_data(
                    survey_section_id=section_id,
                    survey_question_id=first_question.get("id"),
                    survey_question_index=0,
                    survey_mode=True,
                    survey_is_generated=False
                )
                await state.set_state(ProfileStates.answering_question)
                
                question_text = first_question.get("question_text", "")
                is_optional = first_question.get("is_optional", False)
                
                await callback.message.edit_text(
                    f"👣 Пройти мини-опрос\n\n"
                    f"❓ {question_text}",
                    reply_markup=build_mini_survey_markup(first_question.get("id"), can_skip=is_optional)
                )
            except Exception as e:
                logger.exception("Error starting survey: %s", e)
                await callback.message.edit_text(
                    f"❌ Ошибка загрузки опроса: {str(e)[:100]}\n\nПопробуй позже.",
                    reply_markup=build_about_me_main_markup()
                )
            return
    
        if data == "about_survey_skip":
            # Skip current question - move to next
            await callback.answer("Пропускаю вопрос...")
            try:
                token = await get_or_fetch_token(telegram_id, username, first_name)
                if token:
                    state_data = await state.get_data()
                    section_id = state_data.get("survey_section_id")
                    
                    # Get all sections and find next question
                    sections_data = await BACKEND_CLIENT.get_profile_sections(token)
                    sections = sections_data.get("sections", []) if sections_data else []
                    
                    next_question = None
                    next_section_id = None
                    
                    # Find next unanswered question
                    for section in sections:
                        section_detail = await BACKEND_CLIENT.get_section_detail(token, section.get("id"))
                        questions = section_detail.get("section", {}).get("questions", [])
                        
                        for q in questions:
                            next_question = q
                            next_section_id = section.get("id")
                            break
                        
                        if next_question:
                            break
                    
                    if next_question:
                        question_text = next_question.get("question_text", "")
                        is_optional = next_question.get("is_optional", False)
                        
                        await state.update_data(
                            survey_section_id=next_section_id,
                            survey_question_id=next_question.get("id"),
                            survey_is_generated=False
                        )
                        
                        await callback.message.edit_text(
                            f"👣 Пройти мини-опрос\n\n"
                            f"❓ {question_text}",
                            reply_markup=build_mini_survey_markup(next_question.get("id"), can_skip=is_optional)
                        )
                    else:
                        await state.clear()
                        await callback.message.edit_text(
                            "✅ Мини-опрос завершён!\n\n"
                            "Спасибо за ответы.",
                            reply_markup=build_about_me_main_markup()
                        )
            except Exception as e:
                logger.exception("Error skipping question: %s", e)
                await callback.message.edit_text(
                    "❌ Ошибка при пропуске вопроса. Попробуй позже.",
                    reply_markup=build_about_me_main_markup()
                )
            return
        
        if data == "about_survey_pause":
            # Pause survey
            await callback.answer()
            await state.clear()
            await callback.message.edit_text(
                "⏸ Мини-опрос поставлен на паузу.\n\n"
                "Можешь продолжить позже.",
                reply_markup=build_about_me_main_markup()
            )
            return
        
        if data == "about_survey_save":
            # Save and continue - this button should only appear after user entered answer
            # The actual save happens in handle_profile_answer
            await callback.answer("Введи ответ на вопрос выше, затем он автоматически сохранится")
            return
        
        await callback.answer()
    except Exception as e:
        logger.exception("Error in handle_about_callback: %s", e)
        try:
            await callback.answer("Ошибка. Попробуй позже.")
        except:
            pass


async def handle_about_entry_input(message: Message, state: FSMContext) -> None:
    """Handle input for about me section entry"""
    text = message.text
    data = await state.get_data()
    section = data.get("about_section", "about_free")
    
    # TODO: Save to backend
    await state.clear()
    
    await message.answer(
        f"✅ Записано!\n\n"
        f"Твоя информация сохранена.",
        reply_markup=build_main_menu_markup()
    )


# ---------------------------------------------------------
# THANKS/GRATITUDE HANDLERS
# ---------------------------------------------------------

async def handle_thanks_menu(message: Message, state: FSMContext) -> None:
    """Handle gratitude button - show gratitude menu"""
    thanks_text = (
        "🙏 Благодарности\n\n"
        "Благодарность помогает переключить мышление и снизить тревогу.\n\n"
        "Записывай за что ты благодарен — это может быть что угодно: "
        "тёплый день, вкусный завтрак, разговор с другом.\n\n"
        "Только ты видишь свои записи."
    )
    await message.answer(thanks_text, reply_markup=build_thanks_menu_markup())


async def handle_thanks_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle thanks/gratitude callbacks"""
    data = callback.data
    telegram_id = callback.from_user.id
    
    if data == "thanks_back":
        # Return to main menu
        await callback.message.delete()
        await callback.message.answer("Главное меню:", reply_markup=build_main_menu_markup())
        await callback.answer()
        return
    
    if data == "thanks_menu":
        # Return to thanks menu
        await callback.message.edit_text(
            "🙏 Благодарности\n\n"
            "Благодарность помогает переключить мышление и снизить тревогу.\n\n"
            "Записывай за что ты благодарен — это может быть что угодно.",
            reply_markup=build_thanks_menu_markup()
        )
        await callback.answer()
        return
    
    if data == "thanks_add":
        # Start adding gratitude entry
        await state.set_state(ThanksStates.adding_entry)
        await callback.message.edit_text(
            "🙏 Добавить благодарность\n\n"
            "Напиши за что ты сегодня благодарен.\n\n"
            "Можно написать 3-4 вещи через запятую или отдельными строками."
        )
        await callback.answer()
        return
    
    if data == "thanks_history":
        # Show history - load from backend
        try:
            token = await get_or_fetch_token(telegram_id, callback.from_user.username, callback.from_user.first_name)
            if not token:
                await callback.answer("Ошибка авторизации")
                return
            
            gratitudes_data = await BACKEND_CLIENT.get_gratitudes(token, page=1, page_size=20)
            gratitudes = gratitudes_data.get("gratitudes", []) if gratitudes_data else []
            total = gratitudes_data.get("total", 0) if gratitudes_data else 0
            
            if not gratitudes:
                history_text = "🗃️ История благодарностей\n\nПока записей нет. Добавь свою первую благодарность!"
            else:
                history_text = f"🗃️ История благодарностей\n\nВсего записей: {total}\n\n"
                for i, g in enumerate(gratitudes[:10], 1):  # Показываем первые 10
                    created_at = g.get("created_at", "")
                    if created_at:
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            date_str = dt.strftime("%d.%m.%Y")
                        except:
                            date_str = ""
                    else:
                        date_str = ""
                    
                    text = g.get("text", "")[:100]
                    if len(g.get("text", "")) > 100:
                        text += "..."
                    
                    history_text += f"{i}. {text}\n"
                    if date_str:
                        history_text += f"   📅 {date_str}\n"
                    history_text += "\n"
                
                if total > 10:
                    history_text += f"\n... и ещё {total - 10} записей"
            
            await callback.message.edit_text(
                history_text,
                reply_markup=build_thanks_history_markup()
            )
        except Exception as e:
            logger.exception("Error loading gratitude history: %s", e)
            await callback.message.edit_text(
                "🗃️ История благодарностей\n\n"
                "❌ Ошибка при загрузке истории. Попробуй позже.",
                reply_markup=build_thanks_history_markup()
            )
        await callback.answer()
        return
    
    if data.startswith("thanks_page_"):
        page = int(data.replace("thanks_page_", ""))
        # TODO: Load page from backend
        await callback.answer(f"Страница {page}")
        return
    
    await callback.answer()


async def handle_thanks_entry_input(message: Message, state: FSMContext) -> None:
    """Handle input for gratitude entry"""
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    text = message.text
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await message.answer("Ошибка авторизации")
            await state.clear()
            return
        
        # Save gratitude to backend
        await BACKEND_CLIENT.create_gratitude(token, text)
        
        # Get motivational response from backend
        try:
            backend_reply = await BACKEND_CLIENT.thanks(telegram_id=telegram_id, debug=False)
            reply_text = backend_reply.reply if backend_reply else "Благодарность сохранена! 🙏"
        except Exception:
            reply_text = "✅ Благодарность записана! 🙏\n\nПродолжай в том же духе!"
        
        await state.clear()
        await send_long_message(
            message, 
            f"✅ Сохранено!\n\n{text}\n\n{reply_text}",
            reply_markup=build_thanks_menu_markup()
        )
    except Exception as e:
        logger.exception("Error saving gratitude: %s", e)
        await state.clear()
        await message.answer(
            "❌ Ошибка при сохранении благодарности. Попробуй ещё раз.",
            reply_markup=build_thanks_menu_markup()
        )


# ---------------------------------------------------------
# PROGRESS HANDLERS
# ---------------------------------------------------------

async def handle_progress_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle progress view callbacks"""
    data = callback.data
    telegram_id = callback.from_user.id
    username = callback.from_user.username
    first_name = callback.from_user.first_name
    
    try:
        token = await get_or_fetch_token(telegram_id, username, first_name)
        if not token:
            await callback.answer("Ошибка авторизации")
            return
    except Exception as e:
        logger.exception("Error getting token: %s", e)
        await callback.answer("Ошибка авторизации")
        return
    
    if data == "progress_main" or data == "step_progress":
        # Show main progress menu with steps and "View answers" button
        try:
            steps_list = await BACKEND_CLIENT.get_steps_list(token)
            steps = steps_list.get("steps", []) if steps_list else []
            
            # Get progress for each step
            steps_with_progress = []
            for step in steps:
                step_id = step.get("id")
                questions_data = await BACKEND_CLIENT.get_step_questions(token, step_id)
                questions = questions_data.get("questions", []) if questions_data else []
                answered = sum(1 for q in questions if q.get("status") == "COMPLETED")
                total = len(questions)
                
                step_info = questions_data.get("step", {}) if questions_data else {}
                step_number = step_info.get("number", step.get("number", step_id))
                step_title = step_info.get("title", step.get("title", ""))
                
                steps_with_progress.append({
                    "id": step_id,
                    "number": step_number,
                    "title": step_title,
                    "answered_questions": answered,
                    "total_questions": total
                })
            
            progress_text = "📋 Мой прогресс\n\n"
            for step in steps_with_progress:
                progress_text += f"🪜 Шаг {step['number']} — {step['title']} ({step['answered_questions']}/{step['total_questions']})\n"
            
            await callback.message.edit_text(
                progress_text,
                reply_markup=build_progress_main_markup(steps_with_progress)
            )
        except Exception as e:
            logger.exception("Error loading steps: %s", e)
            await callback.answer("Ошибка загрузки")
        await callback.answer()
        return
    
    if data.startswith("progress_step_"):
        # Show step details
        step_id = int(data.replace("progress_step_", ""))
        
        try:
            questions_data = await BACKEND_CLIENT.get_step_questions(token, step_id)
            questions = questions_data.get("questions", []) if questions_data else []
            step_info = questions_data.get("step", {}) if questions_data else {}
            
            step_number = step_info.get("number", step_id)
            step_title = step_info.get("title", "")
            answered = sum(1 for q in questions if q.get("status") == "COMPLETED")
            total = len(questions)
            
            progress_text = f"🪜 Шаг {step_number} — {step_title} ({answered}/{total})\n\n"
            progress_text += "Выбери действие:"
            
            await callback.message.edit_text(
                progress_text,
                reply_markup=build_progress_step_markup(step_id, step_number, step_title)
            )
        except Exception as e:
            logger.exception("Error loading step: %s", e)
            await callback.answer("Ошибка загрузки")
        await callback.answer()
        return
    
    if data == "progress_view_answers":
        # Show step selection for viewing answers
        try:
            steps_list = await BACKEND_CLIENT.get_steps_list(token)
            steps = steps_list.get("steps", []) if steps_list else []
            
            await callback.message.edit_text(
                "📄 Посмотреть ответы\n\n"
                "Выбери номер шага:",
                reply_markup=build_progress_view_answers_steps_markup(steps)
            )
        except Exception as e:
            logger.exception("Error loading steps: %s", e)
            await callback.answer("Ошибка загрузки")
        await callback.answer()
        return
    
    if data.startswith("progress_answers_step_"):
        # Show question selection for a step
        step_id = int(data.replace("progress_answers_step_", ""))
        
        try:
            questions_data = await BACKEND_CLIENT.get_step_questions(token, step_id)
            questions = questions_data.get("questions", []) if questions_data else []
            step_info = questions_data.get("step", {}) if questions_data else {}
            
            step_number = step_info.get("number", step_id)
            step_title = step_info.get("title", "")
            
            # Store step_id in state for back navigation
            await state.update_data(progress_view_step_id=step_id)
            
            await callback.message.edit_text(
                f"📄 Посмотреть ответы\n\n"
                f"Шаг {step_number} — {step_title}\n"
                f"Выбери номер вопроса:",
                reply_markup=build_progress_view_answers_questions_markup(questions, step_id)
            )
        except Exception as e:
            logger.exception("Error loading questions: %s", e)
            await callback.answer("Ошибка загрузки")
        await callback.answer()
        return
    
    if data.startswith("progress_answers_question_"):
        # Show answer for selected question
        question_id = int(data.replace("progress_answers_question_", ""))
        
        try:
            # Get previous answer
            answer_data = await BACKEND_CLIENT.get_previous_answer(token, question_id)
            answer_text = answer_data.get("answer_text", "") if answer_data else ""
            
            # Get step_id from state or find it
            state_data = await state.get_data()
            step_id_for_back = state_data.get("progress_view_step_id")
            
            # Get question info
            current_question = None
            if step_id_for_back:
                questions_data = await BACKEND_CLIENT.get_step_questions(token, step_id_for_back)
                questions = questions_data.get("questions", []) if questions_data else []
                for q in questions:
                    if q.get("id") == question_id:
                        current_question = q
                        break
            
            # If not found, search all steps
            if not current_question:
                steps_list = await BACKEND_CLIENT.get_steps_list(token)
                steps = steps_list.get("steps", []) if steps_list else []
                
                for step in steps:
                    step_id = step.get("id")
                    questions_data = await BACKEND_CLIENT.get_step_questions(token, step_id)
                    questions = questions_data.get("questions", []) if questions_data else []
                    
                    for q in questions:
                        if q.get("id") == question_id:
                            current_question = q
                            if not step_id_for_back:
                                step_id_for_back = step_id
                            break
                    
                    if current_question:
                        break
            
            if current_question:
                question_text = current_question.get("text", "Вопрос")
            else:
                question_text = "Вопрос"
            
            if answer_text:
                display_text = (
                    f"📄 Ответ\n\n"
                    f"❓ {question_text}\n\n"
                    f"💬 Твой ответ:\n\n{answer_text}"
                )
            else:
                display_text = (
                    f"📄 Ответ\n\n"
                    f"❓ {question_text}\n\n"
                    f"💬 Ответ пока не сохранён."
                )
            
            back_button = [InlineKeyboardButton(text="◀️ Назад к вопросам", callback_data=f"progress_answers_step_{step_id_for_back}")] if step_id_for_back else []
            
            await callback.message.edit_text(
                display_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[back_button] if back_button else [])
            )
        except Exception as e:
            logger.exception("Error loading answer: %s", e)
            await callback.answer("Ошибка загрузки ответа")
        await callback.answer()
        return
    
    await callback.answer()


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
        survey_mode = state_data.get("survey_mode", False)
        
        if survey_mode:
            # Handle mini survey mode
            section_id = state_data.get("survey_section_id")
            question_id = state_data.get("survey_question_id")
            is_generated = state_data.get("survey_is_generated", False)
            
            if not section_id:
                await message.answer("Ошибка: не найден раздел.")
                await state.clear()
                return
            
            # For generated questions, question_id can be None
            if not is_generated and not question_id:
                await message.answer("Ошибка: не найден вопрос.")
                await state.clear()
                return
            
            # Submit answer (question_id can be None for generated questions)
            result = await BACKEND_CLIENT.submit_profile_answer(
                token, section_id, question_id, answer_text
            )
            
            # Check if there's a next question in the response
            next_question_data = result.get("next_question")
            
            if next_question_data:
                # Show next question (can be basic or generated follow-up)
                question_text = next_question_data.get("text", "")
                is_optional = next_question_data.get("is_optional", True)
                is_generated = next_question_data.get("is_generated", False)
                next_question_id = next_question_data.get("id")
                
                # For generated questions, we still need section_id
                # For regular questions, use the question's section
                if is_generated:
                    # Generated question - keep same section
                    next_section_id = section_id
                    # Store that it's a generated question
                    await state.update_data(
                        survey_section_id=next_section_id,
                        survey_question_id=None,  # No DB ID for generated questions
                        survey_is_generated=True,
                        survey_generated_text=question_text
                    )
                else:
                    # Regular question from DB
                    next_section_id = section_id  # Same section for now
                    await state.update_data(
                        survey_section_id=next_section_id,
                        survey_question_id=next_question_id,
                        survey_is_generated=False
                    )
                
                await send_long_message(
                    message,
                    f"✅ Ответ сохранён!\n\n"
                    f"👣 Пройти мини-опрос\n\n"
                    f"❓ {question_text}",
                    reply_markup=build_mini_survey_markup(next_question_id if next_question_id else -1, can_skip=is_optional)
                )
            else:
                # All questions answered (including follow-ups)
                await state.clear()
                await message.answer(
                    "✅ Мини-опрос завершён!\n\n"
                    "Спасибо за ответы.",
                    reply_markup=build_about_me_main_markup()
                )
        else:
            # Handle regular profile mode
        section_id = state_data.get("section_id")
        question_id = state_data.get("current_question_id")
            is_generated = state_data.get("is_generated_question", False)
        questions = state_data.get("questions", [])
        question_index = state_data.get("question_index", 0)
        
            if not section_id:
                await message.answer("Ошибка: не найден раздел. Начни заново с /profile")
                await state.clear()
                return
            
            # For generated questions, question_id might be None
            if not is_generated and not question_id:
            await message.answer("Ошибка: не найден вопрос. Начни заново с /profile")
            await state.clear()
            return
        
            # Submit answer (question_id can be None for generated questions)
        result = await BACKEND_CLIENT.submit_profile_answer(
            token, section_id, question_id, answer_text
        )
        
        # Check if there's a next question
        next_question = result.get("next_question")
        
        if next_question:
                # Show next question (can be basic or generated follow-up)
            next_question_text = next_question.get("text", "")
                is_generated_next = next_question.get("is_generated", False)
                next_question_id = next_question.get("id")
                
                if is_generated_next:
                    # Generated follow-up question
            await state.update_data(
                        current_question_id=None,  # No DB ID for generated questions
                        question_index=question_index + 1,
                        is_generated_question=True
                    )
                else:
                    # Regular question from DB
                    await state.update_data(
                        current_question_id=next_question_id,
                        question_index=question_index + 1,
                        is_generated_question=False
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
                # All questions answered (including follow-ups)
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
            # Return to main settings menu
            await callback.message.edit_text(
                "⚙️ Настройки\n\n"
                "Выбери раздел настроек:",
                reply_markup=build_main_settings_markup()
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
            await callback.answer()
            return
        
        if data == "settings_template_back":
            # Return to steps settings from template selection
            settings = await BACKEND_CLIENT.get_steps_settings(token)
            active_template_name = settings.get("active_template_name", "Не выбран")
            reminders_enabled = settings.get("reminders_enabled", False)
            
            settings_text = (
                "⚙️ Настройки работы по шагу\n\n"
                f"⚙️ Активный шаблон: {active_template_name}\n"
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
        
        if data.startswith("settings_select_template_"):
            # Select template
            template_id = int(data.split("_")[-1])
            
            # Get template name before updating
            templates_data = await BACKEND_CLIENT.get_templates(token)
            templates = templates_data.get("templates", [])
            selected_template = next((t for t in templates if t.get("id") == template_id), None)
            template_name = selected_template.get("name", "Неизвестно") if selected_template else "Неизвестно"
            
            # Update settings
            await BACKEND_CLIENT.update_steps_settings(token, active_template_id=template_id)
            
            # Get updated settings (only for reminders status)
            settings = await BACKEND_CLIENT.get_steps_settings(token)
            reminders_enabled = settings.get("reminders_enabled", False)
            
            settings_text = (
                "⚙️ Настройки работы по шагу\n\n"
                f"⚙️ Активный шаблон: {template_name}\n"
                f"⏰ Напоминания: {'✅ Включены' if reminders_enabled else '❌ Выключены'}\n\n"
                "Выбери настройку для изменения:"
            )
            
            await edit_long_message(
                callback,
                settings_text,
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
                
                # Get updated settings (only for reminders status)
                settings = await BACKEND_CLIENT.get_steps_settings(token)
                reminders_enabled = settings.get("reminders_enabled", False)
                
                settings_text = (
                    "⚙️ Настройки работы по шагу\n\n"
                    f"⚙️ Активный шаблон: {author_template.get('name')}\n"
                    f"⏰ Напоминания: {'✅ Включены' if reminders_enabled else '❌ Выключены'}\n\n"
                    "Выбери настройку для изменения:"
                )
                
                await edit_long_message(
                    callback,
                    settings_text,
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
                buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="settings_edit_template_back")])
                
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
                        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_edit_template_back")]
                    ])
                )
            await callback.answer()
            return
        
        if data == "settings_edit_template_back":
            # Return to steps settings from edit template menu
            settings = await BACKEND_CLIENT.get_steps_settings(token)
            active_template_name = settings.get("active_template_name", "Не выбран")
            reminders_enabled = settings.get("reminders_enabled", False)
            
            settings_text = (
                "⚙️ Настройки работы по шагу\n\n"
                f"⚙️ Активный шаблон: {active_template_name}\n"
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
        
        if data.startswith("settings_edit_template_"):
            # Edit specific template (for now, just show info)
            template_id = int(data.split("_")[-1])
            await callback.answer("Редактирование шаблона будет реализовано позже")
            return
        
        if data == "settings_reminders_back":
            # Return to steps settings from reminders
            settings = await BACKEND_CLIENT.get_steps_settings(token)
            active_template_name = settings.get("active_template_name", "Не выбран")
            reminders_enabled = settings.get("reminders_enabled", False)
            
            settings_text = (
                "⚙️ Настройки работы по шагу\n\n"
                f"⚙️ Активный шаблон: {active_template_name}\n"
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
        
        if data == "step_continue":
            # Continue working - open answer mode
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            if not step_info:
                await callback.answer("Не удалось получить информацию о шаге")
                return
            
            step_data = await get_current_step_question(telegram_id, username, first_name)
            if step_data:
                response_text = step_data.get("message", "")
                if response_text:
                    progress_indicator = format_step_progress_indicator(
                        step_number=step_info.get("step_number"),
                        total_steps=step_info.get("total_steps", 12),
                        step_title=step_info.get("step_title"),
                        answered_questions=step_info.get("answered_questions", 0),
                        total_questions=step_info.get("total_questions", 0)
                    )
                    
                    # Check if there's a draft
                    draft_data = await BACKEND_CLIENT.get_draft(token)
                    draft_text = draft_data.get("draft", "") if draft_data else ""
                    
                    if draft_text:
                        full_text = (
                            f"{progress_indicator}\n\n"
                            f"❔{response_text}\n\n"
                            f"📝 Поле для ответа:\n"
                            f"💾 Черновик: {draft_text[:100]}{'...' if len(draft_text) > 100 else ''}"
                        )
                    else:
                        full_text = (
                            f"{progress_indicator}\n\n"
                            f"❔{response_text}\n\n"
                            f"📝 Поле для ответа:\n"
                            f"[Введи свой ответ здесь]"
                        )
                    
                    # Store step description and question info in state
                    await state.update_data(
                        step_description=step_info.get("step_description", ""),
                        current_draft=draft_text
                    )
                    
                    await edit_long_message(
                        callback,
                        full_text,
                        reply_markup=build_step_answer_mode_markup()
                    )
                    await state.set_state(StepState.answer_mode)
                    await callback.answer()
                return
            
        if data == "step_back_from_answer":
            # Return to step actions menu
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            if not step_info:
                await callback.answer("Не удалось получить информацию о шаге")
                return
            
            step_data = await get_current_step_question(telegram_id, username, first_name)
            if step_data:
                response_text = step_data.get("message", "")
                if response_text:
                    progress_indicator = format_step_progress_indicator(
                        step_number=step_info.get("step_number"),
                        total_steps=step_info.get("total_steps", 12),
                        step_title=step_info.get("step_title"),
                        answered_questions=step_info.get("answered_questions", 0),
                        total_questions=step_info.get("total_questions", 0)
                    )
                    full_text = f"{progress_indicator}\n\n❔{response_text}"
                    
                    await state.update_data(step_description=step_info.get("step_description", ""))
                    
                    await edit_long_message(
                        callback,
                        full_text,
                        reply_markup=build_step_actions_markup(show_description=False)
                    )
                    await state.set_state(StepState.answering)
                    await callback.answer()
            return
        
        if data == "step_save_draft":
            # Save draft - prompt user to enter text
            await state.update_data(action="save_draft")
            await callback.message.edit_text(
                "💾 Сохранить черновик\n\n"
                "Введи текст черновика и отправь его:"
            )
            await callback.answer()
            return
        
        if data == "step_edit_last":
            # Edit last answer - get previous answer
            step_data = await get_current_step_question(telegram_id, username, first_name)
            if not step_data:
                await callback.answer("Нет активного вопроса")
                return
            
            # Get question ID from active tail
            questions_data = await BACKEND_CLIENT.get_current_step_questions(token)
            questions = questions_data.get("questions", []) if questions_data else []
            current_question_text = step_data.get("message", "")
            question_id = None
            for q in questions:
                if q.get("text") == current_question_text:
                    question_id = q.get("id")
                    break
            
            if question_id:
                prev_answer_data = await BACKEND_CLIENT.get_previous_answer(token, question_id)
                prev_answer = prev_answer_data.get("answer_text", "") if prev_answer_data else ""
                
                if prev_answer:
                    step_info = await BACKEND_CLIENT.get_current_step_info(token)
                    progress_indicator = format_step_progress_indicator(
                        step_number=step_info.get("step_number"),
                        total_steps=step_info.get("total_steps", 12),
                        step_title=step_info.get("step_title"),
                        answered_questions=step_info.get("answered_questions", 0),
                        total_questions=step_info.get("total_questions", 0)
                    )
                    
                    await callback.message.edit_text(
                        f"{progress_indicator}\n\n"
                        f"❔{current_question_text}\n\n"
                        f"✏️ Редактировать последний ответ:\n\n"
                        f"Предыдущий ответ:\n{prev_answer}\n\n"
                        f"Введи новый ответ:",
                        reply_markup=build_step_answer_mode_markup()
                    )
                    await state.update_data(action="edit_answer", previous_answer=prev_answer)
                    await callback.answer()
                else:
                    await callback.answer("Предыдущий ответ не найден")
            else:
                await callback.answer("Не удалось определить вопрос")
                return
            
        if data == "step_reset_draft":
            # Reset draft - clear current draft
            await BACKEND_CLIENT.save_draft(token, "")
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            step_data = await get_current_step_question(telegram_id, username, first_name)
            if step_data:
                response_text = step_data.get("message", "")
                if response_text:
                    progress_indicator = format_step_progress_indicator(
                        step_number=step_info.get("step_number"),
                        total_steps=step_info.get("total_steps", 12),
                        step_title=step_info.get("step_title"),
                        answered_questions=step_info.get("answered_questions", 0),
                        total_questions=step_info.get("total_questions", 0)
                    )
                    full_text = (
                        f"{progress_indicator}\n\n"
                        f"❔{response_text}\n\n"
                        f"📝 Поле для ответа:\n"
                        f"[Поле очищено]"
                    )
                    await state.update_data(current_draft="")
                    await callback.message.edit_text(
                        full_text,
                        reply_markup=build_step_answer_mode_markup()
                    )
            await callback.answer("Поле очищено")
            return
        
        if data == "step_complete":
            # Complete and move to next - prompt to enter final answer
            await state.update_data(action="complete")
            await callback.message.edit_text(
                "✔️ Завершить и перейти\n\n"
                "Введи финальный ответ и отправь его. После этого ответ будет сохранён и ты перейдёшь к следующему вопросу:"
            )
            await callback.answer()
            return
        
        if data == "step_toggle_description":
            # Toggle step description visibility
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            if not step_info:
                await callback.answer("Не удалось получить информацию о шаге")
                return
            
            step_data = await get_current_step_question(telegram_id, username, first_name)
            if not step_data:
                await callback.answer("Нет активного вопроса")
                return
            
            response_text = step_data.get("message", "")
            state_data = await state.get_data()
            show_description = state_data.get("show_step_description", False)
            step_description = step_info.get("step_description", "")
            
            progress_indicator = format_step_progress_indicator(
                step_number=step_info.get("step_number"),
                total_steps=step_info.get("total_steps", 12),
                step_title=step_info.get("step_title"),
                answered_questions=step_info.get("answered_questions", 0),
                total_questions=step_info.get("total_questions", 0)
            )
            
            if show_description:
                # Hide description
                full_text = f"{progress_indicator}\n\n❔{response_text}"
                new_show_description = False
            else:
                # Show description - only description, no extra text
                if step_description:
                    full_text = f"{progress_indicator}\n\n{step_description}\n\n❔{response_text}"
                else:
                    full_text = f"{progress_indicator}\n\n❔{response_text}"
                    await callback.answer("Описание шага пока не добавлено")
                    return
                new_show_description = True
            
            await state.update_data(show_step_description=new_show_description)
            
            await edit_long_message(
                callback,
                full_text,
                reply_markup=build_step_actions_markup(show_description=new_show_description)
            )
            await callback.answer()
                return
            
        elif data == "step_progress":
            # Show my progress - only menu with steps, no text list
            steps_list = await BACKEND_CLIENT.get_steps_list(token)
            steps = steps_list.get("steps", []) if steps_list else []
            
            progress_text = "📋 Мой прогресс\n\nВыбери шаг для просмотра:"
            
            await callback.message.edit_text(
                progress_text,
                reply_markup=build_progress_main_markup(steps)
            )
            await callback.answer()
            return
        
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
            # Return to "Работа по шагу" screen (not main menu)
            await callback.answer()
            # Get current step info and show it
            step_info = await BACKEND_CLIENT.get_current_step_info(token)
            if step_info:
                step_number = step_info.get("step_number")
                step_data = await get_current_step_question(telegram_id, username, first_name)
                if step_data:
                    response_text = step_data.get("message", "")
                    if response_text:
                        progress_indicator = format_step_progress_indicator(
                            step_number=step_number,
                            total_steps=step_info.get("total_steps", 12),
                            step_title=step_info.get("step_title"),
                            answered_questions=step_info.get("answered_questions", 0),
                            total_questions=step_info.get("total_questions", 0)
                        )
                        full_text = f"{progress_indicator}\n\n{response_text}"
            await edit_long_message(
                callback,
                            full_text,
                            reply_markup=build_step_actions_markup()
                        )
                        await state.set_state(StepState.answering)
                        return
            # Fallback: show steps navigation
            await edit_long_message(
                callback,
                "🪜 Работа по шагу",
                reply_markup=build_steps_navigation_markup()
            )
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
            
            full_text = f"{progress_indicator}\n\n❔{response_text}"
            
            # Store step description in state
            await state.update_data(step_description=step_description)
            
            try:
                await edit_long_message(
                    callback,
                    full_text,
                    reply_markup=build_step_actions_markup(show_description=False)
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
                        reply_markup=build_step_actions_markup(show_description=False)
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