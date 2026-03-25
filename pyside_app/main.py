import sys
import os
from PySide6.QtCore import Qt, QUrl, Slot, QObject
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QHBoxLayout, QStackedWidget
from qfluentwidgets import (NavigationInterface, NavigationItemPosition,
                            setTheme, Theme, InfoBar, InfoBarPosition,
                            CardWidget, SubtitleLabel, BodyLabel,
                            PrimaryPushButton, FluentIcon)

class MarkdownBackend(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot(str)
    def receive_markdown(self, content):
        # We purposely do not log content here so we don't spam standard output
        # or leak the user's exam content into debugging tools.
        pass

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

        self._original_theme = None

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

        # Stacked Widget for pages
        self.stack = QStackedWidget(self)
        self.hBoxLayout.addWidget(self.stack)

        # Register global F11 Shortcut for Zen mode toggle
        self.toggleZenShortcut = QShortcut(QKeySequence("F11"), self)
        self.toggleZenShortcut.activated.connect(self.enterZenMode)

        self.routes = {}
        self.initPages()
        self.initNavigation()

    def initPages(self):
        # 1. Library Page
        self.libraryPage = QWidget()
        libLayout = QVBoxLayout(self.libraryPage)
        card = QuestionCard("1. 物理题", "关于动滑轮的受力分析...", self.libraryPage)
        libLayout.addWidget(card)
        btn = PrimaryPushButton("测试通知")
        btn.clicked.connect(self.showNotification)
        libLayout.addWidget(btn)
        self.stack.addWidget(self.libraryPage)
        self.routes['Library'] = self.libraryPage

        # 2. Editor Page
        self.editorPage = QWidget()
        editorLayout = QVBoxLayout(self.editorPage)

        self.webView = QWebEngineView(self)
        self.channel = QWebChannel()
        self.backend = MarkdownBackend(self)
        self.channel.registerObject("backend", self.backend)
        self.webView.page().setWebChannel(self.channel)

        local_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "resources", "html", "editor.html"))
        if os.path.exists(local_path):
            self.webView.setUrl(QUrl.fromLocalFile(local_path))
        else:
            self.webView.setHtml(f"<h1>Error</h1><p>Editor resources not found at: {local_path}</p>")

        editorLayout.addWidget(self.webView)
        self.stack.addWidget(self.editorPage)
        self.routes['Editor'] = self.editorPage

    def initNavigation(self):
        # Add items to navigation
        self.navigationInterface.addItem(
            routeKey='Library',
            icon=FluentIcon.BOOK_SHELF,
            text='题库',
            onClick=lambda: self.switchTo('Library')
        )
        self.navigationInterface.addItem(
            routeKey='Editor',
            icon=FluentIcon.EDIT,
            text='试卷袋',
            onClick=lambda: self.switchTo('Editor')
        )
        self.navigationInterface.addSeparator()
        self.navigationInterface.addItem(
            routeKey='Zen',
            icon=FluentIcon.FULLSCREEN,
            text='专注模式',
            position=NavigationItemPosition.BOTTOM,
            onClick=self.enterZenMode
        )

        # Default to library
        self.switchTo('Library')

    def switchTo(self, route):
        if route in self.routes:
            self.stack.setCurrentWidget(self.routes[route])
        else:
            print(f"Error: Route {route} not found.")

    def enterZenMode(self):
        # F11 Zen Mode
        if self.isFullScreen():
            self.showNormal()
            self.navigationInterface.show()
            if self._original_theme is not None:
                setTheme(self._original_theme)
                self._original_theme = None
            else:
                setTheme(Theme.LIGHT)
        else:
            self._original_theme = Theme.LIGHT  # Assumption based on app default
            self.showFullScreen()
            self.navigationInterface.hide()
            setTheme(Theme.DARK)
            InfoBar.success(
                title='专注模式',
                content="按原按钮或 F11 退出全屏",
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
    # Add flag only for headless Linux environments to prevent breaking native desktop users
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
