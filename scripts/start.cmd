@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set PYTHON=%~dp0..\venv\Scripts\python.exe
if not exist "%PYTHON%" set PYTHON=python

"%PYTHON%" main.py
