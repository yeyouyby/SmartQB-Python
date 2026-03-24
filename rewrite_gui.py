with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write("""import os
import warnings
import json
import re
import tempfile
import subprocess
from utils import logger

try:
    from pix2text import Pix2Text
except Exception as e:
    Pix2Text = None
    print(f"Warning: Failed to import Pix2Text: {e}")

from config import DB_NAME
from settings_manager import SettingsManager
from doclayout_yolo_engine import DocLayoutYOLO
from ai_service import AIService
from search_service import vector_search_db

import sys
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (MSFluentWindow, NavigationItemPosition,
                            Theme, setTheme, InfoBar, InfoBarPosition)
from qfluentwidgets import FluentIcon as FIF

from notifications import show_message
from dialogs import APIRetryDialog

from ui_import_tab import ImportTab
from ui_manual_tab import ManualTab
from ui_library_tab import LibraryTab
from ui_export_tab import ExportTab
from ui_settings_tab import SettingsTab

os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")

class SmartQBApp(MSFluentWindow):
    update_import_status_signal = Signal(str)
    refresh_staging_tree_signal = Signal()
    api_retry_signal = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.settings = SettingsManager()
        self.ai_service = AIService(self.settings)

        self.resize(1300, 850)
        self.setWindowTitle("SmartQB Pro V3 - 智能题库桌面端 (完整版)")
        self.setWindowIcon(QIcon("assets/logo.png")) if os.path.exists("assets/logo.png") else None

        if hasattr(self, "windowEffect"):
            is_dark = getattr(self.settings, 'theme', 'Light') == 'Dark'
            self.windowEffect.setMicaEffect(self.winId(), isDarkMode=is_dark)

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

        self.update_import_status_signal.connect(self.tab_import.on_update_import_status)
        self.refresh_staging_tree_signal.connect(self.tab_import.refresh_staging_tree)
        self.api_retry_signal.connect(self.show_api_retry_dialog)

    def initSubInterfaces(self):
        self.tab_import = ImportTab(self)
        self.tab_manual = ManualTab(self)
        self.tab_library = LibraryTab(self)
        self.tab_export = ExportTab(self)
        self.tab_settings = SettingsTab(self)

    def initNavigation(self):
        self.addSubInterface(self.tab_import, FIF.DOCUMENT, '导入与审阅')
        self.addSubInterface(self.tab_manual, FIF.ADD, '手动录入')
        self.addSubInterface(self.tab_library, FIF.LIBRARY, '题库维护')
        self.addSubInterface(self.tab_export, FIF.PRINT, '题目袋组卷')

        self.addSubInterface(self.tab_settings, FIF.SETTING, '设置', position=NavigationItemPosition.BOTTOM)

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

        if hasattr(self, "windowEffect"):
            self.windowEffect.setMicaEffect(self.winId(), isDarkMode=(self.settings.theme == "Dark"))

    def notify_info(self, title, content, duration=None):
        show_message(self, "info", title, content, duration)

    def notify_error(self, title, content, duration=None):
        show_message(self, "error", title, content, duration)

    def notify_success(self, title, content, duration=None):
        show_message(self, "success", title, content, duration)

    def notify_warning(self, title, content, duration=None):
        show_message(self, "warning", title, content, duration)

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

        self.tab_import.txt_stg_content.clear()
        self.tab_import.ent_stg_tags.clear()
        self.tab_import.lbl_vector_info.setText("未生成向量")
        self.tab_import.lbl_stg_diagram.clear()
        self.tab_import.lbl_stg_diagram.setText("无图样")

        import gc
        gc.collect()

    def show_api_retry_dialog(self, error_msg, on_complete_callback):
        dialog = APIRetryDialog(error_msg, self.settings.api_key, self.settings.base_url, self)
        if dialog.exec():
            self.settings.api_key = dialog.ent_api.text()
            self.settings.base_url = dialog.ent_base.text()
            self.settings.save()
            self.ai_service.settings = self.settings
            on_complete_callback(True)
        else:
            on_complete_callback(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SmartQBApp()
    window.show()
    sys.exit(app.exec())
""")
