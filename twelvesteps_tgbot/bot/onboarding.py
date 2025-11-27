"""Onboarding FSM flow: Name -> Experience -> Date -> Bio (Analyzer)."""

from __future__ import annotations

import datetime
import logging

from aiogram import Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove

# Imports from your backend
from bot.backend import update_user_profile, call_legacy_chat
from bot.config import (
    build_experience_markup,
    build_main_menu_markup,
    build_skip_markup,
)

logger = logging.getLogger(__name__)

class OnboardingStates(StatesGroup):
    display_name = State()
    program_experience = State()
    sobriety_date = State()
    self_description = State()

# --- CONFIGURATION ---

# 1. Valid values that the Database accepts
VALID_CODES = {"NEWBIE", "SOME_EXPERIENCE", "LONG_TERM"}

# 2. Mapping User Input (Russian) -> Database Value (English)
# Keys must be UPPERCASE for case-insensitive matching
EXPERIENCE_MAPPING = {
    "НОВИЧОК": "NEWBIE",
    "NEWBIE": "NEWBIE",
    
    "УЖЕ В ПРОГРАММЕ": "SOME_EXPERIENCE",
    "ЕСТЬ ОПЫТ": "SOME_EXPERIENCE",
    "SOME_EXPERIENCE": "SOME_EXPERIENCE",
    
    "ПРОХОДИЛ ШАГИ": "LONG_TERM",
    "СПОНСОР": "LONG_TERM",
    "ДАВНО В ПРОГРАММЕ": "LONG_TERM",
    "LONG_TERM": "LONG_TERM"
}

async def handle_display_name(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if not text or text.startswith("/"):
        await message.answer("Пожалуйста, напиши имя, под которым мне к тебе обращаться.")
        return
    
    await update_user_profile(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        display_name=text,
    )
    
    await state.set_state(OnboardingStates.program_experience)
    await message.answer(
        "Отлично! Какой у тебя опыт работы с программой?",
        reply_markup=build_experience_markup(),
    )


async def handle_experience(message: Message, state: FSMContext) -> None:
    # Debug print to see what exactly is coming in
    raw_text = message.text.strip()
    normalized_text = raw_text.upper()
    print(f"[Onboarding Debug] Received Experience: '{raw_text}' (Normalized: '{normalized_text}')")

    # 1. Try to map the text to a valid code
    selected_code = EXPERIENCE_MAPPING.get(normalized_text)

    # 2. Validation: Ensure we found a code and it is valid
    if not selected_code or selected_code not in VALID_CODES:
        await message.answer(
            f"Я не понял ответ '{raw_text}'. Пожалуйста, выбери один из вариантов на клавиатуре.",
            reply_markup=build_experience_markup(),
        )
        return

    # 3. Save to Backend
    try:
        await update_user_profile(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            program_experience=selected_code,
        )
    except Exception as e:
        logger.error(f"Failed to update experience: {e}")
        # Continue anyway to not block the user

    # 4. Move to Next Step
    await state.set_state(OnboardingStates.sobriety_date)
    await message.answer(
        "Хочешь ли ты рассказать свою дату трезвости? Отправь её в формате YYYY-MM-DD или /skip.",
        reply_markup=build_skip_markup(),
    )


async def handle_sobriety(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    sobriety_date = None
    
    if text.lower() not in ("/skip", "skip"):
        try:
            parsed = datetime.datetime.strptime(text, "%Y-%m-%d")
            sobriety_date = parsed.date().isoformat()
        except ValueError:
            await message.answer(
                "Неправильный формат даты. Отправь в формате YYYY-MM-DD или /skip."
            )
            return

    if sobriety_date:
        await update_user_profile(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            sobriety_date=sobriety_date,
        )

    # Move to Analyzer Step
    await state.set_state(OnboardingStates.self_description)
    
    await message.answer(
        "Принято.\n\n"
        "<b>Последний шаг:</b>\n"
        "Расскажи немного о себе в одном сообщении. "
        "Как ты себя чувствуешь? Что тебя беспокоит? Или просто пару слов о своей истории.\n\n"
        "<i>(Я проанализирую это сообщение и создам твой персональный профиль)</i>",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )


async def handle_self_description(message: Message, state: FSMContext) -> None:
    """
    Takes the user's bio, sends it to the backend chatbot.
    Triggers: Classify -> Analyze Profile -> Update DB -> Reply.
    """
    processing_msg = await message.answer("Настраиваю твой профиль...")

    try:
        # Send to backend as a regular message to trigger the Analyzer
        backend_reply = await call_legacy_chat(
            telegram_id=message.from_user.id,
            text=message.text,
            debug=False
        )
        
        await processing_msg.delete()
        await state.clear()

        if backend_reply.reply:
            await message.answer(backend_reply.reply, reply_markup=build_main_menu_markup())
        else:
            await message.answer(
                "Спасибо! Я запомнил всё. Можем начинать общение.", 
                reply_markup=build_main_menu_markup()
            )

    except Exception as e:
        logger.error(f"Onboarding Bridge Error: {e}")
        await state.clear()
        await processing_msg.edit_text("Профиль сохранен, но сервер не ответил. Можем просто продолжить.")
        await message.answer(
            "Ты можешь использовать меню для навигации.",
            reply_markup=build_main_menu_markup()
        )


def register_onboarding_handlers(dp: Dispatcher) -> None:
    """Attach onboarding FSM handlers to the dispatcher."""
    dp.message(OnboardingStates.display_name, F.text)(handle_display_name)
    dp.message(OnboardingStates.program_experience, F.text)(handle_experience)
    dp.message(OnboardingStates.sobriety_date, F.text)(handle_sobriety)
    dp.message(OnboardingStates.self_description, F.text)(handle_self_description)  