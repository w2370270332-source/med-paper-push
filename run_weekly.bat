@echo off
cd /d g:\vs\med-paper-push
python pipeline.py 2>&1
echo.
echo Done. Exit code: %ERRORLEVEL%
