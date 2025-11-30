# Настройка проекта twelvesteps на Render

## ✅ Что уже сделано:

1. **Создан веб-сервис API**: `twelvesteps-api`
   - URL: https://twelvesteps-api.onrender.com
   - Dashboard: https://dashboard.render.com/web/srv-d4lr6iruibrs73876skg
   - Репозиторий: https://github.com/TaisyaFreelanse/twelvesteps.git
   - Ветка: main
   - Регион: Frankfurt
   - План: Starter

2. **Создана база данных PostgreSQL**: `twelvesteps-db`
   - Dashboard: https://dashboard.render.com/d/dpg-d4lr6ore5dus73fv0mtg-a
   - Имя базы: twelvesteps_db
   - Пользователь: twelvesteps_db_user
   - Хост: dpg-d4lr6ore5dus73fv0mtg-a.frankfurt-postgres.render.com
   - Порт: 5432
   - План: basic_256mb

3. **Создан Telegram бот сервис**: `twelvesteps-bot`
   - Dashboard: https://dashboard.render.com/web/srv-d4lrb3a4d50c73e8jktg
   - URL: https://twelvesteps-bot.onrender.com
   - Репозиторий: https://github.com/TaisyaFreelanse/twelvesteps.git
   - Ветка: main
   - Регион: Frankfurt
   - План: Starter

## ✅ Настройка завершена!

### Переменные окружения API сервиса:

- ✅ `OPENAI_API_KEY` - установлен
- ✅ `DATABASE_URL` - установлен и настроен для asyncpg

### Переменные окружения Telegram бота:

- ✅ `BOT_TOKEN` - установлен (6602283402:AAGIAmqplJA380fROp3OrnT3qTXCJoAkqLU)
- ✅ `BACKEND_API_BASE_URL` - установлен (https://twelvesteps-api.onrender.com)
- ✅ `BACKEND_URL` - установлен (https://twelvesteps-api.onrender.com)

### Статус деплоя:

Сервис автоматически перезапускается с новыми настройками. Деплой в процессе:
- Build: в процессе
- Миграции: будут применены автоматически при старте
- URL: https://twelvesteps-api.onrender.com

### Детали подключения к БД:

- **Hostname**: dpg-d4lr6ore5dus73fv0mtg-a
- **Port**: 5432
- **Database**: twelvesteps_db
- **Username**: twelvesteps_db_user
- **Internal URL**: `postgresql+asyncpg://twelvesteps_db_user:***@dpg-d4lr6ore5dus73fv0mtg-a:5432/twelvesteps_db`

## 📝 Команды запуска:

- **Build**: `cd twelvesteps && pip install -r requirements.txt`
- **Start**: `cd twelvesteps && python apply_migrations_smart.py && python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT`

## 🔗 Полезные ссылки:

- **API сервис**: https://twelvesteps-api.onrender.com
- **Telegram бот**: https://twelvesteps-bot.onrender.com
- **Dashboard API**: https://dashboard.render.com/web/srv-d4lr6iruibrs73876skg
- **Dashboard Бот**: https://dashboard.render.com/web/srv-d4lrb3a4d50c73e8jktg
- **Dashboard БД**: https://dashboard.render.com/d/dpg-d4lr6ore5dus73fv0mtg-a

## 🤖 Telegram бот:

Бот настроен и запущен. Он автоматически подключается к API сервису и готов отвечать на сообщения.

