@echo off
REM Double-click to run. First run creates a venv and installs packages.
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist .venv (
  echo First run: setting up... this takes a few minutes
  python -m venv .venv || (echo Python not found. Install Python 3.10+ first & pause & exit /b 1)
  .venv\Scripts\python -m pip install -r requirements.txt || (echo pip install failed & pause & exit /b 1)
)
.venv\Scripts\python run.py %*
pause
