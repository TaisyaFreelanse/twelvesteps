"""Shared configuration and markup helpers for the Telegram frontend."""

from __future__ import annotations

import os
from typing import List

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

BACKEND_API_BASE = (
    os.getenv("BACKEND_API_BASE_URL")
    or os.getenv("BACKEND_URL")
    or "http://127.0.0.1:8000"
)
BACKEND_CHAT_URL = os.getenv("BACKEND_CHAT_URL", f"{BACKEND_API_BASE.rstrip('/')}/chat")

PROGRAM_EXPERIENCE_OPTIONS: List[str] = ["Новичок", "Есть немного опыта", "Бывалый"]


def build_main_menu_markup() -> ReplyKeyboardMarkup:
    """Produce the quick action keyboard shown after onboarding or in main flow."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/steps"), KeyboardButton(text="/day")],
            [KeyboardButton(text="/sos"), KeyboardButton(text="/thanks")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_experience_markup() -> ReplyKeyboardMarkup:
    """Inline keyboard for selecting program experience."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=option)] for option in PROGRAM_EXPERIENCE_OPTIONS],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def build_exit_markup() -> ReplyKeyboardMarkup:
    """Minimal keyboard that offers an /exit option during onboarding."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="/exit")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def build_skip_markup() -> ReplyKeyboardMarkup:
    """Simple markup that highlights /skip for optional questions."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="/skip")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
