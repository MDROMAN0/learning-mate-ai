@echo off
REM This PC = AI engine (Ollama) for the online site. Close window = site uses Gemini.
cd /d "%~dp0"
title Learning Mate - PC AI server (keep open)
python pc_server.py
pause
