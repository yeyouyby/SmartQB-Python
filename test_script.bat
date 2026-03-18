@echo off
setlocal EnableDelayedExpansion

:: Check system python
python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" > tmp_pyver.txt 2>nul
set /p SYS_PYVER=<tmp_pyver.txt
del tmp_pyver.txt 2>nul

echo System Python is: !SYS_PYVER!
