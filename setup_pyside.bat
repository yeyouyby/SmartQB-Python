@echo off
echo Installing PySide6 and required dependencies...
pip install PySide6 qfluentwidgets paddlepaddle paddleocr python-docx Jinja2 lancedb pyarrow numpy cryptography mcp
if %errorlevel% neq 0 (
    echo Setup failed: dependency installation error.
    cmd /c exit /b 1
)
echo Setup complete.
