@echo off
echo ========================================
echo   InvoiceAI - Starting Application
echo ========================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

:: Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

:: Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate

:: Install/update dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet

:: Check if .env exists
if not exist ".env" (
    echo.
    echo Creating .env file from template...
    copy .env.example .env
    echo.
    echo IMPORTANT: Edit the .env file with your configuration
    echo Opening .env in Notepad...
    notepad .env
    echo.
    echo After editing .env, run this script again.
    pause
    exit /b 0
)

:: Run the application
echo.
echo ========================================
echo   Starting InvoiceAI on port 5000
echo   Open http://localhost:5000 in your browser
echo ========================================
echo.
echo Press Ctrl+C to stop the server
echo.
python app.py

pause
