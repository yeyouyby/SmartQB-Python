import sys
import os
from PySide6.QtCore import Qt, QUrl, Slot, QObject, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QStackedWidget,
)
from qfluentwidgets import (
    NavigationInterface,
    NavigationItemPosition,
    setTheme,
    Theme,
    InfoBar,
    InfoBarPosition,
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    PrimaryPushButton,
    FluentIcon,
    theme,
    Slider,
    SpinBox,
    TextEdit,
)


class GlobalSignals(QObject):
    db_updated = Signal()


signals = GlobalSignals()


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

        signals.db_updated.connect(self.on_db_updated)

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
        self.routes["Library"] = self.libraryPage

        # 2. Exam Bag (SA Generation) Page
        self.examBagPage = QWidget()
        examLayout = QVBoxLayout(self.examBagPage)

        examLayout.addWidget(SubtitleLabel("智能组卷参数设置 (Simulated Annealing)"))
        examLayout.addWidget(BodyLabel("期望难度系数 (0.0 - 1.0)"))
        self.diff_slider = Slider(Qt.Horizontal)
        self.diff_slider.setRange(0, 100)
        self.diff_slider.setValue(65)
        examLayout.addWidget(self.diff_slider)

        examLayout.addWidget(BodyLabel("目标总分"))
        self.score_spinbox = SpinBox()
        self.score_spinbox.setRange(10, 300)
        self.score_spinbox.setValue(100)
        examLayout.addWidget(self.score_spinbox)

        gen_btn = PrimaryPushButton("一键智能组卷")
        gen_btn.clicked.connect(self.generate_exam)
        examLayout.addWidget(gen_btn)

        self.exam_result_text = TextEdit()
        self.exam_result_text.setReadOnly(True)
        examLayout.addWidget(self.exam_result_text)

        self.stack.addWidget(self.examBagPage)
        self.routes["ExamBag"] = self.examBagPage

        # 3. Editor Page
        self.editorPage = QWidget()
        editorLayout = QVBoxLayout(self.editorPage)

        self.webView = QWebEngineView(self)
        self.channel = QWebChannel()
        self.backend = MarkdownBackend(self)
        self.channel.registerObject("backend", self.backend)
        self.webView.page().setWebChannel(self.channel)

        local_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "resources", "html", "editor.html"
            )
        )
        if os.path.exists(local_path):
            self.webView.setUrl(QUrl.fromLocalFile(local_path))
        else:
            self.webView.setHtml(
                f"<h1>Error</h1><p>Editor resources not found at: {local_path}</p>"
            )

        editorLayout.addWidget(self.webView)
        self.stack.addWidget(self.editorPage)
        self.routes["Editor"] = self.editorPage

    def initNavigation(self):
        # Add items to navigation
        self.navigationInterface.addItem(
            routeKey="Library",
            icon=FluentIcon.BOOK_SHELF,
            text="题库",
            onClick=lambda: self.switchTo("Library"),
        )
        self.navigationInterface.addItem(
            routeKey="ExamBag",
            icon=FluentIcon.DOCUMENT,
            text="试卷袋",
            onClick=lambda: self.switchTo("ExamBag"),
        )
        self.navigationInterface.addItem(
            routeKey="Editor",
            icon=FluentIcon.EDIT,
            text="沉浸草稿",
            onClick=lambda: self.switchTo("Editor"),
        )
        self.navigationInterface.addSeparator()
        self.navigationInterface.addItem(
            routeKey="Zen",
            icon=FluentIcon.FULL_SCREEN,
            text="专注模式",
            position=NavigationItemPosition.BOTTOM,
            onClick=self.enterZenMode,
        )

        # Default to library
        self.switchTo("Library")

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
            # Dynamically grab the active theme instead of assuming LIGHT
            self._original_theme = theme()
            self.showFullScreen()
            self.navigationInterface.hide()
            setTheme(Theme.DARK)
            InfoBar.success(
                title="专注模式",
                content="按原按钮或 F11 退出全屏",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self,
            )

    def generate_exam(self):
        from algorithms.simulated_annealing import SimulatedAnnealingExamBuilder
        import db_manager

        try:
            db = db_manager.dbManager()
            pool = db.get_all_questions_for_sa()

            if not pool:
                self.exam_result_text.setText("题库为空，请先录入题目。")
                return

            target_diff = self.diff_slider.value() / 100.0
            target_score = self.score_spinbox.value()

            self.exam_result_text.setText(
                f"开始退火计算：目标分数 {target_score}, 期望难度 {target_diff:.2f}...\n"
            )
            QApplication.processEvents()

            builder = SimulatedAnnealingExamBuilder(
                pool, target_score=target_score, target_difficulty=target_diff
            )
            best_state = builder.build_exam(initial_temp=50.0, max_iterations=500)

            selected_ids = [q["id"] for q in best_state]
            final_score = sum(q.get("score", 0) for q in best_state)
            final_diff = (
                sum(q.get("difficulty", 0.5) for q in best_state) / len(best_state)
                if best_state
                else 0
            )

            result_str = (
                f"✅ 组卷成功！\n"
                f"选中题目数量: {len(selected_ids)}\n"
                f"总分: {final_score} (目标: {target_score})\n"
                f"平均难度: {final_diff:.2f} (目标: {target_diff:.2f})\n"
                f"题目ID列表: {selected_ids}"
            )
            self.exam_result_text.setText(result_str)
        except Exception as e:
            self.exam_result_text.setText(f"❌ 组卷失败: {str(e)}")

    def showNotification(self):
        InfoBar.success(
            title="操作成功",
            content="题库已更新，128 道题目已就绪",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=3000,
            parent=self,
        )

    def on_db_updated(self):
        # Refresh UI lists here when db updates happen in background
        print("Database changed. UI components will refresh data.")


if __name__ == "__main__":
    # Add flag only for headless Linux environments to prevent breaking native desktop users
    if (
        sys.platform.startswith("linux")
        and not os.environ.get("DISPLAY")
        and not os.environ.get("WAYLAND_DISPLAY")
    ):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
