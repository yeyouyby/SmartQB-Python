import json

def generate_js(html_content):
    safe_html = json.dumps(html_content)
    return f"""
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
    """
