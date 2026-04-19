with open('gui/views/knowledge_base.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_kb = """class KnowledgeBaseWorkspace(QFrame):
    \"\"\"
    题库管理模块基座 (Knowledge Base Workspace)
    \"\"\"


class DBLoaderWorker(QThread):
    finished = Signal(object)

    def run(self):
        try:
            from db_adapter import LanceDBAdapter

            adapter = LanceDBAdapter()
            self.finished.emit(adapter)
        except Exception as e:
            logger.error(f"Failed to load DB in background: {e}")
            self.finished.emit(None)

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("KnowledgeBaseWorkspace")

        self.setup_ui()
        self.setup_connections()

        self._db_adapter = None
        self.db_loader = DBLoaderWorker(self)
        self.db_loader.finished.connect(self._on_db_loaded)
        self.db_loader.finished.connect(self.db_loader.deleteLater)
        self.db_loader.start()

    def _on_db_loaded(self, adapter):
        self._db_adapter = adapter
        if hasattr(self, "_pending_query"):
            self._perform_search()"""

new_kb = """class DBLoaderWorker(QThread):
    finished = Signal(object)

    def run(self):
        try:
            from db_adapter import LanceDBAdapter

            adapter = LanceDBAdapter()
            self.finished.emit(adapter)
        except Exception as e:
            logger.error(f"Failed to load DB in background: {e}")
            self.finished.emit(None)


class KnowledgeBaseWorkspace(QFrame):
    \"\"\"
    题库管理模块基座 (Knowledge Base Workspace)
    \"\"\"

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("KnowledgeBaseWorkspace")

        self.setup_ui()
        self.setup_connections()

        self._db_adapter = None
        self.db_loader = DBLoaderWorker(self)
        self.db_loader.finished.connect(self._on_db_loaded)
        self.db_loader.finished.connect(self.db_loader.deleteLater)
        self.db_loader.start()

    def _on_db_loaded(self, adapter):
        self._db_adapter = adapter
        if hasattr(self, "_pending_query"):
            self._perform_search()"""

content = content.replace(old_kb, new_kb)

with open('gui/views/knowledge_base.py', 'w', encoding='utf-8') as f:
    f.write(content)
