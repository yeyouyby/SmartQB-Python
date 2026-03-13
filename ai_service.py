# ai_service.py
import json
import re
import base64
from openai import OpenAI

# ==========================================
# AI 服务与纠错闭环
# ==========================================

class AIService:
    def __init__(self, settings):
        self.settings = settings

    def get_client(self):
        if not self.settings.api_key:
            raise ValueError("请先在设置中配置 API Key")
        return OpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url if self.settings.base_url else None
        )

    def _get_system_prompt(self):
        return """你是一个极其严谨的学术级智能题库处理引擎。
你的唯一目标是从混杂的 OCR 文本（及附加图片）中提取出结构完整、排版规范的题目。

【极其严格的 LaTeX 编译格式约束（必须遵守，否则系统将崩溃）】
1. 输出的 Content 必须能被 xelatex 与 ctexart 环境无错编译。
2. 正文普通文本中的所有 LaTeX 保留字符 (如 %, &, _, #, {, }) 必须使用反斜杠严格转义 (例如 \%, \&, \_, \#)。
3. 所有的数学公式、字母变量、数字、数学运算符必须严格包裹在行内公式 $...$ 或行间公式 $$...$$ 中。
4. 禁止把非数学内容的普通中文段落放进数学环境中。
5. 彻底删除最开头的题目序号（如 "1.", "(2)", "一、" 等）。

【绝对强制的输出格式】
你必须且只能输出合法的 JSON 格式字符串，绝对不要包含任何 markdown 代码块标记 (如 ```json) 或多余的说明对话文字。"""

    def process_text_with_correction(self, raw_text):
        """用于手动录入界面的单文本清洗"""
        client = self.get_client()
        prompt = f"""
{self._get_system_prompt()}

请解析以下输入文本，并严格按照以下 JSON 格式返回结果：
{{
    "Content": "纯正 LaTeX 格式的题目内容（已转义特殊字符）...",
    "LogicDescriptor": "解题思路或考点分析...",
    "Tags": ["知识点标签1", "知识点标签2"]
}}

【输入文本】：
{raw_text}
"""
        response = client.chat.completions.create(
            model=self.settings.model_id,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return self._parse_json(response.choices[0].message.content)

    def process_slices_with_context(self, slices_batch, use_vision=False):
        """核心引擎 (支持动态切片合并的滑动窗口状态机)"""
        client = self.get_client()
        
        system_content = self._get_system_prompt() + """

【切片合并与状态机规则】
我将提供一段按绝对序号 (Index) 排列的文本切片。它们是按文档物理顺序截取的。一道题可能跨越多个切片。
1. 提供的【最后一个切片】仅作为辅助上下文！如果没有发生题目跨页截断，绝对不能强行合并最后一个切片。
2. 对于提取出的每一道完整题目，明确指出它是由哪些切片序号合并而成的 (放入 SourceSliceIndices 数组)。
3. 返回 NextIndex，它等于【第一个未被包含在任何题目的 SourceSliceIndices 中的切片序号】。如果你消化了所有切片，它等于最后一个切片序号 + 1。
4. 如果传入的所有切片全是无效的页眉页脚或乱码，请返回空的 Questions 数组，并将 NextIndex 设为最后切片序号 + 1。

请严格返回如下 JSON 结构：
{
    "Questions": [
        {
            "Content": "第一题内容(纯正LaTeX格式，严格转义)...",
            "LogicDescriptor": "解析...",
            "Tags": ["标签1"],
            "SourceSliceIndices": [0, 1] 
        }
    ],
    "NextIndex": 2
}
"""
        messages_content = [{"type": "text", "text": system_content}]

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
        
        response = client.chat.completions.create(
            model=self.settings.model_id,
            messages=[{"role": "user", "content": messages_content}],
            response_format={"type": "json_object"}
        )
        return self._parse_json(response.choices[0].message.content)

    def _parse_json(self, raw_content):
        # 终极容错解析：即使 AI 不听话加了 markdown 标记，也能强行剥离
        try:
            return json.loads(raw_content)
        except:
            clean = re.sub(r'^```json\s*|\s*```$', '', raw_content.strip(), flags=re.MULTILINE)
            return json.loads(clean)

    def get_embedding(self, text):
        if not text: return []
        try:
            res = self.get_client().embeddings.create(input=text, model="text-embedding-3-small")
            return res.data[0].embedding
        except:
            return []

    def chat_with_tools(self, messages, callbacks):
        client = self.get_client()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_database",
                    "description": "通过语义搜索本地题库。当你需要查找题目、找相似题时调用此工具。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "用于进行向量检索的语义搜索词"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_to_bag",
                    "description": "将题目加入到用户的组卷题目袋中。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "question_ids": {
                                "type": "array",
                                "items": {"type": "integer"}
                            }
                        },
                        "required": ["question_ids"]
                    }
                }
            }
        ]
        
        response = client.chat.completions.create(
            model=self.settings.model_id,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        msg = response.choices[0].message
        
        if msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                if func_name in callbacks:
                    results = callbacks[func_name](**args)
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": func_name,
                        "content": json.dumps(results, ensure_ascii=False)
                    })
            final_response = client.chat.completions.create(
                model=self.settings.model_id,
                messages=messages
            )
            return final_response.choices[0].message.content, messages
        else:
            return msg.content, messages