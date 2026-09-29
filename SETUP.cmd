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
echo.
echo SETUP DONE.
echo 1. Fill .env with approved company settings.
echo 2. Run CHECK.cmd.
echo 3. Run SYNC_ORACLE.cmd once for the MATNR / CONV_CODE / CONVEQQTY conversion model.
echo 4. Run VERIFY_CONVERSION.cmd, then START.cmd.
echo DEMO.cmd works without Oracle/Splunk and uses a SEPARATE synthetic database.
echo No packages were downloaded or installed.
pause
exit /b 0
:failed
echo Setup failed. Read the message above. The existing database was not reset.
pause
exit /b 1
