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
                result = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", f"-output-directory={export_dir}", export_tex_path],
                    cwd=export_dir,
                    capture_output=True,
                    check=False
                )
                if result.returncode != 0:
                    try:
                        out_str = result.stdout.decode('utf-8', errors='replace')
                    except Exception:
                        out_str = str(result.stdout)
                    error_msg = f"LaTeX 编译错误，部分符号未被 AI 成功转义导致中断。\n日志片段: {out_str[-500:]}"
                    raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
                pdf_success = True
            except FileNotFoundError:
                error_msg = "未检测到本地 LaTeX 编译器 (未安装 TeX Live / MiKTeX)。"
            except subprocess.CalledProcessError as e:
                pass # Handled above
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
    def save_settings(self):
        self.settings.api_key = self.ent_api.get().strip()
        self.settings.base_url = self.ent_base.get().strip()
        self.settings.model_id = self.ent_model.get().strip()

        self.settings.embed_api_key = self.ent_embed_api.get().strip()
        self.settings.embed_base_url = self.ent_embed_base.get().strip()
        self.settings.embed_model_id = self.ent_embed_model.get().strip()

        self.settings.recognition_mode = self.var_rec_mode.get()
        self.settings.use_prm_optimization = self.var_use_prm.get()
        try:
            self.settings.prm_batch_size = max(2, min(15, int(self.ent_prm_batch.get())))
        except ValueError:
            self.settings.prm_batch_size = 3
            self.ent_prm_batch.set(self.settings.prm_batch_size)
            messagebox.showwarning("输入无效", f"“单次并发主切片数”的值无效，已重置为默认值: {self.settings.prm_batch_size}")

        try:
            self.settings.save()
            # Also update AI Service instance settings
            self.ai_service.settings = self.settings
            messagebox.showinfo("成功", "设置保存成功！")
        except Exception as e:
            print(f"Save settings failed: {e}")
            messagebox.showerror("错误", f"保存设置时发生异常:\n{e}")

    def build_settings_tab(self):
        container = ttk.Frame(self.tab_settings)
        container.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        provider_frame = ttk.Frame(container)
        provider_frame.pack(anchor=tk.W, pady=5, fill=tk.X)
        ttk.Label(provider_frame, text="快捷服务商配置:").pack(side=tk.LEFT)
        self.cbo_provider = ttk.Combobox(provider_frame, values=["自定义", "DeepSeek", "Kimi", "GLM (智谱)", "SiliconFlow (硅基)"], width=20, state="readonly")
        self.cbo_provider.current(0)
        self.cbo_provider.pack(side=tk.LEFT, padx=10)
        self.cbo_provider.bind("<<ComboboxSelected>>", self.on_provider_changed)

        ttk.Label(container, text="API Key (将通过系统凭证管理器自动加密):").pack(anchor=tk.W, pady=5)
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

        ttk.Label(container, text="Embedding API Key (系统级加密):").pack(anchor=tk.W, pady=(15, 5))
        self.ent_embed_api = ttk.Entry(container, width=50, show="*")
        self.ent_embed_api.insert(0, self.settings.embed_api_key)
        self.ent_embed_api.pack(anchor=tk.W)

        ttk.Label(container, text="Embedding Base URL:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_embed_base = ttk.Entry(container, width=50)
        self.ent_embed_base.insert(0, self.settings.embed_base_url)
        self.ent_embed_base.pack(anchor=tk.W)

        ttk.Label(container, text="Embedding Model ID:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_embed_model = ttk.Entry(container, width=50)
        self.ent_embed_model.insert(0, self.settings.embed_model_id)
        self.ent_embed_model.pack(anchor=tk.W)

        ttk.Label(container, text="📝 核心图像与文字识别模式:").pack(anchor=tk.W, pady=(20, 5))
        self.var_rec_mode = tk.IntVar(value=self.settings.recognition_mode)
        ttk.Radiobutton(container, text="1. 仅本地 OCR (最快且免费，但不做任何AI纠错处理)", variable=self.var_rec_mode, value=1).pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(container, text="2. 本地 OCR + 纯文字 AI 纠错 (省流推荐，AI 仅根据 OCR 文本脑补排版)", variable=self.var_rec_mode, value=2).pack(anchor=tk.W, padx=20, pady=2)
        ttk.Radiobutton(container, text="3. 本地 OCR + Vision 图片 AI 纠错 (精准推荐，AI 结合原图修正 OCR 错误)", variable=self.var_rec_mode, value=3).pack(anchor=tk.W, padx=20, pady=2)

        ttk.Label(container, text="🚀 高级选项:").pack(anchor=tk.W, pady=(20, 5))
        prm_frame = ttk.Frame(container)
        prm_frame.pack(anchor=tk.W, padx=20, fill=tk.X)
        self.var_use_prm = tk.BooleanVar(value=self.settings.use_prm_optimization)
        ttk.Checkbutton(prm_frame, text="启用多切片并发", variable=self.var_use_prm).pack(side=tk.LEFT)

        ttk.Label(prm_frame, text="单次并发主切片数 (大于1即启用 PRM 优化):").pack(side=tk.LEFT, padx=(30, 5))
        self.ent_prm_batch = ttk.Spinbox(prm_frame, from_=2, to=15, width=5)
        self.ent_prm_batch.set(self.settings.prm_batch_size)
        self.ent_prm_batch.pack(side=tk.LEFT)

        ttk.Button(container, text="💾 保存所有设置", command=self.save_settings).pack(anchor=tk.W, pady=30)
    def on_provider_changed(self, event):
        provider_presets = {
            "DeepSeek": {"base": "https://api.deepseek.com", "model": "deepseek-chat", "embed_base": "", "embed_model": ""},
            "Kimi": {"base": "https://api.moonshot.cn/v1", "model": "kimi-k2.5", "embed_base": "", "embed_model": ""},
            "GLM (智谱)": {
                "base": "https://open.bigmodel.cn/api/paas/v4/",
                "model": "glm-4-plus-0326",
                "embed_base": "https://open.bigmodel.cn/api/paas/v4/",
                "embed_model": "embedding-3",
            },
            "SiliconFlow (硅基)": {
                "base": "https://api.siliconflow.cn/v1",
                "model": "deepseek-ai/DeepSeek-V3.2",
                "embed_base": "https://api.siliconflow.cn/v1",
                "embed_model": "BAAI/bge-m3",
            },
        }
        provider = self.cbo_provider.get()
        config = provider_presets.get(provider)

        if not config:
            return

        def update_entry(widget, value):
            if value is not None:
                widget.delete(0, tk.END)
                widget.insert(0, value)

        update_entry(self.ent_base, config.get("base"))
        update_entry(self.ent_model, config.get("model"))

        # We only update embed details if they are explicitly mapped.
        # This clears DeepSeek/Kimi embedding fields, indicating no default embedding model.
        update_entry(self.ent_embed_base, config.get("embed_base"))
        update_entry(self.ent_embed_model, config.get("embed_model"))
    def on_tab_changed(self, event):
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        if "Library" in current_tab:
            self.on_hard_search()
        elif "Export" in current_tab:
            self.refresh_bag_ui()

if __name__ == "__main__":
    app = SmartQBApp()
    app.mainloop()