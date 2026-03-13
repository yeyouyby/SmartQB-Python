# gui_app.py
import os
import io
import json
import sqlite3
import threading
import base64
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from pix2text import Pix2Text

from config import DB_NAME
from settings_manager import SettingsManager
from ai_service import AIService
from document_service import DocumentService
from search_service import vector_search_db

# ==========================================
# 主应用 GUI
# ==========================================
class SmartQBApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SmartQB Pro V3 - 智能题库桌面端 (完整版)")
        self.geometry("1300x850")
        
        self.settings = SettingsManager()
        self.ai_service = AIService(self.settings)
        
        print("正在加载 Pix2Text 引擎 (首次启动可能需要下载模型，请耐心等待)...")
        self.ocr_engine = Pix2Text.from_config()
        print("Pix2Text 引擎加载完成！")
        
        self.staging_questions = []
        self.export_bag = []
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.tab_import = ttk.Frame(self.notebook)
        self.tab_manual = ttk.Frame(self.notebook) 
        self.tab_library = ttk.Frame(self.notebook)
        self.tab_export = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_import, text="1. 文件导入与审阅 (Import)")
        self.notebook.add(self.tab_manual, text="➕ 手动单题录入")
        self.notebook.add(self.tab_library, text="2. 题库维护 (Library)")
        self.notebook.add(self.tab_export, text="3. 题目袋组卷 (Export)")
        self.notebook.add(self.tab_settings, text="设置 (Settings)")
        
        self.build_import_tab()
        self.build_manual_tab()
        self.build_library_tab()
        self.build_export_tab()
        self.build_settings_tab()
        
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    # ------------------------------------------
    # API 错误拦截
    # ------------------------------------------
    def ask_api_retry_sync(self, error_msg):
        result = [False]
        event = threading.Event()
        def show_dialog():
            dialog = tk.Toplevel(self)
            dialog.title("⚠️ API 请求失败")
            dialog.geometry("450x300")
            dialog.grab_set()

            ttk.Label(dialog, text=f"发生错误:\n{error_msg}", foreground="red", wraplength=430).pack(pady=10)
            
            form_frame = ttk.Frame(dialog)
            form_frame.pack(fill=tk.X, padx=20, pady=5)
            
            ttk.Label(form_frame, text="API Key:").grid(row=0, column=0, sticky=tk.W, pady=5)
            ent_api = ttk.Entry(form_frame, width=35)
            ent_api.insert(0, self.settings.api_key)
            ent_api.grid(row=0, column=1, pady=5)

            ttk.Label(form_frame, text="Base URL:").grid(row=1, column=0, sticky=tk.W, pady=5)
            ent_base = ttk.Entry(form_frame, width=35)
            ent_base.insert(0, self.settings.base_url)
            ent_base.grid(row=1, column=1, pady=5)

            def on_save():
                self.settings.api_key = ent_api.get().strip()
                self.settings.base_url = ent_base.get().strip()
                self.settings.save()
                self.ai_service.settings = self.settings
                result[0] = True
                dialog.destroy()
                event.set()

            def on_cancel():
                result[0] = False
                dialog.destroy()
                event.set()

            btn_frame = ttk.Frame(dialog)
            btn_frame.pack(pady=10)
            ttk.Button(btn_frame, text="💾 保存并继续重试", command=on_save).pack(side=tk.LEFT, padx=10)
            ttk.Button(btn_frame, text="⏭️ 取消并降级跳过", command=on_cancel).pack(side=tk.LEFT, padx=10)
            dialog.protocol("WM_DELETE_WINDOW", on_cancel)

        self.after(0, show_dialog)
        event.wait()
        return result[0]

    # ------------------------------------------
    # Import View
    # ------------------------------------------
    def build_import_tab(self):
        top_frame = ttk.Frame(self.tab_import)
        top_frame.pack(fill=tk.X, pady=5, padx=5)
        
        ttk.Button(top_frame, text="📄 导入 PDF", command=lambda: self.on_import_file("pdf")).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_frame, text="📝 导入 Word", command=lambda: self.on_import_file("word")).pack(side=tk.LEFT, padx=2)
        ttk.Button(top_frame, text="🖼️ 导入单张图片", command=lambda: self.on_import_file("image")).pack(side=tk.LEFT, padx=2)
        
        self.lbl_import_status = ttk.Label(top_frame, text="等待导入...", foreground="blue")
        self.lbl_import_status.pack(side=tk.LEFT, padx=10)
        
        paned = ttk.PanedWindow(self.tab_import, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        
        self.tree_staging = ttk.Treeview(left_frame, columns=("id", "content", "tags"), show="headings")
        self.tree_staging.heading("id", text="序号")
        self.tree_staging.column("id", width=40)
        self.tree_staging.heading("content", text="识别内容预览")
        self.tree_staging.heading("tags", text="标签")
        self.tree_staging.column("tags", width=100)
        self.tree_staging.pack(fill=tk.BOTH, expand=True)
        self.tree_staging.bind('<<TreeviewSelect>>', self.on_staging_select)
        
        ttk.Button(left_frame, text="❌ 彻底删除选中题目", command=self.delete_staging_item).pack(fill=tk.X, pady=2)
        
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)
        
        ttk.Label(right_frame, text="AI 优化后文字内容 (可在此纠错):").pack(anchor=tk.W)
        self.txt_stg_content = tk.Text(right_frame, height=8, font=("Consolas", 10))
        self.txt_stg_content.pack(fill=tk.X, pady=2)
        
        ttk.Label(right_frame, text="AI 打标 (逗号分隔):").pack(anchor=tk.W)
        self.ent_stg_tags = ttk.Entry(right_frame)
        self.ent_stg_tags.pack(fill=tk.X, pady=2)
        ttk.Button(right_frame, text="💾 更新当前题目", command=self.update_stg_item).pack(anchor=tk.E, pady=5)
        
        self.lbl_stg_diagram = ttk.Label(right_frame, text="图样显示区", background="#e0e0e0", anchor=tk.CENTER)
        self.lbl_stg_diagram.pack(fill=tk.BOTH, expand=True, pady=5)
        
        bottom_frame = ttk.Frame(self.tab_import)
        bottom_frame.pack(fill=tk.X, pady=5, padx=5)
        
        ttk.Label(bottom_frame, text="为整个试卷批量追加标签:").pack(side=tk.LEFT)
        self.ent_batch_tag = ttk.Entry(bottom_frame, width=20)
        self.ent_batch_tag.pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="应用批量标签", command=self.apply_batch_tags).pack(side=tk.LEFT)
        
        ttk.Button(bottom_frame, text="✅ 确认暂存区无误，全部保存入库", command=self.save_staging_to_db).pack(side=tk.RIGHT)

    def on_import_file(self, file_type):
        exts = {"pdf": [("PDF", "*.pdf")], "word": [("Word", "*.docx")], "image": [("Image", "*.png;*.jpg;*.jpeg")]}
        file_path = filedialog.askopenfilename(filetypes=exts[file_type])
        if not file_path: return
        self.staging_questions.clear()
        self.refresh_staging_tree()
        threading.Thread(target=self.run_ingestion_pipeline, args=(file_path, file_type), daemon=True).start()

    def run_ingestion_pipeline(self, file_path, file_type):
        self.update_status("正在提取文档切片...")
        pending_slices = []
        mode = self.settings.recognition_mode

        try:
            if file_type in ["pdf", "image"]:
                pending_slices = DocumentService.process_doc_with_layout(
                    file_path, file_type, self.ocr_engine, self.update_status
                )
            elif file_type == "word":
                pending_slices = DocumentService.extract_from_word(file_path)
                
            if mode == 1:
                # 模式 1: 仅 OCR，不走 AI
                for s in pending_slices:
                    self.staging_questions.append({
                        "content": s["text"], "logic": "无 (本地OCR模式)", "tags": ["本地提取"], "diagram": s.get("diagram")
                    })
                self.after(0, self.refresh_staging_tree)
                self.update_status("✅ 本地提取完毕！(未调用 AI)")
                return
                
        except Exception as e:
            self.update_status(f"提取文件失败: {e}")
            return
            
        if not pending_slices:
            self.update_status("✅ 处理完毕！没有提取到文字。")
            return
            
        # 模式 2 & 3 的核心处理循环
        use_vision = (mode == 3 and file_type != "word")
        batch_size = self.settings.prm_batch_size if self.settings.use_prm_optimization else 1
        
        current_idx = 0
        while current_idx < len(pending_slices):
            end_idx = min(current_idx + batch_size + 1, len(pending_slices))
            
            slices_to_send = []
            for i in range(current_idx, end_idx):
                slices_to_send.append({
                    "index": i,
                    "text": pending_slices[i]["text"],
                    "image_b64": pending_slices[i].get("image_b64", "")
                })

            desc = "多模态视觉版面合并中" if use_vision else "纯文本版面合并中"
            self.update_status(f"AI {desc}: 窗口 {current_idx} ~ {end_idx-1} / {len(pending_slices)}...")

            try:
                ai_res = self.ai_service.process_slices_with_context(slices_to_send, use_vision=use_vision)
                questions = ai_res.get("Questions", [])
                
                next_index = ai_res.get("NextIndex", current_idx + 1)
                if next_index <= current_idx:
                    next_index = current_idx + 1

                for q in questions:
                    source_indices = q.get("SourceSliceIndices", [])
                    diagram = None
                    for idx in source_indices:
                        if idx < len(pending_slices) and pending_slices[idx].get("diagram"):
                            diagram = pending_slices[idx]["diagram"]
                            break

                    self.staging_questions.append({
                        "content": q.get("Content", ""),
                        "logic": q.get("LogicDescriptor", ""),
                        "tags": q.get("Tags", []),
                        "diagram": diagram
                    })

                self.after(0, self.refresh_staging_tree)
                current_idx = next_index 

            except Exception as e:
                print(f"AI 处理异常: {e}")
                if self.ask_api_retry_sync(str(e)):
                    continue
                else:
                    # 降级：放弃批次，保存源数据
                    fallback_end = min(current_idx + batch_size, len(pending_slices))
                    if fallback_end == current_idx: fallback_end += 1
                    for i in range(current_idx, fallback_end):
                        self.staging_questions.append({
                            "content": pending_slices[i]["text"],
                            "logic": "API 失败，未解析",
                            "tags": ["API错误", "需人工校对"],
                            "diagram": pending_slices[i].get("diagram")
                        })
                    self.after(0, self.refresh_staging_tree)
                    current_idx = fallback_end

        self.update_status("✅ 文件全部处理并关联合并完毕！")

    def update_status(self, text):
        self.after(0, lambda: self.lbl_import_status.config(text=text))

    def refresh_staging_tree(self):
        for i in self.tree_staging.get_children(): self.tree_staging.delete(i)
        for idx, q in enumerate(self.staging_questions):
            preview = q["content"][:40].replace('\n', ' ')
            self.tree_staging.insert("", tk.END, iid=str(idx), values=(idx+1, preview, ",".join(q["tags"])))

    def on_staging_select(self, event):
        sel = self.tree_staging.selection()
        if not sel: return
        q = self.staging_questions[int(sel[0])]
        self.txt_stg_content.delete("1.0", tk.END); self.txt_stg_content.insert(tk.END, q["content"])
        self.ent_stg_tags.delete(0, tk.END); self.ent_stg_tags.insert(0, ",".join(q["tags"]))
        if q["diagram"]:
            img = Image.open(io.BytesIO(base64.b64decode(q["diagram"]))).copy()
            img.thumbnail((400, 300))
            photo = ImageTk.PhotoImage(img)
            self.lbl_stg_diagram.config(image=photo, text=""); self.lbl_stg_diagram.image = photo 
        else:
            self.lbl_stg_diagram.config(image='', text="无图样附图")

    def update_stg_item(self):
        sel = self.tree_staging.selection()
        if not sel: return
        idx = int(sel[0])
        self.staging_questions[idx]["content"] = self.txt_stg_content.get("1.0", tk.END).strip()
        self.staging_questions[idx]["tags"] = [t.strip() for t in self.ent_stg_tags.get().split(",") if t.strip()]
        self.refresh_staging_tree()

    def delete_staging_item(self):
        sel = self.tree_staging.selection()
        if not sel: return
        if messagebox.askyesno("警告", "确定要彻底删除该暂存区的题目吗？"):
            idx = int(sel[0])
            self.staging_questions.pop(idx)
            self.refresh_staging_tree()
            self.txt_stg_content.delete("1.0", tk.END)
            self.ent_stg_tags.delete(0, tk.END)

    def apply_batch_tags(self):
        batch_tag = self.ent_batch_tag.get().strip()
        if not batch_tag: return
        for q in self.staging_questions:
            if batch_tag not in q["tags"]:
                q["tags"].append(batch_tag)
        self.refresh_staging_tree()

    def save_staging_to_db(self):
        if not self.staging_questions: return
        self.update_status("正在生成向量并保存入库...")
        self.update()
        
        conn = sqlite3.connect(DB_NAME); c = conn.cursor()
        for q in self.staging_questions:
            vec = self.ai_service.get_embedding(q["logic"] or q["content"])
            c.execute("INSERT INTO questions (content, logic_descriptor, embedding_json, diagram_base64) VALUES (?, ?, ?, ?)",
                      (q["content"], q["logic"], json.dumps(vec) if vec else None, q["diagram"]))
            q_id = c.lastrowid
            for t in q["tags"]:
                c.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (t,))
                c.execute("SELECT id FROM tags WHERE name=?", (t,))
                t_id = c.fetchone()[0]
                c.execute("INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)", (q_id, t_id))
        conn.commit(); conn.close()
        
        self.staging_questions.clear()
        self.refresh_staging_tree()
        self.update_status("入库成功！您可以前往题库查看。")
        messagebox.showinfo("成功", "已全部保存至题库！")

    # ------------------------------------------
    # Manual Input View
    # ------------------------------------------
    def build_manual_tab(self):
        frame = ttk.Frame(self.tab_manual, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="题干文字内容 (支持直接粘贴纯文本):").pack(anchor=tk.W)
        self.txt_manual = tk.Text(frame, height=10, font=("Consolas", 11))
        self.txt_manual.pack(fill=tk.X, pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="✨ 呼叫 AI 自动排版纠错并生成标签", command=self.on_manual_ai).pack(side=tk.LEFT)
        self.lbl_manual_status = ttk.Label(btn_frame, text="", foreground="blue")
        self.lbl_manual_status.pack(side=tk.LEFT, padx=10)
        
        ttk.Label(frame, text="知识点标签 (逗号分隔):").pack(anchor=tk.W, pady=(10,0))
        self.ent_manual_tags = ttk.Entry(frame)
        self.ent_manual_tags.pack(fill=tk.X, pady=5)
        
        ttk.Button(frame, text="💾 保存并直接入库", command=self.save_manual).pack(anchor=tk.E, pady=20)

    def on_manual_ai(self):
        text = self.txt_manual.get("1.0", tk.END).strip()
        if not text: return
        self.lbl_manual_status.config(text="AI 分析中...")
        def task():
            while True:
                try:
                    res = self.ai_service.process_text_with_correction(text)
                    self.after(0, lambda: self.txt_manual.delete("1.0", tk.END))
                    self.after(0, lambda: self.txt_manual.insert(tk.END, res.get("Content", "")))
                    self.after(0, lambda: self.ent_manual_tags.delete(0, tk.END))
                    self.after(0, lambda: self.ent_manual_tags.insert(0, ",".join(res.get("Tags", []))))
                    self.after(0, lambda: self.lbl_manual_status.config(text="AI 处理完成！请核对后保存。"))
                    break
                except Exception as e:
                    if self.ask_api_retry_sync(str(e)):
                        continue
                    else:
                        self.after(0, lambda: self.lbl_manual_status.config(text=f"AI 处理已取消。"))
                        break
        threading.Thread(target=task, daemon=True).start()

    def save_manual(self):
        content = self.txt_manual.get("1.0", tk.END).strip()
        if not content: return
        tags = [t.strip() for t in self.ent_manual_tags.get().split(",") if t.strip()]
        
        conn = sqlite3.connect(DB_NAME); c = conn.cursor()
        vec = self.ai_service.get_embedding(content)
        c.execute("INSERT INTO questions (content, embedding_json) VALUES (?, ?)", (content, json.dumps(vec) if vec else None))
        q_id = c.lastrowid
        for t in tags:
            c.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (t,))
            c.execute("SELECT id FROM tags WHERE name=?", (t,))
            t_id = c.fetchone()[0]
            c.execute("INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)", (q_id, t_id))
        conn.commit(); conn.close()
        self.txt_manual.delete("1.0", tk.END); self.ent_manual_tags.delete(0, tk.END)
        messagebox.showinfo("成功", "手工录入成功，已存入题库！")

    # ------------------------------------------
    # Library View
    # ------------------------------------------
    def build_library_tab(self):
        top_frame = ttk.Frame(self.tab_library)
        top_frame.pack(fill=tk.X, pady=5, padx=5)
        self.ent_lib_search = ttk.Entry(top_frame, width=30)
        self.ent_lib_search.pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="🔍 搜索题库 (硬匹配)", command=self.on_hard_search).pack(side=tk.LEFT)
        
        main_paned = ttk.PanedWindow(self.tab_library, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=3)
        
        self.tree_lib = ttk.Treeview(left_frame, columns=("id", "content"), show="headings", height=8)
        self.tree_lib.heading("id", text="ID"); self.tree_lib.column("id", width=40)
        self.tree_lib.heading("content", text="题目内容")
        self.tree_lib.pack(fill=tk.BOTH, expand=True)
        self.tree_lib.bind('<<TreeviewSelect>>', self.on_lib_select)
        
        det_frame = ttk.LabelFrame(left_frame, text="题目详情与修改")
        det_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.txt_lib_det = tk.Text(det_frame, height=5, font=("Consolas", 10))
        self.txt_lib_det.pack(fill=tk.BOTH, expand=True, pady=2)
        
        action_frame = ttk.Frame(det_frame)
        action_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(action_frame, text="当前标签:").pack(side=tk.LEFT)
        self.ent_lib_tags = ttk.Entry(action_frame, width=30)
        self.ent_lib_tags.pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="更新标签", command=self.update_lib_tags).pack(side=tk.LEFT)
        
        ttk.Button(action_frame, text="🛍️ 加入题目袋", command=self.add_to_bag).pack(side=tk.LEFT, padx=10)
        ttk.Button(action_frame, text="🗑️ 彻底删除", command=self.delete_lib_question).pack(side=tk.RIGHT)
        
        right_frame = ttk.LabelFrame(main_paned, text="AI 软搜索助手 (MCP)")
        main_paned.add(right_frame, weight=2)
        
        self.txt_chat = tk.Text(right_frame, wrap=tk.WORD, font=("微软雅黑", 10), state=tk.DISABLED)
        self.txt_chat.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        chat_bot_frame = ttk.Frame(right_frame)
        chat_bot_frame.pack(fill=tk.X, pady=2)
        
        self.ent_chat = ttk.Entry(chat_bot_frame)
        self.ent_chat.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ent_chat.bind("<Return>", lambda e: self.on_ai_chat())
        ttk.Button(chat_bot_frame, text="发送", command=self.on_ai_chat).pack(side=tk.RIGHT)
        
        self.chat_history = [
            {"role": "system", "content": "你是 SmartQB 的寻题助手。你可以理解用户的寻题需求，调用 search_database 工具查询题库向量。如果用户要求将某些题加入题目袋/试卷，请调用 add_to_bag 工具。"}
        ]
        self.append_chat("🤖 助手", "您好！想找什么样的题目？(例如：帮我找两道关于导数极值的题，并加入题目袋)")

    def append_chat(self, sender, text):
        self.txt_chat.config(state=tk.NORMAL)
        self.txt_chat.insert(tk.END, f"{sender}: {text}\n\n")
        self.txt_chat.see(tk.END)
        self.txt_chat.config(state=tk.DISABLED)

    def on_ai_chat(self):
        user_text = self.ent_chat.get().strip()
        if not user_text: return
        self.ent_chat.delete(0, tk.END)
        self.append_chat("🧑 你", user_text)
        
        self.chat_history.append({"role": "user", "content": user_text})
        
        def task():
            try:
                callbacks = {
                    "search_database": lambda query: vector_search_db(self.ai_service, query),
                    "add_to_bag": lambda question_ids: self.ai_add_to_bag(question_ids)
                }
                res_text, updated_history = self.ai_service.chat_with_tools(
                    self.chat_history, 
                    callbacks=callbacks
                )
                self.chat_history = updated_history
                self.chat_history.append({"role": "assistant", "content": res_text})
                self.after(0, lambda: self.append_chat("🤖 助手", res_text))
            except Exception as e:
                self.after(0, lambda: self.append_chat("⚠️ 系统", f"请求出错: {e}"))
                
        threading.Thread(target=task, daemon=True).start()

    def on_hard_search(self):
        kw = self.ent_lib_search.get().strip()
        conn = sqlite3.connect(DB_NAME); c = conn.cursor()
        if kw:
            c.execute("SELECT DISTINCT q.id, q.content FROM questions q LEFT JOIN question_tags qt ON q.id = qt.question_id LEFT JOIN tags t ON qt.tag_id = t.id WHERE q.content LIKE ? OR t.name LIKE ?", (f'%{kw}%', f'%{kw}%'))
        else:
            c.execute("SELECT id, content FROM questions ORDER BY id DESC")
        rows = c.fetchall()
        conn.close()
        for i in self.tree_lib.get_children(): self.tree_lib.delete(i)
        for r in rows: self.tree_lib.insert("", tk.END, values=(r[0], r[1][:60].replace('\n',' ')))

    def on_lib_select(self, event):
        sel = self.tree_lib.selection()
        if not sel: return
        self.current_lib_q_id = self.tree_lib.item(sel[0])["values"][0]
        conn = sqlite3.connect(DB_NAME); c = conn.cursor()
        c.execute("SELECT content FROM questions WHERE id=?", (self.current_lib_q_id,))
        self.txt_lib_det.delete("1.0", tk.END); self.txt_lib_det.insert(tk.END, c.fetchone()[0])
        c.execute("SELECT t.name FROM tags t JOIN question_tags qt ON t.id=qt.tag_id WHERE qt.question_id=?", (self.current_lib_q_id,))
        self.ent_lib_tags.delete(0, tk.END); self.ent_lib_tags.insert(0, ",".join([r[0] for r in c.fetchall()]))
        conn.close()

    def update_lib_tags(self):
        if not hasattr(self, 'current_lib_q_id'): return
        new_tags = [t.strip() for t in self.ent_lib_tags.get().split(',') if t.strip()]
        conn = sqlite3.connect(DB_NAME); c = conn.cursor()
        c.execute("DELETE FROM question_tags WHERE question_id=?", (self.current_lib_q_id,))
        for t in new_tags:
            c.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (t,))
            c.execute("SELECT id FROM tags WHERE name=?", (t,))
            c.execute("INSERT INTO question_tags (question_id, tag_id) VALUES (?, ?)", (self.current_lib_q_id, c.fetchone()[0]))
        conn.commit(); conn.close()
        messagebox.showinfo("成功", "标签修改成功！")

    def delete_lib_question(self):
        if not hasattr(self, 'current_lib_q_id'): return
        if messagebox.askyesno("危险操作", "确定要彻底删除该题目吗？不可恢复！"):
            conn = sqlite3.connect(DB_NAME); c = conn.cursor()
            c.execute("DELETE FROM question_tags WHERE question_id=?", (self.current_lib_q_id,))
            c.execute("DELETE FROM questions WHERE id=?", (self.current_lib_q_id,))
            conn.commit(); conn.close()
            
            self.export_bag = [q for q in self.export_bag if q["id"] != self.current_lib_q_id]
            
            self.on_hard_search()
            self.txt_lib_det.delete("1.0", tk.END)
            self.ent_lib_tags.delete(0, tk.END)
            messagebox.showinfo("成功", "题目已彻底删除！")

    def add_to_bag(self):
        if not hasattr(self, 'current_lib_q_id'): return
        if any(item['id'] == self.current_lib_q_id for item in self.export_bag):
            messagebox.showinfo("提示", "该题已在题目袋中。")
            return
        conn = sqlite3.connect(DB_NAME); c = conn.cursor()
        c.execute("SELECT content, diagram_base64 FROM questions WHERE id=?", (self.current_lib_q_id,))
        row = c.fetchone(); conn.close()
        if row:
            self.export_bag.append({"id": self.current_lib_q_id, "content": row[0], "diagram": row[1]})
            messagebox.showinfo("成功", "已加入题目袋！")

    def ai_add_to_bag(self, question_ids):
        added = 0
        conn = sqlite3.connect(DB_NAME); c = conn.cursor()
        for q_id in question_ids:
            if any(item['id'] == q_id for item in self.export_bag): continue
            c.execute("SELECT content, diagram_base64 FROM questions WHERE id=?", (q_id,))
            row = c.fetchone()
            if row:
                self.export_bag.append({"id": q_id, "content": row[0], "diagram": row[1]})
                added += 1
        conn.close()
        self.after(0, self.refresh_bag_ui)
        return {"status": "success", "message": f"成功加入了 {added} 道题目到题目袋"}

    # ------------------------------------------
    # Export View
    # ------------------------------------------
    def build_export_tab(self):
        top_frame = ttk.Frame(self.tab_export)
        top_frame.pack(fill=tk.X, pady=5, padx=10)
        ttk.Label(top_frame, text="组卷题目袋 (选中题目可上下移动排序):", font=("", 12, "bold")).pack(side=tk.LEFT)
        
        middle_frame = ttk.Frame(self.tab_export)
        middle_frame.pack(fill=tk.BOTH, expand=True, padx=10)
        
        self.listbox_bag = tk.Listbox(middle_frame, font=("微软雅黑", 10))
        self.listbox_bag.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        btn_frame = ttk.Frame(middle_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        
        ttk.Button(btn_frame, text="⬆️ 上移", command=self.bag_move_up).pack(pady=5)
        ttk.Button(btn_frame, text="⬇️ 下移", command=self.bag_move_down).pack(pady=5)
        ttk.Button(btn_frame, text="❌ 移除", command=self.bag_remove).pack(pady=20)
        
        bottom_frame = ttk.Frame(self.tab_export)
        bottom_frame.pack(fill=tk.X, pady=10, padx=10)
        
        self.lbl_export_status = ttk.Label(bottom_frame, text="", foreground="green")
        self.lbl_export_status.pack(side=tk.LEFT, padx=10)
        ttk.Button(bottom_frame, text="🖨️ 导出试卷并自动编译 PDF", command=self.export_paper).pack(side=tk.RIGHT)

    def refresh_bag_ui(self):
        if hasattr(self, 'listbox_bag'):
            self.listbox_bag.delete(0, tk.END)
            for idx, item in enumerate(self.export_bag):
                preview = item["content"][:40].replace('\n', '')
                has_img = "[含图]" if item["diagram"] else ""
                self.listbox_bag.insert(tk.END, f"{idx+1}. {has_img} {preview}...")

    def bag_move_up(self):
        sel = self.listbox_bag.curselection()
        if not sel: return
        idx = sel[0]
        if idx > 0:
            self.export_bag.insert(idx - 1, self.export_bag.pop(idx))
            self.refresh_bag_ui()
            self.listbox_bag.select_set(idx - 1)

    def bag_move_down(self):
        sel = self.listbox_bag.curselection()
        if not sel: return
        idx = sel[0]
        if idx < len(self.export_bag) - 1:
            self.export_bag.insert(idx + 1, self.export_bag.pop(idx))
            self.refresh_bag_ui()
            self.listbox_bag.select_set(idx + 1)

    def bag_remove(self):
        sel = self.listbox_bag.curselection()
        if not sel: return
        idx = sel[0]
        self.export_bag.pop(idx)
        self.refresh_bag_ui()

    def export_paper(self):
        if not self.export_bag:
            messagebox.showwarning("提示", "题目袋为空！")
            return
            
        file_path = filedialog.asksaveasfilename(
            title="选择试卷保存位置", 
            initialfile="SmartQB_Paper",
            filetypes=[("PDF 输出目标", "*.*")]
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
            r"\geometry{left=2cm, right=2cm, top=2.5cm, bottom=2.5cm}",
            r"\begin{document}",
            r"\begin{center}",
            r"\Large\textbf{SmartQB 导出试卷}",
            r"\end{center}",
            r"\vspace{1em}",
            r"\begin{enumerate}"
        ]

        for q in self.export_bag:
            tex_content = q["content"]
            tex.append(r"\item " + tex_content)

            if q.get("diagram"):
                img_data = base64.b64decode(q["diagram"])
                img_filename = f"diagram_{q['id']}.png"
                img_filepath = os.path.join(img_dir, img_filename)
                with open(img_filepath, "wb") as f:
                    f.write(img_data)
                
                rel_img_path = f"{img_dir_name}/{img_filename}".replace("\\", "/")
                tex.append(r"\begin{center}")
                tex.append(rf"\includegraphics[width=0.6\textwidth]{{{rel_img_path}}}")
                tex.append(r"\end{center}")
            
            tex.append(r"\vspace{0.5em}")
            
        tex.append(r"\end{enumerate}")
        tex.append(r"\end{document}")
        
        with open(export_tex_path, "w", encoding="utf-8") as f:
            f.write("\n".join(tex))
            
        self.lbl_export_status.config(text="⏳ 正在后台调用 xelatex 编译 PDF，请稍候...", foreground="blue")
        self.update()
        
        def compile_pdf():
            pdf_success = False
            error_msg = ""
            try:
                subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", f"-output-directory={export_dir}", export_tex_path],
                    cwd=export_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                pdf_success = True
            except FileNotFoundError:
                error_msg = "未检测到本地 LaTeX 编译器 (未安装 TeX Live / MiKTeX)。"
            except subprocess.CalledProcessError as e:
                error_msg = f"LaTeX 编译错误，部分符号未被 AI 成功转义导致中断。\n日志片段: {e.stdout[-500:]}"
            except Exception as e:
                error_msg = str(e)
                
            def on_finish():
                self.lbl_export_status.config(text="")
                if pdf_success:
                    messagebox.showinfo("✅ 自动编译成功", f"文件已保存: {base_path}.pdf")
                else:
                    messagebox.showwarning("⚠️ PDF 编译未成功", f"后台转 PDF 失败了。\n\n【失败原因】\n{error_msg}\n\n您可以手动去检查并编译 .tex 文件。")
            self.after(0, on_finish)

        threading.Thread(target=compile_pdf, daemon=True).start()

    # ------------------------------------------
    # Settings View
    # ------------------------------------------
    def build_settings_tab(self):
        container = ttk.Frame(self.tab_settings)
        container.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)
        
        ttk.Label(container, text="API Key:").pack(anchor=tk.W, pady=5)
        self.ent_api = ttk.Entry(container, width=50, show="*")
        self.ent_api.insert(0, self.settings.api_key)
        self.ent_api.pack(anchor=tk.W)
        
        ttk.Label(container, text="Base URL:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_base = ttk.Entry(container, width=50)
        self.ent_base.insert(0, self.settings.base_url)
        self.ent_base.pack(anchor=tk.W)
        
        ttk.Label(container, text="Model ID:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_model = ttk.Entry(container, width=50)
        self.ent_model.insert(0, self.settings.model_id)
        self.ent_model.pack(anchor=tk.W)

        ttk.Label(container, text="📝 核心图像与文字识别模式:").pack(anchor=tk.W, pady=(20, 5))
        self.var_rec_mode = tk.IntVar(value=self.settings.recognition_mode)
        ttk.Radiobutton(container, text="1. 仅本地 OCR (最快且免费，但不做任何AI纠错处理)", variable=self.var_rec_mode, value=1).pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(container, text="2. 本地 OCR + 纯文字 AI 纠错 (省流推荐，AI 仅根据 OCR 文本脑补排版)", variable=self.var_rec_mode, value=2).pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(container, text="3. 本地 OCR + Vision 图片 AI 纠错 (精准推荐，AI 结合原图修正 OCR 错误)", variable=self.var_rec_mode, value=3).pack(anchor=tk.W, padx=20, pady=2)

        ttk.Label(container, text="🚀 高级选项:").pack(anchor=tk.W, pady=(20, 5))
        prm_frame = ttk.Frame(container)
        prm_frame.pack(anchor=tk.W, padx=20, fill=tk.X)
        self.var_use_prm = tk.BooleanVar(value=self.settings.use_prm_optimization)
        ttk.Checkbutton(prm_frame, text="启用 PRM 批量优化", variable=self.var_use_prm).pack(side=tk.LEFT)
        
        ttk.Label(prm_frame, text="单次并发主切片数:").pack(side=tk.LEFT, padx=(30, 5))
        self.ent_prm_batch = ttk.Spinbox(prm_frame, from_=2, to=15, width=5)
        self.ent_prm_batch.set(self.settings.prm_batch_size)
        self.ent_prm_batch.pack(side=tk.LEFT)
        
        ttk.Button(container, text="💾 保存所有设置", command=self.save_settings).pack(anchor=tk.W, pady=30)

    def save_settings(self):
        self.settings.api_key = self.ent_api.get().strip()
        self.settings.base_url = self.ent_base.get().strip()
        self.settings.model_id = self.ent_model.get().strip()
        self.settings.recognition_mode = self.var_rec_mode.get()
        self.settings.use_prm_optimization = self.var_use_prm.get()
        try:
            self.settings.prm_batch_size = int(self.ent_prm_batch.get())
        except:
            self.settings.prm_batch_size = 3
        self.settings.save()
        
        self.ai_service.settings = self.settings
        messagebox.showinfo("成功", "设置已保存！新的识别模式即刻生效。")

    def on_tab_changed(self, event):
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        if "Library" in current_tab:
            self.on_hard_search()
        elif "Export" in current_tab:
            self.refresh_bag_ui()

if __name__ == "__main__":
    app = SmartQBApp()
    app.mainloop()