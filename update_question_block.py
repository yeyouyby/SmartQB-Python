
with open('gui/components/question_block.py', 'r') as f:
    content = f.read()

# Replace the _sync_preview method safely using regex or string replacement
old_method = """        # Escape for JS template literal
        safe_html = html_content.replace('`', '\\\\`').replace('$', '\\\\$')

        js_code = f\"\"\"
        (function() {{
            const container = document.getElementById('math-content');
            if (container) {{
                container.innerHTML = \\`{safe_html}\\`;
                if (typeof MathJax !== 'undefined') {{
                    MathJax.typesetPromise([container]).catch(function (err) {{
                        console.log(err.message);
                    }});
                }}
            }}
        }})();
        \"\"\""""


new_method = """        import json
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
        \"\"\""""

if old_method in content:
    content = content.replace(old_method, new_method)
    with open('gui/components/question_block.py', 'w') as f:
        f.write(content)
    print("Updated _sync_preview safely")
else:
    print("Could not find old method to replace")
