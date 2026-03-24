import json
import base64
import io
import threading
from PySide6.QtCore import Qt, Signal, QThread, QObject, Slot, QMetaObject, Q_ARG
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QHeaderView, QSplitter, QTableWidgetItem, QListWidgetItem, QApplication, QStackedWidget

from qfluentwidgets import (PrimaryPushButton, PushButton, TextEdit, LineEdit,
                            BodyLabel, ImageLabel, MessageBox, InfoBar, InfoBarPosition)

from utils import logger

class ManualWorker(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, action, app_logic, text=None, parent=None):
        super().__init__(parent)
        self.action = action
        self.app_logic = app_logic
        self.text = text

    def run(self):
        try:
            if self.action == "ai":
                res = self.app_logic.ai_service.process_text_with_correction(self.text)
                self.finished.emit(res)
            elif self.action == "format":
                formatted = self.app_logic.ai_service.ai_format_question(self.text)
                self.finished.emit({"formatted": formatted})
            elif self.action == "retag":
                res = self.app_logic.ai_service.process_text_with_correction(self.text)
                tags = res.get("Tags", [])
                self.finished.emit({"tags": tags})
            elif self.action == "vector":
                vec = self.app_logic.ai_service.get_embedding(self.text)
                self.finished.emit({"vector": vec})
        except Exception as e:
            logger.error(f"Manual action error: {e}", exc_info=True)
            self.error.emit(str(e))

class ManualInterface(QWidget):
    def __init__(self, app_logic, parent=None):
        super().__init__(parent=parent)
        self.app_logic = app_logic
        self.manual_diagram_b64 = None
        self.manual_vector = None
        self.setup_ui()

    def setup_ui(self):
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(20, 20, 20, 20)
        self.vBoxLayout.setSpacing(10)

        self.vBoxLayout.addWidget(BodyLabel("题干文字内容 (支持直接粘贴纯文本):"))
        self.txt_manual = TextEdit()
        self.txt_manual.setMinimumHeight(200)
        self.vBoxLayout.addWidget(self.txt_manual)

        btn_layout = QHBoxLayout()
        btn_ai = PushButton("✨ 呼叫 AI 自动排版纠错并生成标签")
        btn_ai.clicked.connect(self.on_manual_ai)
        btn_layout.addWidget(btn_ai)

        btn_reformat = PushButton("✨ 重新排版(修正格式)")
        btn_reformat.clicked.connect(self.on_manual_reformat)
        btn_layout.addWidget(btn_reformat)

        btn_retag = PushButton("🏷️ 重新生成标签")
        btn_retag.clicked.connect(self.on_manual_retag)
        btn_layout.addWidget(btn_retag)

        btn_vector = PushButton("🔄 预览向量化")
        btn_vector.clicked.connect(self.on_manual_preview_vector)
        btn_layout.addWidget(btn_vector)

        self.lbl_status = BodyLabel("")
        btn_layout.addWidget(self.lbl_status)

        self.lbl_vector_status = BodyLabel("未生成向量")
        btn_layout.addWidget(self.lbl_vector_status)

        btn_layout.addStretch(1)
        self.vBoxLayout.addLayout(btn_layout)

        self.vBoxLayout.addWidget(BodyLabel("知识点标签 (逗号分隔):"))
        self.ent_tags = LineEdit()
        self.vBoxLayout.addWidget(self.ent_tags)

        diag_layout = QHBoxLayout()
        btn_diag = PushButton("🖼️ 选择配套图样")
        btn_diag.clicked.connect(self.on_select_diagram)
        diag_layout.addWidget(btn_diag)

        self.lbl_diag_status = BodyLabel("未选择图片")
        diag_layout.addWidget(self.lbl_diag_status)
        diag_layout.addStretch(1)
        self.vBoxLayout.addLayout(diag_layout)

        btn_save = PrimaryPushButton("💾 保存并直接入库")
        btn_save.clicked.connect(self.save_manual)
        self.vBoxLayout.addWidget(btn_save, 0, Qt.AlignRight)

    def on_select_diagram(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not file_path: return

        try:
            with open(file_path, "rb") as f:
                img_data = f.read()
            self.manual_diagram_b64 = base64.b64encode(img_data).decode('utf-8')
            import os
            self.lbl_diag_status.setText(f"已选择: {os.path.basename(file_path)}")
        except Exception as e:
            self.lbl_diag_status.setText(f"图片读取失败: {e}")
            self.manual_diagram_b64 = None

    def on_manual_ai(self):
        text = self.txt_manual.toPlainText().strip()
        if not text: return
        self.lbl_status.setText("AI 分析与向量化中...")
        self.worker = ManualWorker("ai", self.app_logic, text)
        self.worker.finished.connect(self.on_ai_finished)
        self.worker.error.connect(lambda err: self.lbl_status.setText(f"失败: {err}"))
        self.worker.start()

    def on_ai_finished(self, res):
        content = res.get("Content", "")
        tags = res.get("Tags", [])
        self.txt_manual.setPlainText(content)
        self.ent_tags.setText(",".join(tags))
        self.lbl_status.setText("AI 处理完成！请核对后保存。")

        if content:
            self.on_manual_preview_vector()

    def on_manual_reformat(self):
        text = self.txt_manual.toPlainText().strip()
        if not text: return
        self.lbl_status.setText("正在重新排版...")
        self.worker = ManualWorker("format", self.app_logic, text)
        self.worker.finished.connect(lambda res: self.txt_manual.setPlainText(res.get("formatted", "")) or self.lbl_status.setText("排版完成"))
        self.worker.error.connect(lambda err: self.lbl_status.setText(f"失败: {err}"))
        self.worker.start()

    def on_manual_retag(self):
        text = self.txt_manual.toPlainText().strip()
        if not text: return
        self.lbl_status.setText("正在生成标签...")
        self.worker = ManualWorker("retag", self.app_logic, text)
        self.worker.finished.connect(lambda res: self.ent_tags.setText(",".join(res.get("tags", []))) or self.lbl_status.setText("标签生成完成"))
        self.worker.error.connect(lambda err: self.lbl_status.setText(f"失败: {err}"))
        self.worker.start()

    def on_manual_preview_vector(self):
        text = self.txt_manual.toPlainText().strip()
        if not text: return
        self.lbl_vector_status.setText("正在生成...")
        self.worker = ManualWorker("vector", self.app_logic, text)
        self.worker.finished.connect(self.on_vector_finished)
        self.worker.error.connect(lambda err: self.lbl_vector_status.setText(f"向量生成失败: {err}"))
        self.worker.start()

    def on_vector_finished(self, res):
        vec = res.get("vector")
        if vec:
            self.manual_vector = vec
            self.manual_vector_text_hash = hash(self.txt_manual.toPlainText().strip())
            preview = str([round(v, 3) for v in vec[:3]]) + "..."
            self.lbl_vector_status.setText(f"已生成向量 (维度: {len(vec)}) {preview}")

    def save_manual(self):
        content = self.txt_manual.toPlainText().strip()
        if not content: return
        tags = [t.strip() for t in self.ent_tags.text().split(",") if t.strip()]

        self.lbl_status.setText("正在入库...")

        def task():
            from db_adapter import LanceDBAdapter
            try:
                db = LanceDBAdapter()
                vec = self.manual_vector
                if hasattr(self, 'manual_vector_text_hash') and self.manual_vector_text_hash != hash(content):
                    vec = None

                if not vec:
                    vec = self.app_logic.ai_service.get_embedding(content)

                q_id = db.execute_insert_question(content, "", vec if vec else None, self.manual_diagram_b64)

                for t in tags:
                    t_id = db.execute_insert_tag(t)
                    db.execute_insert_question_tag(q_id, t_id)
                return True
            except Exception as e:
                return e

        def _run():
            res = task()
            QMetaObject.invokeMethod(self, "on_save_result", Qt.QueuedConnection, Q_ARG(object, res))

        threading.Thread(target=_run, daemon=True).start()

    @Slot(object)
    def on_save_result(self, res):
        if isinstance(res, Exception):
            MessageBox("错误", f"保存入库时发生异常:\n{res}", self.window()).exec()
            self.lbl_status.setText(f"保存失败: {res}")
        else:
            self.txt_manual.clear()
            self.ent_tags.clear()
            self.manual_diagram_b64 = None
            self.manual_vector = None
            if hasattr(self, 'manual_vector_text_hash'):
                delattr(self, 'manual_vector_text_hash')
            self.lbl_diag_status.setText("未选择图片")
            self.lbl_vector_status.setText("未生成向量")
            self.lbl_status.setText("")
            InfoBar.success("成功", "手工录入成功，已存入题库！", duration=3000, position=InfoBarPosition.TOP, parent=self)
