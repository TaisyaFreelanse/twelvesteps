# Статус тестирования проекта 12 шагов

## Запущенные сервисы

### ✅ API сервер
- **Статус:** Запущен в фоновом режиме
- **URL:** http://localhost:8000
- **Документация:** http://localhost:8000/docs
- **Команда запуска:** `python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000`

### ✅ Telegram бот
- **Статус:** Запущен в фоновом режиме
- **Токен:** Настроен из `telegram.env`
- **Команда запуска:** `python main.py` (из директории `twelvesteps_tgbot`)

### ⚠️ База данных
- **Статус:** Работает на порту 5432
- **URL:** postgresql+asyncpg://postgres:password@localhost:5432/twelvesteps
- **Миграции:** Требуется применение (alembic upgrade head)

## Следующие шаги для тестирования

1. **Применить миграции:**
   ```bash
   cd twelvesteps
   python -c "from alembic.config import Config; from alembic import command; cfg = Config('alembic.ini'); command.upgrade(cfg, 'head')"
   ```

2. **Проверить API эндпоинты:**
   - Открыть http://localhost:8000/docs в браузере
   - Протестировать эндпоинты через Swagger UI

3. **Протестировать Telegram бота:**
   - Найти бота в Telegram
   - Отправить команду `/start`
   - Проверить регистрацию и валидацию ввода

4. **Выполнить тесты из TESTING_CHECKLIST.md**

## Проверка работы сервисов

### Проверка API:
```bash
curl http://localhost:8000/docs
curl http://localhost:8000/health  # если есть health endpoint
```

### Проверка бота:
- Откройте Telegram
- Найдите вашего бота по токену
- Отправьте `/start`

## Логи

Логи API и бота выводятся в терминалы, где они запущены.

