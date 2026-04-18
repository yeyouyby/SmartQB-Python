import sys
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentWindow,
    NavigationItemPosition,
    FluentIcon as FIF,
)


class SmartQBProWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmartQB Pro V3 - Pyside Edition")
        self.resize(1000, 700)

        # Add basic navigation
        from gui.views.home import HomeDashboard
        from ui_calibration import CalibrationWorkspace
        from gui.views.knowledge_base import KnowledgeBaseWorkspace
        from gui.views.production import ProductionWorkspace
        from gui.views.settings import SettingsCenter

        self.home_dashboard = HomeDashboard(self)
        self.addSubInterface(self.home_dashboard, FIF.HOME, "主页")

        self.calibration_workspace = CalibrationWorkspace(self)
        self.addSubInterface(self.calibration_workspace, FIF.DOCUMENT, "数据清洗")

        self.knowledge_base_workspace = KnowledgeBaseWorkspace(self)
        self.addSubInterface(self.knowledge_base_workspace, FIF.LIBRARY, "教研大脑")

        self.production_workspace = ProductionWorkspace(self)
        self.addSubInterface(self.production_workspace, FIF.PRINT, "组卷导出")

        self.settings_center = SettingsCenter(self)
        self.addSubInterface(
            self.settings_center,
            FIF.SETTING,
            "设置",
            NavigationItemPosition.BOTTOM,
        )

    def create_placeholder(self, text):
        from PySide6.QtWidgets import QLabel, QFrame
        from PySide6.QtCore import Qt

        frame = QFrame(self)
        label = QLabel(text, frame)
        label.setAlignment(Qt.AlignCenter)
        frame.setObjectName(text)
        return frame


def main():
    app = QApplication(sys.argv)
    w = SmartQBProWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
