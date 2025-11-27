import asyncio

from dotenv import load_dotenv

from core.chat_service import handle_chat
import asyncio

load_dotenv() 




async def main_loop():
    user_telegram_id = 1
    print("Пользователь готов к работе. Начинаем чат.")
    print("Наберите сообщение и нажмите Enter (Ctrl+C для выхода).")

    while True:
        message_text = input(">>> ")
        if not message_text.strip():
            continue

        try:
            reply = await handle_chat(user_telegram_id, message_text)
        except Exception as e:
            print(f"Ошибка при обработке сообщения: {e}")
            continue

        print("Ассистент:", reply)


if __name__ == "__main__":
    asyncio.run(main_loop())
