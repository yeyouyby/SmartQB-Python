def fix_setup():
    with open("setup.bat", "r", encoding="utf-8") as f:
        content = f.read()

    # The existing `pip install` command is:
    # pip install -r requirements.txt !ONNX_PKG! PyMuPDF python-docx httpx opencv-python-headless pyarrow psutil pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
    # We can simplify this since we added these to requirements.txt

    old_cmd = "pip install -r requirements.txt !ONNX_PKG! PyMuPDF python-docx httpx opencv-python-headless pyarrow psutil pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple"
    new_cmd = "pip install -r requirements.txt !ONNX_PKG! pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple"

    if old_cmd in content:
        content = content.replace(old_cmd, new_cmd)
        with open("setup.bat", "w", encoding="utf-8") as f:
            f.write(content)
        print("Updated setup.bat")
    else:
        print("Could not find the pip command in setup.bat")


fix_setup()
