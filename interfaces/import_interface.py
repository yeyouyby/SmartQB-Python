import json
import io
import base64
import re
import threading
import tempfile
import subprocess
import gc
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QHeaderView, QSplitter)

from qfluentwidgets import (PrimaryPushButton, PushButton, TableWidget, TextEdit, LineEdit,
                            SubtitleLabel, BodyLabel, ImageLabel, ProgressBar, MessageBox, InfoBar, InfoBarPosition)

from utils import logger
from document_service import DocumentService
from doclayout_yolo_engine import DocLayoutYOLO

class IngestionWorker(QThread):
    status_updated = Signal(str)
    slice_ready = Signal(dict)
    finished_all = Signal(list)
    error_occurred = Signal(str)

    def __init__(self, file_path, file_type, app_logic, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.file_type = file_type
        self.app_logic = app_logic

    def run(self):
        try:
            pending_slices = []

            def handle_slice_ready(s):
                self.slice_ready.emit(s)

            if self.file_type in ["pdf", "image"]:
                if self.app_logic.doclayout_yolo is None:
                    self.status_updated.emit("正在首次加载 DocLayout-YOLO 引擎，请稍候...")
                    try:
                        self.app_logic.doclayout_yolo = DocLayoutYOLO()
                    except Exception as e:
                        self.error_occurred.emit(f"无法加载 DocLayout-YOLO 引擎:\n{e}")
                        return

                if self.app_logic.ocr_engine is None:
                    self.error_occurred.emit("无可用 OCR 引擎。请检查环境依赖。")
                    return

                pending_slices = DocumentService.process_doc_with_layout(
                    self.file_path, self.file_type,
                    self.app_logic.doclayout_yolo,
                    self.app_logic.ocr_engine,
                    "Pix2Text",
                    lambda msg: self.status_updated.emit(msg),
                    handle_slice_ready,
                    det_predictor=None
                )
            elif self.file_type == "word":
                pending_slices = DocumentService.extract_from_word(self.file_path)
                for s in pending_slices:
                    handle_slice_ready(s)

            self.finished_all.emit(pending_slices)
        except Exception as e:
            logger.error(f"Ingestion worker failed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))


class AIProcessingWorker(QThread):
    status_updated = Signal(str)
    questions_ready = Signal(list)
    finished_processing = Signal()
    error_occurred = Signal(str)

    def __init__(self, pending_slices, mode, file_type, app_logic, parent=None):
        super().__init__(parent)
        self.pending_slices = pending_slices
        self.mode = mode
        self.file_type = file_type
        self.app_logic = app_logic

    def run(self):
        try:
            use_vision = (self.mode == 3 and self.file_type != "word")
            batch_size = self.app_logic.settings.prm_batch_size if self.app_logic.settings.use_prm_optimization else 1

            current_idx = 0
            pending_fragment = ""
            cumulative_d_map = {}

            slices = self.pending_slices

            while current_idx < len(slices):
                end_idx = min(current_idx + batch_size + 1, len(slices))
                is_last_batch = (end_idx == len(slices))

                slices_to_send = []
                for i in range(current_idx, end_idx):
                    slices_to_send.append({
                        "index": i,
                        "text": slices[i]["text"],
                        "image_b64": slices[i].get("image_b64", "")
                    })
                    cumulative_d_map.update(slices[i].get("diagram_map", {}))

                desc = "多模态视觉版面合并中" if use_vision else "纯文本版面合并中"
                self.status_updated.emit(f"AI {desc}: 窗口 {current_idx} ~ {end_idx-1} / {len(slices)}...")

                try:
                    ai_res = self.app_logic.ai_service.process_slices_with_context(
                        slices_to_send,
                        use_vision=use_vision,
                        pending_fragment=pending_fragment,
                        is_last_batch=is_last_batch
                    )

                    questions = ai_res.get("Questions", [])
                    pending_fragment = ai_res.get("PendingFragment", "")

                    try:
                        next_index = int(ai_res.get("NextIndex", current_idx + 1))
                    except (TypeError, ValueError):
                        next_index = current_idx + 1

                    if next_index <= current_idx:
                        next_index = current_idx + 1

                    processed_q = []
                    for q in questions:
                        status = q.get("Status", "Complete")
                        if status == "NotQuestion":
                            continue

                        source_indices_raw = q.get("SourceSliceIndices", [])
                        if not isinstance(source_indices_raw, list):
                            source_indices_raw = []

                        source_indices = []
                        for raw_idx in source_indices_raw:
                            try:
                                source_indices.append(int(raw_idx))
                            except (TypeError, ValueError):
                                pass

                        image_b64 = ""
                        page_annotated_b64 = ""
                        content_text = q.get("Content", "")

                        per_question_d_map = {}
                        for idx in source_indices:
                            if 0 <= idx < len(slices):
                                if not image_b64 and slices[idx].get("image_b64"):
                                    image_b64 = slices[idx]["image_b64"]
                                if not page_annotated_b64 and slices[idx].get("page_annotated_b64"):
                                    page_annotated_b64 = slices[idx].get("page_annotated_b64")
                                per_question_d_map.update(slices[idx].get("diagram_map", {}))

                        content_text, diagram = self.app_logic._resolve_markers_and_extract_diagrams(content_text, cumulative_d_map, per_question_d_map)

                        item = {
                            "content": content_text,
                            "logic": q.get("LogicDescriptor", ""),
                            "tags": q.get("Tags") if isinstance(q.get("Tags"), list) else [],
                            "diagram": diagram,
                            "image_b64": image_b64,
                            "page_annotated_b64": page_annotated_b64
                        }
                        processed_q.append(item)

                    if processed_q:
                        self.questions_ready.emit(processed_q)
                    current_idx = next_index

                except Exception as e:
                    logger.error(f"AI 处理异常: {e}", exc_info=True)
                    # We will emit error and let UI decide to retry or fallback
                    self.error_occurred.emit(str(e))
                    return # Stop current worker if error, requires UI logic to restart or fallback

            if pending_fragment and pending_fragment.strip():
                clean_frag, diag_frag = self.app_logic._resolve_markers_and_extract_diagrams(pending_fragment, cumulative_d_map, {})
                item = {
                    "content": clean_frag,
                    "logic": "跨页未完结残段 (合并结束仍遗留)",
                    "tags": ["需人工校对"],
                    "diagram": diag_frag,
                    "image_b64": ""
                }
                self.questions_ready.emit([item])

            self.finished_processing.emit()

        except Exception as e:
            logger.error(f"AI worker failed: {e}", exc_info=True)
            self.error_occurred.emit(str(e))

class ImportInterface(QWidget):
    def __init__(self, app_logic, parent=None):
        super().__init__(parent=parent)
        self.app_logic = app_logic
        self.staging_questions = []
        self.current_img_index = 0
        self.stg_current_diags = []
        self.setup_ui()

    def setup_ui(self):
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(10, 10, 10, 10)
        self.vBoxLayout.setSpacing(10)

        # Top Bar
        top_frame = QWidget()
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_import_pdf = PushButton("📄 导入 PDF")
        self.btn_import_word = PushButton("📝 导入 Word")
        self.btn_import_img = PushButton("🖼️ 导入单张图片")

        self.btn_import_pdf.clicked.connect(lambda: self.on_import_file("pdf"))
        self.btn_import_word.clicked.connect(lambda: self.on_import_file("word"))
        self.btn_import_img.clicked.connect(lambda: self.on_import_file("image"))

        self.lbl_status = BodyLabel("等待导入...")
        self.progress_bar = ProgressBar()
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.hide()

        top_layout.addWidget(self.btn_import_pdf)
        top_layout.addWidget(self.btn_import_word)
        top_layout.addWidget(self.btn_import_img)
        top_layout.addWidget(self.lbl_status)
        top_layout.addWidget(self.progress_bar)
        top_layout.addStretch(1)

        self.vBoxLayout.addWidget(top_frame)

        # Splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.vBoxLayout.addWidget(self.splitter, 1)

        # Left Panel (Table + Actions)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0,0,0,0)

        self.table = TableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(['序号', '识别内容预览', '标签'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(TableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_table_selection)

        left_layout.addWidget(self.table)

        btn_del = PushButton("❌ 彻底删除选中题目")
        btn_del.clicked.connect(self.delete_selected)
        left_layout.addWidget(btn_del)

        btn_merge = PushButton("🔗 合并选中项")
        btn_merge.clicked.connect(self.merge_items)
        left_layout.addWidget(btn_merge)

        btn_split = PushButton("✂️ 拆分当前项")
        left_layout.addWidget(btn_split)

        btn_format = PushButton("✨ 重新排版(修正格式)")
        left_layout.addWidget(btn_format)

        self.splitter.addWidget(left_widget)

        # Right Panel (Details)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0,0,0,0)

        right_layout.addWidget(BodyLabel("AI 优化后文字内容 (可在此纠错):"))
        self.txt_content = TextEdit()
        right_layout.addWidget(self.txt_content)

        tag_layout = QHBoxLayout()
        tag_layout.addWidget(BodyLabel("AI 打标 (逗号分隔):"))
        self.ent_tags = LineEdit()
        tag_layout.addWidget(self.ent_tags)
        btn_update = PrimaryPushButton("💾 更新当前题目")
        btn_update.clicked.connect(self.update_current_item)
        tag_layout.addWidget(btn_update)
        right_layout.addLayout(tag_layout)

        vec_layout = QHBoxLayout()
        vec_layout.addWidget(BodyLabel("向量化预览:"))
        self.lbl_vector = BodyLabel("未生成向量")
        vec_layout.addWidget(self.lbl_vector)
        btn_gen_vec = PushButton("🔄 生成/更新向量")
        btn_gen_vec.clicked.connect(self.generate_vectors)
        vec_layout.addWidget(btn_gen_vec)
        vec_layout.addStretch(1)
        right_layout.addLayout(vec_layout)

        self.lbl_diagram = ImageLabel()
        self.lbl_diagram.setFixedHeight(250)
        self.lbl_diagram.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.lbl_diagram)

        self.lbl_diag_info = BodyLabel("")
        self.lbl_diag_info.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.lbl_diag_info)

        diag_btn_layout = QHBoxLayout()
        btn_prev_diag = PushButton("⬅️ 上一图")
        btn_prev_diag.clicked.connect(self.prev_diagram)
        btn_del_diag = PushButton("❌ 删除当前图")
        btn_del_diag.clicked.connect(self.delete_diagram)
        btn_next_diag = PushButton("下一图 ➡️")
        btn_next_diag.clicked.connect(self.next_diagram)
        diag_btn_layout.addWidget(btn_prev_diag)
        diag_btn_layout.addWidget(btn_del_diag)
        diag_btn_layout.addWidget(btn_next_diag)
        right_layout.addLayout(diag_btn_layout)

        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([400, 600])

        # Bottom Bar
        bottom_frame = QWidget()
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        bottom_layout.addWidget(BodyLabel("批量标签:"))
        self.ent_batch_tag = LineEdit()
        bottom_layout.addWidget(self.ent_batch_tag)
        btn_batch = PushButton("应用批量标签")
        bottom_layout.addWidget(btn_batch)

        bottom_layout.addStretch(1)

        btn_save_db = PrimaryPushButton("💾 全部直接入库")
        btn_save_db.clicked.connect(self.save_to_db)
        bottom_layout.addWidget(btn_save_db)

        self.vBoxLayout.addWidget(bottom_frame)

    def on_import_file(self, file_type):
        filters = {
            "pdf": "PDF (*.pdf)",
            "word": "Word (*.docx)",
            "image": "Image (*.png *.jpg *.jpeg)"
        }
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", filters[file_type])
        if not file_path: return

        self.staging_questions.clear()
        self.refresh_table()

        self.progress_bar.show()
        self.progress_bar.resume()

        self.worker = IngestionWorker(file_path, file_type, self.app_logic)
        self.worker.status_updated.connect(self.update_status)
        self.worker.slice_ready.connect(self.on_slice_ready)
        self.worker.finished_all.connect(lambda slices: self.on_ingestion_finished(slices, file_type))
        self.worker.error_occurred.connect(self.on_worker_error)
        self.worker.start()

    def update_status(self, msg):
        self.lbl_status.setText(msg)

    def on_slice_ready(self, s):
        mode = self.app_logic.settings.recognition_mode
        if mode == 1:
            combined_map = dict(s.get("diagram_map", {}))
            content_text, diagram = self.app_logic._resolve_markers_and_extract_diagrams(s["text"], combined_map, {})
            item = {
                "content": content_text, "logic": "无 (本地OCR模式)", "tags": ["本地提取"], "diagram": diagram, "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
            }
        else:
            item = {
                "content": s["text"], "logic": "等待 AI 处理...", "tags": ["本地提取中"], "diagram": s.get("diagram"), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
            }
        self.staging_questions.append(item)
        self.refresh_table()

    def on_ingestion_finished(self, pending_slices, file_type):
        mode = self.app_logic.settings.recognition_mode
        if mode == 1 or not pending_slices:
            self.progress_bar.hide()
            self.update_status("✅ 处理完毕！")
            return

        self.update_status("文档解析完毕，即将进入 AI 处理...")
        self.staging_questions.clear()
        self.refresh_table()

        self.ai_worker = AIProcessingWorker(pending_slices, mode, file_type, self.app_logic)
        self.ai_worker.status_updated.connect(self.update_status)
        self.ai_worker.questions_ready.connect(self.on_ai_questions_ready)
        self.ai_worker.finished_processing.connect(self.on_ai_finished)
        self.ai_worker.error_occurred.connect(self.on_ai_error)
        self.ai_worker.start()

    def on_ai_questions_ready(self, questions):
        for q in questions:
            self.staging_questions.append(q)
        self.refresh_table()

    def on_ai_finished(self):
        self.progress_bar.hide()
        self.update_status("✅ 文件全部处理并关联合并完毕！")
        InfoBar.success("成功", "文档处理完毕", duration=2000, position=InfoBarPosition.TOP, parent=self)

    def on_worker_error(self, err):
        self.progress_bar.hide()
        self.update_status("处理出错")
        MessageBox("错误", f"解析文档失败:\n{err}", self.window()).exec()

    def on_ai_error(self, err):
        self.progress_bar.hide()
        w = MessageBox("API 失败", f"AI 处理异常: {err}\n\n是否打开设置修改API重试？", self.window())
        if w.exec():
            # In a full app, this might navigate to settings. Here we just notify.
            pass

    def refresh_table(self):
        self.table.setRowCount(len(self.staging_questions))
        for idx, q in enumerate(self.staging_questions):
            preview = q["content"][:40].replace('\n', ' ')
            self.table.setItem(idx, 0, self._create_item(str(idx+1)))
            self.table.setItem(idx, 1, self._create_item(preview))
            self.table.setItem(idx, 2, self._create_item(",".join(q.get("tags", []))))

    def _create_item(self, text):
        from PySide6.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem(text)
        # item.setTextAlignment(Qt.AlignCenter)
        return item

    def on_table_selection(self):
        items = self.table.selectedItems()
        if not items: return
        row = items[0].row()
        q = self.staging_questions[row]

        self.txt_content.setText(q["content"])
        self.ent_tags.setText(",".join(q.get("tags", [])))

        vec = q.get("embedding", [])
        if vec:
            preview = str([round(v, 3) for v in vec[:3]]) + "..."
            self.lbl_vector.setText(f"已生成 (维度: {len(vec)}) {preview}")
        else:
            self.lbl_vector.setText("未生成向量")

        display_img_b64 = q.get("diagram")
        self.stg_current_diags = self.app_logic._parse_diagram_json(display_img_b64)
        self.current_img_index = 0
        self.render_diagram()

    def render_diagram(self):
        if not self.stg_current_diags:
            self.lbl_diagram.setImage(QImage())
            self.lbl_diagram.setText("无图样")
            self.lbl_diag_info.setText("")
            return

        display_img_b64 = self.stg_current_diags[self.current_img_index]
        if display_img_b64:
            try:
                img_data = base64.b64decode(display_img_b64.split(",")[-1] if "," in display_img_b64 else display_img_b64)
                img = QImage.fromData(img_data)
                self.lbl_diagram.setImage(img.scaled(400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.lbl_diag_info.setText(f"图样 {self.current_img_index + 1} / {len(self.stg_current_diags)}")
            except Exception as e:
                self.lbl_diagram.setText(f"加载失败: {e}")
        else:
            self.lbl_diagram.setImage(QImage())
            self.lbl_diagram.setText("无图样")
            self.lbl_diag_info.setText("")

    def prev_diagram(self):
        if self.stg_current_diags:
            self.current_img_index = (self.current_img_index - 1) % len(self.stg_current_diags)
            self.render_diagram()

    def next_diagram(self):
        if self.stg_current_diags:
            self.current_img_index = (self.current_img_index + 1) % len(self.stg_current_diags)
            self.render_diagram()

    def delete_diagram(self):
        items = self.table.selectedItems()
        if not items or not self.stg_current_diags: return
        row = items[0].row()

        del self.stg_current_diags[self.current_img_index]
        q = self.staging_questions[row]

        if not self.stg_current_diags:
            q["diagram"] = None
        elif len(self.stg_current_diags) == 1:
            q["diagram"] = self.stg_current_diags[0]
        else:
            import json
            q["diagram"] = json.dumps(self.stg_current_diags)

        self.current_img_index = max(0, min(self.current_img_index, len(self.stg_current_diags) - 1))
        self.render_diagram()

    def update_current_item(self):
        items = self.table.selectedItems()
        if not items: return
        row = items[0].row()
        self.staging_questions[row]["content"] = self.txt_content.toPlainText().strip()
        self.staging_questions[row]["tags"] = [t.strip() for t in self.ent_tags.text().split(",") if t.strip()]
        self.refresh_table()

    def delete_selected(self):
        items = self.table.selectedItems()
        if not items: return
        rows = sorted(list(set(item.row() for item in items)), reverse=True)

        w = MessageBox("警告", f"确定要彻底删除选中的 {len(rows)} 道题目吗？", self.window())
        if w.exec():
            for row in rows:
                self.staging_questions.pop(row)
            self.refresh_table()
            self.txt_content.clear()
            self.ent_tags.clear()
            self.lbl_diagram.setImage(QImage())
            self.stg_current_diags.clear()
            gc.collect()

    def merge_items(self):
        # Implement async merge using Thread/Signal
        pass

    def generate_vectors(self):
        # Implement async generation
        pass

    def save_to_db(self):
        if not self.staging_questions: return

        for q in self.staging_questions:
            if q.get("logic") == "等待 AI 处理...":
                MessageBox("无法入库", "部分题目还在等待 AI 处理，请等全部识别并格式化完毕后再入库！", self.window()).exec()
                return

        self.update_status("正在保存入库...")

        def task():
            from db_adapter import LanceDBAdapter
            successful_count = 0
            try:
                adapter = LanceDBAdapter()
                for q in self.staging_questions:
                    vec = q.get("embedding") or self.app_logic.ai_service.get_embedding(q["logic"] or q["content"])
                    q_id = adapter.execute_insert_question(q["content"], q["logic"], vec, q["diagram"])
                    for t in q["tags"]:
                        if not t: continue
                        t_id = adapter.execute_insert_tag(t)
                        adapter.execute_insert_question_tag(q_id, t_id)
                    successful_count += 1
                return successful_count
            except Exception as e:
                return e

        # Basic thread for db saving
        import threading
        def _run():
            res = task()
            from PySide6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self, "on_save_db_result", Qt.QueuedConnection, Q_ARG(object, res))

        threading.Thread(target=_run, daemon=True).start()

    @Slot(object)
    def on_save_db_result(self, res):
        if isinstance(res, Exception):
            MessageBox("错误", f"数据库保存失败:\n{res}", self.window()).exec()
        else:
            self.staging_questions.clear()
            self.refresh_table()
            self.update_status(f"成功直接入库 {res} 题！您可以前往题库查看。")
            InfoBar.success("成功", f"已直接保存 {res} 题至题库！", duration=3000, position=InfoBarPosition.TOP, parent=self)


    # Implement missing methods
    def merge_items(self):
        items = self.table.selectedItems()
        if not items: return
        rows = sorted(list(set(item.row() for item in items)))
        if len(rows) < 2:
            MessageBox("提示", "请按住 Ctrl/Cmd 选择至少两道相邻的题目进行合并。", self.window()).exec()
            return

        texts_to_merge = [self.staging_questions[idx]["content"] for idx in rows]
        self.update_status(f"🚀 AI 正在合并 {len(rows)} 道题目...")
        self.progress_bar.show()

        def task():
            return self.app_logic.ai_service.ai_merge_questions(texts_to_merge)

        def _run():
            res = task()
            from PySide6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self, "on_merge_result", Qt.QueuedConnection, Q_ARG(object, {"res": res, "rows": rows}))

        import threading
        threading.Thread(target=_run, daemon=True).start()

    @Slot(object)
    def on_merge_result(self, data):
        self.progress_bar.hide()
        merged = data["res"]
        rows = data["rows"]
        if not merged:
            MessageBox("错误", "合并失败，AI 未返回有效内容。", self.window()).exec()
            self.update_status("合并失败")
            return

        first_idx = rows[0]
        self.staging_questions[first_idx]["content"] = merged
        merged_tags = set(self.staging_questions[first_idx].get("tags", []))
        for idx in rows[1:]:
            merged_tags.update(self.staging_questions[idx].get("tags", []))
        self.staging_questions[first_idx]["tags"] = list(merged_tags)

        for idx in reversed(rows[1:]):
            self.staging_questions.pop(idx)

        self.refresh_table()
        self.update_status("✅ AI 合并完成")
        self.table.selectRow(first_idx)

    def generate_vectors(self):
        items = self.table.selectedItems()
        if not items: return
        rows = sorted(list(set(item.row() for item in items)))
        self.update_status(f"正在为 {len(rows)} 题生成向量...")
        self.progress_bar.show()

        def task():
            success_count = 0
            fail_count = 0
            last_vec = None
            for idx in rows:
                q = self.staging_questions[idx]
                text_to_embed = q.get("logic", "") or q.get("content", "")
                if not text_to_embed:
                    fail_count += 1
                    continue
                vec = self.app_logic.ai_service.get_embedding(text_to_embed)
                if vec:
                    q["embedding"] = vec
                    success_count += 1
                    if idx == rows[0]:
                        last_vec = vec
                else:
                    fail_count += 1
            return success_count, fail_count, last_vec

        def _run():
            s, f, v = task()
            from PySide6.QtCore import QMetaObject, Q_ARG
            QMetaObject.invokeMethod(self, "on_generate_vectors_result", Qt.QueuedConnection, Q_ARG(int, s), Q_ARG(int, f), Q_ARG(object, v))

        import threading
        threading.Thread(target=_run, daemon=True).start()

    @Slot(int, int, object)
    def on_generate_vectors_result(self, success_count, fail_count, last_vec):
        self.progress_bar.hide()
        if success_count > 0:
            preview = str([round(v, 3) for v in last_vec[:3]]) + "..." if last_vec else ""
            self.lbl_vector.setText(f"成功: {success_count}, 失败: {fail_count}. {preview}")
        else:
            self.lbl_vector.setText("生成失败")
        self.update_status("✅ 向量生成完毕")
