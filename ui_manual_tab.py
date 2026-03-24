import json
import os
import base64
import io
import hashlib
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QFileDialog
from qfluentwidgets import (
    SubtitleLabel, BodyLabel, PushButton, PrimaryPushButton,
    LineEdit, TextEdit
)
from utils import logger
from background_tasks import WorkerThread

class ManualTab(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.settings = parent.settings
        self.ai_service = parent.ai_service
        self.setObjectName('Manual'.replace(' ', '-'))
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 16, 16, 16)

        self.manual_diagram_b64 = None
        self.manual_vector = None
        self._manual_save_inflight = False

        self._build_ui()

    def _build_ui(self):
        container = QFrame(self)
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(20, 20, 20, 20)
        self.vBoxLayout.addWidget(container)

        v_layout.addWidget(SubtitleLabel("题干文字内容 (支持直接粘贴纯文本):"))
        self.txt_manual = TextEdit(container)
        self.txt_manual.setMinimumHeight(150)
        v_layout.addWidget(self.txt_manual)

        btn_frame = QFrame(container)
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0,0,0,0)

        btn_ai_reformat = PrimaryPushButton("✨ 呼叫 AI 自动排版纠错并生成标签")
        btn_ai_reformat.clicked.connect(self.on_manual_ai)
        btn_reformat = PushButton("✨ 重新排版(修正格式)")
        btn_reformat.clicked.connect(self.on_manual_reformat)
        btn_retag = PushButton("🏷️ 重新生成标签")
        btn_retag.clicked.connect(self.on_manual_retag)
        btn_preview_vec = PushButton("🔄 预览向量化")
        btn_preview_vec.clicked.connect(self.on_manual_preview_vector)

        btn_layout.addWidget(btn_ai_reformat)
        btn_layout.addWidget(btn_reformat)
        btn_layout.addWidget(btn_retag)
        btn_layout.addWidget(btn_preview_vec)

        self.lbl_manual_status = BodyLabel("")
        self.lbl_manual_status.setStyleSheet("color: #0078D7;")
        btn_layout.addWidget(self.lbl_manual_status)

        btn_layout.addStretch(1)

        self.lbl_manual_vector_status = BodyLabel("未生成向量")
        self.lbl_manual_vector_status.setStyleSheet("color: gray;")
        btn_layout.addWidget(self.lbl_manual_vector_status)

        v_layout.addWidget(btn_frame)

        v_layout.addWidget(SubtitleLabel("知识点标签 (逗号分隔):"))
        self.ent_manual_tags = LineEdit(container)
        v_layout.addWidget(self.ent_manual_tags)

        diagram_frame = QFrame(container)
        diag_layout = QHBoxLayout(diagram_frame)
        diag_layout.setContentsMargins(0,0,0,0)

        btn_select_diag = PushButton("🖼️ 选择配套图样")
        btn_select_diag.clicked.connect(self.on_select_manual_diagram)
        diag_layout.addWidget(btn_select_diag)

        self.lbl_manual_diagram_status = BodyLabel("未选择图片")
        self.lbl_manual_diagram_status.setStyleSheet("color: gray;")
        diag_layout.addWidget(self.lbl_manual_diagram_status)
        diag_layout.addStretch(1)

        v_layout.addWidget(diagram_frame)

        btn_save_manual = PrimaryPushButton("💾 保存并直接入库")
        btn_save_manual.clicked.connect(self.save_manual)

        save_layout = QHBoxLayout()
        save_layout.addStretch(1)
        save_layout.addWidget(btn_save_manual)
        v_layout.addLayout(save_layout)
        v_layout.addStretch(1)

    def on_select_manual_diagram(self):
        from PIL import Image
        file_path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "Image files (*.png *.jpg *.jpeg *.bmp)")
        if not file_path:
            return

        try:
            img = Image.open(file_path)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            self.manual_diagram_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

            filename = os.path.basename(file_path)
            self.lbl_manual_diagram_status.setText(f"已选择: {filename}")
            self.lbl_manual_diagram_status.setStyleSheet("color: green;")
        except Exception as e:
            self.lbl_manual_diagram_status.setText(f"图片读取失败: {e}")
            self.lbl_manual_diagram_status.setStyleSheet("color: red;")
            self.manual_diagram_b64 = None

    def on_manual_reformat(self):
        text = self.txt_manual.toPlainText().strip()
        if not text: return
        self.lbl_manual_status.setText("正在重新排版...")

        self.worker = WorkerThread(self.ai_service.ai_format_question, text)
        def on_done(formatted):
            if formatted:
                self.txt_manual.setText(formatted)
                self.lbl_manual_status.setText("重新排版完成")
            else:
                self.lbl_manual_status.setText("排版失败")
                self.lbl_manual_status.setStyleSheet("color: red;")
        self.worker.finished_signal.connect(on_done)
        self.worker.start()

    def on_manual_retag(self):
        text = self.txt_manual.toPlainText().strip()
        if not text: return
        self.lbl_manual_status.setText("正在生成标签...")

        self.worker = WorkerThread(self.ai_service.process_text_with_correction, text)
        def on_done(res):
            tags = res.get("Tags", []) if res else []
            if tags:
                self.ent_manual_tags.setText(",".join(tags))
                self.lbl_manual_status.setText("标签生成完成")
            else:
                self.lbl_manual_status.setText("生成标签失败")
                self.lbl_manual_status.setStyleSheet("color: red;")
        def on_err(e):
            self.lbl_manual_status.setText(f"生成标签失败: {e}")
            self.lbl_manual_status.setStyleSheet("color: red;")

        self.worker.finished_signal.connect(on_done)
        self.worker.error_signal.connect(on_err)
        self.worker.start()

    def on_manual_preview_vector(self):
        text = self.txt_manual.toPlainText().strip()
        if not text: return
        self.lbl_manual_vector_status.setText("正在生成...")
        self.lbl_manual_vector_status.setStyleSheet("color: blue;")

        self.worker = WorkerThread(self.ai_service.get_embedding, text)
        def on_done(vec):
            if vec:
                self.manual_vector = vec
                self.manual_vector_text_hash = hash(text)
                preview = str([round(v, 3) for v in vec[:3]]) + "..."
                self.lbl_manual_vector_status.setText(f"已生成向量 (维度: {len(vec)}) {preview}")
                self.lbl_manual_vector_status.setStyleSheet("color: green;")
            else:
                self.lbl_manual_vector_status.setText("向量生成失败")
                self.lbl_manual_vector_status.setStyleSheet("color: red;")
        self.worker.finished_signal.connect(on_done)
        self.worker.start()

    def on_manual_ai(self):
        text = self.txt_manual.toPlainText().strip()
        if not text: return
        self.lbl_manual_status.setText("AI 分析与向量化中...")

        self.worker = WorkerThread(self.ai_service.process_text_with_correction, text)
        def on_done(res):
            if res:
                content_result = res.get("Content", "")
                self.txt_manual.setText(content_result)
                self.ent_manual_tags.setText(",".join(res.get("Tags", [])))
                self.lbl_manual_status.setText("AI 处理完成！请核对后保存。")

                if content_result:
                    self.on_manual_preview_vector()
            else:
                self.lbl_manual_status.setText("AI 处理失败")

        def on_err(e):
            self.parent_app.show_api_retry_dialog(e, self.on_manual_ai)
            self.lbl_manual_status.setText("AI 处理遇到错误")

        self.worker.finished_signal.connect(on_done)
        self.worker.error_signal.connect(on_err)
        self.worker.start()

    def save_manual(self):
        content = self.txt_manual.toPlainText().strip()
        if not content: return
        tags = [t.strip() for t in self.ent_manual_tags.text().split(",") if t.strip()]

        if self._manual_save_inflight:
            self.parent_app.notify_warning("提示", "正在入库，请勿重复提交。")
            return

        self._manual_save_inflight = True
        self.lbl_manual_status.setText("正在入库...")
        self.lbl_manual_status.setStyleSheet("color: blue;")

        def db_task():
            from db_adapter import LanceDBAdapter
            db = LanceDBAdapter()
            vec = self.manual_vector
            if hasattr(self, 'manual_vector_text_hash') and self.manual_vector_text_hash != hash(content):
                vec = None
            if not vec:
                vec = self.ai_service.get_embedding(content)

            q_id = db.execute_insert_question(content, "", vec if vec else None, self.manual_diagram_b64)
            for t in tags:
                if t:
                    t_id = db.execute_insert_tag(t)
                    db.execute_insert_question_tag(q_id, t_id)
            return True

        self.worker = WorkerThread(db_task)
        def on_done(res):
            self.txt_manual.clear()
            self.ent_manual_tags.clear()
            self.manual_diagram_b64 = None
            self.manual_vector = None
            if hasattr(self, 'manual_vector_text_hash'):
                delattr(self, 'manual_vector_text_hash')
            self.lbl_manual_diagram_status.setText("未选择图片")
            self.lbl_manual_diagram_status.setStyleSheet("color: gray;")
            self.lbl_manual_vector_status.setText("未生成向量")
            self.lbl_manual_vector_status.setStyleSheet("color: gray;")
            self.lbl_manual_status.setText("")
            self.parent_app.notify_success("成功", "手工录入成功，已存入题库！")
            self._manual_save_inflight = False

        def on_err(e):
            self.lbl_manual_status.setText(f"保存失败: {e}")
            self.lbl_manual_status.setStyleSheet("color: red;")
            self.parent_app.notify_error("错误", f"保存入库时发生异常:\n{e}")
            self._manual_save_inflight = False

        self.worker.finished_signal.connect(on_done)
        self.worker.error_signal.connect(on_err)
        self.worker.start()
