with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("f'''\\documentclass{{article}}\\n\\usepackage{{ctex}}\\n\\usepackage{{amsmath}}\\n\\usepackage{{amssymb}}\\n\\begin{{document}}\\n{content_text}\\n\\end{{document}}'''",
                          "f'''\\\\documentclass{{article}}\\n\\\\usepackage{{ctex}}\\n\\\\usepackage{{amsmath}}\\n\\\\usepackage{{amssymb}}\\n\\\\begin{{document}}\\n{content_text}\\n\\\\end{{document}}'''")

content = content.replace("f'''\\documentclass{{article}}\\n\\usepackage{{ctex}}\\n\\usepackage{{amsmath}}\\n\\usepackage{{amssymb}}\\n\\begin{{document}}\\n{fixed_content}\\n\\end{{document}}'''",
                          "f'''\\\\documentclass{{article}}\\n\\\\usepackage{{ctex}}\\n\\\\usepackage{{amsmath}}\\n\\\\usepackage{{amssymb}}\\n\\\\begin{{document}}\\n{fixed_content}\\n\\\\end{{document}}'''")

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
