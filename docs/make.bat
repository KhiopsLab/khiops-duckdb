@echo off
sphinx-build -W --keep-going -b html . _build/html
exit /b %errorlevel%
