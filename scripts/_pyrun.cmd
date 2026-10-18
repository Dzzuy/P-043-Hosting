@echo off
REM Local virtualenv first. Preserve Python's exit code, including failures.
if exist "%~dp0..\.venv\Scripts\python.exe" goto local_python
where py >nul 2>nul
if not errorlevel 1 goto py_launcher
where python >nul 2>nul
if not errorlevel 1 goto system_python
where python3 >nul 2>nul
if not errorlevel 1 goto python3_launcher
echo [ai-log] Python not found; hook was not executed. 1>&2
exit /b 1

:local_python
"%~dp0..\.venv\Scripts\python.exe" %*
exit /b %ERRORLEVEL%

:py_launcher
py -3 %*
exit /b %ERRORLEVEL%

:system_python
python %*
exit /b %ERRORLEVEL%

:python3_launcher
python3 %*
exit /b %ERRORLEVEL%
