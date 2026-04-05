import sys
from PySide6.QtWidgets import QApplication
from gui.components.question_block import QuestionBlockWidget

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = QuestionBlockWidget()
    print("QuestionBlockWidget created")
