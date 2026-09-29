@echo off
set "SCM_PYTHON="
if defined PYTHON_EXE if exist "%PYTHON_EXE%" set "SCM_PYTHON=%PYTHON_EXE%"
if defined SCM_PYTHON goto found
if exist "%~dp0.venv\Scripts\python.exe" set "SCM_PYTHON=%~dp0.venv\Scripts\python.exe"
if defined SCM_PYTHON goto found
if exist "%~dp0.python_path" set /p "SCM_PYTHON="<"%~dp0.python_path"
if defined SCM_PYTHON if exist "%SCM_PYTHON%" goto found
set "SCM_PYTHON="
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "SCM_PYTHON=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if defined SCM_PYTHON goto found
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "SCM_PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if defined SCM_PYTHON goto found
if exist "%~dp0..\LogisticsLiveHub\.venv\Scripts\python.exe" set "SCM_PYTHON=%~dp0..\LogisticsLiveHub\.venv\Scripts\python.exe"
if defined SCM_PYTHON goto found
for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined SCM_PYTHON set "SCM_PYTHON=%%P"
if defined SCM_PYTHON goto found
echo ERROR: Python not found. Set PYTHON_EXE to the full python.exe path.
exit /b 1
:found
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
exit /b 0
