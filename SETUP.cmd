@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0_python.cmd"
if errorlevel 1 goto failed
"%SCM_PYTHON%" tools\select_python.py --auto
if errorlevel 1 goto failed
call "%~dp0_python.cmd"
"%SCM_PYTHON%" run.py setup
if errorlevel 1 goto failed
"%SCM_PYTHON%" run.py init
if errorlevel 1 goto failed
"%SCM_PYTHON%" run.py doctor
echo.
echo SETUP DONE. Fill .env with approved company settings, then run START.cmd.
echo DEMO.cmd works without Oracle/Splunk and uses a SEPARATE synthetic database.
echo No packages were downloaded or installed.
pause
exit /b 0
:failed
echo Setup failed. Read the message above. The existing database was not reset.
pause
exit /b 1
