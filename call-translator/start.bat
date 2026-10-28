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
if not exist .env copy .env.example .env >nul

call .venv\Scripts\activate.bat
set PORT=8000
for /f "tokens=2 delims==" %%a in ('findstr /b "PORT=" .env') do set PORT=%%a
REM Open the browser once the server answers (up to ~2 minutes).
start "" /min powershell -NoProfile -Command "for($i=0;$i -lt 120;$i++){try{Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/api/status | Out-Null; Start-Process http://localhost:%PORT%; break}catch{Start-Sleep 1}}"
echo Starting on http://localhost:%PORT%  (close this window to stop)
python -m app.server
pause
