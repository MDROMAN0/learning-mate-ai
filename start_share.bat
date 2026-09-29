@echo off
REM Same as start.bat but also creates a free public link (needs APP_PASSWORD in .env and cloudflared)
cd /d "%~dp0"
call start.bat --share
