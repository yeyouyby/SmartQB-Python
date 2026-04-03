def check_and_update_reqs():
    with open("requirements.txt", "r") as f:
        reqs = [r.strip() for r in f.readlines() if r.strip()]

    needed = [
        "ruff",
        "mypy",
        "bandit",
        "PySide6",
        "openai",
        "pillow",
        "paddleocr",
        "onnx>=1.21.0",
        "lancedb",
        "keyring",
        "markdown",
        "rich>=13.8.0",
        "tkhtmlview",
        "types-Markdown",
        "PySide6-Fluent-Widgets[full]",
        "requests",
        "httpx",
        "PyMuPDF",
        "python-docx",
        "pyarrow",
        "numpy",
        "opencv-python-headless",
        "psutil",
    ]

    for n in needed:
        # Simple check, not parsing versions
        base_n = n.split(">=")[0].split("[")[0].lower()
        found = False
        for r in reqs:
            base_r = r.split(">=")[0].split("[")[0].lower()
            if base_n == base_r:
                found = True
                break
        if not found:
            reqs.append(n)

    with open("requirements.txt", "w") as f:
        f.write("\n".join(reqs) + "\n")

    print("Updated requirements.txt")


check_and_update_reqs()
