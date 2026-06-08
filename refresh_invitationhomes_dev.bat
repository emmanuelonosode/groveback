@echo off
setlocal

set "BACKEND_DIR=%~dp0"
set "SCRAPER_DIR=C:\Users\emman\Documents\Codex\2026-05-18\base-on-our-conversation-on-invitationhome"
set "JSON_FILE=%SCRAPER_DIR%\data\invitationhomes_properties_latest.json"
set "NODE_EXE=C:\Users\emman\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
set "PYTHON_EXE=%BACKEND_DIR%venv\Scripts\python.exe"

echo Refreshing Invitation Homes JSON...
"%NODE_EXE%" "%SCRAPER_DIR%\scrape_invitationhomes_json.mjs" --output "%JSON_FILE%"
if errorlevel 1 exit /b %errorlevel%

echo Importing JSON into the dev database...
cd /d "%BACKEND_DIR%"
"%PYTHON_EXE%" manage.py import_invitationhomes_json --json "%JSON_FILE%" --clear
if errorlevel 1 exit /b %errorlevel%

echo Done. Start the dev server with:
echo "%PYTHON_EXE%" manage.py runserver
