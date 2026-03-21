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
    print("Replaced format constraints")

old_system_prompt_addition = """system_content = self._get_system_prompt(is_vision_mode=use_vision) + \"\"\"

【切片合并与状态机规则】
我将提供一段按绝对序号 (Index) 排列的文本切片。它们是按文档物理顺序截取的。一道题可能跨越多个切片。
1. 你的任务是提取出所有题目。一道题目可能横跨多个切片。
2. 请对每一道识别出的题目评估其跨越的切片序号（放入 SourceSliceIndices 数组）。
3. \"\"\" + (f"【关键跨页处理】如果某道题目延伸或触碰到了提供的【最后一个辅助切片】（其序号为 {aux_slice_index}），**绝对不要**把它放进 `Questions` 数组中！你必须将这道触碰到最后辅助切片的题目的原始文本放入 `PendingFragment` 字段中，系统会将其与下一个批次的切片合并处理。对于未触碰到该辅助切片的题目，正常放入 `Questions` 数组。" if has_aux else "【关键跨页处理】当前批次没有辅助切片。请将所有完整或残缺的题目都直接放入 `Questions` 数组中，不需要使用 `PendingFragment`。") + \"\"\"
4. \"\"\" + ("当前是文档末尾，没有辅助切片，请将所有识别出的题目都放入 `Questions` 数组，不要放入 `PendingFragment`。" if is_last_batch else "不要把辅助切片里的新题目和前面的残缺题目强行合并在一起！遇到真正的新题号就立刻切断！") + \"\"\"
5. `NextIndex` 指向下一个批次的主切片起始位置。\"\"\" + (f"当前是最后批次或单切片，必须返回 {last_index_plus_one}。" if not has_aux else f"应返回本批次辅助切片的序号（即 {aux_slice_index}）。") + f\"\"\""""

new_system_prompt_addition = """system_content = self._get_system_prompt(is_vision_mode=use_vision) + \"\"\"

【极其重要】：当前请求包含按顺序提供的一个或多个整页切片（每个切片代表一页文字），里面通常会包含【多道独立的题目】！你的核心任务是将它们一道道拆分出来！

【切片合并与状态机规则】
我将提供一段按绝对序号 (Index) 排列的文本切片。它们是按文档物理顺序截取的。一道题可能跨越多个切片。
1. 你的任务是提取主切片中的完整题目（拆分为多个 Question 对象）；若题目触碰辅助切片，必须按后续规则放入 PendingFragment，不要放入 Questions。
2. 请对每一道识别出的题目评估其跨越的切片序号（放入 SourceSliceIndices 数组）。
3. \"\"\" + (f"【关键跨页处理】如果某道题目延伸或触碰到了提供的【最后一个辅助切片】（其序号为 {aux_slice_index}），**绝对不要**把它放进 `Questions` 数组中！你必须将这道触碰到最后辅助切片的题目的原始文本放入 `PendingFragment` 字段中，系统会将其与下一个批次的切片合并处理。对于未触碰到该辅助切片的题目，正常放入 `Questions` 数组。" if has_aux else "【关键跨页处理】当前批次没有辅助切片。请将所有完整或残缺的题目都直接放入 `Questions` 数组中，不需要使用 `PendingFragment`。") + \"\"\"
4. \"\"\" + ("当前是文档末尾，没有辅助切片，请将所有识别出的题目都放入 `Questions` 数组，不要放入 `PendingFragment`。" if is_last_batch else "不要把辅助切片里的新题目和前面的残缺题目强行合并在一起！遇到真正的新题号就立刻切断！") + \"\"\"
5. `NextIndex` 指向下一个批次的主切片起始位置。\"\"\" + (f"当前是最后批次或单切片，必须返回 {last_index_plus_one}。" if not has_aux else f"应返回本批次辅助切片的序号（即 {aux_slice_index}）。") + f\"\"\""""

if old_system_prompt_addition in content:
    content = content.replace(old_system_prompt_addition, new_system_prompt_addition)
    print("Replaced system prompt addition")

with open("ai_service.py", "w", encoding="utf-8") as f:
    f.write(content)
