"""

import asyncio
import asyncpg
import os
from datetime import datetime

DB_CONFIG = {
    "host": "dpg-d4lr6ore5dus73fv0mtg-a.frankfurt-postgres.render.com",
    "port": 5432,
    "database": "twelvesteps_db",
    "user": "twelvesteps_db_user",
    "password": "WALT3o3sIG7q6BPeijZZQmdA7AJ2E3Nn"
}

TARGET_TELEGRAM_ID = "1797952290"


async def reset_user_data():
    """Полная очистка данных пользователя"""
    conn = None
    try:
        print(f"Подключение к базе данных...")
        conn = await asyncpg.connect(**DB_CONFIG)
        print("[OK] Подключение установлено")

        user_id = await conn.fetchval(
            "SELECT id FROM users WHERE telegram_id = $1",
            TARGET_TELEGRAM_ID
        )

        if user_id is None:
            print(f"[ERROR] Пользователь с telegram_id = {TARGET_TELEGRAM_ID} не найден")
            return

        print(f"[OK] Найден пользователь с ID: {user_id}")
        print(f"\nНачинаем удаление данных...")

        async with conn.transaction():
            profile_data_count = await conn.execute(
                "DELETE FROM profile_section_data WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из profile_section_data: {profile_data_count.split()[-1]}")

            profile_answers_count = await conn.execute(
                "DELETE FROM profile_answers WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из profile_answers: {profile_answers_count.split()[-1]}")

            template_progress_count = await conn.execute(
                "DELETE FROM template_progress WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из template_progress: {template_progress_count.split()[-1]}")

            step10_count = await conn.execute(
                "DELETE FROM step10_daily_analysis WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из step10_daily_analysis: {step10_count.split()[-1]}")

            step_answers_count = await conn.execute(
                "DELETE FROM step_answers WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из step_answers: {step_answers_count.split()[-1]}")

            user_steps_count = await conn.execute(
                "DELETE FROM user_steps WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из user_steps: {user_steps_count.split()[-1]}")

            tails_count = await conn.execute(
                "DELETE FROM tails WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из tails: {tails_count.split()[-1]}")

            messages_count = await conn.execute(
                "DELETE FROM messages WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из messages: {messages_count.split()[-1]}")

            frames_count = await conn.execute(
                "DELETE FROM frames WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из frames: {frames_count.split()[-1]}")

            session_contexts_count = await conn.execute(
                "DELETE FROM session_contexts WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из session_contexts: {session_contexts_count.split()[-1]}")

            session_states_count = await conn.execute(
                "DELETE FROM session_states WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из session_states: {session_states_count.split()[-1]}")

            frame_tracking_count = await conn.execute(
                "DELETE FROM frame_tracking WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из frame_tracking: {frame_tracking_count.split()[-1]}")

            qa_status_count = await conn.execute(
                "DELETE FROM qa_status WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из qa_status: {qa_status_count.split()[-1]}")

            user_meta_count = await conn.execute(
                "DELETE FROM user_meta WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из user_meta: {user_meta_count.split()[-1]}")

            tracker_summaries_count = await conn.execute(
                "DELETE FROM tracker_summaries WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из tracker_summaries: {tracker_summaries_count.split()[-1]}")

            gratitudes_count = await conn.execute(
                "DELETE FROM gratitudes WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из gratitudes: {gratitudes_count.split()[-1]}")

            answer_templates_count = await conn.execute(
                "DELETE FROM answer_templates WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из answer_templates: {answer_templates_count.split()[-1]}")

            profile_sections_count = await conn.execute(
                "DELETE FROM profile_sections WHERE user_id = $1",
                user_id
            )
            print(f"  [OK] Удалено записей из profile_sections: {profile_sections_count.split()[-1]}")

            """, user_id)
            print(f"  [OK] Поля в таблице users обнулены")

        print(f"\n[SUCCESS] Все данные пользователя с telegram_id = {TARGET_TELEGRAM_ID} успешно удалены")
        print(f"[SUCCESS] Запись пользователя сохранена, но все поля обнулены")

        print(f"\n[INFO] Проверка оставшихся данных:")
        tables_to_check = [
            "profile_section_data",
            "profile_answers",
            "messages",
            "frames",
            "step_answers",
            "user_steps",
            "template_progress",
            "step10_daily_analysis",
            "gratitudes"
        ]

        for table in tables_to_check:
            count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {table} WHERE user_id = $1",
                user_id
            )
            if count > 0:
                print(f"  [WARNING] В таблице {table} осталось {count} записей")
            else:
                print(f"  [OK] Таблица {table} пуста")

        user_exists = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE telegram_id = $1",
            TARGET_TELEGRAM_ID
        )
        print(f"  [OK] Запись в users сохранена: {user_exists > 0}")

    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            await conn.close()
            print(f"\n[OK] Соединение закрыто")


if __name__ == "__main__":
    print("=" * 60)
    print("Скрипт очистки данных пользователя")
    print(f"Telegram ID: {TARGET_TELEGRAM_ID}")
    print(f"Время запуска: {datetime.now()}")
    print("=" * 60)
    print()

    asyncio.run(reset_user_data())

