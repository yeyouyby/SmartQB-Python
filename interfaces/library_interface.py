import json
import base64
import io
import threading
from PySide6.QtCore import Qt, Signal, QThread, QObject, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QHeaderView, QSplitter

from qfluentwidgets import (PrimaryPushButton, PushButton, TableWidget, TextEdit, LineEdit,
                            BodyLabel, SubtitleLabel, ImageLabel, SearchLineEdit, MessageBox, InfoBar, InfoBarPosition)

from utils import logger
from search_service import vector_search_db

class ChatWorker(QThread):
    chat_updated = Signal(str, str)
    error = Signal(str)

    def __init__(self, history, user_text, app_logic, parent=None):
        super().__init__(parent)
        self.history = history
        self.user_text = user_text
        self.app_logic = app_logic

    def run(self):
        try:
            callbacks = {
                "search_database": lambda query: vector_search_db(self.app_logic.ai_service, query),
                "add_to_bag": self.app_logic.ai_add_to_bag
            }
            res_text, updated_history = self.app_logic.ai_service.chat_with_tools(
                self.history,
                callbacks=callbacks
            )
            self.history = updated_history
            self.history.append({"role": "assistant", "content": res_text})
            self.chat_updated.emit("🤖 助手", res_text)
        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            self.error.emit(str(e))

class LibraryInterface(QWidget):
    def __init__(self, app_logic, parent=None):
        super().__init__(parent=parent)
        self.app_logic = app_logic
        self.current_lib_q_id = None
        self.lib_current_diags = []
        self.lib_img_index = 0
        self.chat_history = [
            {"role": "system", "content": "你是 SmartQB 的寻题助手。你可以理解用户的寻题需求，调用 search_database 工具查询题库向量。如果用户要求将某些题加入题目袋/试卷，请调用 add_to_bag 工具。"}
        ]
        self.setup_ui()

    def setup_ui(self):
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(10, 10, 10, 10)
        self.vBoxLayout.setSpacing(10)

        # Top Search Bar
        top_layout = QHBoxLayout()
        self.ent_search = SearchLineEdit()
        self.ent_search.setPlaceholderText("🔍 搜索题库 (硬匹配)...")
        self.ent_search.setFixedWidth(300)
        self.ent_search.searchSignal.connect(self.on_hard_search)
        top_layout.addWidget(self.ent_search)

        btn_search = PushButton("搜索")
        btn_search.clicked.connect(self.on_hard_search)
        top_layout.addWidget(btn_search)
        top_layout.addStretch(1)
        self.vBoxLayout.addLayout(top_layout)

        # Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.vBoxLayout.addWidget(self.splitter, 1)

        # Left Panel (Table + Details)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0,0,0,0)

        self.table = TableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['ID', '题目内容'])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(TableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_lib_select)
        left_layout.addWidget(self.table, 1)

        det_frame = QWidget()
        det_layout = QVBoxLayout(det_frame)
        det_layout.setContentsMargins(0,10,0,0)

        det_layout.addWidget(SubtitleLabel("题目详情与修改"))
        self.txt_lib_det = TextEdit()
        self.txt_lib_det.setFixedHeight(100)
        det_layout.addWidget(self.txt_lib_det)

        action_layout = QHBoxLayout()
        action_layout.addWidget(BodyLabel("当前标签:"))
        self.ent_lib_tags = LineEdit()
        action_layout.addWidget(self.ent_lib_tags)

        btn_update = PrimaryPushButton("更新标签")
        btn_update.clicked.connect(self.update_lib_tags)
        action_layout.addWidget(btn_update)

        btn_bag = PushButton("🛍️ 加入题目袋")
        btn_bag.clicked.connect(self.add_to_bag)
        action_layout.addWidget(btn_bag)

        btn_del = PushButton("🗑️ 彻底删除")
        btn_del.clicked.connect(self.delete_lib_question)
        action_layout.addWidget(btn_del)
        det_layout.addLayout(action_layout)

        self.lbl_lib_diagram = ImageLabel()
        self.lbl_lib_diagram.setFixedHeight(200)
        self.lbl_lib_diagram.setAlignment(Qt.AlignCenter)
        det_layout.addWidget(self.lbl_lib_diagram)

        self.lbl_lib_diag_info = BodyLabel("")
        self.lbl_lib_diag_info.setAlignment(Qt.AlignCenter)
        det_layout.addWidget(self.lbl_lib_diag_info)

        diag_btn_layout = QHBoxLayout()
        btn_prev = PushButton("⬅️ 上一图")
        btn_prev.clicked.connect(self.lib_prev_diagram)
        btn_next = PushButton("下一图 ➡️")
        btn_next.clicked.connect(self.lib_next_diagram)
        diag_btn_layout.addWidget(btn_prev)
        diag_btn_layout.addWidget(btn_next)
        det_layout.addLayout(diag_btn_layout)

        left_layout.addWidget(det_frame, 1)
        self.splitter.addWidget(left_widget)

        # Right Panel (AI Chat)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10,0,0,0)

        right_layout.addWidget(SubtitleLabel("AI 软搜索助手 (MCP)"))

        self.txt_chat = TextEdit()
        self.txt_chat.setReadOnly(True)
        right_layout.addWidget(self.txt_chat, 1)

        chat_input_layout = QHBoxLayout()
        self.ent_chat = LineEdit()
        self.ent_chat.setPlaceholderText("想找什么样的题目？(回车发送)")
        self.ent_chat.returnPressed.connect(self.on_ai_chat)
        chat_input_layout.addWidget(self.ent_chat, 1)

        btn_send = PrimaryPushButton("发送")
        btn_send.clicked.connect(self.on_ai_chat)
        chat_input_layout.addWidget(btn_send)
        right_layout.addLayout(chat_input_layout)

        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([600, 400])

        self.append_chat("🤖 助手", "您好！想找什么样的题目？(例如：帮我找两道关于导数极值的题，并加入题目袋)")

    def append_chat(self, sender, text):
        self.txt_chat.append(f"{sender}: {text}\n")
        scrollbar = self.txt_chat.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_ai_chat(self):
        user_text = self.ent_chat.text().strip()
        if not user_text: return

        self.ent_chat.clear()
        self.append_chat("🧑 你", user_text)
        self.chat_history.append({"role": "user", "content": user_text})

        self.worker = ChatWorker(self.chat_history, user_text, self.app_logic)
        self.worker.chat_updated.connect(self.append_chat)
        self.worker.error.connect(lambda err: self.append_chat("⚠️ 系统", f"请求出错: {err}"))
        self.worker.start()

    def on_hard_search(self):
        kw = self.ent_search.text().strip()

        def task():
            from db_adapter import LanceDBAdapter
            adapter = LanceDBAdapter()
            return adapter.search_questions(kw)

        def _run():
            res = task()
            from PySide6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self, "on_search_result", Qt.QueuedConnection, Q_ARG(list, res))

        threading.Thread(target=_run, daemon=True).start()

    @Slot(list)
    def on_search_result(self, rows):
        self.table.setRowCount(len(rows))
        for idx, r in enumerate(rows):
            from PySide6.QtWidgets import QTableWidgetItem
            short_c = r[1][:30].replace('\n', ' ')
            self.table.setItem(idx, 0, QTableWidgetItem(str(r[0])))
            self.table.setItem(idx, 1, QTableWidgetItem(short_c))

    def on_lib_select(self):
        items = self.table.selectedItems()
        if not items: return
        row = items[0].row()
        q_id_item = self.table.item(row, 0)
        self.current_lib_q_id = int(q_id_item.text())

        try:
            from db_adapter import LanceDBAdapter
            adapter = LanceDBAdapter()
            content_text, diagram_base64 = adapter.get_question(self.current_lib_q_id)
            self.txt_lib_det.setPlainText(content_text if content_text else "")

            tags_rows = adapter.get_question_tags(self.current_lib_q_id)
            self.ent_lib_tags.setText(",".join([r[0] for r in tags_rows]))

            self.lib_current_diags = self.app_logic._parse_diagram_json(diagram_base64)
            self.lib_img_index = 0
            self._render_lib_diagram()

        except Exception as e:
            logger.error(f"DB Load Question Error: {e}", exc_info=True)

    def _render_lib_diagram(self):
        if not self.lib_current_diags:
            self.lbl_lib_diagram.setImage(QImage())
            self.lbl_lib_diagram.setText("无图样")
            self.lbl_lib_diag_info.setText("")
            return

        display_img_b64 = self.lib_current_diags[self.lib_img_index]
        if display_img_b64:
            try:
                img_data = base64.b64decode(display_img_b64.split(",")[-1] if "," in display_img_b64 else display_img_b64)
                img = QImage.fromData(img_data)
                self.lbl_lib_diagram.setImage(img.scaled(400, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.lbl_lib_diag_info.setText(f"图样 {self.lib_img_index + 1} / {len(self.lib_current_diags)}")
            except Exception as e:
                self.lbl_lib_diagram.setText(f"加载失败: {e}")
        else:
            self.lbl_lib_diagram.setImage(QImage())
            self.lbl_lib_diagram.setText("无图样")
            self.lbl_lib_diag_info.setText("")

    def lib_prev_diagram(self):
        if self.lib_current_diags:
            self.lib_img_index = (self.lib_img_index - 1) % len(self.lib_current_diags)
            self._render_lib_diagram()

    def lib_next_diagram(self):
        if self.lib_current_diags:
            self.lib_img_index = (self.lib_img_index + 1) % len(self.lib_current_diags)
            self._render_lib_diagram()

    def update_lib_tags(self):
        if self.current_lib_q_id is None: return
        new_tags = [t.strip() for t in self.ent_lib_tags.text().split(',') if t.strip()]
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        adapter.clear_question_tags(self.current_lib_q_id)
        for tn in new_tags:
            tid = adapter.execute_insert_tag(tn)
            adapter.execute_insert_question_tag(self.current_lib_q_id, tid)
        InfoBar.success('提示', '标签更新成功！', duration=2000, position=InfoBarPosition.TOP, parent=self)

    def delete_lib_question(self):
        items = self.table.selectedItems()
        if not items: return

        selected_rows = set(item.row() for item in items)
        selected_ids = [int(self.table.item(row, 0).text()) for row in selected_rows]

        w = MessageBox("危险操作", f"确定要彻底删除选中的 {len(selected_ids)} 道题目吗？不可恢复！", self.window())
        if w.exec():
            from db_adapter import LanceDBAdapter
            adapter = LanceDBAdapter()
            adapter.delete_questions(selected_ids)

            selected_id_set = set(selected_ids)
            self.app_logic.export_bag = [q for q in self.app_logic.export_bag if q["id"] not in selected_id_set]

            self.on_hard_search()
            self.txt_lib_det.clear()
            self.ent_lib_tags.clear()

            if self.current_lib_q_id in selected_id_set:
                self.current_lib_q_id = None

            InfoBar.success("成功", "选中题目已彻底删除！", duration=2000, position=InfoBarPosition.TOP, parent=self)

    def add_to_bag(self):
        if self.current_lib_q_id is None: return
        if any(item['id'] == self.current_lib_q_id for item in self.app_logic.export_bag):
            InfoBar.warning("提示", "该题已在题目袋中。", duration=2000, position=InfoBarPosition.TOP, parent=self)
            return

        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        content, diagram = adapter.get_question(self.current_lib_q_id)
        if content:
            self.app_logic.export_bag.append({"id": self.current_lib_q_id, "content": content, "diagram": diagram})
            InfoBar.success("成功", "已加入题目袋！", duration=2000, position=InfoBarPosition.TOP, parent=self)
