@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run.py
) else (
  echo This Windows installation has not been prepared yet.
  echo Please use the Mac app for now. Windows needs its own local runtime and firewall setup.
  pause
)
