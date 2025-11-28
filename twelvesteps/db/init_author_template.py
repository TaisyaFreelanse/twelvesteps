"""Initialize author template if it doesn't exist."""
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, insert, update
from db.models import AnswerTemplate, TemplateType

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@postgres:5432/twelvesteps")

# Структура авторского шаблона согласно Руководству.pdf (РАСШИРЕННАЯ ВЕРСИЯ)
# Поддерживает множественные ситуации в одном ответе
#
# Формат:
# - Дата, Вопрос
# - СИТУАЦИЯ 1, 2, 3... (неограниченно)
#   - Где (контекст)
#   - Думаю (мысли)
#   - Чувства до (минимум 3)
#   - Действия (по факту)
#   - Чувства здоровой части (после)
#   - Пути выхода / следующий шаг
# - ВЫВОД (общий)

author_template_structure = {
    "version": 2,  # Версия шаблона для обратной совместимости
    
    # Заголовок ответа
    "header": {
        "date": {
            "label": "Дата",
            "description": "Дата заполнения (формат: YYYY-MM-DD)",
            "order": 1,
            "type": "date"
        },
        "question": {
            "label": "Вопрос",
            "description": "Текст вопроса, на который отвечаешь",
            "order": 2,
            "type": "text",
            "auto_fill": True  # Система заполнит автоматически
        }
    },
    
    # Массив ситуаций (можно добавлять сколько угодно)
    "situations": {
        "label": "Ситуации",
        "description": "Можешь описать одну или несколько ситуаций",
        "type": "array",
        "min_items": 1,
        "max_items": 10,
        "item_structure": {
            "where": {
                "label": "Где",
                "description": "Где/когда произошла ситуация? Контекст.",
                "order": 1,
                "type": "text",
                "example": "Оплата сервера, саппорт молчит (день)"
            },
            "thoughts": {
                "label": "Думаю",
                "description": "Какие мысли были? Внутренний диалог.",
                "order": 2,
                "type": "text",
                "example": "«Застрял. Всё встанет»"
            },
            "feelings_before": {
                "label": "Чувства (до)",
                "description": "Какие чувства испытывал(а) до действий? Минимум 3. Можно с интенсивностью (1-10).",
                "order": 3,
                "type": "text",
                "min_items": 3,
                "example": "тревога 6/10, раздражение, беспомощность"
            },
            "actions": {
                "label": "Действия",
                "description": "Что сделал(а) по факту?",
                "order": 4,
                "type": "text",
                "example": "залип в почте, отложил другие задачи"
            },
            "feelings_after": {
                "label": "Чувства от здоровой части",
                "description": "Что чувствует здоровая часть? Какие чувства появились после осознания?",
                "order": 5,
                "type": "text",
                "example": "принятие, лёгкая надежда"
            },
            "exit_paths": {
                "label": "Пути выхода / следующий шаг",
                "description": "Конкретный следующий шаг с дедлайном.",
                "order": 6,
                "type": "text",
                "example": "написать 1 письмо в саппорт и статус партнёрам до 12:30; затем 10 мин на запасную задачу"
            }
        }
    },
    
    # Общий вывод по всем ситуациям
    "conclusion": {
        "label": "ВЫВОД",
        "description": "Общий вывод по всем ситуациям. Что понял(а)? Какие паттерны заметил(а)?",
        "order": 100,
        "type": "text",
        "optional": True
    },
    
    # Дополнительные заметки
    "notes": {
        "label": "Что не попало",
        "description": "Что ещё важно, но не вошло в ситуации?",
        "order": 101,
        "type": "text",
        "optional": True
    }
}

# Пример заполненного ответа по новому шаблону (для документации)
example_filled_answer = {
    "header": {
        "date": "2025-08-18",
        "question": "Опускаются ли у меня руки, когда всё идёт не по плану?"
    },
    "situations": [
        {
            "where": "Оплата сервера, саппорт молчит (день)",
            "thoughts": "«Застрял. Всё встанет»",
            "feelings_before": "тревога 6/10, раздражение, беспомощность",
            "actions": "залип в почте, отложил другие задачи",
            "feelings_after": "принятие, лёгкая надежда",
            "exit_paths": "написать 1 письмо в саппорт и статус партнёрам до 12:30; затем 10 мин на запасную задачу"
        },
        {
            "where": "Вечер, окно шага пропущено",
            "thoughts": "«Поздно. Завтра»",
            "feelings_before": "усталость, стыд, жалость к себе",
            "actions": "хотел отменить шаг",
            "feelings_after": "уважение к себе за минимум",
            "exit_paths": "10-мин краткий шаг сейчас; спать до 23:30; завтра — 30 мин шага до 18:00"
        },
        {
            "where": "Переписка с женой про отпуск",
            "thoughts": "«Не готов к общему отпуску сейчас»",
            "feelings_before": "напряжение, вина, грусть",
            "actions": "честно отказал",
            "feelings_after": "ясность, уважение к границам, сострадание",
            "exit_paths": "предложить жене короткий уикенд вместе; обсудить сегодня 19:30"
        }
    ],
    "conclusion": "Паттерн: при неопределённости включается тревога и желание контролировать. Здоровый выход — конкретный минимальный шаг с дедлайном.",
    "notes": None
}


async def main():
    """Initialize or update author template."""
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        async with session.begin():
            # Check if author template exists
            query = select(AnswerTemplate).where(AnswerTemplate.template_type == TemplateType.AUTHOR)
            result = await session.execute(query)
            existing_template = result.scalar_one_or_none()
            
            if existing_template:
                # Update existing template to new structure
                print(f"Updating author template (ID={existing_template.id}) to version 2...")
                existing_template.structure = author_template_structure
                existing_template.name = "Авторский шаблон (множественные ситуации)"
                await session.commit()
                print("✅ Author template updated to version 2!")
                print(f"   Now supports multiple situations per answer.")
                return
            
            # Create author template
            print("Creating author template (version 2)...")
            new_template = AnswerTemplate(
                id=1,
                user_id=None,
                name="Авторский шаблон (множественные ситуации)",
                template_type=TemplateType.AUTHOR,
                structure=author_template_structure
            )
            session.add(new_template)
            await session.commit()
            print("✅ Author template created successfully!")


async def show_example():
    """Print example of filled answer."""
    import json
    print("\n📝 Пример заполненного ответа по шаблону:")
    print("=" * 60)
    print(json.dumps(example_filled_answer, ensure_ascii=False, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
