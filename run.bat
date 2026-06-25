@echo off
REM Launch the assistant (no console window). For debugging, run: .venv\Scripts\python.exe run.py
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" run.py
