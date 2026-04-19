with open('gui/views/knowledge_base.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_import = """from PySide6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QSplitter,
    QSizePolicy,
)"""

new_import = """from PySide6.QtWidgets import (
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

content = content.replace(old_import, new_import)

with open('gui/views/knowledge_base.py', 'w', encoding='utf-8') as f:
    f.write(content)
