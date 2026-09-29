@echo off
REM One-click: install everything, run doctor + offline tests, write logs for Claude.
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set LOG=%~dp0setup_log.txt
echo === setup_check %date% %time% === > "%LOG%"
where python >> "%LOG%" 2>&1
python --version >> "%LOG%" 2>&1
if errorlevel 1 (
  echo Python nai. Install korchi... install shesh hole ei window bondho kore setup_check.bat abar chalao
  echo PYTHON_MISSING >> "%LOG%"
  winget install -e --id Python.Python.3.12
  pause & exit /b 1
)
where ffmpeg >nul 2>&1 || (echo ffmpeg install korchi... & winget install -e --id Gyan.FFmpeg)
where deno >nul 2>&1 || (echo deno install korchi... & winget install -e --id DenoLand.Deno)
if not exist .venv (
  echo Prothombar: venv + packages install hocche, kichu minute lagbe...
  python -m venv .venv >> "%LOG%" 2>&1 || (echo VENV_FAILED >> "%LOG%" & echo venv fail & pause & exit /b 1)
)
echo Packages install/update hocche...
.venv\Scripts\python -m pip install -q --upgrade pip >> "%LOG%" 2>&1
.venv\Scripts\python -m pip install -q -r requirements.txt >> "%LOG%" 2>&1 || (echo PIP_FAILED >> "%LOG%" & echo pip fail & pause & exit /b 1)
echo Doctor check cholche...
echo ===== DOCTOR ===== >> "%LOG%"
.venv\Scripts\python doctor.py >> "%LOG%" 2>&1
echo Offline test cholche...
echo ===== TEST_MOCK ===== >> "%LOG%"
.venv\Scripts\python test_mock.py > test_log.txt 2>&1
findstr /C:"ALL TESTS PASSED" test_log.txt >> "%LOG%" || (echo TEST_FAILED >> "%LOG%" & powershell -NoProfile -Command "Get-Content test_log.txt -Tail 25" >> "%LOG%")
echo ===== DONE ===== >> "%LOG%"
echo.
echo Shesh! Claude-ke "done" likho.
pause
