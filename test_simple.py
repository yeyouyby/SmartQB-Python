import sys
from PySide6.QtWidgets import QApplication
from qfluentwidgets import ElevatedCardWidget

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = ElevatedCardWidget()
    print("ElevatedCardWidget created")
