@echo off
cd /d "%~dp0"
where python >nul 2>nul && (python run.py) || (py run.py)
pause
