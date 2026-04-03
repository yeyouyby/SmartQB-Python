@echo off
setlocal EnableDelayedExpansion
set "EXIT_CODE=0"
color 0A

echo ========================================================
echo        SmartQB Pro V3 (Ultimate) Environment Setup
echo ========================================================
echo.
echo Note 1: PP-StructureV3 contain deep learning models (PyTorch/ONNX).
echo Note 2: We will also install MiKTeX for automatic PDF compilation.
echo [!] MiKTeX install typically takes 5-10 minutes.
echo     It will run silently in the background. Please BE PATIENT.
echo.

:: 1. Check Python installation and Version 3.12.x Requirement
echo [1/5] Checking Python 3.12.x Environment...

set "PYTHON_CMD="
set "PYTHON_VER="
set "LOCAL_PY312=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"

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
:: 2. Check and Install MiKTeX (LaTeX Engine)
echo [INFO] Checking LaTeX Compiler (xelatex)...
xelatex --version >nul 2>&1

if %errorlevel% equ 0 (
    echo [OK] xelatex found. Skipping MiKTeX download.
    goto ConfigureLaTeX
)

echo [INFO] xelatex not found. Downloading MiKTeX Installer...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://mirrors.ctan.org/systems/win32/miktex/setup/windows-x64/basic-miktex-24.4-x64.exe', 'miktex-setup.exe')"

if not exist miktex-setup.exe (
    echo [WARNING] Failed to download MiKTeX. Automatic PDF compilation will be disabled.
    goto SetupPythonEnv
)

echo [INFO] Download finished. Starting silent installation...
echo [!] This step will take 3-5 minutes. The window may seem idle.
start /wait "" miktex-setup.exe --unattended --private

echo [INFO] Updating PATH environment variable for LaTeX...
set "PATH=%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64;%PATH%"
del miktex-setup.exe
echo [OK] MiKTeX installed successfully!

:ConfigureLaTeX
echo [INFO] Checking and Configuring LaTeX Packages...
mpm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Not a MiKTeX environment ^(possibly TeX Live^). Skipping explicit package installation.
    goto SetupPythonEnv
)

echo [INFO] MiKTeX detected. Installing required packages...
mpm --install=ctex >nul 2>&1
mpm --install=amsmath >nul 2>&1
mpm --install=amsfonts >nul 2>&1
mpm --install=geometry >nul 2>&1
mpm --install=graphicx >nul 2>&1
mpm --install=xecjk >nul 2>&1
mpm --install=cjk >nul 2>&1
mpm --install=zhnumber >nul 2>&1
echo [OK] Package configuration completed.

:SetupPythonEnv
echo.

:: 3. Create and activate virtual environment
echo [2/5] Creating virtual environment (venv)...
if not exist "venv" (
    !PYTHON_CMD! -c "import venv; venv.create('venv', with_pip=True)"
)
if not exist "venv" (
    echo [ERROR] Failed to create virtual environment.
    set "EXIT_CODE=1"
    pause
    goto end_script
)

echo [3/5] Activating virtual environment...
call venv\Scripts\activate
python -m pip install --upgrade pip >nul 2>&1

:: 4. Direct Install Dependencies
echo [4/5] Detecting GPU and installing Python dependencies...

set "GPU_VENDOR="
set "ONNX_PKG=onnxruntime"

for /f "tokens=2 delims==" %%I in ('wmic path win32_VideoController get name /value ^| findstr "="') do (
    set "GPU_NAME=%%I"
    echo [INFO] Found GPU: !GPU_NAME!

    echo !GPU_NAME! | findstr /i "NVIDIA" >nul
    if !errorlevel! equ 0 set "GPU_VENDOR=NVIDIA"

    echo !GPU_NAME! | findstr /i "AMD" >nul
    if !errorlevel! equ 0 if "!GPU_VENDOR!"=="" set "GPU_VENDOR=AMD"

    echo !GPU_NAME! | findstr /i "Intel" >nul
    if !errorlevel! equ 0 if "!GPU_VENDOR!"=="" set "GPU_VENDOR=Intel"

    echo !GPU_NAME! | findstr /i "Radeon" >nul
    if !errorlevel! equ 0 if "!GPU_VENDOR!"=="" set "GPU_VENDOR=AMD"
)

if "!GPU_VENDOR!"=="NVIDIA" (
    set "ONNX_PKG=onnxruntime-gpu"
    echo [INFO] NVIDIA GPU detected. Will install !ONNX_PKG!
) else if "!GPU_VENDOR!"=="AMD" (
    set "ONNX_PKG=onnxruntime-directml"
    echo [INFO] AMD GPU detected. Will install !ONNX_PKG!
) else if "!GPU_VENDOR!"=="Intel" (
    set "ONNX_PKG=onnxruntime-directml"
    echo [INFO] Intel GPU detected. Will install !ONNX_PKG!
) else (
    set "ONNX_PKG=onnxruntime"
    echo [INFO] No dedicated GPU vendor recognized. Will install !ONNX_PKG!
)

pip install -r requirements.txt !ONNX_PKG! pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [ERROR] Python dependency installation failed.
    set "EXIT_CODE=1"
    pause
    goto end_script
)

echo.

echo ========================================================
echo [SUCCESS] Environment setup completed successfully!
echo ========================================================
echo.
echo You can now start the application by running 'python main.py'
pause
:end_script
exit /b %EXIT_CODE%
