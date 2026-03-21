with open("ai_service.py", "r", encoding="utf-8") as f:
    content = f.read()

old_format_constraints = """【极其严格的 LaTeX 编译格式约束】
1. 彻底删除最开头的题目序号（如 "1.", "(2)", "一、" 等），绝对不允许保留题号。
2. 对于编程语言代码块（如C++/Python），绝对不能丢失，必须完整保留，并严格包裹在 \\begin{lstlisting} 和 \\end{lstlisting} 中。
3. 对于选项（A, B, C, D等），直接保留纯文本即可（例如 A. xxxx），不要在字母前面加任何斜杠（如 \\A）。
4. 输出的 Content 必须能被 xelatex 与 ctexart 环境无错编译，除了特别包裹的代码块，普通文本中的所有 LaTeX 保留字符 (如 %, &, _, #) 必须使用反斜杠严格转义 (例如 \\%, \\&)。
5. 数学公式、变量必须包裹在 $...$ 或 $$...$$ 中，但普通中文不要放进数学环境。"""

new_format_constraints = """【极其严格的 LaTeX 编译格式约束】
0. 文本中可能会出现图样标记（如 [[{ima_dont_del_0_1}]]），你必须原封不动地将其保留在它所在的题目文本中，绝对不要修改、删除、转义（包括下划线 _）或添加任何额外字符；这些标记不参与 LaTeX 转义规则。
1. 彻底删除最开头的题目序号（如 "1.", "(2)", "一、" 等），绝对不允许保留题号。
2. 对于编程语言代码块（如C++/Python），绝对不能丢失，必须完整保留，并严格包裹在 \\begin{lstlisting} 和 \\end{lstlisting} 中。
3. 对于选项（A, B, C, D等），直接保留纯文本即可（例如 A. xxxx），不要在字母前面加任何斜杠（如 \\A）。
4. 输出的 Content 必须能被 xelatex 与 ctexart 环境无错编译，除了特别包裹的代码块和上面的图样标记，普通文本中的所有 LaTeX 保留字符 (如 %, &, _, #) 必须使用反斜杠严格转义 (例如 \\%, \\&)。
5. 数学公式、变量必须包裹在 $...$ 或 $$...$$ 中，但普通中文不要放进数学环境。"""

if old_format_constraints in content:
    content = content.replace(old_format_constraints, new_format_constraints)
    with open("ai_service.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Replaced format constraints")
else:
    print("Could not find format constraints")
