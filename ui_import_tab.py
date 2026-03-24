from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QSplitter, QTableWidgetItem, QFileDialog
from qfluentwidgets import (
    SubtitleLabel, BodyLabel, PushButton, PrimaryPushButton,
    LineEdit, TextEdit, TableWidget, ImageLabel, MessageBox
)
import json
import base64
import io
import gc
import threading
from PIL import Image
from PySide6.QtGui import QPixmap, QImage
from utils import logger
from background_tasks import WorkerThread
from document_service import DocumentService

class ImportTab(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.settings = parent.settings
        self.ai_service = parent.ai_service
        self.setObjectName('Import'.replace(' ', '-'))
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 16, 16, 16)

        self.stg_current_diags = []
        self.current_img_index = 0
        self._build_ui()

    def _build_ui(self):
        # Top toolbar
        top_frame = QFrame(self)
        h_layout = QHBoxLayout(top_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)

        btn_import_pdf = PushButton("📄 导入 PDF")
        btn_import_word = PushButton("📝 导入 Word")
        btn_import_image = PushButton("🖼️ 导入单张图片")

        btn_import_pdf.clicked.connect(lambda: self.on_import_file("pdf"))
        btn_import_word.clicked.connect(lambda: self.on_import_file("word"))
        btn_import_image.clicked.connect(lambda: self.on_import_file("image"))

        h_layout.addWidget(btn_import_pdf)
        h_layout.addWidget(btn_import_word)
        h_layout.addWidget(btn_import_image)

        self.lbl_import_status = SubtitleLabel("等待导入...")
        self.lbl_import_status.setStyleSheet("color: #0078D7;")
        h_layout.addWidget(self.lbl_import_status)
        h_layout.addStretch(1)

        self.vBoxLayout.addWidget(top_frame)

        # Paned Window (Splitter)
        paned = QSplitter(Qt.Horizontal, self)
        self.vBoxLayout.addWidget(paned, 1)

        # Left Frame
        left_frame = QFrame(paned)
        v_layout_left = QVBoxLayout(left_frame)

        self.tree_staging = TableWidget()
        self.tree_staging.setColumnCount(3)
        self.tree_staging.setHorizontalHeaderLabels(["序号", "识别内容预览", "标签"])
        self.tree_staging.setSelectionBehavior(TableWidget.SelectRows)
        self.tree_staging.itemSelectionChanged.connect(self.on_staging_select)
        v_layout_left.addWidget(self.tree_staging, 1)

        btn_delete_item = PushButton("❌ 彻底删除选中题目")
        btn_delete_item.clicked.connect(self.delete_staging_item)
        v_layout_left.addWidget(btn_delete_item)

        ai_frame = QFrame(left_frame)
        ai_layout = QVBoxLayout(ai_frame)
        ai_layout.setContentsMargins(0,0,0,0)

        ai_label = SubtitleLabel("AI 题目整理 (二次处理)")
        ai_layout.addWidget(ai_label)

        btn_merge = PushButton("🔗 合并选中项")
        btn_split = PushButton("✂️ 拆分当前项")
        btn_format = PushButton("✨ 重新排版(修正格式)")
        btn_merge.clicked.connect(self.merge_staging_items)
        btn_split.clicked.connect(self.split_staging_item)
        btn_format.clicked.connect(self.format_staging_item)
        ai_layout.addWidget(btn_merge)
        ai_layout.addWidget(btn_split)
        ai_layout.addWidget(btn_format)

        v_layout_left.addWidget(ai_frame)

        # Right Frame
        right_frame = QFrame(paned)
        v_layout_right = QVBoxLayout(right_frame)

        v_layout_right.addWidget(BodyLabel("AI 优化后文字内容 (可在此纠错):"))
        self.txt_stg_content = TextEdit()
        v_layout_right.addWidget(self.txt_stg_content, 1)

        v_layout_right.addWidget(BodyLabel("AI 打标 (逗号分隔):"))
        self.ent_stg_tags = LineEdit()
        v_layout_right.addWidget(self.ent_stg_tags)

        btn_update_stg = PushButton("💾 更新当前题目")
        btn_update_stg.clicked.connect(self.update_stg_item)
        v_layout_right.addWidget(btn_update_stg, alignment=Qt.AlignRight)

        vec_frame = QFrame()
        vec_layout = QHBoxLayout(vec_frame)
        vec_layout.addWidget(BodyLabel("向量化预览:"))
        self.lbl_vector_info = BodyLabel("未生成向量")
        vec_layout.addWidget(self.lbl_vector_info)
        vec_layout.addStretch(1)
        btn_vector = PushButton("🔄 生成/更新向量")
        btn_vector.clicked.connect(self.update_staging_vector)
        vec_layout.addWidget(btn_vector)
        v_layout_right.addWidget(vec_frame)

        self.lbl_stg_diagram = ImageLabel(self)
        self.lbl_stg_diagram.setFixedSize(400, 300)
        self.lbl_stg_diagram.setStyleSheet("background-color: #e0e0e0;")
        self.lbl_stg_diagram.setAlignment(Qt.AlignCenter)
        v_layout_right.addWidget(self.lbl_stg_diagram, alignment=Qt.AlignCenter)

        self.lbl_stg_diag_info = BodyLabel("")
        self.lbl_stg_diag_info.setAlignment(Qt.AlignCenter)
        v_layout_right.addWidget(self.lbl_stg_diag_info)

        diag_btn_frame = QFrame()
        diag_layout = QHBoxLayout(diag_btn_frame)
        btn_prev_diag = PushButton("⬅️ 上一图")
        btn_del_diag = PushButton("❌ 删除当前图")
        btn_next_diag = PushButton("下一图 ➡️")
        btn_prev_diag.clicked.connect(self.stg_prev_diagram)
        btn_del_diag.clicked.connect(self.stg_delete_diagram)
        btn_next_diag.clicked.connect(self.stg_next_diagram)
        diag_layout.addWidget(btn_prev_diag)
        diag_layout.addWidget(btn_del_diag)
        diag_layout.addWidget(btn_next_diag)
        v_layout_right.addWidget(diag_btn_frame)

        move_btn_frame = QFrame()
        move_layout = QHBoxLayout(move_btn_frame)
        btn_move_up = PushButton("⬆️ 将当前图样移至上一题")
        btn_move_down = PushButton("⬇️ 将当前图样移至下一题")
        btn_move_up.clicked.connect(self.move_diagram_up)
        btn_move_down.clicked.connect(self.move_diagram_down)
        move_layout.addWidget(btn_move_up)
        move_layout.addWidget(btn_move_down)
        v_layout_right.addWidget(move_btn_frame)

        btn_show_layout = PushButton("👁️ 查看完整版面分析图 (Pix2Text/Surya)")
        btn_show_layout.clicked.connect(self.show_page_layout_view)
        v_layout_right.addWidget(btn_show_layout, alignment=Qt.AlignRight)

        paned.addWidget(left_frame)
        paned.addWidget(right_frame)
        paned.setStretchFactor(0, 1)
        paned.setStretchFactor(1, 2)

        # Bottom Frame
        bottom_frame = QFrame(self)
        h_layout_bottom = QHBoxLayout(bottom_frame)
        h_layout_bottom.setContentsMargins(0,0,0,0)

        h_layout_bottom.addWidget(BodyLabel("为整个试卷批量追加标签:"))
        self.ent_batch_tag = LineEdit()
        h_layout_bottom.addWidget(self.ent_batch_tag)
        btn_batch_tag = PushButton("应用批量标签")
        btn_batch_tag.clicked.connect(self.apply_batch_tags)
        h_layout_bottom.addWidget(btn_batch_tag)

        h_layout_bottom.addStretch(1)

        btn_save_db = PrimaryPushButton("💾 全部直接入库 (跳过编译检查)")
        btn_fix_latex = PushButton("🛠️ 检查并修复选中题目的 LaTeX")
        btn_save_db.clicked.connect(self.save_staging_to_db)
        btn_fix_latex.clicked.connect(self.check_and_fix_latex)

        h_layout_bottom.addWidget(btn_fix_latex)
        h_layout_bottom.addWidget(btn_save_db)

        self.vBoxLayout.addWidget(bottom_frame)

    def update_status(self, text):
        self.parent_app.update_import_status_signal.emit(text)

    def refresh_staging_tree(self):
        self.tree_staging.setRowCount(0)
        for idx, q in enumerate(self.parent_app.staging_questions):
            preview = q["content"][:40].replace('\n', ' ')
            row_pos = self.tree_staging.rowCount()
            self.tree_staging.insertRow(row_pos)
            self.tree_staging.setItem(row_pos, 0, QTableWidgetItem(str(idx+1)))
            self.tree_staging.setItem(row_pos, 1, QTableWidgetItem(preview))
            self.tree_staging.setItem(row_pos, 2, QTableWidgetItem(",".join(q["tags"])))

    def on_import_file(self, file_type):
        exts = {"pdf": "PDF (*.pdf)", "word": "Word (*.docx)", "image": "Image (*.png *.jpg *.jpeg)"}
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", exts[file_type])
        if not file_path: return
        self.parent_app.staging_questions.clear()
        self.refresh_staging_tree()
        threading.Thread(target=self.run_ingestion_pipeline, args=(file_path, file_type), daemon=True).start()

    def run_ingestion_pipeline(self, file_path, file_type):
        self.update_status("正在提取文档切片...")
        pending_slices = []
        mode = self.settings.recognition_mode

        def handle_slice_ready(s):
            if mode == 1:
                combined_map = dict(s.get("diagram_map", {}))
                content_text, diagram = self.parent_app._resolve_markers_and_extract_diagrams(s["text"], combined_map)
                item = {
                    "content": content_text, "logic": "无 (本地OCR模式)", "tags": ["本地提取"], "diagram": diagram, "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            else:
                item = {
                    "content": s["text"], "logic": "等待 AI 处理...", "tags": ["本地提取中"], "diagram": s.get("diagram"), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            self.parent_app.staging_questions.append(item)
            self.parent_app.refresh_staging_tree_signal.emit()

        try:
            if file_type in ["pdf", "image"]:
                self.parent_app.staging_questions.clear()
                self.parent_app.refresh_staging_tree_signal.emit()

                if self.parent_app.doclayout_yolo is None:
                    self.update_status("正在首次加载 DocLayout-YOLO 引擎，请稍候...")
                    try:
                        from doclayout_yolo_engine import DocLayoutYOLO
                        self.parent_app.doclayout_yolo = DocLayoutYOLO()
                    except Exception as e:
                        logger.error(f"Failed to lazy load DocLayout-YOLO: {e}", exc_info=True)
                        self.parent_app.error_signal.emit(f"无法加载 DocLayout-YOLO 引擎:\n{e}")
                        return

                if self.parent_app.doclayout_yolo is None:
                    return
                if self.parent_app.ocr_engine is None:
                    return

                pending_slices = DocumentService.process_doc_with_layout(
                    file_path, file_type,
                    self.parent_app.doclayout_yolo,
                    self.parent_app.ocr_engine,
                    "Pix2Text",
                    self.update_status, handle_slice_ready,
                    det_predictor=None
                )
            elif file_type == "word":
                self.parent_app.staging_questions.clear()
                self.parent_app.refresh_staging_tree_signal.emit()
                pending_slices = DocumentService.extract_from_word(file_path)
                for s in pending_slices:
                    handle_slice_ready(s)

            if mode == 1:
                self.update_status("✅ 本地提取完毕！(未调用 AI)")
                return

        except Exception as e:
            self.update_status(f"提取文件失败: {e}")
            return

        if not pending_slices:
            self.update_status("✅ 处理完毕！没有提取到文字。")
            return

        self.parent_app.staging_questions.clear()
        self.parent_app.refresh_staging_tree_signal.emit()

        self._process_ai_slices(pending_slices, mode, file_type)
        self.update_status("✅ 文件全部处理并关联合并完毕！")

    def _parse_and_append_ai_res(self, ai_res, current_idx, pending_slices, cumulative_d_map):
        questions = ai_res.get("Questions", [])
        pending_fragment = ai_res.get("PendingFragment", "")

        try:
            next_index = int(ai_res.get("NextIndex", current_idx + 1))
        except (TypeError, ValueError):
            next_index = current_idx + 1

        if next_index <= current_idx:
            next_index = current_idx + 1

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
                if 0 <= idx < len(pending_slices):
                    if not image_b64 and pending_slices[idx].get("image_b64"):
                        image_b64 = pending_slices[idx]["image_b64"]
                    if not page_annotated_b64 and pending_slices[idx].get("page_annotated_b64"):
                        page_annotated_b64 = pending_slices[idx].get("page_annotated_b64")
                    per_question_d_map.update(pending_slices[idx].get("diagram_map", {}))

            content_text, diagram = self.parent_app._resolve_markers_and_extract_diagrams(content_text, cumulative_d_map, per_question_d_map)

            item = {
                "content": content_text,
                "logic": q.get("LogicDescriptor", ""),
                "tags": q.get("Tags") if isinstance(q.get("Tags"), list) else [],
                "diagram": diagram,
                "image_b64": image_b64,
                "page_annotated_b64": page_annotated_b64
            }
            self.parent_app.staging_questions.append(item)

        self.parent_app.refresh_staging_tree_signal.emit()
        return next_index, pending_fragment

    def _process_ai_slices(self, pending_slices, mode, file_type):
        use_vision = (mode == 3 and file_type != "word")
        batch_size = self.settings.prm_batch_size if self.settings.use_prm_optimization else 1

        current_idx = 0
        pending_fragment = ""
        cumulative_d_map = {}

        while current_idx < len(pending_slices):
            end_idx = min(current_idx + batch_size + 1, len(pending_slices))
            is_last_batch = (end_idx == len(pending_slices))

            slices_to_send = []
            for i in range(current_idx, end_idx):
                slices_to_send.append({
                    "index": i,
                    "text": pending_slices[i]["text"],
                    "image_b64": pending_slices[i].get("image_b64", "")
                })
                cumulative_d_map.update(pending_slices[i].get("diagram_map", {}))

            desc = "多模态视觉版面合并中" if use_vision else "纯文本版面合并中"
            self.update_status(f"AI {desc}: 窗口 {current_idx} ~ {end_idx-1} / {len(pending_slices)}...")

            try:
                ai_res = self.ai_service.process_slices_with_context(
                    slices_to_send,
                    use_vision=use_vision,
                    pending_fragment=pending_fragment,
                    is_last_batch=is_last_batch
                )

                current_idx, pending_fragment = self._parse_and_append_ai_res(ai_res, current_idx, pending_slices, cumulative_d_map)

            except Exception as e:
                logger.error(f"AI 处理异常: {e}", exc_info=True)

                retry_flag = [False]
                cv = threading.Condition()

                def on_retry_complete(should_retry):
                    with cv:
                        retry_flag[0] = should_retry
                        cv.notify()

                self.parent_app.api_retry_signal.emit(str(e), on_retry_complete)

                with cv:
                    cv.wait()

                if retry_flag[0]:
                    continue
                else:
                    # Fallback
                    fallback_end = min(current_idx + batch_size, len(pending_slices))
                    if fallback_end == current_idx: fallback_end += 1
                    for i in range(current_idx, fallback_end):
                        raw_text = pending_slices[i]["text"]
                        clean_text, fallback_diagram = self.parent_app._resolve_markers_and_extract_diagrams(raw_text, cumulative_d_map, pending_slices[i].get("diagram_map", {}))

                        item = {
                            "content": clean_text,
                            "logic": "API 失败，未解析",
                            "tags": ["API错误", "需人工校对"],
                            "diagram": fallback_diagram,
                            "page_annotated_b64": pending_slices[i].get("page_annotated_b64")
                        }
                        self.parent_app.staging_questions.append(item)
                    self.parent_app.refresh_staging_tree_signal.emit()
                    current_idx = fallback_end

        if pending_fragment and pending_fragment.strip():
            clean_frag, diag_frag = self.parent_app._resolve_markers_and_extract_diagrams(pending_fragment, cumulative_d_map)
            item = {
                "content": clean_frag,
                "logic": "跨页未完结残段 (合并结束仍遗留)",
                "tags": ["需人工校对"],
                "diagram": diag_frag,
                "image_b64": ""
            }
            self.parent_app.staging_questions.append(item)
            self.parent_app.refresh_staging_tree_signal.emit()

    def on_staging_select(self):
        items = self.tree_staging.selectedItems()
        if not items: return

        q = self.parent_app.staging_questions[items[0].row()]
        self.txt_stg_content.setText(q["content"])
        self.ent_stg_tags.setText(",".join(q.get("tags", [])))

        display_img_b64 = q.get("diagram")
        self.stg_current_diags = self.parent_app._parse_diagram_json(display_img_b64)
        self.current_img_index = 0
        self._render_stg_diagram()

        vec = q.get("embedding", [])
        if vec:
            preview = str([round(v, 3) for v in vec[:3]]) + "..."
            self.lbl_vector_info.setText(f"已生成 (维度: {len(vec)}) {preview}")
        else:
            self.lbl_vector_info.setText("未生成向量")

    def _render_stg_diagram(self):
        if not hasattr(self, 'stg_current_diags') or not self.stg_current_diags:
            self.lbl_stg_diagram.clear()
            self.lbl_stg_diagram.setText("无图样")
            self.lbl_stg_diag_info.setText("")
            return

        display_img_b64 = self.stg_current_diags[self.current_img_index]
        if display_img_b64:
            try:
                display_img_clean = display_img_b64.split(",")[-1] if "," in display_img_b64 else display_img_b64
                img = Image.open(io.BytesIO(base64.b64decode(display_img_clean))).copy()
                img.thumbnail((400, 300))
                qim = QImage(img.tobytes(), img.width, img.height, img.width * 3, QImage.Format_RGB888)
                pix = QPixmap.fromImage(qim)
                self.lbl_stg_diagram.setPixmap(pix)
                info_text = f"图样 {self.current_img_index + 1} / {len(self.stg_current_diags)}"
                self.lbl_stg_diag_info.setText(info_text)
            except Exception as e:
                self.lbl_stg_diagram.clear()
                self.lbl_stg_diagram.setText(f"图片加载失败: {e}")
                self.lbl_stg_diag_info.setText("")
        else:
            self.lbl_stg_diagram.clear()
            self.lbl_stg_diagram.setText("无图样")
            self.lbl_stg_diag_info.setText("")

    def stg_prev_diagram(self):
        if hasattr(self, 'stg_current_diags') and self.stg_current_diags:
            self.current_img_index = (self.current_img_index - 1) % len(self.stg_current_diags)
            self._render_stg_diagram()

    def stg_next_diagram(self):
        if hasattr(self, 'stg_current_diags') and self.stg_current_diags:
            self.current_img_index = (self.current_img_index + 1) % len(self.stg_current_diags)
            self._render_stg_diagram()

    def stg_delete_diagram(self):
        items = self.tree_staging.selectedItems()
        if not items: return
        idx = items[0].row()

        if not (hasattr(self, 'stg_current_diags') and self.stg_current_diags):
            return

        del self.stg_current_diags[self.current_img_index]

        q = self.parent_app.staging_questions[idx]
        if not self.stg_current_diags:
            q["diagram"] = None
        elif len(self.stg_current_diags) == 1:
            q["diagram"] = self.stg_current_diags[0]
        else:
            q["diagram"] = json.dumps(self.stg_current_diags)

        self.current_img_index = max(0, min(self.current_img_index, len(self.stg_current_diags) - 1))
        self._render_stg_diagram()

    def update_staging_vector(self):
        items = self.tree_staging.selectedItems()
        if not items: return
        self.lbl_vector_info.setText(f"正在为 {len(items)//3} 题生成向量...")

        def task():
            success_count = 0
            fail_count = 0
            last_vec = None

            for i in range(0, len(items), 3):
                idx = items[i].row()
                q = self.parent_app.staging_questions[idx]
                text_to_embed = q.get("logic", "") or q.get("content", "")
                if not text_to_embed:
                    fail_count += 1
                    continue

                vec = self.ai_service.get_embedding(text_to_embed)
                if vec:
                    q["embedding"] = vec
                    success_count += 1
                    if i == 0:
                        last_vec = vec
                else:
                    fail_count += 1
            return success_count, fail_count, last_vec

        self.worker = WorkerThread(task)
        def on_done(res):
            success_count, fail_count, last_vec = res
            if success_count > 0:
                preview = str([round(v, 3) for v in last_vec[:3]]) + "..." if last_vec else ""
                self.lbl_vector_info.setText(f"成功: {success_count}, 失败: {fail_count}. {preview}")
            else:
                self.lbl_vector_info.setText("生成失败")
        self.worker.finished_signal.connect(on_done)
        self.worker.start()

    def merge_staging_items(self):
        items = self.tree_staging.selectedItems()
        if len(items) < 6: # 2 rows * 3 cols
            self.parent_app.notify_info("提示", "请按住 Ctrl/Cmd 选择至少两道相邻的题目进行合并。")
            return

        indices = sorted(list(set([item.row() for item in items])))
        texts_to_merge = [self.parent_app.staging_questions[idx]["content"] for idx in indices]

        self.update_status(f"🚀 AI 正在合并 {len(indices)} 道题目...")

        def task():
            merged = self.ai_service.ai_merge_questions(texts_to_merge)
            if not merged:
                raise Exception("合并失败，AI 未返回有效内容。")
            return merged, indices

        self.worker = WorkerThread(task)
        def on_done(res):
            merged, indices = res
            first_idx = indices[0]
            self.parent_app.staging_questions[first_idx]["content"] = merged

            merged_tags = set(self.parent_app.staging_questions[first_idx].get("tags", []))
            for idx in indices[1:]:
                merged_tags.update(self.parent_app.staging_questions[idx].get("tags", []))
            self.parent_app.staging_questions[first_idx]["tags"] = list(merged_tags)

            for idx in reversed(indices[1:]):
                self.parent_app.staging_questions.pop(idx)

            self.refresh_staging_tree()
            self.update_status("✅ AI 合并完成")
            self.tree_staging.selectRow(first_idx)

        def on_err(e):
            self.parent_app.notify_error("错误", str(e))
            self.update_status("合并失败")

        self.worker.finished_signal.connect(on_done)
        self.worker.error_signal.connect(on_err)
        self.worker.start()

    def split_staging_item(self):
        items = self.tree_staging.selectedItems()
        if len(items) != 3: # 1 row * 3 cols
            self.parent_app.notify_info("提示", "请选择且仅选择一道需要拆分的复杂题目。")
            return

        idx = items[0].row()
        q = self.parent_app.staging_questions[idx]
        text_to_split = q["content"]

        self.update_status("🚀 AI 正在尝试拆分题目...")

        def task():
            splits = self.ai_service.ai_split_question(text_to_split)
            if not splits or len(splits) <= 1:
                raise Exception("拆分失败或未发现可拆分的子题。")
            return splits, idx

        self.worker = WorkerThread(task)
        def on_done(res):
            splits, idx = res
            self.parent_app.staging_questions[idx]["content"] = splits[0]

            for i, split_text in enumerate(splits[1:]):
                new_q = self.parent_app.staging_questions[idx].copy()
                new_q["content"] = split_text
                new_q["tags"] = list(new_q.get("tags", []))
                self.parent_app.staging_questions.insert(idx + 1 + i, new_q)

            self.refresh_staging_tree()
            self.update_status(f"✅ AI 成功拆分出 {len(splits)} 道题")

        def on_err(e):
            self.parent_app.notify_error("提示", str(e))
            self.update_status("拆分无效")

        self.worker.finished_signal.connect(on_done)
        self.worker.error_signal.connect(on_err)
        self.worker.start()

    def format_staging_item(self):
        items = self.tree_staging.selectedItems()
        if not items:
            self.parent_app.notify_info("提示", "请选择需要重新排版的题目。")
            return

        idx = items[0].row()
        q = self.parent_app.staging_questions[idx]
        text_to_format = self.txt_stg_content.toPlainText().strip()
        if not text_to_format: return

        self.update_status("🚀 AI 正在重新排版格式化题目...")

        def task():
            formatted = self.ai_service.ai_format_question(text_to_format)
            if not formatted:
                raise Exception("格式化失败。")
            return formatted, idx

        self.worker = WorkerThread(task)
        def on_done(res):
            formatted, idx = res
            self.parent_app.staging_questions[idx]["content"] = formatted
            self.txt_stg_content.setText(formatted)
            self.refresh_staging_tree()
            self.update_status("✅ 重新排版完成")

        def on_err(e):
            self.parent_app.notify_error("错误", str(e))
            self.update_status("格式化失败")

        self.worker.finished_signal.connect(on_done)
        self.worker.error_signal.connect(on_err)
        self.worker.start()

    def update_stg_item(self):
        items = self.tree_staging.selectedItems()
        if not items: return
        idx = items[0].row()
        self.parent_app.staging_questions[idx]["content"] = self.txt_stg_content.toPlainText().strip()
        self.parent_app.staging_questions[idx]["tags"] = [t.strip() for t in self.ent_stg_tags.text().split(",") if t.strip()]
        self.refresh_staging_tree()

    def delete_staging_item(self):
        items = self.tree_staging.selectedItems()
        if not items: return

        dialog = MessageBox("警告", f"确定要彻底删除选中的 {len(items)//3} 道题目吗？", self)
        if dialog.exec():
            indices = sorted(list(set([item.row() for item in items])), reverse=True)
            for idx in indices:
                item = self.parent_app.staging_questions.pop(idx)
                item.pop('diagram', None)
                item.pop('image_b64', None)
                item.pop('page_annotated_b64', None)
            self.refresh_staging_tree()
            self.parent_app._clear_staging_ui()

    def apply_batch_tags(self):
        batch_tag = self.ent_batch_tag.text().strip()
        if not batch_tag: return
        for q in self.parent_app.staging_questions:
            if batch_tag not in q["tags"]:
                q["tags"].append(batch_tag)
        self.refresh_staging_tree()

    def save_staging_to_db(self):
        if not self.parent_app.staging_questions: return

        for q in self.parent_app.staging_questions:
            if q.get("logic") == "等待 AI 处理...":
                self.parent_app.notify_warning("无法入库", "部分题目还在等待 AI 处理，请等全部识别并格式化完毕后再入库！")
                return

        self.update_status("正在保存入库...")

        def task():
            from db_adapter import LanceDBAdapter
            successful_count = 0
            adapter = LanceDBAdapter()
            for q in self.parent_app.staging_questions:
                vec = q.get("embedding") or self.ai_service.get_embedding(q["logic"] or q["content"])
                q_id = adapter.execute_insert_question(q["content"], q["logic"], vec, q["diagram"])
                for t in q["tags"]:
                    if not t: continue
                    t_id = adapter.execute_insert_tag(t)
                    adapter.execute_insert_question_tag(q_id, t_id)
                successful_count += 1
            return successful_count

        self.worker = WorkerThread(task)
        def on_done(successful_count):
            self.parent_app._clear_staging_ui()
            self.refresh_staging_tree()
            self.update_status(f"成功直接入库 {successful_count} 题！您可以前往题库查看。")
            self.parent_app.notify_success("成功", f"已直接保存 {successful_count} 题至题库！")

        def on_err(e):
            self.parent_app.notify_error("错误", f"数据库保存失败: {e}")

        self.worker.finished_signal.connect(on_done)
        self.worker.error_signal.connect(on_err)
        self.worker.start()

    def check_and_fix_latex(self):
        items = self.tree_staging.selectedItems()
        if not items:
            self.parent_app.notify_info("提示", "请选择需要检查 LaTeX 的题目。")
            return

        selected_indices = sorted(list(set([item.row() for item in items])))
        for idx in selected_indices:
            q = self.parent_app.staging_questions[idx]
            if q.get("logic") == "等待 AI 处理...":
                self.parent_app.notify_warning("无法检查", "选中的部分题目还在等待 AI 处理，请等全部识别并格式化完毕后再检查！")
                return

        self.update_status("正在检查选中题目的 LaTeX 编译...")

        def task():
            failed_indices = []
            successful_questions = []

            for idx in selected_indices:
                q = self.parent_app.staging_questions[idx]
                success, err_msg = self.parent_app._test_compile_latex(q["content"])
                if not success:
                    fixed_content = self.ai_service.ai_fix_latex(q["content"], err_msg)
                    if fixed_content:
                        success2, err_msg2 = self.parent_app._test_compile_latex(fixed_content)
                        if success2:
                            q["content"] = fixed_content
                            successful_questions.append((idx, q))
                        else:
                            failed_indices.append(idx)
                    else:
                        failed_indices.append(idx)
                else:
                    successful_questions.append((idx, q))
            return successful_questions, failed_indices

        self.worker = WorkerThread(task)
        def on_done(res):
            successful_questions, failed_indices = res
            self.refresh_staging_tree()
            for idx in selected_indices:
                self.tree_staging.selectRow(idx)

            total = len(selected_indices)
            self.update_status(f"LaTeX 检查完成。选中 {total} 题，成功修复 {len(successful_questions)} 题，失败 {len(failed_indices)} 题。")
            self.parent_app.notify_info("检查完成", f"成功检查修复 {len(successful_questions)} 题。有 {len(failed_indices)} 题编译失败。")

        self.worker.finished_signal.connect(on_done)
        self.worker.start()

    def move_diagram_up(self):
        items = self.tree_staging.selectedItems()
        if not items: return
        idx = items[0].row()
        if idx == 0:
            self.parent_app.notify_info("提示", "已经是第一题，无法上移。")
            return

        if not hasattr(self, 'stg_current_diags') or not self.stg_current_diags:
            self.parent_app.notify_info("提示", "当前题目没有图样。")
            return

        current_q = self.parent_app.staging_questions[idx]
        prev_q = self.parent_app.staging_questions[idx - 1]

        diag_to_move = self.stg_current_diags.pop(self.current_img_index)

        if not self.stg_current_diags:
            current_q["diagram"] = None
        elif len(self.stg_current_diags) == 1:
            current_q["diagram"] = self.stg_current_diags[0]
        else:
            current_q["diagram"] = json.dumps(self.stg_current_diags)

        self.current_img_index = max(0, min(self.current_img_index, len(self.stg_current_diags) - 1))

        prev_diags = self.parent_app._parse_diagram_json(prev_q.get("diagram"))
        prev_diags.append(diag_to_move)
        if len(prev_diags) == 1:
            prev_q["diagram"] = prev_diags[0]
        else:
            prev_q["diagram"] = json.dumps(prev_diags)

        self.refresh_staging_tree()
        self.tree_staging.selectRow(idx - 1)
        self.update_status(f"图样已移至第 {idx} 题")

    def move_diagram_down(self):
        items = self.tree_staging.selectedItems()
        if not items: return
        idx = items[0].row()
        if idx == len(self.parent_app.staging_questions) - 1:
            self.parent_app.notify_info("提示", "已经是最后一题，无法下移。")
            return

        if not hasattr(self, 'stg_current_diags') or not self.stg_current_diags:
            self.parent_app.notify_info("提示", "当前题目没有图样。")
            return

        current_q = self.parent_app.staging_questions[idx]
        next_q = self.parent_app.staging_questions[idx + 1]

        diag_to_move = self.stg_current_diags.pop(self.current_img_index)

        if not self.stg_current_diags:
            current_q["diagram"] = None
        elif len(self.stg_current_diags) == 1:
            current_q["diagram"] = self.stg_current_diags[0]
        else:
            current_q["diagram"] = json.dumps(self.stg_current_diags)

        self.current_img_index = max(0, min(self.current_img_index, len(self.stg_current_diags) - 1))

        next_diags = self.parent_app._parse_diagram_json(next_q.get("diagram"))
        next_diags.append(diag_to_move)
        if len(next_diags) == 1:
            next_q["diagram"] = next_diags[0]
        else:
            next_q["diagram"] = json.dumps(next_diags)

        self.refresh_staging_tree()
        self.tree_staging.selectRow(idx + 1)
        self.update_status(f"图样已移至第 {idx + 2} 题")

    def show_page_layout_view(self):
        items = self.tree_staging.selectedItems()
        if not items:
            self.parent_app.notify_info("提示", "请先在左侧选择一道题目。")
            return

        q = self.parent_app.staging_questions[items[0].row()]
        page_b64 = q.get("page_annotated_b64")

        if not page_b64:
            self.parent_app.notify_info("提示", "当前题目没有对应的完整版面分析图。")
            return

        try:
            img = Image.open(io.BytesIO(base64.b64decode(page_b64)))
            # Create a simple top level dialog to show image
            from PySide6.QtWidgets import QDialog, QScrollArea
            dialog = QDialog(self)
            dialog.setWindowTitle("完整版面分析预览")
            dialog.resize(800, 900)
            layout = QVBoxLayout(dialog)
            scroll = QScrollArea()
            lbl = ImageLabel()
            qim = QImage(img.tobytes(), img.width, img.height, img.width * 3, QImage.Format_RGB888)
            pix = QPixmap.fromImage(qim)
            lbl.setPixmap(pix)
            scroll.setWidget(lbl)
            layout.addWidget(scroll)
            dialog.exec()
        except Exception as e:
            self.parent_app.notify_error("错误", f"无法加载版面图: {e}")


    def on_update_import_status(self, text):
        self.lbl_import_status.setText(text)
