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
    """
    Produce the quick action keyboard shown after onboarding or in main flow.
    
    According to requirements:
    - 🪜 Работа по шагу     📖 Самоанализ  
    - 📘 Чувства            🙏 Благодарности  
    - ⚙️ Настройки          📎 Инструкция
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🪜 Работа по шагу"), KeyboardButton(text="📖 Самоанализ")],
            [KeyboardButton(text="📘 Чувства"), KeyboardButton(text="🙏 Благодарности")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📎 Инструкция")],
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
        [InlineKeyboardButton(text="💭 Не понял вопрос", callback_data="sos_help_question")],
        [InlineKeyboardButton(text="🔍 Хочу примеры", callback_data="sos_help_examples")],
        [InlineKeyboardButton(text="🪫 Просто тяжело", callback_data="sos_help_support")],
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
    import logging
    logger = logging.getLogger(__name__)
    
    buttons = []
    # Create buttons in rows of 3
    for i in range(0, len(steps), 3):
        row = []
        for j in range(3):
            if i + j < len(steps):
                step = steps[i + j]
                step_id = step.get('id')
                step_number = step.get('number')
                
                # Validate step data
                if step_id is None:
                    logger.warning(f"Step {i+j} has no 'id': {step}")
                    continue
                if step_number is None:
                    logger.warning(f"Step {i+j} has no 'number': {step}")
                    step_number = step_id  # Fallback to ID
                
                row.append(InlineKeyboardButton(
                    text=f"Шаг {step_number}",
                    callback_data=f"step_select_{step_id}"
                ))
        if row:  # Only add non-empty rows
            buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="steps_back")])
    logger.info(f"Built steps list markup with {len(buttons)-1} rows of step buttons")
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


def build_step_actions_markup(has_template_progress: bool = False) -> InlineKeyboardMarkup:
    """Markup for step actions during answering."""
    buttons = []
    
    # First row: Продолжить and Мой прогресс
    buttons.append([
        InlineKeyboardButton(text="▶️ Продолжить", callback_data="step_continue"),
        InlineKeyboardButton(text="📋 Мой прогресс", callback_data="step_progress")
    ])
    
    # Second row: Помощь and Сохранить
    buttons.append([
        InlineKeyboardButton(text="🧭 Помощь", callback_data="sos_help"),
        InlineKeyboardButton(text="⏸ Сохранить", callback_data="step_pause")
    ])
    
    # Third row: Назад
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="steps_back")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_template_filling_markup() -> InlineKeyboardMarkup:
    """Markup for template filling mode - pause and cancel options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏸ Пауза (сохранить прогресс)", callback_data="tpl_pause")],
        [InlineKeyboardButton(text="❌ Отменить заполнение", callback_data="tpl_cancel")]
    ])


def build_template_situation_complete_markup() -> InlineKeyboardMarkup:
    """Markup shown when a situation is complete."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Продолжить к следующей ситуации", callback_data="tpl_next_situation")],
        [InlineKeyboardButton(text="⏸ Пауза", callback_data="tpl_pause")]
    ])


def build_template_conclusion_markup() -> InlineKeyboardMarkup:
    """Markup shown before conclusion (after 3 situations)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Написать финальный вывод", callback_data="tpl_write_conclusion")],
        [InlineKeyboardButton(text="⏸ Пауза", callback_data="tpl_pause")]
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


# --- Main Settings Keyboards ---

def build_main_settings_markup() -> InlineKeyboardMarkup:
    """Main settings menu according to interface spec."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Напоминания", callback_data="main_settings_reminders")],
        [InlineKeyboardButton(text="🌐 Язык интерфейса", callback_data="main_settings_language")],
        [InlineKeyboardButton(text="🪪 Мой профиль", callback_data="main_settings_profile")],
        [InlineKeyboardButton(text="🔧 Настройки по шагу", callback_data="main_settings_steps")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_settings_back")]
    ])


def build_language_settings_markup(current_lang: str = "ru") -> InlineKeyboardMarkup:
    """Language selection menu."""
    ru_prefix = "✅ " if current_lang == "ru" else ""
    en_prefix = "✅ " if current_lang == "en" else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{ru_prefix}🇷🇺 Русский", callback_data="lang_ru")],
        [InlineKeyboardButton(text=f"{en_prefix}🇺🇸 English", callback_data="lang_en")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_settings_back")]
    ])


def build_step_settings_markup() -> InlineKeyboardMarkup:
    """Step-specific settings menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Начать заново текущий шаг", callback_data="step_settings_restart")],
        [InlineKeyboardButton(text="✏️ Настроить кастомный шаблон", callback_data="step_settings_custom_template")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_settings_back")]
    ])


def build_profile_settings_markup() -> InlineKeyboardMarkup:
    """Profile settings menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Рассказать о себе", callback_data="profile_settings_about")],
        [InlineKeyboardButton(text="🧭 Мои цели и мотивации (скоро)", callback_data="profile_settings_goals")],
        [InlineKeyboardButton(text="📈 История шагов (скоро)", callback_data="profile_settings_history")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_settings_back")]
    ])


def build_about_me_sections_markup() -> InlineKeyboardMarkup:
    """About me sections menu."""
    sections = [
        ("🏠 Семья", "about_family"),
        ("🧑‍🤝‍🧑 Друзья", "about_friends"),
        ("🎓 Учёба", "about_education"),
        ("🧒 Детство", "about_childhood"),
        ("🎨 Хобби", "about_hobby"),
        ("💼 Работа / Дело", "about_work"),
        ("🙌 Поддержка рядом", "about_support"),
        ("🕒 Режим и быт", "about_routine"),
        ("🧭 Ценности и правила", "about_values"),
        ("🛑 Границы и \"не трогать\"", "about_boundaries"),
        ("💪 Сильные стороны", "about_strengths"),
        ("🩺 Здоровье", "about_health"),
        ("📜 Свободный рассказ", "about_free"),
        ("➕ Добавить свой блок", "about_custom"),
    ]
    
    buttons = []
    row = []
    for text, callback in sections:
        row.append(InlineKeyboardButton(text=text, callback_data=callback))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="profile_settings_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_about_section_actions_markup(section_id: str) -> InlineKeyboardMarkup:
    """Actions inside an about me section."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить запись", callback_data=f"about_add_{section_id}"),
            InlineKeyboardButton(text="🗃️ История", callback_data=f"about_history_{section_id}")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="profile_settings_about")]
    ])


# --- Progress Keyboards ---

def build_progress_step_markup(step_id: int, step_number: int, step_title: str) -> InlineKeyboardMarkup:
    """Markup for viewing a specific step's progress with questions."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗂 Выбрать вопрос", callback_data=f"progress_questions_{step_id}")],
        [InlineKeyboardButton(text="▶️ Продолжить работу", callback_data="steps_continue")],
        [InlineKeyboardButton(text="◀️ Назад к списку шагов", callback_data="progress_steps_list")]
    ])


def build_progress_questions_markup(questions: list[dict], step_id: int) -> InlineKeyboardMarkup:
    """Markup for listing questions with status and allowing selection."""
    buttons = []
    for q in questions:
        q_id = q.get("id")
        q_number = q.get("number", 0)
        q_text = q.get("text", "")[:35]
        status = q.get("status", "")
        answer_preview = q.get("answer_preview", "")
        
        # Status emoji
        if status == "COMPLETED":
            status_emoji = "✅"
            if answer_preview:
                display_text = f"{status_emoji} {q_number}. {answer_preview[:30]}..."
            else:
                display_text = f"{status_emoji} {q_number}. {q_text}..."
        elif status == "IN_PROGRESS" or answer_preview:
            status_emoji = "⏳"
            display_text = f"{status_emoji} {q_number}. (черновик)"
        else:
            status_emoji = "⬜"
            display_text = f"{status_emoji} {q_number}. {q_text}..."
        
        buttons.append([InlineKeyboardButton(
            text=display_text[:60],
            callback_data=f"progress_select_q_{q_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"progress_step_{step_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_progress_steps_list_markup(steps: list[dict]) -> InlineKeyboardMarkup:
    """Markup for progress view - list of steps with their progress."""
    buttons = []
    for step in steps:
        step_id = step.get("id")
        step_number = step.get("number", step_id)
        step_title = step.get("title", "")[:20]
        answered = step.get("answered_questions", 0)
        total = step.get("total_questions", 0)
        
        if answered > 0:
            buttons.append([InlineKeyboardButton(
                text=f"🪜 Шаг {step_number} — {step_title} ({answered}/{total})",
                callback_data=f"progress_step_{step_id}"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                text=f"⬜ Шаг {step_number} — {step_title} (0/{total})",
                callback_data=f"progress_step_{step_id}"
            )])
    
    buttons.append([InlineKeyboardButton(text="🔁 Сменить текущий шаг", callback_data="steps_select")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="steps_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Gratitude/Thanks Keyboards ---

def build_thanks_menu_markup() -> InlineKeyboardMarkup:
    """Main gratitude/thanks menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить запись", callback_data="thanks_add")],
        [InlineKeyboardButton(text="🗃️ История", callback_data="thanks_history")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="thanks_back")]
    ])


def build_thanks_history_markup(page: int = 1, has_more: bool = False) -> InlineKeyboardMarkup:
    """Pagination for thanks history."""
    buttons = []
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"thanks_page_{page - 1}"))
    if has_more:
        nav_row.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"thanks_page_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="thanks_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Feelings Keyboards ---

# Categorized feelings list based on the feelings table (таблица чувств)
FEELINGS_CATEGORIES = {
    "😠 ГНЕВ": [
        "бешенство", "ярость", "ненависть", "истерия", "злость", "раздражение", 
        "презрение", "негодование", "обида", "ревность", "уязвлённость", "досада", 
        "зависть", "неприязнь", "возмущение", "отвращение"
    ],
    "😰 СТРАХ": [
        "ужас", "отчаяние", "испуг", "оцепенение", "подозрение", "тревога", 
        "ошарашенность", "беспокойство", "боязнь", "унижение", "замешательство", 
        "растерянность", "вина", "стыд", "сомнение", "застенчивость", "опасение", 
        "смущение", "сломленность", "надменность", "ошеломлённость"
    ],
    "😢 ГРУСТЬ": [
        "горечь", "тоска", "скорбь", "лень", "жалость", "отрешённость", 
        "отчаяние", "беспомощность", "душевная боль", "безнадёжность", 
        "отчуждённость", "разочарование", "потрясение", "сожаление", "скука", 
        "безысходность", "печаль", "загнанность"
    ],
    "😊 РАДОСТЬ": [
        "счастье", "восторг", "ликование", "приподнятость", "оживление", 
        "умиротворение", "увлечение", "интерес", "забота", "ожидание", 
        "возбуждение", "предвкушение", "надежда", "любопытство", "освобождение", 
        "принятие", "нетерпение", "вера", "изумление"
    ],
    "💗 ЛЮБОВЬ": [
        "нежность", "теплота", "сочувствие", "блаженство", "доверие", 
        "безопасность", "благостность", "спокойствие", "симпатия", "гордость", 
        "восхищение", "уважение", "самоценность", "влюблённость", "любовь к себе", 
        "очарованность", "смирение", "искренность", "дружелюбие", "доброта", "взаимовыручка"
    ],
    "🧠 СОСТОЯНИЯ": [
        "нервозность", "пренебрежение", "недовольство", "вредность", "огорчение", 
        "нетерпимость", "вседозволенность", "раскаяние", "безысходность", 
        "превосходство", "высокомерие", "неполноценность", "неудобство", "неловкость", 
        "апатия", "безразличие", "неуверенность", "тупик", "усталость", "принуждение", 
        "одиночество", "отверженность", "подавленность", "холодность", "безучастность", 
        "равнодушие", "удовлетворение", "уверенность", "довольство", "окрылённость", 
        "торжественность", "жизнерадостность", "облегчение", "ободрённость", "удивление",
        "сопереживание", "сопричастность", "уравновешенность", "смирение", 
        "естественность", "жизнелюбие", "вдохновение", "воодушевление"
    ]
}

# Common fears list (страхи)
FEARS_LIST = [
    "страх оценки", "страх ошибки", "страх нового", "страх одиночества", 
    "страх ответственности", "страх темноты", "страх высоты", 
    "страх разочарования в себе", "страх будущего", "страх за свою жизнь"
]


def build_feelings_categories_markup() -> InlineKeyboardMarkup:
    """Markup for selecting feelings category."""
    buttons = []
    for category in FEELINGS_CATEGORIES.keys():
        buttons.append([InlineKeyboardButton(text=category, callback_data=f"feelings_cat_{category[:10]}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="feelings_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_feelings_list_markup(category: str) -> InlineKeyboardMarkup:
    """Markup for selecting specific feelings from a category."""
    feelings = []
    for cat_name, cat_feelings in FEELINGS_CATEGORIES.items():
        if cat_name.startswith(category) or category in cat_name:
            feelings = cat_feelings
            break
    
    buttons = []
    row = []
    for feeling in feelings:
        row.append(InlineKeyboardButton(text=feeling, callback_data=f"feeling_select_{feeling[:15]}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад к категориям", callback_data="feelings_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_all_feelings_markup() -> InlineKeyboardMarkup:
    """Markup with categories to choose from (table is too big for buttons)."""
    buttons = []
    
    for category in FEELINGS_CATEGORIES.keys():
        buttons.append([InlineKeyboardButton(text=category, callback_data=f"feelings_cat_{category}")])
    
    # Add fears button
    buttons.append([InlineKeyboardButton(text="⚠️ СТРАХИ (список)", callback_data="feelings_fears")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="feelings_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_feelings_category_markup(category: str) -> InlineKeyboardMarkup:
    """Show feelings from a specific category."""
    feelings = FEELINGS_CATEGORIES.get(category, [])
    
    buttons = []
    row = []
    for feeling in feelings:
        # Truncate long feelings for button
        btn_text = feeling[:18] if len(feeling) > 18 else feeling
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"feeling_copy_{feeling[:20]}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="◀️ К категориям", callback_data="feelings_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_fears_markup() -> InlineKeyboardMarkup:
    """Show list of common fears."""
    buttons = []
    for fear in FEARS_LIST:
        buttons.append([InlineKeyboardButton(text=fear, callback_data=f"feeling_copy_{fear[:20]}")])
    
    buttons.append([InlineKeyboardButton(text="◀️ К категориям", callback_data="feelings_categories")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def format_feelings_table_text() -> str:
    """Format the feelings table as text for display."""
    text = "📘 ТАБЛИЦА ЧУВСТВ\n\n"
    
    for category, feelings in FEELINGS_CATEGORIES.items():
        text += f"{category}\n"
        # Join feelings with commas, wrap lines
        feelings_line = ", ".join(feelings)
        text += f"{feelings_line}\n\n"
    
    text += "⚠️ СТРАХИ:\n"
    text += ", ".join(FEARS_LIST)
    
    return text
