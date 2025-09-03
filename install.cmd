@echo off
REM Create virtual environment
python -m venv venv

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

REM Install project dependencies
pip install -r requirements.txt

echo.
echo ==================================================
echo Setup complete! To activate the environment later:
echo     call venv\Scripts\activate.bat
echo ==================================================
pause
