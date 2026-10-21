@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 build.py --nro %*) else (python build.py --nro %*)
pause
