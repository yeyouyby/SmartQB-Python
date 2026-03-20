# ai_service.py
import json
import re
import base64
from openai import OpenAI
from utils import logger

SUPPORTED_REASONING_MODELS = ('o1', 'o3', 'o4', 'deepseek-reasoner')

# ==========================================
# AI 服务与纠错闭环
# ==========================================

class AIService:
    def __init__(self, settings):
        self.settings = settings


    def _get_chat_kwargs(self):
        kwargs = {"model": self.settings.model_id}

        if hasattr(self.settings, 'temperature') and self.settings.temperature is not None:
            try:
                temp = float(self.settings.temperature)
                if 0.0 <= temp <= 2.0:
                    kwargs['temperature'] = temp
            except ValueError:
                pass

        if hasattr(self.settings, 'top_p') and self.settings.top_p is not None:
            try:
                top_p = float(self.settings.top_p)
                if 0.0 < top_p <= 1.0:
                    kwargs['top_p'] = top_p
            except ValueError:
                pass

        if hasattr(self.settings, 'max_tokens') and self.settings.max_tokens is not None:
            try:
                max_tokens = int(self.settings.max_tokens)
                if max_tokens > 0:
                    kwargs['max_tokens'] = max_tokens
            except ValueError:
                pass

        if (
            hasattr(self.settings, 'reasoning_effort')
            and self.settings.reasoning_effort
            and self.settings.reasoning_effort != 'none'
            and str(self.settings.model_id).startswith(SUPPORTED_REASONING_MODELS)
        ):
            kwargs['reasoning_effort'] = self.settings.reasoning_effort

        return kwargs

    def get_client(self):
        if not self.settings.api_key:
            raise ValueError("请先在设置中配置 API Key")
        return OpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url if self.settings.base_url else None
        )

    def _get_system_prompt(self, is_vision_mode=False):
        base_prompt = """你是一个极其严谨的学术级智能题库处理引擎。
你的唯一目标是从混杂的 OCR 文本（及可能的附加图片）中提取出结构完整、排版规范的题目。

【极其严格的 LaTeX 编译格式约束】
0. 文本中可能会出现图样标记（如 `[[{ima_dont_del_0_1}]]`），你必须原封不动地将其保留在它所在的题目文本中，绝对不要修改、删除、转义（包括其内部的 `_`）或添加任何额外字符；这些标记享有豁免权，不参与任何 LaTeX 转义规则。
1. 彻底删除最开头的题目序号（如 "1.", "(2)", "一、" 等），绝对不允许保留题号。
2. 对于编程语言代码块（如C++/Python），绝对不能丢失，必须完整保留，并严格包裹在 \\begin{lstlisting} 和 \\end{lstlisting} 中。
3. 对于选项（A, B, C, D等），直接保留纯文本即可（例如 A. xxxx），不要在字母前面加任何斜杠（如 \\A）。
4. 输出的 Content 必须能被 xelatex 与 ctexart 环境无错编译，除了特别包裹的代码块，普通文本中的所有 LaTeX 保留字符 (如 %, &, _, #) 必须使用反斜杠严格转义 (例如 \\%, \\&)。
5. 数学公式、变量必须包裹在 $...$ 或 $$...$$ 中，但普通中文不要放进数学环境。

【针对不同学科与题型的特殊优化规则】
- 英语/语文阅读长题/大题：如果识别到连体大题（包含大段材料及后续的多个小题），必须将其作为“一个整体（一个大题）”合并输出，不要把材料和后面的小题拆散成多个独立的 Questions 对象。
- 理科/数学/物理/化学：重点关注图表和公式，严防 OCR 中的下标/上标/根号识别错乱。
- 信息技术/通用技术：重点关注代码块、算法流程图和操作界面的对应，绝不能漏掉任何逻辑代码行。
- 选择/填空/判断：如果多个选择题是彼此独立的，可作为多道题提取；但如果是针对同一个材料的连锁选择题，应视为大题合并处理。"""

        vision_prompt = """
【视觉参考提示】
你必须仔细观察用户提供的局部截图，修正 OCR 模型提取失败的复杂公式、图表排版。将截图内容转化为合适的文本、公式或占位符融入题目结构中。"""

        output_format = """
【绝对强制的输出格式】
你必须且只能输出合法的 JSON 格式字符串，绝对不要包含任何 markdown 代码块标记 (如 ```json) 或多余的说明对话文字。"""

        if is_vision_mode:
            return base_prompt + vision_prompt + output_format
        return base_prompt + output_format

    def process_text_with_correction(self, raw_text):
        """用于手动录入界面的单文本清洗"""
        client = self.get_client()
        prompt = f"""
{self._get_system_prompt(is_vision_mode=False)}

请解析以下输入文本，并严格按照以下 JSON 格式返回结果：
{{
    "Content": "纯正 LaTeX 格式的题目内容（已转义特殊字符）...",
    "LogicDescriptor": "解题思路或考点分析...",
    "Tags": ["知识点标签1", "知识点标签2"]
}}

【输入文本】：
{raw_text}
"""
        kwargs = self._get_chat_kwargs()
        response = client.chat.completions.create(
            **kwargs,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return self._parse_json(response.choices[0].message.content)

    def process_slices_with_context(self, slices_batch, use_vision=False, pending_fragment="", is_last_batch=False):
        """核心引擎 (支持动态切片合并的滑动窗口状态机)"""
        client = self.get_client()

        has_aux = not is_last_batch and len(slices_batch) > 1
        aux_slice_index = slices_batch[-1]["index"] if has_aux else -1
        last_index_plus_one = slices_batch[-1]["index"] + 1

        system_content = self._get_system_prompt(is_vision_mode=use_vision) + """

【切片合并与状态机规则】
【极其重要】：当前请求包含了一整页的文字，里面通常会包含【多道独立的题目】！你的核心任务是将它们一道道拆分出来！
我将提供一段按绝对序号 (Index) 排列的文本切片。它们是按文档物理顺序截取的。一道题可能跨越多个切片。
1. 你的任务是提取出所有完整的题目（拆分为多个 Question 对象）。
2. 请对每一道识别出的题目评估其跨越的切片序号（放入 SourceSliceIndices 数组）。
3. """ + (f"【关键跨页处理】如果某道题目延伸或触碰到了提供的【最后一个辅助切片】（其序号为 {aux_slice_index}），**绝对不要**把它放进 `Questions` 数组中！你必须将这道触碰到最后辅助切片的题目的原始文本放入 `PendingFragment` 字段中，系统会将其与下一个批次的切片合并处理。对于未触碰到该辅助切片的题目，正常放入 `Questions` 数组。" if has_aux else "【关键跨页处理】当前批次没有辅助切片。请将所有完整或残缺的题目都直接放入 `Questions` 数组中，不需要使用 `PendingFragment`。") + """
4. """ + ("当前是文档末尾，没有辅助切片，请将所有识别出的题目都放入 `Questions` 数组，不要放入 `PendingFragment`。" if is_last_batch else "不要把辅助切片里的新题目和前面的残缺题目强行合并在一起！遇到真正的新题号就立刻切断！") + """
5. `NextIndex` 指向下一个批次的主切片起始位置。""" + (f"当前是最后批次或单切片，必须返回 {last_index_plus_one}。" if not has_aux else f"应返回本批次辅助切片的序号（即 {aux_slice_index}）。") + f"""

请严格返回如下 JSON 结构：
{{
    "Questions": [
        {{
            "Status": "Complete",
            "Content": "第一题内容(纯正LaTeX格式，严格转义)...",
            "LogicDescriptor": "解析...",
            "Tags": ["标签1"],
            "SourceSliceIndices": [0, 1]
        }}
    ],
    "PendingFragment": "如果遇到了跨页的未完结题目，将该片段放入此处，留作下一次前置补全",
    "NextIndex": {last_index_plus_one if not has_aux else aux_slice_index}
}}
"""
        messages_content = [{"type": "text", "text": system_content}]

        if pending_fragment:
            messages_content.append({
                "type": "text",
                "text": f"【上一批次未处理完的跨页题目片段，请将其接续在本次的开头作为第一道题的起始内容】：\n{pending_fragment}\n\n"
            })

        # 组装文本和可能的图像内容
        slices_text = ""
        for s in slices_batch:
            slices_text += f"--- 切片序号 {s['index']} ---\n{s['text']}\n\n"
            if use_vision and s.get('image_b64'):
                messages_content.append({
                    "type": "text",
                    "text": f"[附: 切片序号 {s['index']} 的原始局部截图，请结合此图修正 OCR 识别错误的公式和排版]"
                })
                messages_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{s['image_b64']}"}
                })

        messages_content.append({
            "type": "text",
            "text": f"【本地 OCR 初步提取的连续切片文本如下】：\n{slices_text}"
        })

        kwargs = self._get_chat_kwargs()
        response = client.chat.completions.create(
            **kwargs,
            messages=[{"role": "user", "content": messages_content}],
            response_format={"type": "json_object"}
        )
        return self._parse_json(response.choices[0].message.content)

    def _parse_json(self, raw_content):
        # 终极容错解析：即使 AI 不听话加了 markdown 标记，也能强行剥离
        try:
            return json.loads(raw_content)
        except Exception:
            clean = re.sub(r'^```json\s*|\s*```$', '', raw_content.strip(), flags=re.MULTILINE)
            return json.loads(clean)


    def ai_merge_questions(self, texts_to_merge):
        prompt = '''你是一个专业的试卷排版与解析助手。
我现在给你几段被错误拆分的题目片段。请你将它们合并为一道完整的题目。
要求：
1. 保证题干、选项（如果有）、【答案与解析】格式规范。
2. 删除多余的或是因为错误拆分而带来的无用大题号。
3. 如果原文包含多个小题，保留它们的题意，但请确保整体逻辑顺畅。
4. 返回结构必须是严格的 JSON 格式，只包含 "merged_content" 一个字段。

以下是待合并的片段：
'''
        for idx, t in enumerate(texts_to_merge):
            prompt += f"--- 片段 {idx+1} ---\n{t}\n"

        messages = [
            {"role": "system", "content": "你是一个试题处理专家，必须严格输出JSON格式，不要任何其他废话或Markdown包裹。"},
            {"role": "user", "content": prompt}
        ]

        try:
            kwargs = self._get_chat_kwargs()
            res = self.get_client().chat.completions.create(
                **kwargs,
                messages=messages,
                response_format={"type": "json_object"}
            )
            data = self._parse_json(res.choices[0].message.content)
            merged_content = data.get("merged_content", "")
            return merged_content if isinstance(merged_content, str) else ""
        except Exception as e:
            logger.error(f"Merge error: {e}")
            return ""

    def ai_split_question(self, text_to_split):
        prompt = '''你是一个专业的试卷排版与解析助手。
以下文本被错误地合并在了一起，它实际上包含多道独立的题目。
请你仔细阅读并将其拆分成多道单独的题目。
要求：
1. 每道题目必须包含其完整的题干、选项（如果有）、答案和解析（如果有）。
2. 返回结构必须是严格的 JSON 格式，包含 "split_questions" 数组字段，其中每个元素是拆分出来的单道题的完整文本。

以下是待拆分的文本：
'''
        prompt += text_to_split

        messages = [
            {"role": "system", "content": "你是一个试题处理专家，必须严格输出JSON格式，不要任何其他废话或Markdown包裹。"},
            {"role": "user", "content": prompt}
        ]

        try:
            kwargs = self._get_chat_kwargs()
            res = self.get_client().chat.completions.create(
                **kwargs,
                messages=messages,
                response_format={"type": "json_object"}
            )
            data = self._parse_json(res.choices[0].message.content)
            split_questions = data.get("split_questions", [])
            if not isinstance(split_questions, list):
                return []
            return [q for q in split_questions if isinstance(q, str)]
        except Exception as e:
            logger.error(f"Split error: {e}")
            return []

    def ai_format_question(self, text_to_format):
        prompt = '''你是一个专业的试卷排版与解析助手。
请对以下题目进行格式化修正：
要求：
1. 规范题干、选项、答案、解析的层级与换行。
2. 强制去除不必要的大题号（如 "一、选择题" 或 "1." 等独立的大题编号，若其只是题目的前缀，可以保留数字，但要去除无关的宏观大题号）。
3. 补充或修正小题号：将题目内部的子问题编号规范为带括号的形式，如 (1), (2), (3) ...
4. 修正任何明显的 OCR 错别字。
5. 请返回严格的 JSON 格式，包含 "formatted_content" 字段。

待格式化的题目文本：
'''
        prompt += text_to_format

        messages = [
            {"role": "system", "content": "你是一个试题处理专家，必须严格输出JSON格式，不要任何其他废话或Markdown包裹。"},
            {"role": "user", "content": prompt}
        ]

        try:
            kwargs = self._get_chat_kwargs()
            res = self.get_client().chat.completions.create(
                **kwargs,
                messages=messages,
                response_format={"type": "json_object"}
            )
            data = self._parse_json(res.choices[0].message.content)
            formatted_content = data.get("formatted_content", "")
            return formatted_content if isinstance(formatted_content, str) else ""
        except Exception as e:
            logger.error(f"Format error: {e}")
            return ""

    def ai_fix_latex(self, text_with_error, error_msg):
        prompt = f'''你是一个精通 LaTeX 的试卷排版专家。
以下题目文本在编译时遇到了 LaTeX 语法错误。请根据错误提示，修正文本中的 LaTeX 语法。
要求：
1. 修复公式、特殊字符（如 %, &, $ 等必须转义）。
2. 保持题目原本的结构和文字内容。
3. 请返回严格的 JSON 格式，包含 "fixed_content" 字段。

【原题目文本】
{text_with_error}

【LaTeX 编译错误信息】
{error_msg}
'''
        messages = [
            {"role": "system", "content": "你是一个试题处理与LaTeX专家，必须严格输出JSON格式。"},
            {"role": "user", "content": prompt}
        ]
        try:
            kwargs = self._get_chat_kwargs()
            res = self.get_client().chat.completions.create(
                **kwargs,
                messages=messages,
                response_format={"type": "json_object"}
            )
            data = self._parse_json(res.choices[0].message.content)
            return data.get("fixed_content", "")
        except Exception as e:
            logger.error(f"LaTeX fix error: {e}")
            return ""

    def get_embedding(self, text):
        if not text: return []
        try:
            embed_api_key = self.settings.embed_api_key if self.settings.embed_api_key else self.settings.api_key
            embed_base_url = self.settings.embed_base_url if self.settings.embed_base_url else self.settings.base_url
            embed_model_id = self.settings.embed_model_id if self.settings.embed_model_id else "text-embedding-3-small"

            client = OpenAI(
                api_key=embed_api_key,
                base_url=embed_base_url if embed_base_url else None
            )
            res = client.embeddings.create(input=text, model=embed_model_id)
            return res.data[0].embedding
        except Exception as e:
            print(f"Embedding error: {e}")
            return []

    def chat_with_tools(self, messages, callbacks):
        client = self.get_client()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_database",
                    "description": "通过提取用户语句中的核心数学/物理等学科知识点关键字，搜索本地题库。例如：当用户说“帮我找几道关于导数极值的题目”，你需要提取核心词“导数极值”并调用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "高度凝练的学科或知识点关键词（如：导数、圆锥曲线、牛顿第二定律），不要包含冗余的聊天词语"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_to_bag",
                    "description": "如果用户要求将某些题或搜索出来的题加入到试卷/题目袋中，必须调用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "question_ids": {
                                "type": "array",
                                "items": {"type": "integer", "description": "你要加入试卷的题目ID（通常来自于之前的搜索结果列表中的题号）"}
                            }
                        },
                        "required": ["question_ids"]
                    }
                }
            }
        ]

        # Build and mutate a local copy to prevent race conditions during threading
        working_messages = list(messages)

        # Allow multi-turn tool loops up to a limit
        max_turns = 3
        for _ in range(max_turns):
            kwargs = self._get_chat_kwargs()
            response = client.chat.completions.create(
                **kwargs,
                messages=working_messages,
                tools=tools,
                tool_choice="auto"
            )
            msg = response.choices[0].message

            if msg.tool_calls:
                working_messages.append(msg)
                for tool_call in msg.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    if func_name in callbacks:
                        results = callbacks[func_name](**args)
                        working_messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": func_name,
                            "content": json.dumps(results, ensure_ascii=False)
                        })
                # Continue loop to send tool responses back to model
                continue
            else:
                return msg.content, working_messages

        return "⚠️ 工具调用达到上限，任务终止", working_messages
