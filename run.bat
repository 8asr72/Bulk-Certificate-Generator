@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo  STARTING BULK CERTIFICATE GENERATION PLATFORM
echo ============================================================

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [!] Virtual environment not found at %VENV_PYTHON%
    echo [*] Creating virtual environment...
    python -m venv .venv
    "%VENV_PYTHON%" -m pip install --upgrade pip
    "%VENV_PYTHON%" -m pip install -r requirements.txt
)

echo [+] Using Python: %VENV_PYTHON%
echo [+] Project Root: %~dp0
echo.
echo ^>^> Server listening at: http://127.0.0.1:8000
echo ^>^> Swagger Docs at:     http://127.0.0.1:8000/docs
echo ^>^> Press Ctrl+C in this terminal to stop the server
echo ============================================================
echo.

"%VENV_PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
