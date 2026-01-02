"""Onboarding FSM flow: Name -> Experience -> Date -> Bio (Analyzer)."""

from __future__ import annotations

import datetime
import logging

from aiogram import Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardRemove

from bot.backend import update_user_profile, call_legacy_chat
from bot.config import (
    build_experience_markup,
    build_main_menu_markup,
    build_skip_markup,
    build_error_markup,
)
from bot.utils import is_question

logger = logging.getLogger(__name__)

class OnboardingStates(StatesGroup):
    display_name = State()
    program_experience = State()
    sobriety_date = State()
    self_description = State()


VALID_CODES = {"NEWBIE", "SOME_EXPERIENCE", "LONG_TERM"}

EXPERIENCE_MAPPING = {
    "НОВИЧОК": "NEWBIE",
    "NEWBIE": "NEWBIE",

    "ЕСТЬ НЕМНОГО ОПЫТА": "SOME_EXPERIENCE",
    "ЕСТЬ ОПЫТ": "SOME_EXPERIENCE",
    "УЖЕ В ПРОГРАММЕ": "SOME_EXPERIENCE",
    "SOME_EXPERIENCE": "SOME_EXPERIENCE",

    "БЫВАЛЫЙ": "LONG_TERM",
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
    raw_text = message.text.strip()
    normalized_text = raw_text.upper()
    print(f"[Onboarding Debug] Received Experience: '{raw_text}' (Normalized: '{normalized_text}')")

    selected_code = EXPERIENCE_MAPPING.get(normalized_text)

    if not selected_code or selected_code not in VALID_CODES:
        await message.answer(
            f"Я не понял ответ '{raw_text}'. Пожалуйста, выбери один из вариантов на клавиатуре.",
            reply_markup=build_experience_markup(),
        )
        return

    try:
        await update_user_profile(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            program_experience=selected_code,
        )
    except Exception as e:
        logger.error(f"Failed to update experience: {e}")

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
    text = message.text.strip()

    if is_question(text):
        await message.answer(
            "Это кратко о моих функциях. А теперь, пожалуйста, расскажи о себе, "
            "чтобы я мог лучше тебя понимать.\n\n"
            "Как ты себя чувствуешь? Что тебя беспокоит? Или просто пару слов о своей истории.",
            parse_mode="HTML"
        )
        return

    processing_msg = await message.answer("Настраиваю твой профиль...")

    try:
        backend_reply = await call_legacy_chat(
            telegram_id=message.from_user.id,
            text=text,
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
        try:
            await processing_msg.delete()
        except:
            pass

        error_text = (
            "❌ Произошла ошибка при настройке профиля.\n\n"
            "Профиль может быть частично сохранён, но сервер не ответил.\n\n"
            "Хочешь начать заново?"
        )

        await message.answer(
            error_text,
            reply_markup=build_error_markup()
        )


def register_onboarding_handlers(dp: Dispatcher) -> None:
    """Attach onboarding FSM handlers to the dispatcher."""
    dp.message(OnboardingStates.display_name, F.text)(handle_display_name)
    dp.message(OnboardingStates.program_experience, F.text)(handle_experience)
    dp.message(OnboardingStates.sobriety_date, F.text)(handle_sobriety)
    dp.message(OnboardingStates.self_description, F.text)(handle_self_description)