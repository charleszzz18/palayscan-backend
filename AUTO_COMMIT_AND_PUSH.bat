@echo off
title PalayScan - Auto Git Commit and Push
cd /d "%~dp0"

echo ========================================================
echo       PALAYSCAN - AUTOMATIC COMMIT & PUSH TO GITHUB
echo ========================================================
echo.

:: Show changed files
echo Reviewing current changes:
git status -s
echo.

:: Ask for an optional commit message
set "USER_MSG="
set /p "USER_MSG=Enter commit message (or press ENTER for auto-timestamp): "

if "%USER_MSG%"=="" (
    set "USER_MSG=Auto-update: %date% %time%"
)

echo.
echo [1/3] Staging all changes...
git add .

echo [2/3] Committing changes...
git commit -m "%USER_MSG%"
if errorlevel 1 (
    echo.
    echo [NOTE] Nothing new to commit or working tree is already clean.
) else (
    echo.
    echo [3/3] Pushing to GitHub (origin master and main)...
    git push origin master
    git push origin master:main
    echo.
    echo ========================================================
    echo   SUCCESS! All changes are committed and pushed.
    echo   Vercel will now automatically deploy your updates.
    echo ========================================================
)

echo.
pause
