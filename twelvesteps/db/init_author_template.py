"""Initialize author template if it doesn't exist."""
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, insert
from db.models import AnswerTemplate, TemplateType

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@postgres:5432/twelvesteps")

# Структура авторского шаблона согласно Руководству.pdf
# Порядок: Ситуация → Мысли → Чувства (до, минимум 3) → Действия (по факту) → 
# Чувства здоровой части (после) → Пути выхода / следующий шаг → Вывод → Что не попало
author_template_structure = {
    "situation": {
        "label": "Ситуация",
        "description": "Опиши ситуацию, которая произошла. Что случилось?",
        "order": 1
    },
    "thoughts": {
        "label": "Мысли",
        "description": "Какие мысли у тебя были в этой ситуации?",
        "order": 2
    },
    "feelings_before": {
        "label": "Чувства (до)",
        "description": "Какие чувства ты испытывал(а) до действий? Опиши минимум 3 чувства.",
        "order": 3,
        "min_items": 3
    },
    "actions": {
        "label": "Действия (по факту)",
        "description": "Что ты сделал(а) в этой ситуации? Опиши действия по факту, как они были.",
        "order": 4
    },
    "feelings_after": {
        "label": "Чувства здоровой части (после)",
        "description": "Какие чувства появились после действий? Что чувствует твоя здоровая часть?",
        "order": 5
    },
    "exit_paths": {
        "label": "Пути выхода / следующий шаг",
        "description": "Какие пути выхода ты видишь? Что можешь сделать? (Например: «сделаю X до 18:00»)",
        "order": 6
    },
    "conclusion": {
        "label": "Вывод",
        "description": "Краткий вывод: триггер → мысль → чувство → действие → последствия",
        "order": 7
    },
    "what_didnt_fit": {
        "label": "Что не попало",
        "description": "Что ещё важно, но не попало в предыдущие поля?",
        "order": 8
    }
}

async def main():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        async with session.begin():
            # Check if author template exists
            query = select(AnswerTemplate).where(AnswerTemplate.template_type == TemplateType.AUTHOR)
            result = await session.execute(query)
            existing_template = result.scalar_one_or_none()
            
            if existing_template:
                print(f"Author template already exists: ID={existing_template.id}, Name={existing_template.name}")
                return
            
            # Create author template
            print("Creating author template...")
            new_template = AnswerTemplate(
                id=1,
                user_id=None,
                name="Авторский шаблон",
                template_type=TemplateType.AUTHOR,
                structure=author_template_structure
            )
            session.add(new_template)
            await session.commit()
            print("Author template created successfully!")

if __name__ == "__main__":
    asyncio.run(main())

