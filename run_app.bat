@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.9 or later and try again.
    pause
    exit /b 1
)
if not exist .env copy .env.example .env >nul
python -m pip install -r requirements.txt || (echo Could not install Python dependencies.& pause & exit /b 1)
python app.py --init-db
if errorlevel 1 (
    echo Check that the PostgreSQL service is running and .env has the correct DATABASE_URL.
    pause
    exit /b 1
)
python app.py
pause
