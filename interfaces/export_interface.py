import os
import re
import json
import base64
import threading
import subprocess
from PySide6.QtCore import Qt, Signal, QThread, QObject, Slot, QMetaObject, Q_ARG
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QHeaderView, QSplitter, QTableWidgetItem, QListWidgetItem, QApplication, QStackedWidget

from qfluentwidgets import (PrimaryPushButton, PushButton, ListWidget,
                            BodyLabel, SubtitleLabel, MessageBox, InfoBar, InfoBarPosition)

from utils import logger

class ExportWorker(QThread):
    status = Signal(str)
    finished_export = Signal(bool, str)

    def __init__(self, export_bag, file_path, app_logic, parent=None):
        super().__init__(parent)
        self.export_bag = export_bag
        self.file_path = file_path
        self.app_logic = app_logic

    def run(self):
        try:
            base_path, _ = os.path.splitext(self.file_path)
            export_dir = os.path.dirname(base_path)
            base_name = os.path.basename(base_path)

            export_tex_path = base_path + ".tex"
            img_dir_name = base_name + "_Images"
            img_dir = os.path.join(export_dir, img_dir_name)
            os.makedirs(img_dir, exist_ok=True)

            tex = [
                r"\documentclass[11pt, a4paper]{ctexart}",
                r"\usepackage{amsmath, amssymb, amsfonts}",
                r"\usepackage{graphicx}",
                r"\usepackage{geometry}",
                r"\usepackage{listings}",
                r"\geometry{left=2cm, right=2cm, top=2.5cm, bottom=2.5cm}",
                r"\begin{document}",
                r"\begin{center}",
                r"\Large\textbf{SmartQB 导出试卷}",
                r"\end{center}",
                r"\vspace{1em}",
                r"\begin{enumerate}"
            ]

            for q in self.export_bag:
                # Clean up dangerous newlines in latex around environments
                tex_content = q["content"].replace("\n", " \\newline ")
                tex_content = re.sub(r"\\newline\s*\\begin\{center\}", r"\\begin{center}", tex_content)
                tex_content = re.sub(r"\\newline\s*\\end\{center\}", r"\\end{center}", tex_content)
                tex_content = re.sub(r"\\end\{center\}\s*\\newline", r"\\end{center}", tex_content)
                tex_content = re.sub(r"\\newline\s*\\includegraphics", r"\\includegraphics", tex_content)
                tex.append(r"\item " + tex_content)

                if q.get("diagram"):
                    diags = self.app_logic._parse_diagram_json(q.get("diagram"))
                    for i, d in enumerate(diags):
                        try:
                            d_clean = d.split(",")[-1] if "," in d else d
                            img_data = base64.b64decode(d_clean)
                            img_filename = f"diagram_{q['id']}_{i}.png"
                            img_filepath = os.path.join(img_dir, img_filename)
                            with open(img_filepath, "wb") as f:
                                f.write(img_data)

                            rel_img_path = f"{img_dir_name}/{img_filename}".replace("\\", "/")
                            tex.append(r"\begin{center}")
                            tex.append(rf"\includegraphics[width=0.6\textwidth]{{{rel_img_path}}}")
                            tex.append(r"\end{center}")
                        except Exception as e:
                            logger.error(f"Failed to export diagram {i} for Q {q['id']}: {e}")

                tex.append(r"\vspace{0.5em}")

            tex.append(r"\end{enumerate}")
            tex.append(r"\end{document}")

            with open(export_tex_path, "w", encoding="utf-8") as f:
                f.write("\n".join(tex))

            self.status.emit("⏳ 正在后台调用 xelatex 编译 PDF，请稍候...")

            pdf_success = False
            error_msg = ""
            try:
                result = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "--no-shell-escape", f"-output-directory={export_dir}", export_tex_path],
                    cwd=export_dir,
                    capture_output=True,
                    check=False,
                    encoding="utf-8",
                    errors="replace"
                )
                if result.returncode != 0:
                    out_str = result.stdout
                    error_msg = f"LaTeX 编译错误，部分符号未被 AI 成功转义导致中断。\n日志片段: {out_str[-500:]}"
                    raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
                pdf_success = True
            except FileNotFoundError:
                error_msg = "未检测到本地 LaTeX 编译器 (未安装 TeX Live / MiKTeX)。"
            except subprocess.CalledProcessError as e:
                pass # Handled above
            except Exception as e:
                error_msg = str(e)

            self.finished_export.emit(pdf_success, error_msg if not pdf_success else base_path)

        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            self.finished_export.emit(False, str(e))

class ExportInterface(QWidget):
    def __init__(self, app_logic, parent=None):
        super().__init__(parent=parent)
        self.app_logic = app_logic
        self.setup_ui()

    def setup_ui(self):
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(20, 20, 20, 20)
        self.vBoxLayout.setSpacing(10)

        self.vBoxLayout.addWidget(SubtitleLabel("组卷题目袋 (选中题目可上下移动排序):"))

        mid_layout = QHBoxLayout()
        self.listbox = ListWidget()
        mid_layout.addWidget(self.listbox, 1)

        btn_layout = QVBoxLayout()
        btn_up = PushButton("⬆️ 上移")
        btn_up.clicked.connect(self.bag_move_up)
        btn_down = PushButton("⬇️ 下移")
        btn_down.clicked.connect(self.bag_move_down)
        btn_remove = PushButton("❌ 移除")
        btn_remove.clicked.connect(self.bag_remove)

        btn_layout.addWidget(btn_up)
        btn_layout.addWidget(btn_down)
        btn_layout.addSpacing(20)
        btn_layout.addWidget(btn_remove)
        btn_layout.addStretch(1)

        mid_layout.addLayout(btn_layout)
        self.vBoxLayout.addLayout(mid_layout, 1)

        bottom_layout = QHBoxLayout()
        self.lbl_status = BodyLabel("")
        bottom_layout.addWidget(self.lbl_status, 1)

        btn_export = PrimaryPushButton("🖨️ 导出试卷并自动编译 PDF")
        btn_export.clicked.connect(self.export_paper)
        bottom_layout.addWidget(btn_export)

        self.vBoxLayout.addLayout(bottom_layout)

    def refresh_ui(self):
        self.listbox.clear()
        for idx, item in enumerate(self.app_logic.export_bag):
            preview = item["content"][:40].replace('\n', '')
            has_img = "[含图]" if item["diagram"] else ""
            self.listbox.addItem(QListWidgetItem(f"{idx+1}. {has_img} {preview}..."))

    def bag_move_up(self):
        row = self.listbox.currentRow()
        if row > 0:
            self.app_logic.export_bag.insert(row - 1, self.app_logic.export_bag.pop(row))
            self.refresh_ui()
            self.listbox.setCurrentRow(row - 1)

    def bag_move_down(self):
        row = self.listbox.currentRow()
        if row >= 0 and row < len(self.app_logic.export_bag) - 1:
            self.app_logic.export_bag.insert(row + 1, self.app_logic.export_bag.pop(row))
            self.refresh_ui()
            self.listbox.setCurrentRow(row + 1)

    def bag_remove(self):
        row = self.listbox.currentRow()
        if row >= 0:
            self.app_logic.export_bag.pop(row)
            self.refresh_ui()

    def export_paper(self):
        if not self.app_logic.export_bag:
            MessageBox("提示", "题目袋为空！", self.window()).exec()
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "选择试卷保存位置", "SmartQB_Paper.pdf", "PDF (*.pdf)")
        if not file_path: return

        self.worker = ExportWorker(self.app_logic.export_bag, file_path, self.app_logic)
        self.worker.status.connect(lambda msg: self.lbl_status.setText(msg))
        self.worker.finished_export.connect(self.on_export_finished)
        self.worker.start()

    def on_export_finished(self, success, msg):
        self.lbl_status.setText("")
        if success:
            MessageBox("✅ 自动编译成功", f"文件已保存: {msg}.pdf", self.window()).exec()
        else:
            MessageBox("⚠️ PDF 编译未成功", f"后台转 PDF 失败了。\n\n【失败原因】\n{msg}\n\n您可以手动去检查并编译 .tex 文件。", self.window()).exec()
