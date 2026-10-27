@echo off
REM Start the Live Call Translator (Windows). First run creates the venv.
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo Python 3.11+ is required: https://www.python.org/downloads/
    pause
    exit /b 1
  )
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
if not exist .env (
  copy .env.example .env >nul
  echo Created .env - add your ANTHROPIC_API_KEY to it, then run start.bat again.
  notepad .env
)

call .venv\Scripts\activate.bat
set PORT=8000
for /f "tokens=2 delims==" %%a in ('findstr /b "PORT=" .env') do set PORT=%%a
start "" cmd /c "timeout /t 3 >nul & start http://localhost:%PORT%"
echo Starting on http://localhost:%PORT%  (close this window to stop)
python -m app.server
pause
