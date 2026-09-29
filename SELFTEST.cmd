@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0_python.cmd"
if errorlevel 1 goto failed
"%SCM_PYTHON%" -S -m unittest discover -s tests -v %*
if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo.
echo Command failed. Existing settings and database were preserved.
pause
exit /b 1
