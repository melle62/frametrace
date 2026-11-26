@echo off
rem Opens the Frametrace window. Recording needs admin rights or the one-time
rem "Performance Log Users" setup; the window offers both if they're missing.
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw -m frametrace) || (python -m frametrace)
