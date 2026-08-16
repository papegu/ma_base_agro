@echo off
cd /d "%~dp0"
echo Demarrage de l'interface web sur http://127.0.0.1:5050 ...
".venv\Scripts\python.exe" scripts\db_web_admin.py
pause
