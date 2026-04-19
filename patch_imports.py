with open('gui/views/knowledge_base.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix nested imports
old_import1 = """from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QSplitter,
    QSizePolicy,
)"""

new_import1 = """from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QSplitter,
    QSizePolicy,
    QListView,
    QTreeWidgetItem,
    QTableWidgetItem,
)"""

content = content.replace(old_import1, new_import1)

# Remove the inline ones
content = content.replace("        from PySide6.QtWidgets import QListView\n\n", "")
content = content.replace("        from PySide6.QtWidgets import QTreeWidgetItem\n\n", "")
content = content.replace("        from PySide6.QtWidgets import QTableWidgetItem\n\n", "")

with open('gui/views/knowledge_base.py', 'w', encoding='utf-8') as f:
    f.write(content)

with open('gui/views/home.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_home1 = """from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QWidget, QHeaderView"""
new_home1 = """from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QWidget, QHeaderView, QTableWidgetItem"""
content = content.replace(old_home1, new_home1)
content = content.replace("        from PySide6.QtWidgets import QTableWidgetItem\n        \n", "")

with open('gui/views/home.py', 'w', encoding='utf-8') as f:
    f.write(content)


with open('gui/views/production.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_prod1 = """from PySide6.QtWidgets import QFrame, QVBoxLayout, QSplitter, QWidget"""
new_prod1 = """from PySide6.QtWidgets import QFrame, QVBoxLayout, QSplitter, QWidget, QTreeWidgetItem"""

content = content.replace(old_prod1, new_prod1)
content = content.replace("        from PySide6.QtWidgets import QTreeWidgetItem\n", "")

with open('gui/views/production.py', 'w', encoding='utf-8') as f:
    f.write(content)
