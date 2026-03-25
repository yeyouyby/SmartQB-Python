@echo off
echo Installing PySide6 and required dependencies...
pip install PySide6 qfluentwidgets paddlepaddle paddleocr python-docx lancedb pyarrow numpy cryptography mcp sqlparse PyMuPDF markdown pypandoc
if %errorlevel% neq 0 (
    echo Setup failed: dependency installation error.
    exit /b 1
)
echo Setup complete.
exit /b 0
