@echo off
REM Upload Learning Mate AI to your GitHub (first time: a GitHub login window opens - log in there).
cd /d "%~dp0"
set /p REPO="GitHub repo URL (e.g. https://github.com/yourname/learning-mate-ai.git): "
git remote remove origin >nul 2>&1
git remote add origin %REPO%
git branch -M main
git push -u origin main
echo.
echo Done. Refresh your GitHub page.
pause
