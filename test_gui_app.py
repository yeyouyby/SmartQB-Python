import py_compile
try:
    py_compile.compile('gui_app.py', doraise=True)
    print("gui_app.py compiled successfully")
except Exception as e:
    print(f"Error compiling gui_app.py: {e}")
