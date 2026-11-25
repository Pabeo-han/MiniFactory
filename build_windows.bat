@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto use_python
py -3.14 -m venv .venv
if errorlevel 1 goto failed
goto install
:use_python
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller==6.22.3
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name MiniFactory --add-data "assets:assets" main.py
if errorlevel 1 goto failed
echo Built "%CD%\dist\MiniFactory.exe"
exit /b 0
:failed
echo Build failed. Review the error above. Python 3.14 x64 is recommended.
exit /b 1
