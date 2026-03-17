import re

with open("ai_service.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix ai_merge_questions
content = re.sub(
    r"            data = self\._parse_json\(res\.choices\[0\]\.message\.content\)\n            return data\.get\(\"merged_content\", \"\"\)",
    r"""            data = self._parse_json(res.choices[0].message.content)
            merged_content = data.get("merged_content", "")
            return merged_content if isinstance(merged_content, str) else "" """,
    content
)

# Fix ai_split_question
content = re.sub(
    r"            data = self\._parse_json\(res\.choices\[0\]\.message\.content\)\n            return data\.get\(\"split_questions\", \[\]\)",
    r"""            data = self._parse_json(res.choices[0].message.content)
            split_questions = data.get("split_questions", [])
            if not isinstance(split_questions, list):
                return []
            return [q for q in split_questions if isinstance(q, str)]""",
    content
)

# Fix ai_format_question
content = re.sub(
    r"            data = self\._parse_json\(res\.choices\[0\]\.message\.content\)\n            return data\.get\(\"formatted_content\", \"\"\)",
    r"""            data = self._parse_json(res.choices[0].message.content)
            formatted_content = data.get("formatted_content", "")
            return formatted_content if isinstance(formatted_content, str) else "" """,
    content
)

# Fix prompt typo in ai_format_question (排版助手 -> 解析助手)
content = re.sub(
    r"你是一个专业的试卷排版与排版助手。",
    r"你是一个专业的试卷排版与解析助手。",
    content
)

with open("ai_service.py", "w", encoding="utf-8") as f:
    f.write(content)
