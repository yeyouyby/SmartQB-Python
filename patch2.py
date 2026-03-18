with open('setup_new.bat', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the duplicate (xelatex) in the echo
content = content.replace('echo [INFO] Checking LaTeX Compiler (xelatex) (xelatex)...', 'echo [INFO] Checking LaTeX Compiler (xelatex)...')

# Replace the venv creation python call with !PYTHON_CMD!
old_venv = """if not exist "venv" (
    python -c "import venv; venv.create('venv', with_pip=True)"
)"""
new_venv = """if not exist "venv" (
    !PYTHON_CMD! -c "import venv; venv.create('venv', with_pip=True)"
)"""
content = content.replace(old_venv, new_venv)

with open('setup_new.bat', 'w', encoding='utf-8') as f:
    f.write(content)
