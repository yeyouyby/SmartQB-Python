import gc
# gui_app.py
import os
import warnings
import io
import json
import threading
import base64
import re
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
try:
    from pix2text import Pix2Text
except Exception as e:
    Pix2Text = None
    print(f"Warning: Failed to import Pix2Text: {e}")


try:
    from surya.layout import LayoutPredictor
    from surya.recognition import RecognitionPredictor
    from surya.foundation import FoundationPredictor
    from surya.detection import DetectionPredictor
except ImportError:
    LayoutPredictor = None
    RecognitionPredictor = None
    FoundationPredictor = None
    DetectionPredictor = None
from utils import logger
from config import DB_NAME
from settings_manager import SettingsManager
from utils import check_hardware_requirements
from doclayout_yolo_engine import DocLayoutYOLO
from ai_service import AIService
from document_service import DocumentService
from search_service import vector_search_db

# Set up transformers warnings suppression
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")

# ==========================================
# 主应用 GUI
# ==========================================
class SmartQBApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SmartQB Pro V3 - 智能题库桌面端 (完整版)")
        self.geometry("1300x850")

        self.settings = SettingsManager()
        self.ai_service = AIService(self.settings)

        logger.info("正在加载 Pix2Text 引擎 (首次启动可能需要下载模型，请耐心等待)...")
        try:
            self.ocr_engine = Pix2Text.from_config()
            logger.info("Pix2Text 引擎加载完成！")
        except Exception as e:
            logger.error(f"Failed to load Pix2Text: {e}", exc_info=True)
            self.ocr_engine = None
        self.hardware_ok = check_hardware_requirements()

        # Determine engines to load based on settings and hardware
        layout_engine = getattr(self.settings, 'layout_engine_type', 'DocLayout-YOLO')
        ocr_engine = getattr(self.settings, 'ocr_engine_type', 'Pix2Text')

        if not self.hardware_ok:
            if layout_engine == 'Surya' or ocr_engine == 'Surya':
                logger.warning("硬件不达标，强制回退到 DocLayout-YOLO + Pix2Text。")
            layout_engine = 'DocLayout-YOLO'
            ocr_engine = 'Pix2Text'        self.surya_foundation = None
        self.surya_layout = None
        self.surya_ocr = None
        self.surya_detection = None
        self.doclayout_yolo = None

        self.surya_foundation_failed = False
        self.surya_layout_failed = False
        self.surya_ocr_failed = False
        self.surya_detection_failed = False

        self._engine_load_lock = threading.Lock()

        if layout_engine == 'Surya' or ocr_engine == 'Surya':
            logger.info("正在加载 Surya 基础引擎 (FoundationPredictor)...")
            if FoundationPredictor:
                try:
                    self.surya_foundation = FoundationPredictor()
                except Exception as e:
                    logger.error(f"Failed to load FoundationPredictor: {e}", exc_info=True)
                    self.surya_foundation_failed = True

            if layout_engine == 'Surya':
                logger.info("正在加载 Surya Layout 版面分析引擎...")
                if LayoutPredictor and self.surya_foundation:
                    try:
                        self.surya_layout = LayoutPredictor(self.surya_foundation)
                        logger.info("Surya Layout 引擎加载完成！")
                    except Exception as e:
                        logger.error(f"Failed to load Surya Layout: {e}", exc_info=True)
                        self.surya_layout_failed = True            if ocr_engine == 'Surya':
                logger.info("正在加载 Surya OCR 与检测引擎...")
                if RecognitionPredictor and DetectionPredictor and self.surya_foundation:
                    try:
                        self.surya_ocr = RecognitionPredictor(self.surya_foundation)
                        self.surya_detection = DetectionPredictor()
                        logger.info("Surya OCR 与检测引擎加载完成！")
                    except Exception as e:
                        logger.error(f"Failed to load Surya OCR/Detection: {e}", exc_info=True)
                        self.surya_ocr_failed = True
                        self.surya_detection_failed = True

        if layout_engine == 'DocLayout-YOLO' or self.surya_layout is None:
            logger.info("正在加载 DocLayout-YOLO 版面分析引擎...")
            try:
                self.doclayout_yolo = DocLayoutYOLO()
            except Exception as e:
                logger.error(f"Failed to load DocLayout-YOLO: {e}", exc_info=True)

        self.staging_questions = []
        self.export_bag = []

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tab_import = ttk.Frame(self.notebook)
        self.tab_manual = ttk.Frame(self.notebook)
        self.tab_library = ttk.Frame(self.notebook)
        self.tab_export = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_import, text="1. 文件导入与审阅 (Import)")
        self.notebook.add(self.tab_manual, text="➕ 手动单题录入")
        self.notebook.add(self.tab_library, text="2. 题库维护 (Library)")
        self.notebook.add(self.tab_export, text="3. 题目袋组卷 (Export)")
        self.notebook.add(self.tab_settings, text="设置 (Settings)")

        self.build_import_tab()
        self.build_manual_tab()
        self.build_library_tab()
        self.build_export_tab()
        self.build_settings_tab()

        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    # ------------------------------------------
    # API 错误拦截
    # ------------------------------------------
    def ask_api_retry_sync(self, error_msg):
        result = [False]
        event = threading.Event()
        def show_dialog():
            dialog = tk.Toplevel(self)
            dialog.title("⚠️ API 请求失败")
            dialog.geometry("450x300")
            dialog.grab_set()

            ttk.Label(dialog, text=f"发生错误:\n{error_msg}", foreground="red", wraplength=430).pack(pady=10)

            form_frame = ttk.Frame(dialog)
            form_frame.pack(fill=tk.X, padx=20, pady=5)

            ttk.Label(form_frame, text="API Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
            ent_api = ttk.Entry(form_frame, width=35)
            ent_api.insert(0, self.settings.api_key)
            ent_api.grid(row=0, column=1, pady=5)

            ttk.Label(form_frame, text="Base URL:").grid(row=1, column=0, sticky=tk.W, pady=5)
            ent_base = ttk.Entry(form_frame, width=35)
            ent_base.insert(0, self.settings.base_url)
            ent_base.grid(row=1, column=1, pady=5)

            def on_save():
                self.settings.api_key = ent_api.get().strip()
                self.settings.base_url = ent_base.get().strip()
                self.settings.save()
                self.ai_service.settings = self.settings
                result[0] = True
                dialog.destroy()
                event.set()

            def on_cancel():
                result[0] = False
                dialog.destroy()
                event.set()

            btn_frame = ttk.Frame(dialog)
            btn_frame.pack(pady=10)
            ttk.Button(btn_frame, text="💾 保存并继续重试", command=on_save).pack(side=tk.LEFT, padx=10)
            ttk.Button(btn_frame, text="⏭️ 取消并降级跳过", command=on_cancel).pack(side=tk.LEFT, padx=10)
            dialog.protocol("WM_DELETE_WINDOW", on_cancel)

        self.after(0, show_dialog)
        event.wait()
        return result[0]

    # ------------------------------------------
    # Import View
    # ------------------------------------------
    def build_import_tab(self):
        top_frame = ttk.Frame(self.tab_import)
        top_frame.pack(fill=tk.X, pady=5, padx=5)

        ttk.Button(top_frame, text="📄 导入 PDF", command=lambda: self.on_import_file("pdf")).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_frame, text="📝 导入 Word", command=lambda: self.on_import_file("word")).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_frame, text="🖼️ 导入单张图片", command=lambda: self.on_import_file("image")).pack(side=tk.LEFT, padx=2)

        self.lbl_import_status = ttk.Label(top_frame, text="等待导入...", foreground="blue")
        self.lbl_import_status.pack(side=tk.LEFT, padx=10)

        paned = ttk.PanedWindow(self.tab_import, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        self.tree_staging = ttk.Treeview(left_frame, columns=("id", "content", "tags"), show="headings", selectmode="extended")
        self.tree_staging.heading("id", text="序号")
        self.tree_staging.column("id", width=40)
        self.tree_staging.heading("content", text="识别内容预览")
        self.tree_staging.heading("tags", text="标签")
        self.tree_staging.column("tags", width=100)
        self.tree_staging.pack(fill=tk.BOTH, expand=True)
        self.tree_staging.bind('<<TreeviewSelect>>', self.on_staging_select)

        ttk.Button(left_frame, text="❌ 彻底删除选中题目", command=self.delete_staging_item).pack(fill=tk.X, pady=2)

        # New AI Actions
        ai_frame = ttk.LabelFrame(left_frame, text="AI 题目整理 (二次处理)")
        ai_frame.pack(fill=tk.X, pady=5)
        ttk.Button(ai_frame, text="🔗 合并选中项", command=self.merge_staging_items).pack(fill=tk.X, pady=2)
        ttk.Button(ai_frame, text="✂️ 拆分当前项", command=self.split_staging_item).pack(fill=tk.X, pady=2)
        ttk.Button(ai_frame, text="✨ 重新排版(修正格式)", command=self.format_staging_item).pack(fill=tk.X, pady=2)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        ttk.Label(right_frame, text="AI 优化后文字内容 (可在此纠错):").pack(anchor=tk.W)
        self.txt_stg_content = tk.Text(right_frame, height=8, font=("Consolas", 10))
        self.txt_stg_content.pack(fill=tk.X, pady=2)

        ttk.Label(right_frame, text="AI 打标 (逗号分隔):").pack(anchor=tk.W)
        self.ent_stg_tags = ttk.Entry(right_frame)
        self.ent_stg_tags.pack(fill=tk.X, pady=2)
        ttk.Button(right_frame, text="💾 更新当前题目", command=self.update_stg_item).pack(anchor=tk.E, pady=5)

        vec_frame = ttk.Frame(right_frame)
        vec_frame.pack(fill=tk.X, pady=2)
        ttk.Label(vec_frame, text="向量化预览:").pack(side=tk.LEFT)
        self.lbl_vector_info = ttk.Label(vec_frame, text="未生成向量")
        self.lbl_vector_info.pack(side=tk.LEFT, padx=5)
        ttk.Button(vec_frame, text="🔄 生成/更新向量", command=self.update_staging_vector).pack(side=tk.RIGHT)


        self.lbl_stg_diagram = ttk.Label(right_frame, text="图样显示区", background="#e0e0e0", anchor=tk.CENTER)
        self.lbl_stg_diagram.pack(fill=tk.BOTH, expand=True, pady=5)

        diag_btn_frame = ttk.Frame(right_frame)
        diag_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(diag_btn_frame, text="⬆️ 将图样移至上一题", command=self.move_diagram_up).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(diag_btn_frame, text="⬇️ 将图样移至下一题", command=self.move_diagram_down).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        ttk.Button(right_frame, text="👁️ 查看完整版面分析图 (Pix2Text/Surya)", command=self.show_page_layout_view).pack(anchor=tk.E, pady=2)

        bottom_frame = ttk.Frame(self.tab_import)
        bottom_frame.pack(fill=tk.X, pady=5, padx=5)

        ttk.Label(bottom_frame, text="为整个试卷批量追加标签:").pack(side=tk.LEFT)
        self.ent_batch_tag = ttk.Entry(bottom_frame, width=20)
        self.ent_batch_tag.pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="应用批量标签", command=self.apply_batch_tags).pack(side=tk.LEFT)

        ttk.Button(bottom_frame, text="✅ 确认暂存区无误，全部保存入库", command=self.save_staging_to_db).pack(side=tk.RIGHT)


    def move_diagram_up(self):
        sel = self.tree_staging.selection()
        if not sel: return
        idx = int(sel[0])
        if idx == 0:
            messagebox.showinfo("提示", "已经是第一题，无法上移。")
            return

        # move diagram and image_b64
        self.staging_questions[idx - 1]["diagram"] = self.staging_questions[idx].get("diagram")
        self.staging_questions[idx - 1]["image_b64"] = self.staging_questions[idx].get("image_b64")
        self.staging_questions[idx]["diagram"] = None
        self.staging_questions[idx]["image_b64"] = ""

        self.refresh_staging_tree()
        self.tree_staging.selection_set(str(idx - 1))
        self.on_staging_select(None)
        self.update_status(f"图样已移动至第 {idx} 题")

    def move_diagram_down(self):
        sel = self.tree_staging.selection()
        if not sel: return
        idx = int(sel[0])
        if idx == len(self.staging_questions) - 1:
            messagebox.showinfo("提示", "已经是最后一题，无法下移。")
            return

        self.staging_questions[idx + 1]["diagram"] = self.staging_questions[idx].get("diagram")
        self.staging_questions[idx + 1]["image_b64"] = self.staging_questions[idx].get("image_b64")
        self.staging_questions[idx]["diagram"] = None
        self.staging_questions[idx]["image_b64"] = ""

        self.refresh_staging_tree()
        self.tree_staging.selection_set(str(idx + 1))
        self.on_staging_select(None)
        self.update_status(f"图样已移动至第 {idx + 2} 题")

    def show_page_layout_view(self):
        sel = self.tree_staging.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在左侧选择一道题目。")
            return

        q = self.staging_questions[int(sel[0])]
        page_b64 = q.get("page_annotated_b64")

        if not page_b64:
            messagebox.showinfo("提示", "当前题目没有对应的完整版面分析图。")
            return

        try:
            img = Image.open(io.BytesIO(base64.b64decode(page_b64)))

            top = tk.Toplevel(self)
            top.title("完整版面分析预览")
            top.geometry("800x900")

            canvas = tk.Canvas(top, bg="gray")
            scroll_y = ttk.Scrollbar(top, orient="vertical", command=canvas.yview)
            scroll_x = ttk.Scrollbar(top, orient="horizontal", command=canvas.xview)

            canvas.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

            scroll_y.pack(side="right", fill="y")
            scroll_x.pack(side="bottom", fill="x")
            canvas.pack(side="left", fill="both", expand=True)

            photo = ImageTk.PhotoImage(img)
            canvas.create_image(0, 0, image=photo, anchor="nw")
            canvas.config(scrollregion=canvas.bbox("all"))

            # Keep reference
            top.photo = photo

        except Exception as e:
            messagebox.showerror("错误", f"无法加载版面图: {e}")

    def on_import_file(self, file_type):
        exts = {"pdf": [("PDF", "*.pdf")], "word": [("Word", "*.docx")], "image": [("Image", "*.png;*.jpg;*.jpeg")]}
        file_path = filedialog.askopenfilename(filetypes=exts[file_type])
        if not file_path: return
        self.staging_questions.clear()
        self.refresh_staging_tree()
        threading.Thread(target=self.run_ingestion_pipeline, args=(file_path, file_type), daemon=True).start()

    def run_ingestion_pipeline(self, file_path, file_type):
        self.update_status("正在提取文档切片...")
        pending_slices = []
        mode = self.settings.recognition_mode

        def handle_slice_ready(s):
            if mode == 1:
                item = {
                    "content": s["text"], "logic": "无 (本地OCR模式)", "tags": ["本地提取"], "diagram": s.get("diagram"), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            else:
                item = {
                    "content": s["text"], "logic": "等待 AI 处理...", "tags": ["本地提取中"], "diagram": s.get("diagram"), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            def _append_and_refresh():
                self.staging_questions.append(item)
                self.refresh_staging_tree()
            self.after(0, _append_and_refresh)

        try:
            if file_type in ["pdf", "image"]:
                # 在提取前清空 staging
                def _clear_stg():
                    self.staging_questions.clear()
                    self.refresh_staging_tree()
                self.after(0, _clear_stg)

                layout_engine_type = getattr(self.settings, 'layout_engine_type', 'DocLayout-YOLO')
                ocr_engine_type = getattr(self.settings, 'ocr_engine_type', 'Pix2Text')

                # Lazy load Surya if selected but not loaded
                if self.hardware_ok and FoundationPredictor and not getattr(self, 'surya_init_failed', False):
                    # Ensure FoundationPredictor is initialized exactly once
                    if (layout_engine_type == 'Surya' and self.surya_layout is None and LayoutPredictor) or \
                       (ocr_engine_type == 'Surya' and self.surya_ocr is None and RecognitionPredictor):
                        if self.surya_foundation is None:
                            self.update_status("正在加载 Surya 基础模型...")
                            try:
                                self.surya_foundation = FoundationPredictor()
                            except Exception as e:
                                logger.error(f"Failed to lazy load FoundationPredictor: {e}", exc_info=True)
                                self.surya_init_failed = True

                    if layout_engine_type == 'Surya' and self.surya_layout is None and LayoutPredictor and self.surya_foundation:
                        self.update_status("正在首次加载 Surya 版面引擎，请稍候...")
                        try:
                            self.surya_layout = LayoutPredictor(self.surya_foundation)
                        except Exception as e:
                            logger.error(f"Failed to lazy load Surya Layout: {e}", exc_info=True)
                            self.surya_init_failed = True                    if ocr_engine_type == 'Surya' and self.surya_ocr is None and RecognitionPredictor and self.surya_foundation:
                        self.update_status("正在首次加载 Surya OCR 与检测引擎，请稍候...")
                        try:
                            self.surya_ocr = RecognitionPredictor(self.surya_foundation)
                            if DetectionPredictor and self.surya_detection is None:
                                self.surya_detection = DetectionPredictor()
                        except Exception as e:
                            logger.error(f"Failed to lazy load Surya OCR/Detection: {e}", exc_info=True)
                            self.surya_init_failed = True

                # Lazy load DocLayout-YOLO if selected but not loaded
                if layout_engine_type == 'DocLayout-YOLO' and self.doclayout_yolo is None:
                    self.update_status("正在首次加载 DocLayout-YOLO 引擎，请稍候...")
                    try:
                        self.doclayout_yolo = DocLayoutYOLO()
                    except Exception as e:
                        logger.error(f"Failed to lazy load DocLayout-YOLO: {e}", exc_info=True)
                        self.after(0, lambda err=e: messagebox.showerror("Engine Error", f"无法加载 DocLayout-YOLO 引擎:\n{err}"))
                        return

                use_surya_layout = self.hardware_ok and layout_engine_type == 'Surya' and self.surya_layout is not None
                use_surya_ocr = self.hardware_ok and ocr_engine_type == 'Surya' and self.surya_ocr is not None

                layout_predictor_to_use = self.surya_layout if use_surya_layout else self.doclayout_yolo
                ocr_engine_to_use = self.surya_ocr if use_surya_ocr else self.ocr_engine
                ocr_type_str = 'Surya' if use_surya_ocr else 'Pix2Text'

                if layout_predictor_to_use is None:
                    self.after(0, lambda: messagebox.showerror("Engine Error", "无可用版面分析引擎。请检查模型配置。")); return
                if ocr_engine_to_use is None:
                    self.after(0, lambda: messagebox.showerror("Engine Error", "无可用 OCR 引擎。请检查环境依赖。")); return                pending_slices = DocumentService.process_doc_with_layout(
                    file_path, file_type,
                    layout_predictor_to_use,
                    ocr_engine_to_use,
                    ocr_type_str,
                    self.update_status, handle_slice_ready,
                    det_predictor=self.surya_detection if use_surya_ocr else None
                )
            elif file_type == "word":
                def _clear_word():
                    self.staging_questions.clear()
                    self.refresh_staging_tree()
                self.after(0, _clear_word)
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

        # 模式 2 & 3 的核心处理循环
        # 注意: 前面已经将 pending_slices 放入 staging_questions (作为草稿)，AI 处理后我们将清空它们并放入 AI 结果
        def _clear_pre_ai():
            self.staging_questions.clear()
            self.refresh_staging_tree()
        self.after(0, _clear_pre_ai)

        use_vision = (mode == 3 and file_type != "word")
        batch_size = self.settings.prm_batch_size if self.settings.use_prm_optimization else 1

        current_idx = 0
        pending_fragment = ""

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

            desc = "多模态视觉版面合并中" if use_vision else "纯文本版面合并中"
            self.update_status(f"AI {desc}: 窗口 {current_idx} ~ {end_idx-1} / {len(pending_slices)}...")

            try:
                ai_res = self.ai_service.process_slices_with_context(
                    slices_to_send,
                    use_vision=use_vision,
                    pending_fragment=pending_fragment,
                    is_last_batch=is_last_batch
                )

                questions = ai_res.get("Questions", [])
                pending_fragment = ai_res.get("PendingFragment", "")

                next_index = ai_res.get("NextIndex", current_idx + 1)
                if next_index <= current_idx:
                    next_index = current_idx + 1

                for q in questions:
                    status = q.get("Status", "Complete")
                    if status == "NotQuestion":
                        continue

                    source_indices = q.get("SourceSliceIndices", [])
                    diagram = None
                    image_b64 = ""
                    page_annotated_b64 = ""

                    for idx in source_indices:
                        if 0 <= idx < len(pending_slices):
                            if not image_b64 and pending_slices[idx].get("image_b64"):
                                image_b64 = pending_slices[idx]["image_b64"]
                            if not diagram and pending_slices[idx].get("diagram"):
                                diagram = pending_slices[idx]["diagram"]
                            if not page_annotated_b64 and pending_slices[idx].get("page_annotated_b64"):
                                page_annotated_b64 = pending_slices[idx].get("page_annotated_b64")

                        if diagram and image_b64 and page_annotated_b64:
                            break

                    item = {
                        "content": q.get("Content", ""),
                        "logic": q.get("LogicDescriptor", ""),
                        "tags": q.get("Tags", []),
                        "diagram": diagram,
                        "image_b64": image_b64,
                        "page_annotated_b64": page_annotated_b64
                    }
                    def _safe_append(i=item):
                        self.staging_questions.append(i)
                    self.after(0, _safe_append)

                self.after(0, self.refresh_staging_tree)
                current_idx = next_index

            except Exception as e:
                print(f"AI 处理异常: {e}")
                if self.ask_api_retry_sync(str(e)):
                    continue
                else:
                    # 降级：放弃批次，保存源数据
                    fallback_end = min(current_idx + batch_size, len(pending_slices))
                    if fallback_end == current_idx: fallback_end += 1
                    for i in range(current_idx, fallback_end):
                        item = {
                            "content": pending_slices[i]["text"],
                            "logic": "API 失败，未解析",
                            "tags": ["API错误", "需人工校对"],
                            "diagram": pending_slices[i].get("diagram"),
                            "page_annotated_b64": pending_slices[i].get("page_annotated_b64")
                        }
                        def _safe_append_f(itm=item):
                            self.staging_questions.append(itm)
                        self.after(0, _safe_append_f)
                    self.after(0, self.refresh_staging_tree)
                    current_idx = fallback_end

        # 如果结束时还有没处理完的 fragment，尝试把它作为一个单独题目保存
        if pending_fragment and pending_fragment.strip():
            item = {
                "content": pending_fragment,
                "logic": "跨页未完结残段 (合并结束仍遗留)",
                "tags": ["需人工校对"],
                "diagram": None,
                "image_b64": ""
            }
            def _safe_append_rem(itm=item):
                self.staging_questions.append(itm)
            self.after(0, _safe_append_rem)
            self.after(0, self.refresh_staging_tree)

        self.update_status("✅ 文件全部处理并关联合并完毕！")
    def update_status(self, text):
        self.after(0, lambda: self.lbl_import_status.config(text=text))

    def refresh_staging_tree(self):
        for i in self.tree_staging.get_children(): self.tree_staging.delete(i)
        for idx, q in enumerate(self.staging_questions):
            preview = q["content"][:40].replace('\n', ' ')
            self.tree_staging.insert("", tk.END, iid=str(idx), values=(idx+1, preview, ",".join(q["tags"])))

    def on_staging_select(self, event):
        sel = self.tree_staging.selection()
        if not sel: return

        # We only want to handle the first selected item for preview if multiple are selected
        q = self.staging_questions[int(sel[0])]
        self.txt_stg_content.delete("1.0", tk.END)
        self.txt_stg_content.insert(tk.END, q["content"])
        self.ent_stg_tags.delete(0, tk.END)
        self.ent_stg_tags.insert(0, ",".join(q.get("tags", [])))

        # Determine what to display (diagram if present, else layout image)
        display_img_b64 = q.get("diagram")
        if not display_img_b64 and q.get("image_b64"):
            display_img_b64 = q.get("image_b64")

        if display_img_b64:
            try:
                img = Image.open(io.BytesIO(base64.b64decode(display_img_b64))).copy()
                img.thumbnail((400, 300))
                photo = ImageTk.PhotoImage(img)
                self.lbl_stg_diagram.config(image=photo, text="")
                self.lbl_stg_diagram.image = photo
            except Exception as e:
                self.lbl_stg_diagram.config(image='', text=f"图片加载失败: {e}")
        else:
            self.lbl_stg_diagram.config(image='', text="无图样附图或切片原图")

        vec = q.get("embedding", [])
        if vec:
            preview = str([round(v, 3) for v in vec[:3]]) + "..."
            self.lbl_vector_info.config(text=f"已生成 (维度: {len(vec)}) {preview}")
        else:
            self.lbl_vector_info.config(text="未生成向量")

    def update_staging_vector(self):
        sel = self.tree_staging.selection()
        if not sel: return
        self.lbl_vector_info.config(text=f"正在为 {len(sel)} 题生成向量...")
        self.update()

        def task():
            success_count = 0
            fail_count = 0
            last_vec = None

            for s in sel:
                idx = int(s)
                q = self.staging_questions[idx]
                text_to_embed = q.get("logic", "") or q.get("content", "")
                if not text_to_embed:
                    fail_count += 1
                    continue

                vec = self.ai_service.get_embedding(text_to_embed)
                if vec:
                    q["embedding"] = vec
                    success_count += 1
                    if idx == int(sel[0]):  # Keep preview of the first selected item
                        last_vec = vec
                else:
                    fail_count += 1

            def update_ui():
                if success_count > 0:
                    preview = str([round(v, 3) for v in last_vec[:3]]) + "..." if last_vec else ""
                    self.lbl_vector_info.config(text=f"成功: {success_count}, 失败: {fail_count}. {preview}")
                else:
                    self.lbl_vector_info.config(text="生成失败")

            self.after(0, update_ui)

        threading.Thread(target=task, daemon=True).start()


    def merge_staging_items(self):
        sel = self.tree_staging.selection()
        if len(sel) < 2:
            messagebox.showinfo("提示", "请按住 Ctrl/Cmd 选择至少两道相邻的题目进行合并。")
            return

        indices = sorted([int(s) for s in sel])
        texts_to_merge = [self.staging_questions[idx]["content"] for idx in indices]

        self.update_status(f"🚀 AI 正在合并 {len(indices)} 道题目...")
        import threading

        def task():
            merged = self.ai_service.ai_merge_questions(texts_to_merge)
            if not merged:
                self.after(0, lambda: messagebox.showerror("错误", "合并失败，AI 未返回有效内容。"))
                self.after(0, lambda: self.update_status("合并失败"))
                return

            def update_ui():
                first_idx = indices[0]
                self.staging_questions[first_idx]["content"] = merged
                # Merge tags as well
                merged_tags = set(self.staging_questions[first_idx].get("tags", []))
                for idx in indices[1:]:
                    merged_tags.update(self.staging_questions[idx].get("tags", []))
                self.staging_questions[first_idx]["tags"] = list(merged_tags)

                for idx in reversed(indices[1:]):
                    self.staging_questions.pop(idx)

                self.refresh_staging_tree()
                self.update_status("✅ AI 合并完成")
                # Attempt to select the merged item safely
                try:
                    self.tree_staging.selection_set(str(first_idx))
                    self.on_staging_select(None)
                except Exception:
                    pass

            self.after(0, update_ui)

        def run_merge_task():
            try:
                task()
            finally:
                self.after(0, lambda: setattr(self, "_merge_inflight", False))

        if getattr(self, "_merge_inflight", False):
            messagebox.showinfo("提示", "AI 合并正在进行，请稍候。")
            return
        self._merge_inflight = True
        threading.Thread(target=run_merge_task, daemon=True).start()

    def split_staging_item(self):
        sel = self.tree_staging.selection()
        if len(sel) != 1:
            messagebox.showinfo("提示", "请选择且仅选择一道需要拆分的复杂题目。")
            return

        idx = int(sel[0])
        q = self.staging_questions[idx]
        text_to_split = q["content"]

        self.update_status("🚀 AI 正在尝试拆分题目...")
        import threading

        def task():
            splits = self.ai_service.ai_split_question(text_to_split)
            if not splits or len(splits) <= 1:
                self.after(0, lambda: messagebox.showerror("提示", "拆分失败或未发现可拆分的子题。"))
                self.after(0, lambda: self.update_status("拆分无效"))
                return

            def update_ui():
                self.staging_questions[idx]["content"] = splits[0]

                for i, split_text in enumerate(splits[1:]):
                    new_q = self.staging_questions[idx].copy() # Ensure deepcopy or dict copy
                    new_q["content"] = split_text
                    # Avoid sharing the exact same list of tags in memory
                    new_q["tags"] = list(new_q.get("tags", []))
                    self.staging_questions.insert(idx + 1 + i, new_q)

                self.refresh_staging_tree()
                self.update_status(f"✅ AI 成功拆分出 {len(splits)} 道题")

            self.after(0, update_ui)

        def run_split_task():
            try:
                task()
            finally:
                self.after(0, lambda: setattr(self, "_split_inflight", False))

        if getattr(self, "_split_inflight", False):
            messagebox.showinfo("提示", "AI 拆分正在进行，请稍候。")
            return
        self._split_inflight = True
        threading.Thread(target=run_split_task, daemon=True).start()

    def format_staging_item(self):
        sel = self.tree_staging.selection()
        if not sel:
            messagebox.showinfo("提示", "请选择需要重新排版的题目。")
            return

        idx = int(sel[0])
        q = self.staging_questions[idx]
        text_to_format = self.txt_stg_content.get("1.0", tk.END).strip()
        if not text_to_format: return

        self.update_status("🚀 AI 正在重新排版格式化题目...")
        import threading

        def task():
            formatted = self.ai_service.ai_format_question(text_to_format)
            if not formatted:
                self.after(0, lambda: messagebox.showerror("错误", "格式化失败。"))
                self.after(0, lambda: self.update_status("格式化失败"))
                return

            def update_ui():
                self.staging_questions[idx]["content"] = formatted
                self.txt_stg_content.delete("1.0", tk.END)
                self.txt_stg_content.insert("1.0", formatted)
                self.refresh_staging_tree()
                self.update_status("✅ 重新排版完成")

            self.after(0, update_ui)

        def run_format_task():
            try:
                task()
            finally:
                self.after(0, lambda: setattr(self, "_format_inflight", False))

        if getattr(self, "_format_inflight", False):
            messagebox.showinfo("提示", "AI 格式化正在进行，请稍候。")
            return
        self._format_inflight = True
        threading.Thread(target=run_format_task, daemon=True).start()

    def update_stg_item(self):
        sel = self.tree_staging.selection()
        if not sel: return
        idx = int(sel[0])
        self.staging_questions[idx]["content"] = self.txt_stg_content.get("1.0", tk.END).strip()
        self.staging_questions[idx]["tags"] = [t.strip() for t in self.ent_stg_tags.get().split(",") if t.strip()]
        self.refresh_staging_tree()

    def delete_staging_item(self):
        sel = self.tree_staging.selection()
        if not sel: return
        if messagebox.askyesno("警告", f"确定要彻底删除选中的 {len(sel)} 道题目吗？"):
            # Delete in reverse order to keep indices valid
            indices = sorted([int(s) for s in sel], reverse=True)
            for idx in indices:
                item = self.staging_questions.pop(idx)
                # Cleanup heavy images
                item.pop('diagram', None)
                item.pop('image_b64', None)
                item.pop('page_annotated_b64', None)
            self.refresh_staging_tree()
            self.txt_stg_content.delete("1.0", tk.END)
            self.ent_stg_tags.delete(0, tk.END)
            if hasattr(self, 'lbl_vector_info'):
                self.lbl_vector_info.config(text="未生成向量")
            self.lbl_stg_diagram.config(image='', text="图样显示区")
            if hasattr(self.lbl_stg_diagram, 'image'):
                del self.lbl_stg_diagram.image
            gc.collect()

    def apply_batch_tags(self):
        batch_tag = self.ent_batch_tag.get().strip()
        if not batch_tag: return
        for q in self.staging_questions:
            if batch_tag not in q["tags"]:
                q["tags"].append(batch_tag)
        self.refresh_staging_tree()

    def save_staging_to_db(self):
        if not self.staging_questions: return
        self.update_status("正在检查 LaTeX 编译并准备入库...")
        logger.info("Starting LaTeX check and DB insertion for staged questions...")

        # We need to run this in background thread because compilation takes time
        import threading

        def task():
            from utils import logger
            import tempfile, os, subprocess
            from db_adapter import LanceDBAdapter

            failed_indices = []
            successful_questions = []

            # 1. LaTeX check & Auto Fix
            for idx, q in enumerate(self.staging_questions):
                self.after(0, lambda i=idx: self.update_status(f"正在编译检查第 {i+1}/{len(self.staging_questions)} 题..."))

                content_text = q["content"]

                # Create a minimal tex document to test compilation
                tex_code = f'''\\documentclass{{article}}\n\\usepackage{{ctex}}\n\\usepackage{{amsmath}}\n\\usepackage{{amssymb}}\n\\begin{{document}}\n{content_text}\n\\end{{document}}'''

                def test_compile(code):
                    with tempfile.TemporaryDirectory() as td:
                        tex_file = os.path.join(td, "test.tex")
                        with open(tex_file, "w", encoding="utf-8") as f_tex:
                            f_tex.write(code)
                        try:
                            res = subprocess.run(["xelatex", "-interaction=nonstopmode", "--no-shell-escape", "test.tex"],
                                                 cwd=td, capture_output=True, text=True, timeout=15)
                            if res.returncode == 0:
                                return True, ""
                            else:
                                return False, res.stdout
                        except Exception as e:
                            return False, str(e)

                success, err_msg = test_compile(tex_code)

                if not success:
                    self.after(0, lambda i=idx: self.update_status(f"第 {i+1} 题编译失败，AI 正在尝试修复..."))
                    fixed_content = self.ai_service.ai_fix_latex(content_text, err_msg)
                    if fixed_content:
                        # Test again
                        new_tex_code = f'''\\documentclass{{article}}\n\\usepackage{{ctex}}\n\\usepackage{{amsmath}}\n\\usepackage{{amssymb}}\n\\begin{{document}}\n{fixed_content}\n\\end{{document}}'''
                        success2, err_msg2 = test_compile(new_tex_code)
                        if success2:
                            q["content"] = fixed_content # accept fix
                            successful_questions.append((idx, q))
                        else:
                            failed_indices.append(idx)
                    else:
                        failed_indices.append(idx)
                else:
                    successful_questions.append((idx, q))

            # 2. Save successful questions to DB
            self.after(0, lambda: self.update_status("编译检查完成，正在生成向量并保存..."))
            try:
                adapter = LanceDBAdapter()
                for _, q in successful_questions:
                    vec = q.get("embedding") or self.ai_service.get_embedding(q["logic"] or q["content"])
                    q_id = adapter.execute_insert_question(q["content"], q["logic"], vec, q["diagram"])
                    for t in q["tags"]:
                        if not t: continue
                        t_id = adapter.execute_insert_tag(t)
                        adapter.execute_insert_question_tag(q_id, t_id)
            except Exception as e:
                logger.error(f"DB Insert Error: {e}", exc_info=True)
                self.after(0, lambda err=e: messagebox.showerror("错误", f"数据库保存失败: {err}"))
                return

            # 3. Update UI
            def update_ui():
                import gc
                if not failed_indices:
                    for q in self.staging_questions:
                        q.pop('diagram', None)
                        q.pop('image_b64', None)
                        q.pop('page_annotated_b64', None)
                    self.staging_questions.clear()
                    self.txt_stg_content.delete("1.0", tk.END)
                    self.ent_stg_tags.delete(0, tk.END)
                    self.lbl_stg_diagram.config(image='', text="图样显示区")
                    if hasattr(self.lbl_stg_diagram, 'image'):
                        del self.lbl_stg_diagram.image
                    gc.collect()
                    self.refresh_staging_tree()
                    self.update_status("入库成功！您可以前往题库查看。")
                    logger.info("All staged questions saved to DB successfully.")
                    messagebox.showinfo("成功", "已全部保存至题库！")
                else:
                    # Remove successful ones from staging, keep failed ones
                    for idx, q in reversed(successful_questions):
                        q.pop('diagram', None)
                        q.pop('image_b64', None)
                        q.pop('page_annotated_b64', None)
                        self.staging_questions.pop(idx)

                    self.refresh_staging_tree()
                    self.update_status(f"部分入库完成。保留了 {len(failed_indices)} 道编译失败的题目。")
                    messagebox.showwarning("部分完成", f"已入库成功 {len(successful_questions)} 题。有 {len(failed_indices)} 题由于 LaTeX 编译错误（AI 修复仍失败）未能入库，请手动检查列表中的剩余项。")

            self.after(0, update_ui)

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------
    # Manual Input View
    # ------------------------------------------
    def build_manual_tab(self):
        frame = ttk.Frame(self.tab_manual, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="题干文字内容 (支持直接粘贴纯文本):").pack(anchor=tk.W)
        self.txt_manual = tk.Text(frame, height=10, font=("Consolas", 11))
        self.txt_manual.pack(fill=tk.X, pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="✨ 呼叫 AI 自动排版纠错并生成标签", command=self.on_manual_ai).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="✨ 重新排版(修正格式)", command=self.on_manual_reformat).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🏷️ 重新生成标签", command=self.on_manual_retag).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🔄 预览向量化", command=self.on_manual_preview_vector).pack(side=tk.LEFT, padx=5)

        self.lbl_manual_status = ttk.Label(btn_frame, text="", foreground="blue")
        self.lbl_manual_status.pack(side=tk.LEFT, padx=10)

        # Vectorization preview during AI generation
        self.lbl_manual_vector_status = ttk.Label(btn_frame, text="未生成向量", foreground="gray")
        self.lbl_manual_vector_status.pack(side=tk.RIGHT, padx=10)

        ttk.Label(frame, text="知识点标签 (逗号分隔):").pack(anchor=tk.W, pady=(10,0))
        self.ent_manual_tags = ttk.Entry(frame)
        self.ent_manual_tags.pack(fill=tk.X, pady=5)

        # Companion Diagram Selection
        diagram_frame = ttk.Frame(frame)
        diagram_frame.pack(fill=tk.X, pady=5)
        ttk.Button(diagram_frame, text="🖼️ 选择配套图样", command=self.on_select_manual_diagram).pack(side=tk.LEFT)
        self.lbl_manual_diagram_status = ttk.Label(diagram_frame, text="未选择图片", foreground="gray")
        self.lbl_manual_diagram_status.pack(side=tk.LEFT, padx=10)

        self.manual_diagram_b64 = None
        self.manual_vector = None

        ttk.Button(frame, text="💾 保存并直接入库", command=self.save_manual).pack(anchor=tk.E, pady=20)

    def on_select_manual_diagram(self):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp")])
        if not file_path:
            return

        try:
            # Normalize to PNG
            img = Image.open(file_path)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            self.manual_diagram_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

            filename = os.path.basename(file_path)
            self.lbl_manual_diagram_status.config(text=f"已选择: {filename}", foreground="green")
        except Exception as e:
            self.lbl_manual_diagram_status.config(text=f"图片读取失败: {e}", foreground="red")
            self.manual_diagram_b64 = None


    def on_manual_reformat(self):
        text = self.txt_manual.get("1.0", tk.END).strip()
        if not text: return
        self.lbl_manual_status.config(text="正在重新排版...")
        def task():
            formatted = self.ai_service.ai_format_question(text)
            if formatted:
                self.after(0, lambda: self.txt_manual.delete("1.0", tk.END))
                self.after(0, lambda: self.txt_manual.insert(tk.END, formatted))
                self.after(0, lambda: self.lbl_manual_status.config(text="重新排版完成"))
            else:
                self.after(0, lambda: self.lbl_manual_status.config(text="排版失败", foreground="red"))
        threading.Thread(target=task, daemon=True).start()

    def on_manual_retag(self):
        text = self.txt_manual.get("1.0", tk.END).strip()
        if not text: return
        self.lbl_manual_status.config(text="正在生成标签...")
        def task():
            res = self.ai_service.process_text_with_correction(text)
            tags = res.get("Tags", [])
            if tags:
                self.after(0, lambda: self.ent_manual_tags.delete(0, tk.END))
                self.after(0, lambda: self.ent_manual_tags.insert(0, ",".join(tags)))
                self.after(0, lambda: self.lbl_manual_status.config(text="标签生成完成"))
            else:
                self.after(0, lambda: self.lbl_manual_status.config(text="生成标签失败", foreground="red"))
        threading.Thread(target=task, daemon=True).start()

    def on_manual_preview_vector(self):
        text = self.txt_manual.get("1.0", tk.END).strip()
        if not text: return
        self.lbl_manual_vector_status.config(text="正在生成...", foreground="blue")
        def task():
            vec = self.ai_service.get_embedding(text)
            if vec:
                self.manual_vector = vec
                self.manual_vector_text_hash = hash(text)
                preview = str([round(v, 3) for v in vec[:3]]) + "..."
                self.after(0, lambda: self.lbl_manual_vector_status.config(text=f"已生成向量 (维度: {len(vec)}) {preview}", foreground="green"))
            else:
                self.after(0, lambda: self.lbl_manual_vector_status.config(text="向量生成失败", foreground="red"))
        threading.Thread(target=task, daemon=True).start()

    def on_manual_ai(self):
        text = self.txt_manual.get("1.0", tk.END).strip()
        if not text: return
        self.lbl_manual_status.config(text="AI 分析与向量化中...")
        def task():
            while True:
                try:
                    res = self.ai_service.process_text_with_correction(text)
                    self.after(0, lambda: self.txt_manual.delete("1.0", tk.END))

                    content_result = res.get("Content", "")
                    self.after(0, lambda: self.txt_manual.insert(tk.END, content_result))
                    self.after(0, lambda: self.ent_manual_tags.delete(0, tk.END))
                    self.after(0, lambda: self.ent_manual_tags.insert(0, ",".join(res.get("Tags", []))))
                    self.after(0, lambda: self.lbl_manual_status.config(text="AI 处理完成！请核对后保存。"))

                    # Generate embedding in the background immediately
                    vector_text = content_result
                    if vector_text:
                        vec = self.ai_service.get_embedding(vector_text)
                        if vec:
                            self.manual_vector = vec
                            self.manual_vector_text_hash = hash(vector_text)
                            preview = str([round(v, 3) for v in vec[:3]]) + "..."
                            self.after(0, lambda: self.lbl_manual_vector_status.config(text=f"已生成向量 (维度: {len(vec)}) {preview}", foreground="green"))
                        else:
                            self.after(0, lambda: self.lbl_manual_vector_status.config(text="向量生成失败", foreground="red"))

                    break
                except Exception as e:
                    if self.ask_api_retry_sync(str(e)):
                        continue
                    else:
                        self.after(0, lambda: self.lbl_manual_status.config(text=f"AI 处理已取消。"))
                        break
        threading.Thread(target=task, daemon=True).start()

    def save_manual(self):
        content = self.txt_manual.get("1.0", tk.END).strip()
        if not content: return
        tags = [t.strip() for t in self.ent_manual_tags.get().split(",") if t.strip()]

        def bg_save():
            conn = None
            try:
                from db_adapter import LanceDBAdapter
                db = LanceDBAdapter()
                # Invalidate cached vector if user edited the content after AI generation
                vec = self.manual_vector
                if hasattr(self, 'manual_vector_text_hash') and self.manual_vector_text_hash != hash(content):
                    vec = None

                if not vec:
                    vec = self.ai_service.get_embedding(content)

                q_id = db.execute_insert_question(content, "", vec if vec else None, self.manual_diagram_b64)

                for t in tags:
                    t_id = db.execute_insert_tag(t)
                    db.execute_insert_question_tag(q_id, t_id)

                def on_saved():
                    self.txt_manual.delete("1.0", tk.END)
                    self.ent_manual_tags.delete(0, tk.END)
                    self.manual_diagram_b64 = None
                    self.manual_vector = None
                    if hasattr(self, 'manual_vector_text_hash'):
                        delattr(self, 'manual_vector_text_hash')
                    self.lbl_manual_diagram_status.config(text="未选择图片", foreground="gray")
                    self.lbl_manual_vector_status.config(text="未生成向量", foreground="gray")
                    self.lbl_manual_status.config(text="")
                    logger.info("Manual question saved to DB successfully.")
                    messagebox.showinfo("成功", "手工录入成功，已存入题库！")

                self.after(0, on_saved)
            except Exception as e:
                err_msg = str(e)
                def on_error():
                    self.lbl_manual_status.config(text=f"保存失败: {err_msg}", foreground="red")
                    messagebox.showerror("错误", f"保存入库时发生异常:\n{err_msg}")
                self.after(0, on_error)
            finally:
                self.after(0, lambda: setattr(self, "_manual_save_inflight", False))

        if getattr(self, "_manual_save_inflight", False):
            messagebox.showinfo("提示", "正在入库，请勿重复提交。")
            return
        self._manual_save_inflight = True
        self.lbl_manual_status.config(text="正在入库...", foreground="blue")
        threading.Thread(target=bg_save, daemon=True).start()

    # ------------------------------------------
    # Library View
    # ------------------------------------------
    def build_library_tab(self):
        top_frame = ttk.Frame(self.tab_library)
        top_frame.pack(fill=tk.X, pady=5, padx=5)
        self.ent_lib_search = ttk.Entry(top_frame, width=30)
        self.ent_lib_search.pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="🔍 搜索题库 (硬匹配)", command=self.on_hard_search).pack(side=tk.LEFT)

        main_paned = ttk.PanedWindow(self.tab_library, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=3)

        self.tree_lib = ttk.Treeview(left_frame, columns=("id", "content"), show="headings", height=8, selectmode="extended")
        self.tree_lib.heading("id", text="ID"); self.tree_lib.column("id", width=40)
        self.tree_lib.heading("content", text="题目内容")
        self.tree_lib.pack(fill=tk.BOTH, expand=True)
        self.tree_lib.bind('<<TreeviewSelect>>', self.on_lib_select)

        det_frame = ttk.LabelFrame(left_frame, text="题目详情与修改")
        det_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.txt_lib_det = tk.Text(det_frame, height=5, font=("Consolas", 10))
        self.txt_lib_det.pack(fill=tk.BOTH, expand=True, pady=2)

        action_frame = ttk.Frame(det_frame)
        action_frame.pack(fill=tk.X, pady=2)

        ttk.Label(action_frame, text="当前标签:").pack(side=tk.LEFT)
        self.ent_lib_tags = ttk.Entry(action_frame, width=30)
        self.ent_lib_tags.pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="更新标签", command=self.update_lib_tags).pack(side=tk.LEFT)

        ttk.Button(action_frame, text="🛍️ 加入题目袋", command=self.add_to_bag).pack(side=tk.LEFT, padx=10)
        ttk.Button(action_frame, text="🗑️ 彻底删除", command=self.delete_lib_question).pack(side=tk.RIGHT)

        # New diagram UI missing from previous
        self.lbl_lib_diagram = ttk.Label(det_frame, text="无图样", background="#e0e0e0", anchor=tk.CENTER)
        self.lbl_lib_diagram.pack(fill=tk.BOTH, expand=True, pady=5)

        right_frame = ttk.LabelFrame(main_paned, text="AI 软搜索助手 (MCP)")
        main_paned.add(right_frame, weight=2)

        self.txt_chat = tk.Text(right_frame, wrap=tk.WORD, font=("微软雅黑", 10), state=tk.DISABLED)
        self.txt_chat.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        chat_bot_frame = ttk.Frame(right_frame)
        chat_bot_frame.pack(fill=tk.X, pady=2)

        self.ent_chat = ttk.Entry(chat_bot_frame)
        self.ent_chat.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ent_chat.bind("<Return>", lambda e: self.on_ai_chat())
        ttk.Button(chat_bot_frame, text="发送", command=self.on_ai_chat).pack(side=tk.RIGHT)

        self.chat_history = [
            {"role": "system", "content": "你是 SmartQB 的寻题助手。你可以理解用户的寻题需求，调用 search_database 工具查询题库向量。如果用户要求将某些题加入题目袋/试卷，请调用 add_to_bag 工具。"}
        ]
        self.append_chat("🤖 助手", "您好！想找什么样的题目？(例如：帮我找两道关于导数极值的题，并加入题目袋)")

    def append_chat(self, sender, text):
        self.txt_chat.config(state=tk.NORMAL)
        self.txt_chat.insert(tk.END, f"{sender}: {text}\n\n")
        self.txt_chat.see(tk.END)
        self.txt_chat.config(state=tk.DISABLED)

    def on_ai_chat(self):
        user_text = self.ent_chat.get().strip()
        if not user_text: return

        if getattr(self, "_chat_inflight", False):
            messagebox.showinfo("提示", "助手正在处理中，请稍候再发送下一条消息。")
            return

        self._chat_inflight = True
        self.ent_chat.delete(0, tk.END)
        self.append_chat("🧑 你", user_text)

        self.chat_history.append({"role": "user", "content": user_text})

        def task():
            try:
                callbacks = {
                    "search_database": lambda query: vector_search_db(self.ai_service, query),
                    "add_to_bag": self.ai_add_to_bag
                }
                res_text, updated_history = self.ai_service.chat_with_tools(
                    self.chat_history,
                    callbacks=callbacks
                )
                self.chat_history = updated_history
                self.chat_history.append({"role": "assistant", "content": res_text})
                self.after(0, lambda: self.append_chat("🤖 助手", res_text))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda e_msg=err_msg: self.append_chat("⚠️ 系统", f"请求出错: {e_msg}"))
            finally:
                self.after(0, lambda: setattr(self, "_chat_inflight", False))

        threading.Thread(target=task, daemon=True).start()

    def on_hard_search(self):
        kw = self.ent_lib_search.get().strip()
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        rows = adapter.search_questions(kw)
        for item in self.tree_lib.get_children():
            self.tree_lib.delete(item)
        for r in rows:
            short_c = r[1][:30].replace('\n', ' ')
            self.tree_lib.insert('', 'end', values=(r[0], short_c))
    def on_lib_select(self, event):
        sel = self.tree_lib.selection()
        if not sel: return
        self.current_lib_q_id = self.tree_lib.item(sel[0])["values"][0]
        try:
            from db_adapter import LanceDBAdapter
            adapter = LanceDBAdapter()
            content_text, diagram_base64 = adapter.get_question(self.current_lib_q_id)
            self.txt_lib_det.delete("1.0", tk.END)
            self.txt_lib_det.insert(tk.END, content_text if content_text else "")

            tags_rows = adapter.get_question_tags(self.current_lib_q_id)
            self.ent_lib_tags.delete(0, tk.END)
            self.ent_lib_tags.insert(0, ",".join([r[0] for r in tags_rows]))

            if hasattr(self, 'lbl_lib_diagram'):
                if diagram_base64:
                    import io, base64
                    from PIL import Image, ImageTk
                    try:
                        img_data = base64.b64decode(diagram_base64.split(",")[-1] if "," in diagram_base64 else diagram_base64)
                        img = Image.open(io.BytesIO(img_data)).copy()
                        img.thumbnail((400, 200))
                        photo = ImageTk.PhotoImage(img)
                        self.lbl_lib_diagram.config(image=photo, text="")
                        self.lbl_lib_diagram.image = photo
                    except Exception as e:
                        self.lbl_lib_diagram.config(image='', text=f"图样加载失败: {e}")
                else:
                    self.lbl_lib_diagram.config(image='', text="无图样")

        except Exception as e:
            from utils import logger
            logger.error(f"DB Load Question Error: {e}", exc_info=True)

    def update_lib_tags(self):
        if getattr(self, 'current_lib_q_id', None) is None: return
        new_tags = [t.strip() for t in self.ent_lib_tags.get().split(',') if t.strip()]
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        adapter.clear_question_tags(self.current_lib_q_id)
        for tn in new_tags:
            tid = adapter.execute_insert_tag(tn)
            adapter.execute_insert_question_tag(self.current_lib_q_id, tid)
        messagebox.showinfo('提示', '标签更新成功！')


    def delete_lib_question(self):
        sel = self.tree_lib.selection()
        if not sel: return
        selected_ids = [self.tree_lib.item(item)["values"][0] for item in sel]
        if messagebox.askyesno("危险操作", f"确定要彻底删除选中的 {len(selected_ids)} 道题目吗？不可恢复！"):
            from db_adapter import LanceDBAdapter
            adapter = LanceDBAdapter()
            adapter.delete_questions(selected_ids)

            selected_id_set = set(selected_ids)
            self.export_bag = [q for q in self.export_bag if q["id"] not in selected_id_set]

            self.on_hard_search()
            self.txt_lib_det.delete("1.0", tk.END)
            self.ent_lib_tags.delete(0, tk.END)

            if getattr(self, 'current_lib_q_id', None) in selected_id_set:
                self.current_lib_q_id = None

            messagebox.showinfo("成功", "选中题目已彻底删除！")

    def add_to_bag(self):
        if not hasattr(self, 'current_lib_q_id'): return
        if any(item['id'] == self.current_lib_q_id for item in self.export_bag):
            messagebox.showinfo("提示", "该题已在题目袋中。")
            return
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        content, diagram = adapter.get_question(self.current_lib_q_id)
        if content:
            self.export_bag.append({"id": self.current_lib_q_id, "content": content, "diagram": diagram})
            messagebox.showinfo("成功", "已加入题目袋！")

    def ai_add_to_bag(self, question_ids):
        added = 0
        from db_adapter import LanceDBAdapter
        adapter = LanceDBAdapter()
        for q_id in question_ids:
            if any(item['id'] == q_id for item in self.export_bag): continue
            content, diagram = adapter.get_question(q_id)
            if content:
                self.export_bag.append({"id": q_id, "content": content, "diagram": diagram})
                added += 1
        self.after(0, self.refresh_bag_ui)
        return {"status": "success", "message": f"成功加入了 {added} 道题目到题目袋"}

    # ------------------------------------------
    # Export View
    # ------------------------------------------
    def build_export_tab(self):
        top_frame = ttk.Frame(self.tab_export)
        top_frame.pack(fill=tk.X, pady=5, padx=10)
        ttk.Label(top_frame, text="组卷题目袋 (选中题目可上下移动排序):", font=("", 12, "bold")).pack(side=tk.LEFT)

        middle_frame = ttk.Frame(self.tab_export)
        middle_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        self.listbox_bag = tk.Listbox(middle_frame, font=("微软雅黑", 10))
        self.listbox_bag.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(middle_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)

        ttk.Button(btn_frame, text="⬆️ 上移", command=self.bag_move_up).pack(pady=5)
        ttk.Button(btn_frame, text="⬇️ 下移", command=self.bag_move_down).pack(pady=5)
        ttk.Button(btn_frame, text="❌ 移除", command=self.bag_remove).pack(pady=20)

        bottom_frame = ttk.Frame(self.tab_export)
        bottom_frame.pack(fill=tk.X, pady=10, padx=10)

        self.lbl_export_status = ttk.Label(bottom_frame, text="", foreground="green")
        self.lbl_export_status.pack(side=tk.LEFT, padx=10)
        ttk.Button(bottom_frame, text="🖨️ 导出试卷并自动编译 PDF", command=self.export_paper).pack(side=tk.RIGHT)

    def refresh_bag_ui(self):
        if hasattr(self, 'listbox_bag'):
            self.listbox_bag.delete(0, tk.END)
            for idx, item in enumerate(self.export_bag):
                preview = item["content"][:40].replace('\n', '')
                has_img = "[含图]" if item["diagram"] else ""
                self.listbox_bag.insert(tk.END, f"{idx+1}. {has_img} {preview}...")

    def bag_move_up(self):
        sel = self.listbox_bag.curselection()
        if not sel: return
        idx = sel[0]
        if idx > 0:
            self.export_bag.insert(idx - 1, self.export_bag.pop(idx))
            self.refresh_bag_ui()
            self.listbox_bag.select_set(idx - 1)

    def bag_move_down(self):
        sel = self.listbox_bag.curselection()
        if not sel: return
        idx = sel[0]
        if idx < len(self.export_bag) - 1:
            self.export_bag.insert(idx + 1, self.export_bag.pop(idx))
            self.refresh_bag_ui()
            self.listbox_bag.select_set(idx + 1)

    def bag_remove(self):
        sel = self.listbox_bag.curselection()
        if not sel: return
        idx = sel[0]
        self.export_bag.pop(idx)
        self.refresh_bag_ui()

    def export_paper(self):
        if not self.export_bag:
            messagebox.showwarning("提示", "题目袋为空！")
            return

        file_path = filedialog.asksaveasfilename(
            title="选择试卷保存位置",
            initialfile="SmartQB_Paper",
            filetypes=[("PDF 输出目标", "*.*")]
        )
        if not file_path:
            return

        base_path, _ = os.path.splitext(file_path)
        export_dir = os.path.dirname(base_path)
        base_name = os.path.basename(base_path)

        export_tex_path = base_path + ".tex"
        img_dir_name = base_name + "_Images"
        img_dir = os.path.join(export_dir, img_dir_name)
        os.makedirs(img_dir, exist_ok=True)

        tex = [
            r"\documentclass[11pt, a4paper]{ctexart}",
            r"\usepackage{amsmath, amssymb, amsfonts}",
            r"\usepackage{graphicx}",
            r"\usepackage{geometry}",
            r"\usepackage{listings}",
            r"\geometry{left=2cm, right=2cm, top=2.5cm, bottom=2.5cm}",
            r"\begin{document}",
            r"\begin{center}",
            r"\Large\textbf{SmartQB 导出试卷}",
            r"\end{center}",
            r"\vspace{1em}",
            r"\begin{enumerate}"
        ]

        for q in self.export_bag:
            # Clean up dangerous newlines in latex around environments
            tex_content = q["content"].replace("\n", " \\newline ")
            tex_content = re.sub(r"\\newline\s*\\begin\{center\}", r"\\begin{center}", tex_content)
            tex_content = re.sub(r"\\newline\s*\\end\{center\}", r"\\end{center}", tex_content)
            tex_content = re.sub(r"\\end\{center\}\s*\\newline", r"\\end{center}", tex_content)
            tex_content = re.sub(r"\\newline\s*\\includegraphics", r"\\includegraphics", tex_content)
            tex.append(r"\item " + tex_content)

            if q.get("diagram"):
                img_data = base64.b64decode(q["diagram"])
                img_filename = f"diagram_{q['id']}.png"
                img_filepath = os.path.join(img_dir, img_filename)
                with open(img_filepath, "wb") as f:
                    f.write(img_data)

                rel_img_path = f"{img_dir_name}/{img_filename}".replace("\\", "/")
                tex.append(r"\begin{center}")
                tex.append(rf"\includegraphics[width=0.6\textwidth]{{{rel_img_path}}}")
                tex.append(r"\end{center}")

            tex.append(r"\vspace{0.5em}")

        tex.append(r"\end{enumerate}")
        tex.append(r"\end{document}")

        with open(export_tex_path, "w", encoding="utf-8") as f:
            f.write("\n".join(tex))

        self.lbl_export_status.config(text="⏳ 正在后台调用 xelatex 编译 PDF，请稍候...", foreground="blue")
        self.update()

        def compile_pdf():
            pdf_success = False
            error_msg = ""
            try:
                result = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "--no-shell-escape", f"-output-directory={export_dir}", export_tex_path],
                    cwd=export_dir,
                    capture_output=True,
                    check=False
                )
                if result.returncode != 0:
                    try:
                        out_str = result.stdout.decode('utf-8', errors='replace')
                    except Exception:
                        out_str = str(result.stdout)
                    error_msg = f"LaTeX 编译错误，部分符号未被 AI 成功转义导致中断。\n日志片段: {out_str[-500:]}"
                    raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
                pdf_success = True
            except FileNotFoundError:
                error_msg = "未检测到本地 LaTeX 编译器 (未安装 TeX Live / MiKTeX)。"
            except subprocess.CalledProcessError as e:
                pass # Handled above
            except Exception as e:
                error_msg = str(e)

            def on_finish():
                self.lbl_export_status.config(text="")
                if pdf_success:
                    messagebox.showinfo("✅ 自动编译成功", f"文件已保存: {base_path}.pdf")
                else:
                    messagebox.showwarning("⚠️ PDF 编译未成功", f"后台转 PDF 失败了。\n\n【失败原因】\n{error_msg}\n\n您可以手动去检查并编译 .tex 文件。")
            self.after(0, on_finish)

        threading.Thread(target=compile_pdf, daemon=True).start()

    # ------------------------------------------
    # Settings View
    # ------------------------------------------
    def save_settings(self):
        self.settings.api_key = self.ent_api.get().strip()
        self.settings.base_url = self.ent_base.get().strip()
        self.settings.model_id = self.ent_model.get().strip()

        try:
            self.settings.temperature = float(self.ent_temp.get())
        except ValueError:
            self.settings.temperature = 1.0
        try:
            self.settings.top_p = float(self.ent_top_p.get())
        except ValueError:
            self.settings.top_p = 1.0
        try:
            self.settings.max_tokens = int(self.ent_max_tokens.get())
        except ValueError:
            self.settings.max_tokens = 4096

        self.settings.reasoning_effort = self.cbo_reasoning.get()

        self.settings.embed_api_key = self.ent_embed_api.get().strip()
        self.settings.embed_base_url = self.ent_embed_base.get().strip()
        self.settings.embed_model_id = self.ent_embed_model.get().strip()

        self.settings.recognition_mode = self.var_rec_mode.get()
        self.settings.use_prm_optimization = self.var_use_prm.get()
        if hasattr(self, 'cbo_ocr_engine'):
            self.settings.ocr_engine_type = self.cbo_ocr_engine.get()
        if hasattr(self, 'cbo_layout_engine'):
            self.settings.layout_engine_type = self.cbo_layout_engine.get()
        try:
            self.settings.prm_batch_size = max(2, min(15, int(self.ent_prm_batch.get())))
        except ValueError:
            self.settings.prm_batch_size = 3
            self.ent_prm_batch.set(self.settings.prm_batch_size)
            messagebox.showwarning("输入无效", f"“单次并发主切片数”的值无效，已重置为默认值: {self.settings.prm_batch_size}")

        try:
            self.settings.save()
            # Also update AI Service instance settings
            self.ai_service.settings = self.settings
            messagebox.showinfo("成功", "设置保存成功！")
        except Exception as e:
            print(f"Save settings failed: {e}")
            messagebox.showerror("错误", f"保存设置时发生异常:\n{e}")

    def build_settings_tab(self):
        container = ttk.Frame(self.tab_settings)
        container.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        provider_frame = ttk.Frame(container)
        provider_frame.pack(anchor=tk.W, pady=5, fill=tk.X)
        ttk.Label(provider_frame, text="快捷服务商配置:").pack(side=tk.LEFT)
        self.cbo_provider = ttk.Combobox(provider_frame, values=["自定义", "DeepSeek", "Kimi", "GLM (智谱)", "SiliconFlow (硅基)"], width=20, state="readonly")
        self.cbo_provider.current(0)
        self.cbo_provider.pack(side=tk.LEFT, padx=10)
        self.cbo_provider.bind("<<ComboboxSelected>>", self.on_provider_changed)

        ttk.Label(container, text="API Key (将通过系统凭证管理器自动加密):").pack(anchor=tk.W, pady=5)
        self.ent_api = ttk.Entry(container, width=50, show="*")
        self.ent_api.insert(0, self.settings.api_key)
        self.ent_api.pack(anchor=tk.W)

        ttk.Label(container, text="Base URL:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_base = ttk.Entry(container, width=50)
        self.ent_base.insert(0, self.settings.base_url)
        self.ent_base.pack(anchor=tk.W)        ttk.Label(container, text="Model ID:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_model = ttk.Entry(container, width=50)
        self.ent_model.insert(0, self.settings.model_id)
        self.ent_model.pack(anchor=tk.W)

        # ====== New Advanced API Params ======
        adv_api_frame = ttk.LabelFrame(container, text="高级模型参数")
        adv_api_frame.pack(anchor=tk.W, fill=tk.X, pady=(10, 5), padx=20)

        ttk.Label(adv_api_frame, text="Temperature (0-2):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.ent_temp = ttk.Entry(adv_api_frame, width=10)
        self.ent_temp.insert(0, str(getattr(self.settings, 'temperature', 1.0)))
        self.ent_temp.grid(row=0, column=1, pady=2)

        ttk.Label(adv_api_frame, text="Top P (0-1):").grid(row=0, column=2, sticky=tk.W, padx=(20, 5), pady=2)
        self.ent_top_p = ttk.Entry(adv_api_frame, width=10)
        self.ent_top_p.insert(0, str(getattr(self.settings, 'top_p', 1.0)))
        self.ent_top_p.grid(row=0, column=3, pady=2)

        ttk.Label(adv_api_frame, text="Max Tokens:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.ent_max_tokens = ttk.Entry(adv_api_frame, width=10)
        self.ent_max_tokens.insert(0, str(getattr(self.settings, 'max_tokens', 4096)))
        self.ent_max_tokens.grid(row=1, column=1, pady=2)

        ttk.Label(adv_api_frame, text="思考强度(Reasoning Effort):").grid(row=1, column=2, sticky=tk.W, padx=(20, 5), pady=2)
        self.cbo_reasoning = ttk.Combobox(adv_api_frame, values=["low", "medium", "high", "none"], width=8, state="readonly")
        current_reason = getattr(self.settings, 'reasoning_effort', 'medium')
        self.cbo_reasoning.set(current_reason)
        self.cbo_reasoning.grid(row=1, column=3, pady=2)
        # ======================================

        ttk.Label(container, text="Embedding API Key (系统级加密):").pack(anchor=tk.W, pady=(15, 5))
        self.ent_embed_api = ttk.Entry(container, width=50, show="*")
        self.ent_embed_api.insert(0, self.settings.embed_api_key)
        self.ent_embed_api.pack(anchor=tk.W)

        ttk.Label(container, text="Embedding Base URL:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_embed_base = ttk.Entry(container, width=50)
        self.ent_embed_base.insert(0, self.settings.embed_base_url)
        self.ent_embed_base.pack(anchor=tk.W)

        ttk.Label(container, text="Embedding Model ID:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_embed_model = ttk.Entry(container, width=50)
        self.ent_embed_model.insert(0, self.settings.embed_model_id)
        self.ent_embed_model.pack(anchor=tk.W)

        ttk.Label(container, text="📝 核心图像与文字识别模式:").pack(anchor=tk.W, pady=(20, 5))

        # --- ENGINE TOGGLES ---
        engine_frame = ttk.Frame(container)
        engine_frame.pack(anchor=tk.W, padx=20, fill=tk.X, pady=2)

        ttk.Label(engine_frame, text="版面分析引擎:").grid(row=0, column=0, sticky=tk.W, pady=2)
        surya_found_failed = getattr(self, 'surya_foundation_failed', False)
        surya_layout_failed = getattr(self, 'surya_layout_failed', False)
        surya_ocr_failed = getattr(self, 'surya_ocr_failed', False)

        surya_layout_supported = self.hardware_ok and not surya_found_failed and not surya_layout_failed and LayoutPredictor is not None and FoundationPredictor is not None
        surya_ocr_supported = self.hardware_ok and not surya_found_failed and not surya_ocr_failed and RecognitionPredictor is not None and FoundationPredictor is not None

        layout_vals = ["DocLayout-YOLO", "Surya"] if surya_layout_supported else ["DocLayout-YOLO"]
        self.cbo_layout_engine = ttk.Combobox(engine_frame, values=layout_vals, width=15, state="readonly")
        current_layout = getattr(self.settings, 'layout_engine_type', 'DocLayout-YOLO')
        self.cbo_layout_engine.set(current_layout if surya_layout_supported else "DocLayout-YOLO")
        self.cbo_layout_engine.grid(row=0, column=1, padx=10, pady=2)

        if not self.hardware_ok:
            ttk.Label(engine_frame, text="(硬件不达标，已禁用 Surya)").grid(row=0, column=2, sticky=tk.W)
        elif surya_found_failed or surya_layout_failed:
            ttk.Label(engine_frame, text="(Surya 版面加载失败，已禁用)").grid(row=0, column=2, sticky=tk.W)
        elif not surya_layout_supported:
            ttk.Label(engine_frame, text="(Surya 依赖缺失，已禁用)").grid(row=0, column=2, sticky=tk.W)

        ttk.Label(engine_frame, text="OCR 识别引擎:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ocr_vals = ["Pix2Text", "Surya"] if surya_ocr_supported else ["Pix2Text"]
        self.cbo_ocr_engine = ttk.Combobox(engine_frame, values=ocr_vals, width=15, state="readonly")
        current_ocr = getattr(self.settings, 'ocr_engine_type', 'Pix2Text')
        self.cbo_ocr_engine.set(current_ocr if surya_ocr_supported else "Pix2Text")
        self.cbo_ocr_engine.grid(row=1, column=1, padx=10, pady=2)
        # ----------------------

        self.var_rec_mode = tk.IntVar(value=self.settings.recognition_mode)
        ttk.Radiobutton(container, text="1. 仅本地 OCR (最快且免费，但不做任何AI纠错处理)", variable=self.var_rec_mode, value=1).pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(container, text="2. 本地 OCR + 纯文字 AI 纠错 (省流推荐，AI 仅根据 OCR 文本脑补排版)", variable=self.var_rec_mode, value=2).pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(container, text="3. 本地 OCR + Vision 图片 AI 纠错 (精准推荐，AI 结合原图修正 OCR 错误)", variable=self.var_rec_mode, value=3).pack(anchor=tk.W, padx=20, pady=2)

        ttk.Label(container, text="🚀 高级选项:").pack(anchor=tk.W, pady=(20, 5))
        prm_frame = ttk.Frame(container)
        prm_frame.pack(anchor=tk.W, padx=20, fill=tk.X)
        self.var_use_prm = tk.BooleanVar(value=self.settings.use_prm_optimization)
        ttk.Checkbutton(prm_frame, text="启用多切片并发", variable=self.var_use_prm).pack(side=tk.LEFT)

        ttk.Label(prm_frame, text="单次并发主切片数 (大于1即启用 PRM 优化):").pack(side=tk.LEFT, padx=(30, 5))
        self.ent_prm_batch = ttk.Spinbox(prm_frame, from_=2, to=15, width=5)
        self.ent_prm_batch.set(self.settings.prm_batch_size)
        self.ent_prm_batch.pack(side=tk.LEFT)

        ttk.Button(container, text="💾 保存所有设置", command=self.save_settings).pack(anchor=tk.W, pady=30)
    def on_provider_changed(self, event):
        provider_presets = {
            "DeepSeek": {"base": "https://api.deepseek.com", "model": "deepseek-chat", "embed_base": "", "embed_model": ""},
            "Kimi": {"base": "https://api.moonshot.cn/v1", "model": "kimi-k2.5", "embed_base": "", "embed_model": ""},
            "GLM (智谱)": {
                "base": "https://open.bigmodel.cn/api/paas/v4/",
                "model": "glm-4-plus-0326",
                "embed_base": "https://open.bigmodel.cn/api/paas/v4/",
                "embed_model": "embedding-3",
            },
            "SiliconFlow (硅基)": {
                "base": "https://api.siliconflow.cn/v1",
                "model": "deepseek-ai/DeepSeek-V3.2",
                "embed_base": "https://api.siliconflow.cn/v1",
                "embed_model": "BAAI/bge-m3",
            },
        }
        provider = self.cbo_provider.get()
        config = provider_presets.get(provider)

        if not config:
            return

        def update_entry(widget, value):
            if value is not None:
                widget.delete(0, tk.END)
                widget.insert(0, value)

        update_entry(self.ent_base, config.get("base"))
        update_entry(self.ent_model, config.get("model"))

        # We only update embed details if they are explicitly mapped.
        # This clears DeepSeek/Kimi embedding fields, indicating no default embedding model.
        update_entry(self.ent_embed_base, config.get("embed_base"))
        update_entry(self.ent_embed_model, config.get("embed_model"))
    def on_tab_changed(self, event):
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        if "Library" in current_tab:
            self.on_hard_search()
        elif "Export" in current_tab:
            self.refresh_bag_ui()

if __name__ == "__main__":
    app = SmartQBApp()
    app.mainloop()
