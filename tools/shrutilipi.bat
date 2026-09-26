@echo off
python "%~dp0fetch.py" %*
exit /b %errorlevel%
