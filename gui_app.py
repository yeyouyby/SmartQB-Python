# gui_app.py
import os
import warnings
import io
import json
import gc
import base64
import re
import tempfile
import subprocess
from utils import logger
from PIL import Image

try:
    from pix2text import Pix2Text
except Exception as e:
    Pix2Text = None
    print(f"Warning: Failed to import Pix2Text: {e}")

from config import DB_NAME
from settings_manager import SettingsManager
from doclayout_yolo_engine import DocLayoutYOLO
from ai_service import AIService
from document_service import DocumentService
from search_service import vector_search_db

import sys
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QUrl, QSize
from PySide6.QtGui import QIcon, QPixmap, QImage, QDesktopServices, QColor
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QVBoxLayout,
                               QWidget, QFileDialog, QSplitter)
from qfluentwidgets import (MSFluentWindow, NavigationItemPosition, FluentIcon,
                            SubtitleLabel, setFont, Theme, setTheme, setThemeColor,
                            MessageBox, PrimaryPushButton, PushButton, TextEdit,
                            LineEdit, TableWidget, TreeWidget, QTreeWidgetItem,
                            ImageLabel, BodyLabel, SwitchSettingCard, ComboBox,
                            InfoBar, InfoBarPosition, SpinBox, TitleLabel)
from qfluentwidgets import FluentIcon as FIF

# Set up transformers warnings suppression
os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")

class Widget(QFrame):
    def __init__(self, text: str, parent=None):
        super().__init__(parent=parent)
        self.setObjectName(text.replace(' ', '-'))
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 16, 16, 16)

class SmartQBApp(MSFluentWindow):
    # Signals for thread-safe UI updates
    update_import_status_signal = Signal(str)
    slice_ready_signal = Signal(dict)
    refresh_staging_tree_signal = Signal()
    api_retry_signal = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()
        self.ai_service = AIService(self.settings)

        # Basic Window Setup
        self.resize(1300, 850)
        self.setWindowTitle("SmartQB Pro V3 - 智能题库桌面端 (完整版)")
        self.setWindowIcon(QIcon("assets/logo.png")) if os.path.exists("assets/logo.png") else None

        # Enable Acrylic background
        # Note: Acrylic effect works differently on Windows 10 vs 11
        if hasattr(self, "windowEffect"):
            self.windowEffect.setMicaEffect(self.winId(), isDarkMode=Theme.DARK == self.settings)

        self.staging_questions = []
        self.export_bag = []

        logger.info("正在加载 Pix2Text 引擎 (首次启动可能需要下载模型，请耐心等待)...")
        try:
            self.ocr_engine = Pix2Text.from_config()
            logger.info("Pix2Text 引擎加载完成！")
        except Exception as e:
            logger.error(f"Failed to load Pix2Text: {e}", exc_info=True)
            self.ocr_engine = None

        logger.info("正在加载 DocLayout-YOLO 版面分析引擎...")
        try:
            self.doclayout_yolo = DocLayoutYOLO()
        except Exception as e:
            logger.error(f"Failed to load DocLayout-YOLO: {e}", exc_info=True)
            self.doclayout_yolo = None

        self.initSubInterfaces()
        self.initNavigation()

        # Connect signals
        self.update_import_status_signal.connect(self.on_update_import_status)
        self.slice_ready_signal.connect(self.on_slice_ready)
        self.refresh_staging_tree_signal.connect(self.refresh_staging_tree)
        self.api_retry_signal.connect(self.show_api_retry_dialog)

    def initSubInterfaces(self):
        self.tab_import = Widget('Import', self)
        self.tab_manual = Widget('Manual', self)
        self.tab_library = Widget('Library', self)
        self.tab_export = Widget('Export', self)
        self.tab_settings = Widget('Settings', self)

        self.build_import_tab()
        self.build_manual_tab()
        self.build_library_tab()
        self.build_export_tab()
        self.build_settings_tab()

    def initNavigation(self):
        self.addSubInterface(self.tab_import, FIF.DOCUMENT, '导入与审阅')
        self.addSubInterface(self.tab_manual, FIF.ADD, '手动录入')
        self.addSubInterface(self.tab_library, FIF.LIBRARY, '题库维护')
        self.addSubInterface(self.tab_export, FIF.PRINT, '题目袋组卷')

        self.addSubInterface(self.tab_settings, FIF.SETTING, '设置', position=NavigationItemPosition.BOTTOM)

        # Custom Toggle Theme button
        self.navigationInterface.addItem(
            routeKey='ThemeToggle',
            icon=FIF.BRUSH,
            text='切换主题',
            onClick=self.toggle_theme,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

        self.navigationInterface.setCurrentItem(self.tab_import.objectName())

    def toggle_theme(self):
        current = getattr(self.settings, 'theme', 'Light')
        if current == "Dark":
            setTheme(Theme.LIGHT)
            self.settings.theme = "Light"
        else:
            setTheme(Theme.DARK)
            self.settings.theme = "Dark"

        # Save setting if needed or just apply instantly
        if hasattr(self, "windowEffect"):
            self.windowEffect.setMicaEffect(self.winId(), isDarkMode=(self.settings.theme == "Dark"))

    def show_message_info(self, title, content):
        InfoBar.info(title, content, duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def show_message_error(self, title, content):
        InfoBar.error(title, content, duration=5000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def show_message_success(self, title, content):
        InfoBar.success(title, content, duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def show_message_warning(self, title, content):
        InfoBar.warning(title, content, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    # ------------------------------------------
    # Helper Methods
    # ------------------------------------------
    def _parse_diagram_json(self, diag_data):
        if not diag_data:
            return []
        if isinstance(diag_data, list):
            return diag_data
        if isinstance(diag_data, str):
            try:
                parsed_list = json.loads(diag_data)
                if isinstance(parsed_list, list):
                    return parsed_list
            except json.JSONDecodeError:
                pass
        return [diag_data]

    def _resolve_markers_and_extract_diagrams(self, content_text, combined_d_map, per_question_d_map=None):
        if per_question_d_map is None:
            per_question_d_map = {}

        marker_pattern = re.compile(r'\[\[\{ima_dont_del_(\d+_\d+)\}\]\]')
        matches = marker_pattern.findall(content_text)
        diagrams_list = []
        if matches:
            unique_matches = list(dict.fromkeys(matches))
            for marker_idx in unique_matches:
                if marker_idx in combined_d_map:
                    diagrams_list.append(combined_d_map[marker_idx])
                elif marker_idx in per_question_d_map:
                    diagrams_list.append(per_question_d_map[marker_idx])

            resolved_markers = []
            for m in unique_matches:
                if m in combined_d_map or m in per_question_d_map:
                    resolved_markers.append(m)
            if resolved_markers:
                for m in resolved_markers:
                    content_text = content_text.replace(f"[[{{ima_dont_del_{m}}}]]", "")
                content_text = content_text.strip()
        else:
            if "diagram" in per_question_d_map and per_question_d_map["diagram"]:
                diagrams_list.append(per_question_d_map["diagram"])
            elif len(per_question_d_map) == 1:
                diagrams_list.append(next(iter(per_question_d_map.values())))
            elif "diagram" in combined_d_map and combined_d_map["diagram"]:
                diagrams_list.append(combined_d_map["diagram"])
            elif len(combined_d_map) == 1:
                diagrams_list.append(next(iter(combined_d_map.values())))

        diagram = None
        if len(diagrams_list) == 1:
            diagram = diagrams_list[0]
        elif len(diagrams_list) > 1:
            diagram = json.dumps(diagrams_list)

        return content_text, diagram

    def _test_compile_latex(self, content_text):
        tex_code = f'''\\documentclass{{article}}\n\\usepackage{{ctex}}\n\\usepackage{{amsmath}}\n\\usepackage{{amssymb}}\n\\begin{{document}}\n{content_text}\n\\end{{document}}'''
        with tempfile.TemporaryDirectory() as td:
            tex_file = os.path.join(td, "test.tex")
            with open(tex_file, "w", encoding="utf-8") as f_tex:
                f_tex.write(tex_code)
            try:
                res = subprocess.run(["xelatex", "-interaction=nonstopmode", "--no-shell-escape", "test.tex"],
                                     cwd=td, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")  # nosec
                if res.returncode == 0:
                    return True, ""
                else:
                    return False, res.stdout
            except Exception as e:
                return False, str(e)

    def _clear_staging_ui(self):
        for q in self.staging_questions:
            q.pop('diagram', None)
            q.pop('image_b64', None)
            q.pop('page_annotated_b64', None)
        self.staging_questions.clear()
        self.txt_stg_content.clear()
        self.ent_stg_tags.clear()
        self.lbl_vector_info.setText("未生成向量")
        self.lbl_stg_diagram.clear()
        self.lbl_stg_diagram.setText("无图样")
        gc.collect()

    def update_status(self, text):
        self.update_import_status_signal.emit(text)

    def on_update_import_status(self, text):
        self.lbl_import_status.setText(text)

    # UI Builds
    def build_import_tab(self):
        # Top toolbar
        top_frame = QFrame(self.tab_import)
        h_layout = QHBoxLayout(top_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)

        btn_import_pdf = PushButton("📄 导入 PDF")
        btn_import_word = PushButton("📝 导入 Word")
        btn_import_image = PushButton("🖼️ 导入单张图片")

        h_layout.addWidget(btn_import_pdf)
        h_layout.addWidget(btn_import_word)
        h_layout.addWidget(btn_import_image)

        self.lbl_import_status = SubtitleLabel("等待导入...")
        self.lbl_import_status.setStyleSheet("color: #0078D7;")
        h_layout.addWidget(self.lbl_import_status)
        h_layout.addStretch(1)

        self.tab_import.vBoxLayout.addWidget(top_frame)

        # Paned Window (Splitter)
        paned = QSplitter(Qt.Horizontal, self.tab_import)
        self.tab_import.vBoxLayout.addWidget(paned, 1)

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
        bottom_frame = QFrame(self.tab_import)
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

        self.tab_import.vBoxLayout.addWidget(bottom_frame)

    def build_manual_tab(self):
        container = QFrame(self.tab_manual)
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(20, 20, 20, 20)
        self.tab_manual.vBoxLayout.addWidget(container)

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

        # Companion Diagram Selection
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

        self.manual_diagram_b64 = None
        self.manual_vector = None

        btn_save_manual = PrimaryPushButton("💾 保存并直接入库")
        btn_save_manual.clicked.connect(self.save_manual)

        # Bottom align the save button
        save_layout = QHBoxLayout()
        save_layout.addStretch(1)
        save_layout.addWidget(btn_save_manual)
        v_layout.addLayout(save_layout)
        v_layout.addStretch(1)

    def build_library_tab(self):
        # Top toolbar
        top_frame = QFrame(self.tab_library)
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

        self.tab_library.vBoxLayout.addWidget(top_frame)

        # Paned Window (Splitter)
        paned = QSplitter(Qt.Horizontal, self.tab_library)
        self.tab_library.vBoxLayout.addWidget(paned, 1)

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

        self.chat_history = [
            {"role": "system", "content": "你是 SmartQB 的寻题助手。你可以理解用户的寻题需求，调用 search_database 工具查询题库向量。如果用户要求将某些题加入题目袋/试卷，请调用 add_to_bag 工具。"}
        ]
        self.append_chat("🤖 助手", "您好！想找什么样的题目？(例如：帮我找两道关于导数极值的题，并加入题目袋)")

    def build_export_tab(self):
        container = QFrame(self.tab_export)
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(20, 20, 20, 20)
        self.tab_export.vBoxLayout.addWidget(container)

        v_layout.addWidget(SubtitleLabel("组卷题目袋 (选中题目可上下移动排序):"))

        middle_frame = QFrame(container)
        h_layout = QHBoxLayout(middle_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)

        from PySide6.QtWidgets import QListWidget
        self.listbox_bag = QListWidget(middle_frame)
        self.listbox_bag.setStyleSheet("font-family: 微软雅黑; font-size: 14px;")
        h_layout.addWidget(self.listbox_bag, 1)

        btn_frame = QFrame(middle_frame)
        btn_layout = QVBoxLayout(btn_frame)
        btn_layout.setContentsMargins(10, 0, 0, 0)

        btn_move_up = PushButton("⬆️ 上移")
        btn_move_down = PushButton("⬇️ 下移")
        btn_remove = PushButton("❌ 移除")

        btn_move_up.clicked.connect(self.bag_move_up)
        btn_move_down.clicked.connect(self.bag_move_down)
        btn_remove.clicked.connect(self.bag_remove)

        btn_layout.addWidget(btn_move_up)
        btn_layout.addWidget(btn_move_down)
        btn_layout.addStretch(1)
        btn_layout.addWidget(btn_remove)

        h_layout.addWidget(btn_frame)
        v_layout.addWidget(middle_frame, 1)

        bottom_frame = QFrame(container)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(0, 10, 0, 0)

        self.lbl_export_status = BodyLabel("")
        self.lbl_export_status.setStyleSheet("color: green;")
        bottom_layout.addWidget(self.lbl_export_status)

        bottom_layout.addStretch(1)

        btn_export = PrimaryPushButton("🖨️ 导出试卷并自动编译 PDF")
        btn_export.clicked.connect(self.export_paper)
        bottom_layout.addWidget(btn_export)

        v_layout.addWidget(bottom_frame)

    def build_settings_tab(self):
        from PySide6.QtWidgets import QScrollArea
        scroll_area = QScrollArea(self.tab_settings)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea {border: none; background: transparent;}")

        container = QFrame()
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(20, 20, 20, 20)

        v_layout.addWidget(TitleLabel("应用设置"))

        # Provider Config
        provider_frame = QFrame()
        h_layout_prov = QHBoxLayout(provider_frame)
        h_layout_prov.setContentsMargins(0, 10, 0, 10)
        h_layout_prov.addWidget(BodyLabel("快捷服务商配置:"))

        self.cbo_provider = ComboBox()
        self.cbo_provider.addItems(["自定义", "DeepSeek", "Kimi", "GLM (智谱)", "SiliconFlow (硅基)"])
        self.cbo_provider.setCurrentIndex(0)
        self.cbo_provider.currentIndexChanged.connect(self.on_provider_changed)
        h_layout_prov.addWidget(self.cbo_provider)
        h_layout_prov.addStretch(1)
        v_layout.addWidget(provider_frame)

        # Basic Model Setup
        v_layout.addWidget(BodyLabel("API Key (将通过系统凭证管理器自动加密):"))
        self.ent_api = LineEdit()
        self.ent_api.setEchoMode(LineEdit.Password)
        self.ent_api.setText(self.settings.api_key)
        v_layout.addWidget(self.ent_api)

        v_layout.addWidget(BodyLabel("Base URL:"))
        self.ent_base = LineEdit()
        self.ent_base.setText(self.settings.base_url)
        v_layout.addWidget(self.ent_base)

        v_layout.addWidget(BodyLabel("Model ID:"))
        self.ent_model = LineEdit()
        self.ent_model.setText(self.settings.model_id)
        v_layout.addWidget(self.ent_model)

        # Advanced Model Settings
        v_layout.addWidget(SubtitleLabel("高级模型参数"))
        adv_frame = QFrame()
        adv_layout = QHBoxLayout(adv_frame)
        adv_layout.setContentsMargins(0,0,0,0)

        adv_layout.addWidget(BodyLabel("Temperature (0-2):"))
        self.ent_temp = LineEdit()
        self.ent_temp.setText(str(getattr(self.settings, 'temperature', 1.0)))
        adv_layout.addWidget(self.ent_temp)

        adv_layout.addWidget(BodyLabel("Top P (0-1):"))
        self.ent_top_p = LineEdit()
        self.ent_top_p.setText(str(getattr(self.settings, 'top_p', 1.0)))
        adv_layout.addWidget(self.ent_top_p)

        adv_layout.addWidget(BodyLabel("Max Tokens:"))
        self.ent_max_tokens = LineEdit()
        self.ent_max_tokens.setText(str(getattr(self.settings, 'max_tokens', 4096)))
        adv_layout.addWidget(self.ent_max_tokens)

        adv_layout.addWidget(BodyLabel("思考强度(Reasoning Effort):"))
        self.cbo_reasoning = ComboBox()
        self.cbo_reasoning.addItems(["low", "medium", "high", "none"])
        self.cbo_reasoning.setCurrentText(getattr(self.settings, 'reasoning_effort', 'medium'))
        adv_layout.addWidget(self.cbo_reasoning)

        v_layout.addWidget(adv_frame)

        # Embeddings Config
        v_layout.addWidget(SubtitleLabel("嵌入向量配置"))

        v_layout.addWidget(BodyLabel("Embedding API Key:"))
        self.ent_embed_api = LineEdit()
        self.ent_embed_api.setEchoMode(LineEdit.Password)
        self.ent_embed_api.setText(self.settings.embed_api_key)
        v_layout.addWidget(self.ent_embed_api)

        v_layout.addWidget(BodyLabel("Embedding Base URL:"))
        self.ent_embed_base = LineEdit()
        self.ent_embed_base.setText(self.settings.embed_base_url)
        v_layout.addWidget(self.ent_embed_base)

        v_layout.addWidget(BodyLabel("Embedding Model ID:"))
        self.ent_embed_model = LineEdit()
        self.ent_embed_model.setText(self.settings.embed_model_id)
        v_layout.addWidget(self.ent_embed_model)

        v_layout.addWidget(BodyLabel("Embedding 向量维度 (与模型输出一致，否则报错):"))
        self.ent_embed_dim = LineEdit()
        self.ent_embed_dim.setText(str(getattr(self.settings, 'embedding_dimension', 1024)))
        v_layout.addWidget(self.ent_embed_dim)

        # Engine Settings
        v_layout.addWidget(SubtitleLabel("📝 核心图像与文字识别模式"))

        engine_frame = QFrame()
        engine_layout = QHBoxLayout(engine_frame)
        engine_layout.setContentsMargins(0,0,0,0)

        engine_layout.addWidget(BodyLabel("版面分析引擎:"))
        self.cbo_layout_engine = ComboBox()
        self.cbo_layout_engine.addItem("DocLayout-YOLO")
        engine_layout.addWidget(self.cbo_layout_engine)

        engine_layout.addWidget(BodyLabel("OCR 识别引擎:"))
        self.cbo_ocr_engine = ComboBox()
        self.cbo_ocr_engine.addItem("Pix2Text")
        engine_layout.addWidget(self.cbo_ocr_engine)
        engine_layout.addStretch(1)

        v_layout.addWidget(engine_frame)

        from PySide6.QtWidgets import QButtonGroup, QRadioButton
        self.mode_group = QButtonGroup(self)

        mode1 = QRadioButton("1. 仅本地 OCR (最快且免费，但不做任何AI纠错处理)")
        mode2 = QRadioButton("2. 本地 OCR + 纯文字 AI 纠错 (省流推荐，AI 仅根据 OCR 文本脑补排版)")
        mode3 = QRadioButton("3. 本地 OCR + Vision 图片 AI 纠错 (精准推荐，AI 结合原图修正 OCR 错误)")

        self.mode_group.addButton(mode1, 1)
        self.mode_group.addButton(mode2, 2)
        self.mode_group.addButton(mode3, 3)

        mode_val = self.settings.recognition_mode
        if mode_val == 1: mode1.setChecked(True)
        elif mode_val == 2: mode2.setChecked(True)
        else: mode3.setChecked(True)

        v_layout.addWidget(mode1)
        v_layout.addWidget(mode2)
        v_layout.addWidget(mode3)

        v_layout.addWidget(SubtitleLabel("🚀 高级选项:"))

        self.card_prm = SwitchSettingCard(
            icon=FIF.LIGHTBULB,
            title="启用多切片并发",
            content="大于1即启用 PRM 优化",
            configItem=None
        )
        self.card_prm.setChecked(self.settings.use_prm_optimization)
        v_layout.addWidget(self.card_prm)

        batch_frame = QFrame()
        batch_layout = QHBoxLayout(batch_frame)
        batch_layout.setContentsMargins(0,0,0,0)
        batch_layout.addWidget(BodyLabel("单次并发主切片数:"))
        self.ent_prm_batch = SpinBox()
        self.ent_prm_batch.setRange(2, 15)
        self.ent_prm_batch.setValue(self.settings.prm_batch_size)
        batch_layout.addWidget(self.ent_prm_batch)
        batch_layout.addStretch(1)
        v_layout.addWidget(batch_frame)

        btn_save = PrimaryPushButton("💾 保存所有设置")
        btn_save.clicked.connect(self.save_settings)

        save_layout = QHBoxLayout()
        save_layout.addWidget(btn_save)
        save_layout.addStretch(1)
        v_layout.addLayout(save_layout)

        v_layout.addStretch(1)

        scroll_area.setWidget(container)
        self.tab_settings.vBoxLayout.addWidget(scroll_area)


    # Stubs
    def on_staging_select(self): pass
    def delete_staging_item(self): pass
    def merge_staging_items(self): pass
    def split_staging_item(self): pass
    def format_staging_item(self): pass
    def update_stg_item(self): pass
    def update_staging_vector(self): pass
    def stg_prev_diagram(self): pass
    def stg_delete_diagram(self): pass
    def stg_next_diagram(self): pass
    def move_diagram_up(self): pass
    def move_diagram_down(self): pass
    def show_page_layout_view(self): pass
    def apply_batch_tags(self): pass
    def save_staging_to_db(self): pass
    def check_and_fix_latex(self): pass
    def on_slice_ready(self, s): pass
    def refresh_staging_tree(self): pass
    def show_api_retry_dialog(self, text, obj): pass

    def on_manual_ai(self): pass
    def on_manual_reformat(self): pass
    def on_manual_retag(self): pass
    def on_manual_preview_vector(self): pass
    def on_select_manual_diagram(self): pass
    def save_manual(self): pass

    def append_chat(self, sender, text):
        self.txt_chat.append(f"{sender}: {text}\n")

    def on_hard_search(self): pass
    def on_lib_select(self): pass
    def update_lib_tags(self): pass
    def delete_lib_question(self): pass
    def add_to_bag(self): pass
    def ai_add_to_bag(self): pass
    def lib_prev_diagram(self): pass
    def lib_next_diagram(self): pass
    def on_ai_chat(self): pass

    def refresh_bag_ui(self):
        if hasattr(self, 'listbox_bag'):
            self.listbox_bag.clear()
            for idx, item in enumerate(self.export_bag):
                preview = item["content"][:40].replace('\n', '')
                has_img = "[含图]" if item["diagram"] else ""
                self.listbox_bag.addItem(f"{idx+1}. {has_img} {preview}...")

    def bag_move_up(self): pass
    def bag_move_down(self): pass
    def bag_remove(self): pass
    def export_paper(self): pass

    def on_provider_changed(self, idx): pass
    def save_settings(self): pass

class WorkerThread(QThread):
    finished_signal = Signal(object)
    error_signal = Signal(str)
    progress_signal = Signal(str)

    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.task_func(*self.args, **self.kwargs)
            self.finished_signal.emit(result)
        except Exception as e:
            logger.error(f"WorkerThread Error: {e}", exc_info=True)
            self.error_signal.emit(str(e))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SmartQBApp()
    window.show()
    sys.exit(app.exec())

class APIRetryDialog(MessageBoxBase):
    def __init__(self, error_msg, current_api, current_base, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("⚠️ API 请求失败")
        self.errorLabel = BodyLabel(f"发生错误:\n{error_msg}")
        self.errorLabel.setStyleSheet("color: red;")
        self.errorLabel.setWordWrap(True)

        self.ent_api = LineEdit()
        self.ent_api.setPlaceholderText("API Key")
        self.ent_api.setText(current_api)

        self.ent_base = LineEdit()
        self.ent_base.setPlaceholderText("Base URL")
        self.ent_base.setText(current_base)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.errorLabel)
        self.viewLayout.addWidget(self.ent_api)
        self.viewLayout.addWidget(self.ent_base)

        self.yesButton.setText("💾 保存并继续重试")
        self.cancelButton.setText("⏭️ 取消并降级跳过")

        self.widget.setMinimumWidth(400)
