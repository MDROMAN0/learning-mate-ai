@echo off
REM ON switch: this PC answers for the online site while this window is open.
REM Close this window = OFF (site uses its backup).
cd /d "%~dp0"
title Learning Mate - PC AI server ON (close = OFF)
set "PATH=G:\Ollama;%PATH%"
tasklist /fi "imagename eq ollama.exe" | find /i "ollama.exe" >nul || (start "" /min ollama serve & timeout /t 6 >nul)
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
"%PY%" pc_server.py
pause
