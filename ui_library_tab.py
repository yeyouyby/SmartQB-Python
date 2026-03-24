from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QSplitter, QTableWidgetItem
from qfluentwidgets import (
    SubtitleLabel, BodyLabel, PushButton, PrimaryPushButton,
    LineEdit, TextEdit, TableWidget, ImageLabel
)
import base64
import io
from PIL import Image
from PySide6.QtGui import QPixmap, QImage
from utils import logger
from background_tasks import WorkerThread

class LibraryTab(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.settings = parent.settings
        self.ai_service = parent.ai_service
        self.setObjectName('Library'.replace(' ', '-'))
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 16, 16, 16)

        self.current_lib_q_id = None
        self._chat_inflight = False
        self.chat_history = [
            {"role": "system", "content": "你是 SmartQB 的寻题助手。你可以理解用户的寻题需求，调用 search_database 工具查询题库向量。如果用户要求将某些题加入题目袋/试卷，请调用 add_to_bag 工具。"}
        ]

        self._build_ui()

    def _build_ui(self):
        # Top toolbar
        top_frame = QFrame(self)
        h_layout = QHBoxLayout(top_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)

        self.ent_lib_search = LineEdit()
        self.ent_lib_search.setPlaceholderText("请输入题干关键词...")
        self.ent_lib_search.setFixedWidth(300)
        btn_search = PrimaryPushButton("🔍 搜索题库 (硬匹配)")
        btn_search.clicked.connect(self.on_hard_search)

        h_layout.addWidget(self.ent_lib_search)
        h_layout.addWidget(btn_search)
        h_layout.addStretch(1)

        self.vBoxLayout.addWidget(top_frame)

        # Paned Window (Splitter)
        paned = QSplitter(Qt.Horizontal, self)
        self.vBoxLayout.addWidget(paned, 1)

        # Left Frame
        left_frame = QFrame(paned)
        v_layout_left = QVBoxLayout(left_frame)

        self.tree_lib = TableWidget()
        self.tree_lib.setColumnCount(2)
        self.tree_lib.setHorizontalHeaderLabels(["ID", "题目内容"])
        self.tree_lib.setSelectionBehavior(TableWidget.SelectRows)
        self.tree_lib.itemSelectionChanged.connect(self.on_lib_select)
        v_layout_left.addWidget(self.tree_lib, 1)

        det_frame = QFrame(left_frame)
        det_layout = QVBoxLayout(det_frame)
        det_layout.setContentsMargins(0,0,0,0)
        det_layout.addWidget(SubtitleLabel("题目详情与修改"))

        self.txt_lib_det = TextEdit()
        self.txt_lib_det.setMinimumHeight(120)
        det_layout.addWidget(self.txt_lib_det, 1)

        action_frame = QFrame(det_frame)
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(0,0,0,0)

        action_layout.addWidget(BodyLabel("当前标签:"))
        self.ent_lib_tags = LineEdit()
        self.ent_lib_tags.setFixedWidth(200)
        btn_update_tags = PushButton("更新标签")
        btn_update_tags.clicked.connect(self.update_lib_tags)

        action_layout.addWidget(self.ent_lib_tags)
        action_layout.addWidget(btn_update_tags)

        btn_add_to_bag = PrimaryPushButton("🛍️ 加入题目袋")
        btn_add_to_bag.clicked.connect(self.add_to_bag)
        btn_delete_lib = PushButton("🗑️ 彻底删除")
        btn_delete_lib.clicked.connect(self.delete_lib_question)

        action_layout.addWidget(btn_add_to_bag)
        action_layout.addStretch(1)
        action_layout.addWidget(btn_delete_lib)

        det_layout.addWidget(action_frame)

        # Diagram UI
        self.lbl_lib_diagram = ImageLabel(det_frame)
        self.lbl_lib_diagram.setFixedSize(400, 200)
        self.lbl_lib_diagram.setStyleSheet("background-color: #e0e0e0;")
        self.lbl_lib_diagram.setAlignment(Qt.AlignCenter)
        det_layout.addWidget(self.lbl_lib_diagram, alignment=Qt.AlignCenter)

        self.lbl_lib_diag_info = BodyLabel("")
        self.lbl_lib_diag_info.setAlignment(Qt.AlignCenter)
        det_layout.addWidget(self.lbl_lib_diag_info)

        lib_btn_frame = QFrame(det_frame)
        lib_layout = QHBoxLayout(lib_btn_frame)
        btn_prev_diag = PushButton("⬅️ 上一图")
        btn_next_diag = PushButton("下一图 ➡️")
        btn_prev_diag.clicked.connect(self.lib_prev_diagram)
        btn_next_diag.clicked.connect(self.lib_next_diagram)
        lib_layout.addWidget(btn_prev_diag)
        lib_layout.addWidget(btn_next_diag)
        det_layout.addWidget(lib_btn_frame)

        v_layout_left.addWidget(det_frame)

        # Right Frame (MCP AI Chat)
        right_frame = QFrame(paned)
        v_layout_right = QVBoxLayout(right_frame)

        v_layout_right.addWidget(SubtitleLabel("AI 软搜索助手 (MCP)"))

        self.txt_chat = TextEdit()
        self.txt_chat.setReadOnly(True)
        v_layout_right.addWidget(self.txt_chat, 1)

        chat_bot_frame = QFrame(right_frame)
        chat_layout = QHBoxLayout(chat_bot_frame)
        chat_layout.setContentsMargins(0,0,0,0)

        self.ent_chat = LineEdit()
        self.ent_chat.returnPressed.connect(self.on_ai_chat)
        btn_send = PrimaryPushButton("发送")
        btn_send.clicked.connect(self.on_ai_chat)

        chat_layout.addWidget(self.ent_chat, 1)
        chat_layout.addWidget(btn_send)
        v_layout_right.addWidget(chat_bot_frame)

        paned.addWidget(left_frame)
        paned.addWidget(right_frame)
        paned.setStretchFactor(0, 3)
        paned.setStretchFactor(1, 2)

        self.append_chat("🤖 助手", "您好！想找什么样的题目？(例如：帮我找两道关于导数极值的题，并加入题目袋)")

    def append_chat(self, sender, text):
        self.txt_chat.append(f"{sender}: {text}\n")

    def on_hard_search(self):
        kw = self.ent_lib_search.text().strip()
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        rows = adapter.search_questions(kw)
        self.tree_lib.setRowCount(0)
        for r in rows:
            short_c = r[1][:30].replace('\n', ' ')
            row_pos = self.tree_lib.rowCount()
            self.tree_lib.insertRow(row_pos)
            self.tree_lib.setItem(row_pos, 0, QTableWidgetItem(str(r[0])))
            self.tree_lib.setItem(row_pos, 1, QTableWidgetItem(short_c))

    def on_lib_select(self):
        items = self.tree_lib.selectedItems()
        if not items: return
        self.current_lib_q_id = int(self.tree_lib.item(items[0].row(), 0).text())
        try:
            from db_adapter import LanceDBAdapter
            adapter = LanceDBAdapter()
            content_text, diagram_base64 = adapter.get_question(self.current_lib_q_id)
            self.txt_lib_det.setText(content_text if content_text else "")

            tags_rows = adapter.get_question_tags(self.current_lib_q_id)
            self.ent_lib_tags.setText(",".join([r[0] for r in tags_rows]))

            self.lib_current_diags = self.parent_app._parse_diagram_json(diagram_base64)
            self.lib_img_index = 0
            self._render_lib_diagram()

        except Exception as e:
            logger.error(f"DB Load Question Error: {e}", exc_info=True)

    def _render_lib_diagram(self):
        if not hasattr(self, 'lib_current_diags') or not self.lib_current_diags:
            self.lbl_lib_diagram.clear()
            self.lbl_lib_diagram.setText("无图样")
            self.lbl_lib_diag_info.setText("")
            return

        display_img_b64 = self.lib_current_diags[self.lib_img_index]
        if display_img_b64:
            try:
                img_data = base64.b64decode(display_img_b64.split(",")[-1] if "," in display_img_b64 else display_img_b64)
                img = Image.open(io.BytesIO(img_data)).copy()
                img.thumbnail((400, 200))
                # Convert PIL to QPixmap
                qim = QImage(img.tobytes(), img.width, img.height, img.width * 3, QImage.Format_RGB888)
                pix = QPixmap.fromImage(qim)
                self.lbl_lib_diagram.setPixmap(pix)
                info_text = f"图样 {self.lib_img_index + 1} / {len(self.lib_current_diags)}"
                self.lbl_lib_diag_info.setText(info_text)
            except Exception as e:
                self.lbl_lib_diagram.clear()
                self.lbl_lib_diagram.setText(f"图样加载失败: {e}")
                self.lbl_lib_diag_info.setText("")
        else:
            self.lbl_lib_diagram.clear()
            self.lbl_lib_diagram.setText("无图样")
            self.lbl_lib_diag_info.setText("")

    def lib_prev_diagram(self):
        if hasattr(self, 'lib_current_diags') and self.lib_current_diags:
            self.lib_img_index = (self.lib_img_index - 1) % len(self.lib_current_diags)
            self._render_lib_diagram()

    def lib_next_diagram(self):
        if hasattr(self, 'lib_current_diags') and self.lib_current_diags:
            self.lib_img_index = (self.lib_img_index + 1) % len(self.lib_current_diags)
            self._render_lib_diagram()

    def update_lib_tags(self):
        if getattr(self, 'current_lib_q_id', None) is None: return
        new_tags = [t.strip() for t in self.ent_lib_tags.text().split(',') if t.strip()]
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        adapter.clear_question_tags(self.current_lib_q_id)
        for tn in new_tags:
            tid = adapter.execute_insert_tag(tn)
            adapter.execute_insert_question_tag(self.current_lib_q_id, tid)
        self.parent_app.notify_info('提示', '标签更新成功！')

    def delete_lib_question(self):
        items = self.tree_lib.selectedItems()
        if not items: return

        from qfluentwidgets import MessageBox
        dialog = MessageBox("危险操作", f"确定要彻底删除选中的 {len(items)//2} 道题目吗？不可恢复！", self)
        if dialog.exec():
            selected_ids = []
            for item in items:
                if item.column() == 0:
                    selected_ids.append(int(item.text()))

            from db_adapter import LanceDBAdapter
            adapter = LanceDBAdapter()
            adapter.delete_questions(selected_ids)

            selected_id_set = set(selected_ids)
            self.parent_app.export_bag = [q for q in self.parent_app.export_bag if q["id"] not in selected_id_set]

            self.on_hard_search()
            self.txt_lib_det.clear()
            self.ent_lib_tags.clear()

            if getattr(self, 'current_lib_q_id', None) in selected_id_set:
                self.current_lib_q_id = None

            self.parent_app.notify_success("成功", "选中题目已彻底删除！")

    def add_to_bag(self):
        if not hasattr(self, 'current_lib_q_id') or self.current_lib_q_id is None: return
        if any(item['id'] == self.current_lib_q_id for item in self.parent_app.export_bag):
            self.parent_app.notify_info("提示", "该题已在题目袋中。")
            return
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        content, diagram = adapter.get_question(self.current_lib_q_id)
        if content:
            self.parent_app.export_bag.append({"id": self.current_lib_q_id, "content": content, "diagram": diagram})
            self.parent_app.notify_success("成功", "已加入题目袋！")

    def ai_add_to_bag(self, question_ids):
        added = 0
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        for q_id in question_ids:
            if any(item['id'] == q_id for item in self.parent_app.export_bag): continue
            content, diagram = adapter.get_question(q_id)
            if content:
                self.parent_app.export_bag.append({"id": q_id, "content": content, "diagram": diagram})
                added += 1
        return {"status": "success", "message": f"成功加入了 {added} 道题目到题目袋"}

    def on_ai_chat(self):
        user_text = self.ent_chat.text().strip()
        if not user_text: return

        if self._chat_inflight:
            self.parent_app.notify_warning("提示", "助手正在处理中，请稍候再发送下一条消息。")
            return

        self._chat_inflight = True
        self.ent_chat.clear()
        self.append_chat("🧑 你", user_text)
        self.chat_history.append({"role": "user", "content": user_text})

        from search_service import vector_search_db
        def chat_task():
            callbacks = {
                "search_database": lambda query: vector_search_db(self.ai_service, query),
                "add_to_bag": self.ai_add_to_bag
            }
            res_text, updated_history = self.ai_service.chat_with_tools(
                self.chat_history,
                callbacks=callbacks
            )
            return res_text, updated_history

        self.worker = WorkerThread(chat_task)
        def on_done(res):
            res_text, updated_history = res
            self.chat_history = updated_history
            self.chat_history.append({"role": "assistant", "content": res_text})
            self.append_chat("🤖 助手", res_text)
            self._chat_inflight = False
        def on_err(e):
            self.append_chat("⚠️ 系统", f"请求出错: {e}")
            self._chat_inflight = False

        self.worker.finished_signal.connect(on_done)
        self.worker.error_signal.connect(on_err)
        self.worker.start()
