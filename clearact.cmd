@echo off
setlocal
set "CLEARACT_ROOT=%~dp0"
set "PYTHONPATH=%CLEARACT_ROOT%src;%PYTHONPATH%"
python -m clearact.cli %*
endlocal
