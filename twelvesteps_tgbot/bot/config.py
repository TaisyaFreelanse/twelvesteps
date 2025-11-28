"""Shared configuration and markup helpers for the Telegram frontend."""

from __future__ import annotations

import os
from typing import List, Optional

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
import pathlib

# Load environment variables from telegram.env in parent directory
env_path = pathlib.Path(__file__).parent.parent.parent / "telegram.env"
load_dotenv(env_path)

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
            [KeyboardButton(text="/profile"), KeyboardButton(text="/sos")],
            [KeyboardButton(text="/thanks")],
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


def build_error_markup() -> ReplyKeyboardMarkup:
    """Keyboard shown when errors occur, offering restart option."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/start")],
            [KeyboardButton(text="/reset")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


# --- Profile Keyboards ---

def build_profile_sections_markup(sections: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """
    Build inline keyboard with all profile sections in a grid layout.
    Sections are displayed horizontally (2-3 per row).
    Excludes "Свободный рассказ" (id=14) from the list as it has a separate button at the bottom.
    """
    buttons = []
    row = []
    
    for section in sections:
        section_id = section.get("id")
        # Skip "Свободный рассказ" section (id=14) - it has a separate button at the bottom
        if section_id == 14:
            continue
            
        name = section.get("name", "")
        # Limit button text length for Telegram (max 64 chars)
        button_text = name[:60] + "..." if len(name) > 60 else name
        
        row.append(InlineKeyboardButton(
            text=button_text,
            callback_data=f"profile_section_{section_id}"
        ))
        
        # Add row every 2 buttons (horizontal layout)
        if len(row) >= 2:
            buttons.append(row)
            row = []
    
    # Add remaining buttons
    if row:
        buttons.append(row)
    
    # Add action buttons at the bottom
    buttons.append([
        InlineKeyboardButton(text="✍️ Свободный рассказ", callback_data="profile_free_text"),
        InlineKeyboardButton(text="➕ Добавить свой блок", callback_data="profile_custom_section")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_profile_actions_markup(section_id: int) -> InlineKeyboardMarkup:
    """Build action buttons for a profile section."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✍️ Свободный рассказ", callback_data=f"profile_free_text_{section_id}"),
            InlineKeyboardButton(text="✅ Сохранить", callback_data=f"profile_save_{section_id}")
        ],
        [InlineKeyboardButton(text="⏪ Назад", callback_data="profile_back")]
    ])


def build_profile_skip_markup() -> InlineKeyboardMarkup:
    """Markup for skipping optional questions."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="profile_skip")]
    ])


# --- Steps Template Keyboards ---

def build_template_selection_markup() -> InlineKeyboardMarkup:
    """Markup for selecting answer template on first /steps entry."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Авторский шаблон", callback_data="template_author")],
        [InlineKeyboardButton(text="✍️ Свой шаблон", callback_data="template_custom")]
    ])


# --- SOS Help Keyboards ---

def build_sos_help_type_markup() -> InlineKeyboardMarkup:
    """Markup for selecting type of help in SOS."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Не понимаю вопрос", callback_data="sos_help_question")],
        [InlineKeyboardButton(text="🧱 Не могу вспомнить ситуацию", callback_data="sos_help_memory")],
        [InlineKeyboardButton(text="🔁 Застрял — не могу сформулировать", callback_data="sos_help_formulation")],
        [InlineKeyboardButton(text="😶 Просто тяжело, нужна поддержка", callback_data="sos_help_support")],
        [InlineKeyboardButton(text="✍️ Своё", callback_data="sos_help_custom")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="sos_cancel")]
    ])

def build_sos_save_draft_markup() -> InlineKeyboardMarkup:
    """Markup for saving SOS conversation as draft."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, сохранить", callback_data="sos_save_yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="sos_save_no")]
    ])

def build_sos_exit_markup() -> InlineKeyboardMarkup:
    """Markup for exiting SOS chat."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Выйти из помощи", callback_data="sos_exit")]
    ])


# --- Steps Navigation Keyboards ---

def build_steps_navigation_markup() -> InlineKeyboardMarkup:
    """Markup for steps navigation menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔢 Выбрать другой шаг", callback_data="steps_select")],
        [InlineKeyboardButton(text="📋 Показать список вопросов", callback_data="steps_questions")],
        [InlineKeyboardButton(text="▶️ Продолжить", callback_data="steps_continue")]
    ])

def build_steps_list_markup(steps: list[dict]) -> InlineKeyboardMarkup:
    """Markup for selecting a step (1-12)."""
    buttons = []
    # Create buttons in rows of 3
    for i in range(0, len(steps), 3):
        row = []
        for j in range(3):
            if i + j < len(steps):
                step = steps[i + j]
                row.append(InlineKeyboardButton(
                    text=f"Шаг {step['number']}",
                    callback_data=f"step_select_{step['id']}"
                ))
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="steps_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_step_questions_markup(questions: list[dict], step_id: int) -> InlineKeyboardMarkup:
    """Markup for listing questions in a step."""
    buttons = []
    for i, q in enumerate(questions, 1):
        # Truncate question text for button
        question_text = q.get("text", "")[:40] + "..." if len(q.get("text", "")) > 40 else q.get("text", "")
        buttons.append([InlineKeyboardButton(
            text=f"{i}. {question_text}",
            callback_data=f"question_view_{q['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="steps_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_step_progress_indicator(
    step_number: int,
    total_steps: int,
    step_title: Optional[str] = None,
    answered_questions: Optional[int] = None,
    total_questions: Optional[int] = None
) -> str:
    """
    Format step progress indicator text.
    Example: "📘 Шаг 3 из 12: Принятие решения\nВопрос 5 из 7 в этом шаге"
    """
    from typing import Optional
    
    indicator_parts = []
    
    # Step indicator
    step_text = f"📘 Шаг {step_number} из {total_steps}"
    if step_title:
        step_text += f": {step_title}"
    indicator_parts.append(step_text)
    
    # Question progress indicator
    if answered_questions is not None and total_questions is not None and total_questions > 0:
        question_text = f"Вопрос {answered_questions + 1} из {total_questions} в этом шаге"
        indicator_parts.append(question_text)
    
    return "\n".join(indicator_parts)


def build_step_actions_markup() -> InlineKeyboardMarkup:
    """Markup for additional step actions during answering."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆘 Нужна помощь", callback_data="sos_help")],
        [InlineKeyboardButton(text="🧩 Заполнить по шаблону", callback_data="step_template")],
        [
            InlineKeyboardButton(text="⏸ Пауза", callback_data="step_pause"),
            InlineKeyboardButton(text="🔁 Другой вопрос", callback_data="step_switch_question")
        ],
        [
            InlineKeyboardButton(text="📜 Предыдущий", callback_data="step_previous"),
            InlineKeyboardButton(text="➕ Добавить ещё", callback_data="step_add_more")
        ]
    ])


# --- Steps Settings Keyboards ---

def build_steps_settings_markup() -> InlineKeyboardMarkup:
    """Markup for steps settings main menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧩 Активный шаблон", callback_data="settings_template")],
        [InlineKeyboardButton(text="✏️ Редактировать шаблон", callback_data="settings_edit_template")],
        [InlineKeyboardButton(text="🔄 Сброс на авторский", callback_data="settings_reset_template")],
        [InlineKeyboardButton(text="⏰ Напоминания", callback_data="settings_reminders")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_back")]
    ])

def build_template_selection_settings_markup(templates: list[dict], current_template_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """Markup for selecting template in settings."""
    buttons = []
    for template in templates:
        template_id = template.get("id")
        template_name = template.get("name", "")
        template_type = template.get("template_type", "")
        
        # Add indicator for active template
        prefix = "✅ " if template_id == current_template_id else ""
        type_indicator = "🧩" if template_type == "AUTHOR" else "✍️"
        
        buttons.append([InlineKeyboardButton(
            text=f"{prefix}{type_indicator} {template_name}",
            callback_data=f"settings_select_template_{template_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="settings_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_reminders_settings_markup(reminders_enabled: bool = False) -> InlineKeyboardMarkup:
    """Markup for reminders settings."""
    enabled_text = "✅ Включены" if reminders_enabled else "❌ Выключены"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⏰ Напоминания: {enabled_text}",
            callback_data="settings_toggle_reminders"
        )],
        [InlineKeyboardButton(text="🕐 Время напоминания", callback_data="settings_reminder_time")],
        [InlineKeyboardButton(text="📅 Дни недели", callback_data="settings_reminder_days")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings_back")]
    ])
