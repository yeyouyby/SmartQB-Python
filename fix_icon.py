with open("ui_settings_tab.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "icon=None,",
    "icon=FluentIcon.LIGHTBULB,"
)

content = "from qfluentwidgets import FluentIcon\n" + content

with open("ui_settings_tab.py", "w", encoding="utf-8") as f:
    f.write(content)
