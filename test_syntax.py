import py_compile
try:
    py_compile.compile("gui_app.py", doraise=True)
    print("Syntax OK")
except Exception as e:
    print(f"Syntax Error: {e}")
