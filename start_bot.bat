@echo off
echo Starting API server and Telegram bot...

echo.
echo Step 1: Applying database migrations...
cd twelvesteps
python -c "from alembic.config import Config; from alembic import command; cfg = Config('alembic.ini'); command.upgrade(cfg, 'head')"
if errorlevel 1 (
    echo ERROR: Failed to apply migrations
    pause
    exit /b 1
)

echo.
echo Step 2: Starting API server...
start "API Server" cmd /k "cd twelvesteps && python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"

timeout /t 5 /nobreak >nul

echo.
echo Step 3: Starting Telegram bot...
start "Telegram Bot" cmd /k "cd twelvesteps_tgbot && python main.py"

echo.
echo Both services are starting...
echo API server: http://localhost:8000/docs
echo Check the opened windows for logs.
pause

