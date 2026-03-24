import sys
import os
import io
import json
import base64
import threading
import warnings
import tempfile
import subprocess
import gc
import re

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSize, Slot, QTimer, QMetaObject, Q_ARG
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QFileDialog, QHeaderView, QSplitter, QTableWidgetItem, QListWidgetItem

from qfluentwidgets import (FluentWindow, NavigationItemPosition, MessageBox, FluentIcon as FIF,
                            NavigationAvatarWidget, InfoBar, InfoBarPosition, ProgressBar, ProgressRing)

from utils import logger
from config import DB_NAME
from settings_manager import SettingsManager
from ai_service import AIService

# Import our new Fluent UI components
from interfaces.import_interface import ImportInterface
from interfaces.manual_interface import ManualInterface
from interfaces.library_interface import LibraryInterface
from interfaces.export_interface import ExportInterface
from interfaces.settings_interface import SettingsInterface

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.initWindow()

        # Initialize core services
        self.settings = SettingsManager()
        self.ai_service = AIService(self.settings)

        self.doclayout_yolo = None
        self.ocr_engine = None

        logger.info("正在加载 Pix2Text 引擎 (首次启动可能需要下载模型，请耐心等待)...")
        try:
            from pix2text import Pix2Text
            self.ocr_engine = Pix2Text.from_config()
            logger.info("Pix2Text 引擎加载完成！")
        except Exception as e:
            logger.error(f"Failed to load Pix2Text: {e}", exc_info=True)

        logger.info("正在加载 DocLayout-YOLO 版面分析引擎...")
        try:
            from doclayout_yolo_engine import DocLayoutYOLO
            self.doclayout_yolo = DocLayoutYOLO()
        except Exception as e:
            logger.error(f"Failed to load DocLayout-YOLO: {e}", exc_info=True)

        self.export_bag = []

        # Setup Views (Interfaces)
        self.import_interface = ImportInterface(self, self)
        self.import_interface.setObjectName("importInterface")

        self.manual_interface = ManualInterface(self, self)
        self.manual_interface.setObjectName("manualInterface")

        self.library_interface = LibraryInterface(self, self)
        self.library_interface.setObjectName("libraryInterface")

        self.export_interface = ExportInterface(self, self)
        self.export_interface.setObjectName("exportInterface")

        self.settings_interface = SettingsInterface(self, self)
        self.settings_interface.setObjectName("settingsInterface")

        self.initNavigation()

    def initNavigation(self):
        # Adding items to navigation interface
        self.addSubInterface(self.import_interface, FIF.DOCUMENT, '文件导入与审阅')
        self.addSubInterface(self.manual_interface, FIF.ADD, '手动单题录入')
        self.addSubInterface(self.library_interface, FIF.FOLDER, '题库维护')
        self.addSubInterface(self.export_interface, FIF.PRINT, '题目袋组卷')

        self.navigationInterface.addSeparator()
        self.addSubInterface(self.settings_interface, FIF.SETTING, '设置', NavigationItemPosition.BOTTOM)

        self.stackedWidget.currentChanged.connect(self.on_tab_changed)

    def initWindow(self):
        self.resize(1300, 850)
        self.setWindowIcon(QIcon('assets/icon.png'))
        self.setWindowTitle('SmartQB Pro V3 - 智能题库桌面端 (Fluent 完整版)')

        # Enable Acrylic effect
        self.windowEffect.setMicaEffect(self.winId())

    def on_tab_changed(self, index):
        widget = self.stackedWidget.widget(index)
        if widget == self.library_interface:
            self.library_interface.on_hard_search()
        elif widget == self.export_interface:
            self.export_interface.refresh_ui()

    # --- Common helper logic used across interfaces ---
    def _parse_diagram_json(self, diag_data):
        if not diag_data: return []
        if isinstance(diag_data, list): return diag_data
        if isinstance(diag_data, str):
            try:
                parsed_list = json.loads(diag_data)
                if isinstance(parsed_list, list): return parsed_list
            except json.JSONDecodeError:
                pass
        return [diag_data]

    def _resolve_markers_and_extract_diagrams(self, content_text, combined_d_map, per_question_d_map):
        marker_pattern = re.compile(r'\[\[\{ima_dont_del_(\d+_\d+)\}\]\]')
        matches = marker_pattern.findall(content_text)
        diagrams_list = []

        if matches:
            unique_matches = list(dict.fromkeys(matches))
            for marker_idx in unique_matches:
                if marker_idx in combined_d_map:
                    diagrams_list.append(combined_d_map[marker_idx])

            resolved_markers = []
            for m in unique_matches:
                if m in combined_d_map:
                    resolved_markers.append(m)
            if resolved_markers:
                for m in resolved_markers:
                    content_text = content_text.replace(f"[[{{ima_dont_del_{m}}}]]", "")
                content_text = content_text.strip()
        else:
            # Fallback for legacy items without markers
            if "diagram" in per_question_d_map and per_question_d_map["diagram"]:
                diagrams_list.append(per_question_d_map["diagram"])
            elif len(per_question_d_map) == 1:
                diagrams_list.append(next(iter(per_question_d_map.values())))

        diagram = None
        if len(diagrams_list) == 1:
            diagram = diagrams_list[0]
        elif len(diagrams_list) > 1:
            diagram = json.dumps(diagrams_list)

        return content_text, diagram

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
        return {"status": "success", "message": f"成功加入了 {added} 道题目到题目袋"}


def start_fluent_app():
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    start_fluent_app()
