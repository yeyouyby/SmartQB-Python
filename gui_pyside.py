import sys
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon as FIF


class SmartQBProWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmartQB Pro V3 - Pyside Edition")
        self.resize(1000, 700)

        # Add basic navigation
        from ui_calibration import CalibrationWorkspace
        from gui.views.knowledge_base import KnowledgeBaseWorkspace


        self.calibration_workspace = CalibrationWorkspace(self)
        self.addSubInterface(self.calibration_workspace, FIF.DOCUMENT, "导入")
        self.knowledge_base_workspace = KnowledgeBaseWorkspace(self)
        self.addSubInterface(
            self.knowledge_base_workspace, FIF.LIBRARY, "题库"
        )
        self.addSubInterface(
            self.create_placeholder("设置 (Settings)"),
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
