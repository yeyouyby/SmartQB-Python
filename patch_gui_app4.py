with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add embedding dimension logic
old_save_settings = """        try:
            self.settings.prm_batch_size = max(2, min(15, int(self.ent_prm_batch.get())))
        except ValueError:
            self.settings.prm_batch_size = 3
            self.ent_prm_batch.set(self.settings.prm_batch_size)
            messagebox.showwarning("输入无效", f"“单次并发主切片数”的值无效，已重置为默认值: {self.settings.prm_batch_size}")

        try:
            self.settings.save()"""

new_save_settings = """        try:
            self.settings.prm_batch_size = max(2, min(15, int(self.ent_prm_batch.get())))
        except ValueError:
            self.settings.prm_batch_size = 3
            self.ent_prm_batch.set(self.settings.prm_batch_size)
            messagebox.showwarning("输入无效", f"“单次并发主切片数”的值无效，已重置为默认值: {self.settings.prm_batch_size}")

        try:
            self.settings.embedding_dimension = int(self.ent_embed_dim.get().strip())
        except ValueError:
            self.settings.embedding_dimension = 1536
            self.ent_embed_dim.delete(0, 'end')
            self.ent_embed_dim.insert(0, '1536')

        try:
            self.settings.save()"""

if old_save_settings in content:
    content = content.replace(old_save_settings, new_save_settings)

old_settings_embed = """        ttk.Label(container, text="Embedding Model ID:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_embed_model = ttk.Entry(container, width=50)
        self.ent_embed_model.insert(0, self.settings.embed_model_id)
        self.ent_embed_model.pack(anchor=tk.W)"""

new_settings_embed = """        ttk.Label(container, text="Embedding Model ID:").pack(anchor=tk.W, pady=(15, 5))
        self.ent_embed_model = ttk.Entry(container, width=50)
        self.ent_embed_model.insert(0, self.settings.embed_model_id)
        self.ent_embed_model.pack(anchor=tk.W)

        ttk.Label(container, text="Embedding 向量维度 (与模型输出一致，否则报错):").pack(anchor=tk.W, pady=(15, 5))
        self.ent_embed_dim = ttk.Entry(container, width=15)
        self.ent_embed_dim.insert(0, str(getattr(self.settings, 'embedding_dimension', 1536)))
        self.ent_embed_dim.pack(anchor=tk.W)"""

if old_settings_embed in content:
    content = content.replace(old_settings_embed, new_settings_embed)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
