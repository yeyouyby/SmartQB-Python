import re
import logging
from gui.components.question_block import QuestionBlockWidget
from PySide6.QtCore import Qt, QThread, Signal
from db_adapter import LanceDBAdapter
from PySide6.QtWidgets import (
    QCompleter,
    QDialog,
    QFrame,
    QVBoxLayout,
    QSplitter,
    QLabel,
    QWidget,
)
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
    MessageBox,
    CommandBar,
    PrimaryPushButton,
    ProgressRing,
    FlowLayout,
    PillPushButton,
    LineEdit,
    TextEdit,
    SubtitleLabel,
    SmoothScrollArea,
)


logger = logging.getLogger(__name__)


class TransactionWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, block_data, parent=None):
        super().__init__(parent)
        self.block_data = block_data

    def run(self):
        try:
            db_adapter = LanceDBAdapter()
            from ai_service import AIService
            ai_service = AIService()
            logger.info("Harvesting data from QuestionBlocks...")
            import re
            id_mapping = {}
            pattern = re.compile(r'!\[(?P<alt>.*?)\]\((?P<url>.*?)(?:\s+["'](?P<title>.*?)["'])?\)')
            def replace_id(match):
                temp_id = match.group("url")
                title = match.group("title")
                alt = match.group("alt")
                if not temp_id.startswith("smartqb-image-drag://"):
                    return match.group(0)
                temp_id = temp_id[len("smartqb-image-drag://"):]
                if temp_id in id_mapping:
                    new_id = id_mapping[temp_id]
                else:
                    new_id = str(db_adapter.next_id())
                    id_mapping[temp_id] = new_id
                    logger.info(f"Replaced temporary UUID {temp_id} with Snowflake ID {new_id}")
                if title:
                    return f'![{alt}]({new_id} "{title}")'
                return f"![{alt}]({new_id})"
            results = []
            records = []
            target_dim = getattr(db_adapter, 'embedding_dimension', 1536)
            import asyncio
            async def get_embedding_async(text):
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, ai_service.get_embedding, text)
            async def process_blocks():
                tasks = []
                for idx, block in enumerate(self.block_data):
                    markdown_text = block.get('markdown', '')
                    logic_chain = block.get('logic_chain', '')
                    final_markdown = pattern.sub(replace_id, markdown_text)
                    results.append(final_markdown)
                    embed_text = final_markdown + "\n" + logic_chain
                    tasks.append(get_embedding_async(embed_text))
                embeddings = await asyncio.gather(*tasks)
                from utils import pad_or_truncate_vector
                from datetime import datetime
                timestamp = int(datetime.now().timestamp())
                for idx, block in enumerate(self.block_data):
                    vec = pad_or_truncate_vector(embeddings[idx], target_dim)
                    records.append({
                        'snowflake_id': db_adapter.next_id(),
                        'vector': vec,
                        'content_md': results[idx],
                        'logic_chain': block.get('logic_chain', ''),
                        'tags': block.get('tags', []),
                        'created_at': timestamp
                    })
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(process_blocks())
            loop.close()
            if records:
                import pyarrow as pa
                arrow_table = pa.Table.from_pylist(records)
                db_adapter.add_questions_bulk(arrow_table)
            self.finished.emit(results)
        except Exception as e:
            logger.error(f"Error during transaction pipeline: {e}", exc_info=True)
            self.error.emit(str(e))
class CalibrationWorkspace(QFrame):
    """
    核心校对层：三栏联动工作台 (Calibration Workspace)
    分为左 (3.5)、中 (5)、右 (1.5) 三个区域
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("CalibrationWorkspace")
        self.setup_ui()

    def eventFilter(self, obj, event):
        if (
            obj == self.window()
            and hasattr(self, "freeze_dialog")
            and self.freeze_dialog
        ):
            if event.type() in (event.Type.Move, event.Type.Resize):
                self.freeze_dialog.setGeometry(self.window().geometry())
        return super().eventFilter(obj, event)

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 核心分栏
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.main_layout.addWidget(self.splitter)

        # ==========================================
        # 1. 左栏：原卷保真参照视图 (Left Panel)
        # ==========================================
        self.left_panel = SmoothScrollArea()
        self.left_panel.setWidgetResizable(True)
        self.left_panel_content = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel_content)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(0)

        # Placeholder for lazy loading PDF pages
        self.left_placeholder = QLabel("原卷保真视图 (PDF 懒加载区)")
        self.left_placeholder.setAlignment(Qt.AlignCenter)
        self.left_layout.addWidget(self.left_placeholder)
        self.left_layout.addStretch(1)

        self.left_panel.setWidget(self.left_panel_content)
        self.splitter.addWidget(self.left_panel)

        # ==========================================
        # 2. 中栏：流式双态编辑器 (Mid Panel - 系统的核心与难点)
        # ==========================================
        self.mid_panel = SmoothScrollArea()
        self.mid_panel.setWidgetResizable(True)
        self.mid_panel_content = QWidget()
        self.mid_layout = QVBoxLayout(self.mid_panel_content)
        self.mid_layout.setContentsMargins(10, 10, 10, 10)
        self.mid_layout.setSpacing(15)

        # Instantiate dual-state ElevatedCardWidgets (QuestionBlockWidget)
        self.question_blocks = []
        for i in range(3):
            block = QuestionBlockWidget(self.mid_panel_content)
            block.set_question_number(i + 1)
            # Add some sample math markdown
            block.set_markdown(
                f"**Question {i + 1}**\n\nSolve the equation: $$ x^2 - {i + 4}x + 4 = 0 $$"
            )
            self.mid_layout.addWidget(block)
            self.question_blocks.append(block)

        self.mid_layout.addStretch(1)

        self.mid_panel.setWidget(self.mid_panel_content)
        self.splitter.addWidget(self.mid_panel)

        # ==========================================
        # ==========================================
        # 3. 右栏：元数据属性侧边栏 (Right Panel)
        # ==========================================
        self.right_panel = QFrame()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(10, 10, 10, 10)
        self.right_layout.setSpacing(15)

        # 3.1 Tags Area (标签域)
        self.tags_title = SubtitleLabel("考点标签 (Tags)")
        self.right_layout.addWidget(self.tags_title)

        self.tags_container = QWidget()
        self.tags_flow_layout = FlowLayout(self.tags_container, isTight=True)
        self.tags_flow_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_flow_layout.setSpacing(5)

        # Add initial dummy tags
        dummy_tags = ["Math", "Algebra", "Calculus"]
        for tag in dummy_tags:
            btn = PillPushButton(tag)
            self.tags_flow_layout.addWidget(btn)

        self.right_layout.addWidget(self.tags_container)

        self.tag_input = LineEdit()
        self.tag_input.setPlaceholderText("添加新标签...")

        # Setup Completer with dummy data
        completer_data = [
            "Math",
            "Algebra",
            "Calculus",
            "Geometry",
            "Trigonometry",
            "Physics",
        ]
        self.completer = QCompleter(completer_data, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.tag_input.setCompleter(self.completer)
        self.right_layout.addWidget(self.tag_input)

        # 3.2 AI Logic Area (描述域)
        self.ai_title = SubtitleLabel("AI 解析逻辑 (Chain of Thought)")
        self.right_layout.addWidget(self.ai_title)

        self.ai_logic_edit = TextEdit()
        self.ai_logic_edit.setReadOnly(True)
        self.ai_logic_edit.setPlaceholderText("大模型解析思维链...")
        # Rely on QFluentWidgets built-in theme-aware styling for read-only edits instead of hardcoding
        self.right_layout.addWidget(self.ai_logic_edit)

        # 3.3 State Indicator Placeholder
        self.state_title = SubtitleLabel("处理状态")
        self.right_layout.addWidget(self.state_title)

        self.status_label = QLabel("当前就绪 (Ready)")
        self.right_layout.addWidget(self.status_label)

        self.right_layout.addStretch(1)

        self.splitter.addWidget(self.right_panel)

        # 严格按照比例划分左、中、右 (3.5 : 5 : 1.5) => (7, 10, 3)
        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 10)
        self.splitter.setStretchFactor(2, 3)

        # ==========================================
        # 4. 底部：全局事务控制栏 (Transaction Command Bar)
        # ==========================================
        self.bottom_bar = CommandBar(self)
        # Apply somewhat transparent styling using styling if needed, otherwise rely on CommandBar defaults
        self.bottom_bar.setContentsMargins(10, 10, 10, 10)

        self.commit_btn = PrimaryPushButton("确认导入并生成资产")
        # Align to right
        self.bottom_bar.addWidget(self.commit_btn)

        # We need an overarching layout since `self.main_layout` only has splitter
        self.main_layout.addWidget(self.bottom_bar)

        # Bind the transaction pipeline
        self.commit_btn.clicked.connect(self.run_transaction_pipeline)

    def run_transaction_pipeline(self):

        logger.info("Starting Transaction Pipeline...")

        # 1. UI Freeze - Show overlay mask with ProgressRing
        self.freeze_dialog = QDialog(self.window())
        self.freeze_dialog.setModal(True)
        self.freeze_dialog.setAttribute(Qt.WA_DeleteOnClose)
        self.freeze_dialog.setAttribute(Qt.WA_TranslucentBackground)
        self.freeze_dialog.setWindowFlags(Qt.FramelessWindowHint)
        self.freeze_dialog.setStyleSheet(
            "QDialog { background-color: rgba(0, 0, 0, 150); }"
        )
        self.freeze_dialog.setGeometry(self.window().geometry())

        layout = QVBoxLayout(self.freeze_dialog)
        layout.setAlignment(Qt.AlignCenter)
        ring = ProgressRing()
        ring.setFixedSize(60, 60)
        layout.addWidget(ring)
        label = QLabel("正在生成数字资产，请勿操作...")
        label.setStyleSheet("color: white; font-size: 16px; font-weight: bold;")
        layout.addWidget(label)

        self.window().installEventFilter(self)
        self.freeze_dialog.show()

        # Launch worker
        block_data = []
        for block in self.question_blocks:
            block_data.append(
                {
                    "markdown": block.get_markdown(),
                    "logic_chain": "",  # Will pull from right panel in future
                    "tags": [],  # Will pull from right panel in future
                }
            )
        self.worker = TransactionWorker(block_data, self)
        self.worker.finished.connect(self._on_transaction_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self._on_transaction_error)
        self.worker.error.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_transaction_finished(self, results):

        # Update blocks with their final markdown
        for block, final_markdown in zip(self.question_blocks, results):
            block.set_markdown(final_markdown)

        logger.info("Transaction Pipeline completed successfully.")
        if hasattr(self, "freeze_dialog") and self.freeze_dialog:
            self.window().removeEventFilter(self)
            self.freeze_dialog.accept()
            self.freeze_dialog = None

        InfoBar.success(
            title="落盘成功",
            content="全部试题已成功解析并导入到题库中！",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.window(),
        )

    def _on_transaction_error(self, err_msg):

        logger.error(f"Transaction failed: {err_msg}")
        if hasattr(self, "freeze_dialog") and self.freeze_dialog:
            self.window().removeEventFilter(self)
            self.freeze_dialog.accept()
            self.freeze_dialog = None

        # Display an error message box to the user
        MessageBox(
            "Transaction Failed",
            f"An error occurred during asset generation:\n{err_msg}",
            self.window(),
        ).exec()
