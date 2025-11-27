# ...existing code...

import os
import tempfile
import asyncio

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from repositories.MessageRepository import MessageRepository



async def run():
    # если задана DATABASE_URL — используем её (ожидается async URL, например postgresql+asyncpg://...)
    db_url = os.environ.get("DATABASE_URL")
    using_temp_file = False

    if not db_url:
        # fallback — временный sqlite файл
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tf.close()
        db_path = tf.name
        db_url = f"sqlite+aiosqlite:///{db_path}"
        using_temp_file = True

    engine = create_async_engine(db_url, echo=False)

    # создаём таблицы по моделям (если их ещё нет)

    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        repo = MessageRepository(session)
        user_id = 1

        tx = None
        # when using a real DB, run inside a transaction and rollback it afterwards
        if not using_temp_file:
            print("Using real DATABASE_URL — running test inside a transaction (will rollback).")
            tx = await session.begin()

        try:
            messages = await repo.get_last_messages(user_id,)
        except Exception as e:
            print("get_last_messages raised:", e)
            # ensure messages is defined so rest of flow can run and we rollback once in finally
            messages = []
        

        # печатаем найденные сообщения в терминал
        print("Последние сообщения пользователя", user_id)
        for m in messages:
            print(f"- id={getattr(m,'id',None)} text={m.text_value!r} sender={getattr(m,'sender_role',None)} created_at={getattr(m,'created_at',None)}")

    await engine.dispose()
    if using_temp_file:
        os.unlink(db_path)

if __name__ == "__main__":
    asyncio.run(run())
# ...existing code...