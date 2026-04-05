import sys
from PySide6.QtWidgets import QApplication
from ui_calibration import CalibrationWorkspace

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = CalibrationWorkspace()
    window.show()
    sys.exit(app.exec())
