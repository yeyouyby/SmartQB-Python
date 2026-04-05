with open('gui/components/question_block.py', 'r') as f:
    content = f.read()

import re

# find _sync_preview method
match = re.search(r'def _sync_preview\(self\):.*?(?=def eventFilter)', content, re.DOTALL)
if match:
    old_body = match.group(0)
    new_body = """def _sync_preview(self):
        if not self.web_view:
            return

        import json

        # Convert markdown to HTML
        html_content = markdown.markdown(self._markdown_source)

        safe_html = json.dumps(html_content)

        js_code = f\"\"\"
        (function() {{
            const container = document.getElementById('math-content');
            if (container) {{
                container.innerHTML = {safe_html};
                if (typeof MathJax !== 'undefined') {{
                    MathJax.typesetPromise([container]).catch(function (err) {{
                        console.log(err.message);
                    }});
                }}
            }}
        }})();
        \"\"\"
        self.web_view.page().runJavaScript(js_code)

    """
    content = content.replace(old_body, new_body)
    with open('gui/components/question_block.py', 'w') as f:
        f.write(content)
    print("Patched.")
else:
    print("Not found.")
