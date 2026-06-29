@echo off
REM Builds a double-clickable Windows .exe for the SMD NXT Agent GUI.
REM Run this once from an activated venv with the dev extras installed:
REM   pip install -e ".[dev]"
REM   build_gui_exe.bat
REM The result is dist\smd-nxt-gui.exe. The app reads config\ and writes
REM .env from its current working directory, so keep config\ next to the
REM .exe (copy dist\smd-nxt-gui.exe up into the project root, or copy
REM config\ into dist\) before handing it to a non-technical user.

pyinstaller --noconfirm --onefile --windowed --name smd-nxt-gui ^
    src\smd_nxt_agent\gui.py

echo.
echo Done. Find it at dist\smd-nxt-gui.exe
