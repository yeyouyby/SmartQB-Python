@echo off
color 0A

echo ========================================================
echo        SmartQB Pro V3 (Ultimate) Environment Setup
echo ========================================================
echo.
echo Note 1: Pix2Text contains deep learning models (PyTorch).
echo Note 2: We will also install MiKTeX for automatic PDF compilation.
echo [!] MiKTeX install typically takes 5-10 minutes.
echo     It will run silently in the background. Please BE PATIENT.
echo.

:: 1. Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 goto NoPython

:: Display current Python version
for /f "delims=" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo [OK] Detected Python: %PYTHON_VER%
echo.

:: 2. Check and Install MiKTeX (LaTeX Engine)
echo [1/6] Checking LaTeX Compiler (xelatex)...
xelatex --version >nul 2>&1

:: 如果已经安装，跳过下载安装核心引擎，直接去配置宏包
if %errorlevel% equ 0 goto ConfigureLaTeX

echo [INFO] xelatex not found. Downloading MiKTeX Installer (130MB)...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://mirrors.ctan.org/systems/win32/miktex/setup/windows-x64/basic-miktex-24.4-x64.exe', 'miktex-setup.exe')"

if not exist miktex-setup.exe goto DownloadFailed

echo [INFO] Download finished. Starting silent installation...
echo [!] This step will take 3-5 minutes. The window may seem idle.
start /wait "" miktex-setup.exe --unattended --private

echo [INFO] Updating PATH environment variable for LaTeX...
set "PATH=%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64;%PATH%"
del miktex-setup.exe
echo [OK] MiKTeX installed successfully!

:ConfigureLaTeX
echo [INFO] Checking and Configuring LaTeX Packages...
:: 先测试 mpm (MiKTeX Package Manager) 命令是否存在
mpm --version >nul 2>&1
if %errorlevel% neq 0 goto SkipMiKTeXConfig

echo [INFO] MiKTeX detected. Installing required packages...
:: 彻底移除了导致崩溃的废弃选项，并隐藏了 log4cxx 日志警告
echo [INFO] Installing ctex...
mpm --install=ctex >nul 2>&1
echo [INFO] Installing amsmath...
mpm --install=amsmath >nul 2>&1
echo [INFO] Installing amsfonts...
mpm --install=amsfonts >nul 2>&1
echo [INFO] Installing geometry...
mpm --install=geometry >nul 2>&1
echo [INFO] Installing graphicx...
mpm --install=graphicx >nul 2>&1
echo [INFO] Installing xeCJK...
mpm --install=xecjk >nul 2>&1
echo [INFO] Installing CJK...
mpm --install=cjk >nul 2>&1
echo [INFO] Installing zhnumber...
mpm --install=zhnumber >nul 2>&1
echo [OK] Package configuration completed.
goto SetupPythonEnv

:SkipMiKTeXConfig
echo [INFO] Not a MiKTeX environment (possibly TeX Live). Skipping explicit package installation.
echo [INFO] Assuming essential packages are already included in your distribution.

:SetupPythonEnv
echo.

:: 3. Create and activate virtual environment
echo [2/6] Creating virtual environment (venv)...
if not exist "venv" python -m venv venv
if %errorlevel% neq 0 goto VenvFailed

echo [3/6] Activating virtual environment...
call venv\Scripts\activate
python -m pip install --upgrade pip >nul 2>&1

:: 4. Direct Install Dependencies
echo [4/6] Downloading and installing Python dependencies...
pip install numpy Pillow openai PyMuPDF pix2text python-docx keyring httpx onnxruntime opencv-python-headless lancedb pyarrow -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 goto PipFailed

:: 5. Pre-download Pix2Text AI Models (动态生成一次性脚本并阅后即焚)
echo.
echo [5/6] Pre-downloading AI Models for Pix2Text...

:: 使用追加写入方式逐行生成 Python 文件，改用全英文以彻底避免 CMD 乱码导致的 SyntaxError
echo # -*- coding: utf-8 -*-> pix2text_test.py
echo import sys>> pix2text_test.py
echo from pix2text import Pix2Text>> pix2text_test.py
echo print("========================================================")>> pix2text_test.py
echo print("   Initializing Pix2Text AI Vision Engine... ")>> pix2text_test.py
echo print("========================================================")>> pix2text_test.py
echo print("\n[!] First run: Auto-downloading AI models (approx 1-2 GB).")>> pix2text_test.py
echo print("[!] This may take 5 to 20 minutes depending on your network.")>> pix2text_test.py
echo print("[!] Please wait patiently and do NOT close this window...\n")>> pix2text_test.py
echo try:>> pix2text_test.py
echo     p2t = Pix2Text.from_config()>> pix2text_test.py
echo     print("\n[SUCCESS] AI Models downloaded and initialized successfully!")>> pix2text_test.py
echo     sys.exit(0)>> pix2text_test.py
echo except Exception as e:>> pix2text_test.py
echo     print(f"\n[ERROR] Initialization failed: {e}")>> pix2text_test.py
echo     sys.exit(1)>> pix2text_test.py

:: 执行生成的脚本触发下载
python pix2text_test.py
:: 捕获执行结果的错误码
set P2T_ERR=%errorlevel%

:: ★ 核心：无论下载成功还是失败，都立即删除该临时脚本
del pix2text_test.py

:: 根据捕获的错误码判断是否中断流程
if %P2T_ERR% neq 0 goto ModelFailed
echo.

:: 6. Create the startup script (单行逐句写入，杜绝括号代码块引起的换行截断报错)
echo [6/6] Creating run_smartqb.bat...
echo @echo off> run_smartqb.bat
echo echo Starting SmartQB Pro...>> run_smartqb.bat
echo set "PATH=%%LOCALAPPDATA%%\Programs\MiKTeX\miktex\bin\x64;%%PATH%%">> run_smartqb.bat
echo call venv\Scripts\activate>> run_smartqb.bat
echo python main.py>> run_smartqb.bat
echo pause>> run_smartqb.bat

echo.
echo ========================================================
echo [SUCCESS] Environment setup completed successfully!
echo ========================================================
echo.
echo Please double click "run_smartqb.bat" to start.
pause >nul
exit /b

:NoPython
color 0C
echo [ERROR] Python is not installed or not in PATH!
echo Please install Python 3.9-3.11 from https://www.python.org/
echo Make sure to check "Add Python to PATH" during installation.
pause
exit /b

:DownloadFailed
color 0E
echo [WARNING] Failed to download MiKTeX. Automatic PDF compilation will be disabled.
color 0A
goto SetupPythonEnv

:VenvFailed
color 0C
echo [ERROR] Failed to create virtual environment.
pause
exit /b

:PipFailed
color 0C
echo.
echo [ERROR] Installation failed. Please check your network and try again.
pause
exit /b

:ModelFailed
color 0C
echo.
echo [ERROR] AI Model download failed. The application may not function correctly.
pause
exit /b