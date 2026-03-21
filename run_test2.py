import py_compile
try:
    py_compile.compile('document_service.py', doraise=True)
    py_compile.compile('ai_service.py', doraise=True)
    py_compile.compile('gui_app.py', doraise=True)
    py_compile.compile('db_adapter.py', doraise=True)
    print("All modified files compiled successfully.")
except Exception as e:
    print(e)
