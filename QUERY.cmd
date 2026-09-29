@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0_python.cmd"
if errorlevel 1 goto failed
if "%~1"=="" (
  echo Usage: QUERY.cmd --file "examples\today_inbound.sql"
  echo Usage: QUERY.cmd --sql "SELECT * FROM v_source_health"
  goto finished
)
"%SCM_PYTHON%" run.py query %*
if errorlevel 1 goto failed
:finished

if errorlevel 1 goto failed
pause
exit /b 0
:failed
echo.
echo Command failed. The previous live database is not deleted.
pause
exit /b 1
