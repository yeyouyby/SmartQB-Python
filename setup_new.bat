@echo off
setlocal EnableDelayedExpansion
color 0A

echo ========================================================
echo        SmartQB Pro V3 (Ultimate) Environment Setup
echo ========================================================
echo.
echo Note 1: Pix2Text and Surya contain deep learning models (PyTorch).
echo Note 2: We will also install MiKTeX for automatic PDF compilation.
echo [!] MiKTeX install typically takes 5-10 minutes.
echo     It will run silently in the background. Please BE PATIENT.
echo.

:: 1. Check Python installation and Version 3.12.x Requirement
echo [1/6] Checking Python 3.12.x Environment...

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
echo [2/6] Creating virtual environment (venv)...
if not exist "venv" (
    !PYTHON_CMD! -c "import venv; venv.create('venv', with_pip=True)"
)
if not exist "venv" (
    echo [ERROR] Failed to create virtual environment.
    pause
    goto end_script
)

echo [3/6] Activating virtual environment...
call venv\Scripts\activate
python -m pip install --upgrade pip >nul 2>&1

:: 4. Direct Install Dependencies
echo [4/6] Downloading and installing Python dependencies...
:: Added surya-ocr dependency as required by the latest update
pip install numpy Pillow openai PyMuPDF pix2text python-docx keyring httpx onnxruntime opencv-python-headless lancedb pyarrow surya-ocr -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [ERROR] Installation failed. Please check your network and try again.
    pause
    goto end_script
)

:: 5. Pre-download AI Models
echo.
echo [5/6] Pre-downloading AI Models for Pix2Text and Surya...

echo import sys > init_models.py
echo print("\n========================================================") >> init_models.py
echo print("   Initializing AI Vision Engines... ") >> init_models.py
echo print("========================================================\n") >> init_models.py
echo print("[!] First run: Auto-downloading AI models (approx 1-3 GB).") >> init_models.py
echo print("[!] This may take 5 to 20 minutes depending on your network.") >> init_models.py
echo print("[!] Please wait patiently and do NOT close this window...\n") >> init_models.py
echo try: >> init_models.py
echo     from pix2text import Pix2Text >> init_models.py
echo     print("[INFO] Initializing Pix2Text...") >> init_models.py
echo     p2t = Pix2Text.from_config() >> init_models.py
echo except Exception as e: >> init_models.py
echo     print(f"[WARNING] Pix2Text init failed: {e}") >> init_models.py
echo try: >> init_models.py
echo     from surya.layout import LayoutPredictor >> init_models.py
echo     from surya.ocr import OCRPredictor >> init_models.py
echo     print("[INFO] Initializing Surya Layout and OCR models...") >> init_models.py
echo     lp = LayoutPredictor() >> init_models.py
echo     op = OCRPredictor() >> init_models.py
echo     print("\n[SUCCESS] AI Models downloaded and initialized successfully!") >> init_models.py
echo     sys.exit(0) >> init_models.py
echo except Exception as e: >> init_models.py
echo     print(f"\n[ERROR] Surya Initialization failed: {e}") >> init_models.py
echo     sys.exit(1) >> init_models.py

python init_models.py
set MODEL_ERR=%errorlevel%
del init_models.py

if %MODEL_ERR% neq 0 (
    echo [ERROR] AI Model download failed. The application may not function correctly.
    pause
    goto end_script
)
echo.

:: 6. Create the startup script
echo [6/6] Creating run_smartqb.bat...
echo @echo off > run_smartqb.bat
echo echo Starting SmartQB Pro... >> run_smartqb.bat
echo set "PATH=%%LOCALAPPDATA%%\Programs\MiKTeX\miktex\bin\x64;%%PATH%%" >> run_smartqb.bat
echo call venv\Scripts\activate >> run_smartqb.bat
echo python main.py >> run_smartqb.bat
echo pause >> run_smartqb.bat

echo.
echo ========================================================
echo [SUCCESS] Environment setup completed successfully!
echo ========================================================
echo.
echo Please double click "run_smartqb.bat" to start.
pause >nul
:end_script
