with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    "isDarkMode=Theme.DARK == self.settings",
    "isDarkMode=(getattr(self.settings, 'theme', 'Light') == 'Dark')"
)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
