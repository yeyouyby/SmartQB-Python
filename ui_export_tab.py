import os
import re
import base64
import subprocess
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QListWidget, QFileDialog
from qfluentwidgets import (
    SubtitleLabel, BodyLabel, PushButton, PrimaryPushButton, MessageBox
)
from utils import logger
from background_tasks import WorkerThread

class ExportTab(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.settings = parent.settings
        self.ai_service = parent.ai_service
        self.setObjectName('Export'.replace(' ', '-'))
        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 16, 16, 16)

        self._build_ui()

    def _build_ui(self):
        container = QFrame(self)
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(20, 20, 20, 20)
        self.vBoxLayout.addWidget(container)

        v_layout.addWidget(SubtitleLabel("组卷题目袋 (选中题目可上下移动排序):"))

        middle_frame = QFrame(container)
        h_layout = QHBoxLayout(middle_frame)
        h_layout.setContentsMargins(0, 0, 0, 0)

        self.listbox_bag = QListWidget(middle_frame)
        self.listbox_bag.setStyleSheet("font-family: 微软雅黑; font-size: 14px;")
        h_layout.addWidget(self.listbox_bag, 1)

        btn_frame = QFrame(middle_frame)
        btn_layout = QVBoxLayout(btn_frame)
        btn_layout.setContentsMargins(10, 0, 0, 0)

        btn_move_up = PushButton("⬆️ 上移")
        btn_move_down = PushButton("⬇️ 下移")
        btn_remove = PushButton("❌ 移除")

        btn_move_up.clicked.connect(self.bag_move_up)
        btn_move_down.clicked.connect(self.bag_move_down)
        btn_remove.clicked.connect(self.bag_remove)

        btn_layout.addWidget(btn_move_up)
        btn_layout.addWidget(btn_move_down)
        btn_layout.addStretch(1)
        btn_layout.addWidget(btn_remove)

        h_layout.addWidget(btn_frame)
        v_layout.addWidget(middle_frame, 1)

        bottom_frame = QFrame(container)
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(0, 10, 0, 0)

        self.lbl_export_status = BodyLabel("")
        self.lbl_export_status.setStyleSheet("color: green;")
        bottom_layout.addWidget(self.lbl_export_status)

        bottom_layout.addStretch(1)

        btn_export = PrimaryPushButton("🖨️ 导出试卷并自动编译 PDF")
        btn_export.clicked.connect(self.export_paper)
        bottom_layout.addWidget(btn_export)

        v_layout.addWidget(bottom_frame)

    def refresh_bag_ui(self):
        if hasattr(self, 'listbox_bag'):
            self.listbox_bag.clear()
            for idx, item in enumerate(self.parent_app.export_bag):
                preview = item["content"][:40].replace('\n', '')
                has_img = "[含图]" if item["diagram"] else ""
                self.listbox_bag.addItem(f"{idx+1}. {has_img} {preview}...")

    def bag_move_up(self):
        sel = self.listbox_bag.selectedIndexes()
        if not sel: return
        idx = sel[0].row()
        if idx > 0:
            self.parent_app.export_bag.insert(idx - 1, self.parent_app.export_bag.pop(idx))
            self.refresh_bag_ui()
            self.listbox_bag.setCurrentRow(idx - 1)

    def bag_move_down(self):
        sel = self.listbox_bag.selectedIndexes()
        if not sel: return
        idx = sel[0].row()
        if idx < len(self.parent_app.export_bag) - 1:
            self.parent_app.export_bag.insert(idx + 1, self.parent_app.export_bag.pop(idx))
            self.refresh_bag_ui()
            self.listbox_bag.setCurrentRow(idx + 1)

    def bag_remove(self):
        sel = self.listbox_bag.selectedIndexes()
        if not sel: return
        idx = sel[0].row()
        self.parent_app.export_bag.pop(idx)
        self.refresh_bag_ui()

    def export_paper(self):
        if not self.parent_app.export_bag:
            self.parent_app.notify_warning("提示", "题目袋为空！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "选择试卷保存位置", "SmartQB_Paper", "PDF 输出目标 (*.*)"
        )
        if not file_path:
            return

        base_path, _ = os.path.splitext(file_path)
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

        for q in self.parent_app.export_bag:
            tex_content = q["content"].replace("\n", " \\newline ")
            tex_content = re.sub(r"\\newline\s*\\begin\{center\}", r"\\begin{center}", tex_content)
            tex_content = re.sub(r"\\newline\s*\\end\{center\}", r"\\end{center}", tex_content)
            tex_content = re.sub(r"\\end\{center\}\s*\\newline", r"\\end{center}", tex_content)
            tex_content = re.sub(r"\\newline\s*\\includegraphics", r"\\includegraphics", tex_content)
            tex.append(r"\item " + tex_content)

            if q.get("diagram"):
                diags = self.parent_app._parse_diagram_json(q.get("diagram"))
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

        self.lbl_export_status.setText("⏳ 正在后台调用 xelatex 编译 PDF，请稍候...")
        self.lbl_export_status.setStyleSheet("color: blue;")

        def compile_task():
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
                    raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=error_msg)
                return True, base_path
            except FileNotFoundError:
                raise Exception("未检测到本地 LaTeX 编译器 (未安装 TeX Live / MiKTeX)。")
            except subprocess.CalledProcessError as e:
                raise Exception(e.stderr)
            except Exception as e:
                raise Exception(str(e))

        self.worker = WorkerThread(compile_task)
        def on_done(res):
            success, path = res
            self.lbl_export_status.setText("")
            if success:
                self.parent_app.notify_success("✅ 自动编译成功", f"文件已保存: {path}.pdf")
            else:
                self.parent_app.notify_warning("⚠️ PDF 编译未成功", f"后台转 PDF 失败了。\n\n您可以手动去检查并编译 .tex 文件。")
        def on_err(e):
            self.lbl_export_status.setText("")
            self.parent_app.notify_warning("⚠️ PDF 编译未成功", f"后台转 PDF 失败了。\n\n【失败原因】\n{e}\n\n您可以手动去检查并编译 .tex 文件。")

        self.worker.finished_signal.connect(on_done)
        self.worker.error_signal.connect(on_err)
        self.worker.start()
