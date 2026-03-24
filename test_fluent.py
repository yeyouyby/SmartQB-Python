import sys
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentWindow

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = FluentWindow()
    w.show()
    # app.exec()
