import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Locate the specific latex line that has a syntax error
pattern = r"tex_code = f'\\documentclass.*?\\end\{\{document\}\}'"
replacement = "tex_code = f\"\\\\documentclass{{article}}\\n\\\\usepackage{{ctex}}\\n\\\\usepackage{{amsmath}}\\n\\\\usepackage{{amssymb}}\\n\\\\begin{{document}}\\n{content_text}\\n\\\\end{{document}}\""

content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
