"""Telegram handlers for /start, /exit, /steps and the legacy chat bridge."""

from __future__ import annotations

from functools import partial
import json
import logging
import datetime

from aiogram import Dispatcher, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.backend import (
    BACKEND_CLIENT, 
    TOKEN_STORE, 
    USER_CACHE, 
    Log, 
    call_legacy_chat, 
    get_display_name,
    process_step_message,      
    get_current_step_question 
)
from bot.config import build_exit_markup, build_main_menu_markup
from bot.onboarding import OnboardingStates, register_onboarding_handlers

logger = logging.getLogger(__name__)

USER_LOGS: dict[int, list[Log]] = {}

# --- STATES ---
class StepState(StatesGroup):
    answering = State()  # User is currently answering a step question

# ---------------------------------------------------------
# REGISTER HANDLERS
# ---------------------------------------------------------

def register_handlers(dp: Dispatcher) -> None:
    # 1. Commands (Priority)
    dp.message(CommandStart())(handle_start)
    dp.message(Command(commands=["exit"]))(handle_exit)
    dp.message(Command(commands=["steps"]))(handle_steps)
    dp.message(Command(commands=["sos"]))(handle_sos)

    # 2. Onboarding Flow
    register_onboarding_handlers(dp)

    # 3. Step Answering Flow (Only works if state is StepState.answering)
    dp.message(StateFilter(StepState.answering))(handle_step_answer)
    dp.message(Command(commands=["qa_open"]))(qa_open)

    # 4. QA / Debug Commands
    dp.message(Command(commands=["qa_last"]))(qa_last)
    dp.message(Command(commands=["qa_ctx"]))(qa_ctx)
    dp.message(Command(commands=["qa_trace"]))(qa_trace)
    dp.message(Command(commands=["qa_report"]))(qa_report)
    dp.message(Command(commands=["qa_export"]))(qa_export)
    
    # NEW COMMAND HERE
    

    # 5. General Chat (Fallback for everything else)
    dp.message()(partial(handle_message, debug=False))


# ---------------------------------------------------------
# STEPS HANDLER (/steps)
# ---------------------------------------------------------

async def handle_steps(message: Message, state: FSMContext) -> None:
    """
    Activates 'Step Mode'. Fetches the current question and sets FSM state.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    try:
        step_data = await get_current_step_question(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name
        )
    except Exception as exc:
        logger.exception("Error fetching steps for %s: %s", telegram_id, exc)
        await message.answer("Ошибка сервера. Попробуй позже.")
        return

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
        # Set the state to 'answering' so the next message goes to handle_step_answer
        await state.set_state(StepState.answering)
        await message.answer(response_text, reply_markup=build_exit_markup())


# ---------------------------------------------------------
# STEP ANSWER HANDLER (State: StepState.answering)
# ---------------------------------------------------------

async def handle_step_answer(message: Message, state: FSMContext) -> None:
    """
    Processes the user's text as an answer to the active step question.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    user_text = message.text

    try:
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

        response_text = step_next.get("message", "Ответ принят.")
        is_completed = step_next.get("is_completed", False)

        await message.answer(response_text, reply_markup=build_exit_markup())

        if is_completed:
             await message.answer("Этап завершен! 🎉 Возвращаю в обычный режим.", reply_markup=build_main_menu_markup())
             await state.clear()
             
    except Exception as exc:
        logger.exception("Error processing step answer: %s", exc)
        await message.answer("Произошла ошибка при сохранении ответа. Попробуй еще раз.")


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

        await message.answer(reply_text, reply_markup=build_main_menu_markup())

    except Exception as exc:
        logger.exception("Failed to get response from backend chat: %s", exc)
        await message.answer("Не удалось получить ответ от сервера, попробуй позже.")


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
        await message.answer("Ошибка подключения. Попробуй позже.")
        return

    TOKEN_STORE[key] = access_token
    USER_CACHE[key] = user

    if is_new:
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

async def handle_sos(message: Message) -> None:
    """
    Handles /sos command: Requests a helpful hint/example from the AI.
    """
    telegram_id = message.from_user.id
    
    # 1. Notify user processing started
    processing_msg = await message.answer("🚑 Анализирую контекст...")

    try:
        # 2. Call the method we just added to BACKEND_CLIENT in backend.py
        sos_reply = await BACKEND_CLIENT.get_sos_message(telegram_id)
        
        # 3. Send result
        await processing_msg.delete()
        await message.answer(sos_reply, reply_markup=build_main_menu_markup())
        
    except Exception as exc:
        logger.exception("Error handling /sos for %s: %s", telegram_id, exc)
        await processing_msg.edit_text("❌ Ошибка при получении подсказки.")

# ---------------------------------------------------------
# REGISTER HANDLERS
# ---------------------------------------------------------