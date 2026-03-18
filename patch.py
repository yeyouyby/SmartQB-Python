with open('setup_new.bat', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith(':: 1. Check Python installation'):
        skip = True
        new_lines.append(""":: 1. Check Python installation and Version 3.12.x Requirement
echo [1/6] Checking Python 3.12.x Environment...

set "PYTHON_CMD="
set "PYTHON_VER="
set "LOCAL_PY312=%USERPROFILE%\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"

:: 1.1 Check if default 'python' is 3.12.x
python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" > tmp_pyver.txt 2>nul
if %errorlevel% equ 0 (
    set /p PYTHON_VER=<tmp_pyver.txt
)
del tmp_pyver.txt 2>nul

if "!PYTHON_VER!"=="3.12" (
    echo [OK] System default Python is 3.12.x.
    set "PYTHON_CMD=python"
    goto VerifyLaTeX
)

:: 1.2 If default is not 3.12, check py launcher
py -3.12 --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Found Python 3.12.x via Python Launcher.
    set "PYTHON_CMD=py -3.12"
    goto VerifyLaTeX
)

:: 1.3 Check common installation path
if exist "!LOCAL_PY312!" (
    echo [OK] Found Python 3.12.x in local AppData.
    set "PYTHON_CMD=!LOCAL_PY312!"
    goto VerifyLaTeX
)

:: 1.4 If 3.12.x is completely missing, auto-download and install
echo [INFO] Python 3.12.x is NOT found on your system!
echo [INFO] Downloading Python 3.12.10 installer...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe', 'python-3.12-setup.exe')"

if not exist python-3.12-setup.exe (
    echo [ERROR] Failed to download Python 3.12.10 installer.
    echo Please manually download and install it from https://www.python.org/downloads/release/python-31210/
    pause
    goto end_script
)

echo [INFO] Download complete. Starting silent installation...
echo [!] This will install Python 3.12 for the current user. Please wait...
start /wait "" python-3.12-setup.exe /quiet InstallAllUsers=0 PrependPath=0 Include_test=0

if exist "!LOCAL_PY312!" (
    echo [SUCCESS] Python 3.12.10 installed successfully!
    set "PYTHON_CMD=!LOCAL_PY312!"
    del python-3.12-setup.exe
    goto VerifyLaTeX
) else (
    echo [ERROR] Silent installation failed or path is unexpected.
    echo Please run 'python-3.12-setup.exe' manually.
    pause
    goto end_script
)

:VerifyLaTeX
echo.
""")
        continue

    if line.startswith(':: 2. Check and Install MiKTeX (LaTeX Engine)'):
        skip = False
        new_lines.append(line)
        continue

    if not skip:
        new_lines.append(line)

new_content = "".join(new_lines)
new_content = new_content.replace('echo [1/6] Checking LaTeX Compiler', 'echo [INFO] Checking LaTeX Compiler (xelatex)')
with open('setup_new.bat', 'w', encoding='utf-8') as f:
    f.write(new_content)
