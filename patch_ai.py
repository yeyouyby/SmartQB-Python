import os

with open("ai_service.py", "r", encoding="utf-8") as f:
    content = f.read()

# 替换系统提示词
old_prompt = """【极其严格的 LaTeX 编译格式约束】"""
new_prompt = """【极其严格的 LaTeX 编译格式约束】
0. 文本中可能会出现图样标记（如 `[[{ima_dont_del_0}]]`），你必须原封不动地将其保留在它所在的题目文本中，绝对不要修改或删除这些标记。"""
content = content.replace(old_prompt, new_prompt)

with open("ai_service.py", "w", encoding="utf-8") as f:
    f.write(content)
