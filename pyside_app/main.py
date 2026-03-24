import sys
import os
from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QHBoxLayout
from qfluentwidgets import (NavigationInterface, NavigationItemPosition, MessageBox,
                            isDarkTheme, setTheme, Theme, InfoBar, InfoBarPosition,
                            IndeterminateProgressRing, CardWidget, SubtitleLabel, BodyLabel,
                            PrimaryPushButton)

class MarkdownBackend(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot(str)
    def receive_markdown(self, content):
        print(f"Received from JS: {content[:30]}...")

class QuestionCard(CardWidget):
    def __init__(self, title, content, parent=None):
        super().__init__(parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.titleLabel = SubtitleLabel(title, self)
        self.contentLabel = BodyLabel(content, self)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.contentLabel)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmartQB-QT Ultimate")
        self.resize(1000, 700)

        # Set theme
        setTheme(Theme.LIGHT)

        # Navigation Interface
        self.navigationInterface = NavigationInterface(self, showMenuButton=True)
        self.navigationInterface.setExpandWidth(200)

        # Central Widget
        self.centralWidget = QWidget(self)
        self.setCentralWidget(self.centralWidget)
        self.hBoxLayout = QHBoxLayout(self.centralWidget)
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)

        self.hBoxLayout.addWidget(self.navigationInterface)

        # Main content area
        self.contentArea = QWidget(self)
        self.contentLayout = QVBoxLayout(self.contentArea)
        self.hBoxLayout.addWidget(self.contentArea)

        self.initNavigation()
        self.initContent()

    def initNavigation(self):
        # Add items to navigation
        self.navigationInterface.addItem(
            routeKey='Library',
            icon='Book', # Placeholder icon string, qfluentwidgets uses fluent icons
            text='题库',
            onClick=lambda: self.switchTo('Library')
        )
        self.navigationInterface.addItem(
            routeKey='Editor',
            icon='Edit',
            text='试卷袋',
            onClick=lambda: self.switchTo('Editor')
        )
        self.navigationInterface.addSeparator()
        self.navigationInterface.addItem(
            routeKey='Zen',
            icon='FullScreen',
            text='专注模式',
            position=NavigationItemPosition.BOTTOM,
            onClick=self.enterZenMode
        )

    def initContent(self):
        # Demo card
        card = QuestionCard("1. 物理题", "关于动滑轮的受力分析...", self.contentArea)
        self.contentLayout.addWidget(card)

        # WebEngine
        self.webView = QWebEngineView(self)
        self.channel = QWebChannel()
        self.backend = MarkdownBackend(self)
        self.channel.registerObject("backend", self.backend)
        self.webView.page().setWebChannel(self.channel)

        local_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resources", "html", "editor.html"))
        self.webView.setUrl(QUrl.fromLocalFile(local_path))

        self.contentLayout.addWidget(self.webView)

        # Action button
        btn = PrimaryPushButton("测试通知")
        btn.clicked.connect(self.showNotification)
        self.contentLayout.addWidget(btn)

    def switchTo(self, route):
        print(f"Switched to {route}")

    def enterZenMode(self):
        # F11 Zen Mode
        if self.isFullScreen():
            self.showNormal()
            self.navigationInterface.show()
            setTheme(Theme.LIGHT)
        else:
            self.showFullScreen()
            self.navigationInterface.hide()
            setTheme(Theme.DARK)
            InfoBar.success(
                title='专注模式',
                content="按原按钮退出全屏",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )

    def showNotification(self):
        InfoBar.success(
            title='操作成功',
            content="题库已更新，128 道题目已就绪",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=3000,
            parent=self
        )

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
