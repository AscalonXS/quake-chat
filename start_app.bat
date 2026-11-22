@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo ========================================================
echo   Earthquake Preparedness ^& Real-Time AI Simulator
echo ========================================================
echo.

:: 1. Locate Python executable (.venv, venv, or system python)
set "PY_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0venv\Scripts\python.exe"
)
echo [1/5] Using Python: %PY_EXE%

:: 2. Ensure frontend/.env points to local FastAPI backend
if not exist "%~dp0frontend\.env" (
    echo [2/5] Creating frontend\.env...
    (
        echo VITE_API_URL=http://localhost:8000
        echo VITE_USE_FAKE=false
    ) > "%~dp0frontend\.env"
) else (
    echo [2/5] Found existing frontend\.env
)

:: 3. Start Ollama if not already listening on port 11434
netstat -ano | findstr ":11434" >nul 2>&1
if errorlevel 1 (
    echo [3/5] Starting Ollama background server...
    start "Ollama Server" /min cmd /c "ollama serve"
    timeout /t 3 /nobreak >nul
) else (
    echo [3/5] Ollama is already running on port 11434.
)

:: 4. Install frontend dependencies if node_modules is missing
if not exist "%~dp0frontend\node_modules" (
    echo [4/5] Installing frontend npm packages for first-time setup...
    pushd "%~dp0frontend"
    call npm install
    popd
) else (
    echo [4/5] Frontend dependencies already installed.
)

:: 5. Launch FastAPI Backend and React Frontend in separate windows
echo [5/5] Launching FastAPI Backend on port 8000 and React Frontend on port 5173...
start "FastAPI Backend" /D "%~dp0backend" cmd /k ""%PY_EXE%" -m uvicorn main:app --port 8000"
timeout /t 3 /nobreak >nul

start "React Frontend" /D "%~dp0frontend" cmd /k "npm run dev"
timeout /t 4 /nobreak >nul

echo.
echo All services started! Opening http://localhost:5173 in your browser...
start "" http://localhost:5173

echo.
echo Close the FastAPI and React terminal windows when you want to stop the app.
pause