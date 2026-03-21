import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add _resolve_markers_and_extract_diagrams helper
helper_method = """    def _parse_diagram_json(self, diag_data):
        if not diag_data:
            return []
        if isinstance(diag_data, list):
            return diag_data
        if str(diag_data).startswith('['):
            try:
                parsed_list = json.loads(diag_data)
                if isinstance(parsed_list, list) and parsed_list:
                    return parsed_list
            except json.JSONDecodeError as e:
                from utils import logger
                logger.debug(f"Failed to decode diagram JSON: {e}")
        return [diag_data]

    def _resolve_markers_and_extract_diagrams(self, content_text, combined_d_map):
        marker_pattern = re.compile(r'\[\[\{ima_dont_del_(\d+_\d+)\}\]\]')
        matches = marker_pattern.findall(content_text)
        diagrams_list = []
        if matches:
            unique_matches = list(dict.fromkeys(matches))
            for marker_idx in unique_matches:
                found = False
                if marker_idx in combined_d_map:
                    diagrams_list.append(combined_d_map[marker_idx])
                    found = True
                elif str(marker_idx) in combined_d_map:
                    diagrams_list.append(combined_d_map[str(marker_idx)])
                    found = True

            resolved_markers = []
            for m in unique_matches:
                if m in combined_d_map or str(m) in combined_d_map:
                    resolved_markers.append(m)
            if resolved_markers:
                for m in resolved_markers:
                    content_text = content_text.replace(f"[[{{ima_dont_del_{m}}}]]", "")
                content_text = content_text.strip()

        diagram = None
        if len(diagrams_list) == 1:
            diagram = diagrams_list[0]
        elif len(diagrams_list) > 1:
            diagram = json.dumps(diagrams_list)

        return content_text, diagram

    def _clear_staging_ui(self):
        import gc
        for q in self.staging_questions:
            q.pop('diagram', None)
            q.pop('image_b64', None)
            q.pop('page_annotated_b64', None)
        self.staging_questions.clear()
        self.txt_stg_content.delete("1.0", tk.END)
        self.ent_stg_tags.delete(0, tk.END)
        if hasattr(self, 'lbl_vector_info'):
            self.lbl_vector_info.config(text="未生成向量")
        self.lbl_stg_diagram.config(image='', text="无图样")
        if hasattr(self.lbl_stg_diagram, 'image'):
            del self.lbl_stg_diagram.image
        gc.collect()

    def check_and_fix_latex(self):
        if not self.staging_questions: return
        self.update_status("正在检查 LaTeX 编译...")
        logger.info("Starting LaTeX check for staged questions...")

        import threading
        def task():
            import tempfile, os, subprocess
            from utils import logger

            failed_indices = []
            successful_questions = []

            for idx, q in enumerate(self.staging_questions):
                self.after(0, lambda i=idx: self.update_status(f"正在编译检查第 {i+1}/{len(self.staging_questions)} 题..."))
                content_text = q["content"]
                tex_code = f'''\\documentclass{{article}}\\n\\usepackage{{ctex}}\\n\\usepackage{{amsmath}}\\n\\usepackage{{amssymb}}\\n\\begin{{document}}\\n{content_text}\\n\\end{{document}}'''

                def test_compile(code):
                    with tempfile.TemporaryDirectory() as td:
                        tex_file = os.path.join(td, "test.tex")
                        with open(tex_file, "w", encoding="utf-8") as f_tex:
                            f_tex.write(code)
                        try:
                            res = subprocess.run(["xelatex", "-interaction=nonstopmode", "--no-shell-escape", "test.tex"],
                                                 cwd=td, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
                            if res.returncode == 0:
                                return True, ""
                            else:
                                return False, res.stdout
                        except Exception as e:
                            return False, str(e)

                success, err_msg = test_compile(tex_code)
                if not success:
                    self.after(0, lambda i=idx: self.update_status(f"第 {i+1} 题编译失败，AI 正在尝试修复..."))
                    fixed_content = self.ai_service.ai_fix_latex(content_text, err_msg)
                    if fixed_content:
                        new_tex_code = f'''\\documentclass{{article}}\\n\\usepackage{{ctex}}\\n\\usepackage{{amsmath}}\\n\\usepackage{{amssymb}}\\n\\begin{{document}}\\n{fixed_content}\\n\\end{{document}}'''
                        success2, err_msg2 = test_compile(new_tex_code)
                        if success2:
                            q["content"] = fixed_content
                            successful_questions.append((idx, q))
                        else:
                            failed_indices.append(idx)
                    else:
                        failed_indices.append(idx)
                else:
                    successful_questions.append((idx, q))

            def update_ui():
                self.refresh_staging_tree()
                self.update_status(f"LaTeX 检查完成。成功 {len(successful_questions)} 题，失败 {len(failed_indices)} 题。")
                messagebox.showinfo("检查完成", f"成功检查 {len(successful_questions)} 题。有 {len(failed_indices)} 题编译失败。")

            self.after(0, update_ui)

        threading.Thread(target=task, daemon=True).start()

"""

if "def _parse_diagram_json" not in content:
    content = content.replace("    def ask_api_retry_sync(self, error_msg):", helper_method + "    def ask_api_retry_sync(self, error_msg):")


# Handle Mode 1
old_handle_slice_ready = """        def handle_slice_ready(s):
            if mode == 1:
                item = {
                    "content": s["text"], "logic": "无 (本地OCR模式)", "tags": ["本地提取"], "diagram": s.get("diagram"), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            else:
                item = {
                    "content": s["text"], "logic": "等待 AI 处理...", "tags": ["本地提取中"], "diagram": s.get("diagram"), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            def _append_and_refresh():
                self.staging_questions.append(item)
                self.refresh_staging_tree()
            self.after(0, _append_and_refresh)"""

new_handle_slice_ready = """        def handle_slice_ready(s):
            if mode == 1:
                content_text, diagram = self._resolve_markers_and_extract_diagrams(s["text"], s.get("diagram_map", {}))
                item = {
                    "content": content_text, "logic": "无 (本地OCR模式)", "tags": ["本地提取"], "diagram": diagram, "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            else:
                item = {
                    "content": s["text"], "logic": "等待 AI 处理...", "tags": ["本地提取中"], "diagram": s.get("diagram"), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            def _append_and_refresh():
                self.staging_questions.append(item)
                self.refresh_staging_tree()
            self.after(0, _append_and_refresh)"""

if old_handle_slice_ready in content:
    content = content.replace(old_handle_slice_ready, new_handle_slice_ready)


# Extract _process_ai_slices
old_ai_loop = """        use_vision = (mode == 3 and file_type != "word")
        batch_size = self.settings.prm_batch_size if self.settings.use_prm_optimization else 1

        current_idx = 0
        pending_fragment = ""

        while current_idx < len(pending_slices):
            end_idx = min(current_idx + batch_size + 1, len(pending_slices))
            is_last_batch = (end_idx == len(pending_slices))

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
                ai_res = self.ai_service.process_slices_with_context(
                    slices_to_send,
                    use_vision=use_vision,
                    pending_fragment=pending_fragment,
                    is_last_batch=is_last_batch
                )

                questions = ai_res.get("Questions", [])
                pending_fragment = ai_res.get("PendingFragment", "")

                next_index = ai_res.get("NextIndex", current_idx + 1)
                if next_index <= current_idx:
                    next_index = current_idx + 1

                for q in questions:
                    status = q.get("Status", "Complete")
                    if status == "NotQuestion":
                        continue

                    source_indices = q.get("SourceSliceIndices", [])
                    diagram = None
                    image_b64 = ""
                    page_annotated_b64 = ""

                    for idx in source_indices:
                        if 0 <= idx < len(pending_slices):
                            if not image_b64 and pending_slices[idx].get("image_b64"):
                                image_b64 = pending_slices[idx]["image_b64"]
                            if not diagram and pending_slices[idx].get("diagram"):
                                diagram = pending_slices[idx]["diagram"]
                            if not page_annotated_b64 and pending_slices[idx].get("page_annotated_b64"):
                                page_annotated_b64 = pending_slices[idx].get("page_annotated_b64")

                        if diagram and image_b64 and page_annotated_b64:
                            break

                    item = {
                        "content": q.get("Content", ""),
                        "logic": q.get("LogicDescriptor", ""),
                        "tags": q.get("Tags", []),
                        "diagram": diagram,
                        "image_b64": image_b64,
                        "page_annotated_b64": page_annotated_b64
                    }
                    def _safe_append(i=item):
                        self.staging_questions.append(i)
                    self.after(0, _safe_append)

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
                        item = {
                            "content": pending_slices[i]["text"],
                            "logic": "API 失败，未解析",
                            "tags": ["API错误", "需人工校对"],
                            "diagram": pending_slices[i].get("diagram"),
                            "page_annotated_b64": pending_slices[i].get("page_annotated_b64")
                        }
                        def _safe_append_f(itm=item):
                            self.staging_questions.append(itm)
                        self.after(0, _safe_append_f)
                    self.after(0, self.refresh_staging_tree)
                    current_idx = fallback_end

        # 如果结束时还有没处理完的 fragment，尝试把它作为一个单独题目保存
        if pending_fragment and pending_fragment.strip():
            item = {
                "content": pending_fragment,
                "logic": "跨页未完结残段 (合并结束仍遗留)",
                "tags": ["需人工校对"],
                "diagram": None,
                "image_b64": ""
            }
            def _safe_append_rem(itm=item):
                self.staging_questions.append(itm)
            self.after(0, _safe_append_rem)
            self.after(0, self.refresh_staging_tree)

        self.update_status("✅ 文件全部处理并关联合并完毕！")"""

new_ai_loop = """        self._process_ai_slices(pending_slices, mode, file_type)
        self.update_status("✅ 文件全部处理并关联合并完毕！")

    def _process_ai_slices(self, pending_slices, mode, file_type):
        use_vision = (mode == 3 and file_type != "word")
        batch_size = self.settings.prm_batch_size if self.settings.use_prm_optimization else 1

        current_idx = 0
        pending_fragment = ""
        cumulative_d_map = {}

        while current_idx < len(pending_slices):
            end_idx = min(current_idx + batch_size + 1, len(pending_slices))
            is_last_batch = (end_idx == len(pending_slices))

            slices_to_send = []
            for i in range(current_idx, end_idx):
                slices_to_send.append({
                    "index": i,
                    "text": pending_slices[i]["text"],
                    "image_b64": pending_slices[i].get("image_b64", "")
                })
                cumulative_d_map.update(pending_slices[i].get("diagram_map", {}))

            desc = "多模态视觉版面合并中" if use_vision else "纯文本版面合并中"
            self.update_status(f"AI {desc}: 窗口 {current_idx} ~ {end_idx-1} / {len(pending_slices)}...")

            try:
                ai_res = self.ai_service.process_slices_with_context(
                    slices_to_send,
                    use_vision=use_vision,
                    pending_fragment=pending_fragment,
                    is_last_batch=is_last_batch
                )

                questions = ai_res.get("Questions", [])
                pending_fragment = ai_res.get("PendingFragment", "")

                next_index = ai_res.get("NextIndex", current_idx + 1)
                if next_index <= current_idx:
                    next_index = current_idx + 1

                for q in questions:
                    status = q.get("Status", "Complete")
                    if status == "NotQuestion":
                        continue

                    source_indices = q.get("SourceSliceIndices", [])
                    image_b64 = ""
                    page_annotated_b64 = ""
                    content_text = q.get("Content", "")

                    combined_d_map = {}
                    for idx in source_indices:
                        if 0 <= idx < len(pending_slices):
                            if not image_b64 and pending_slices[idx].get("image_b64"):
                                image_b64 = pending_slices[idx]["image_b64"]
                            if not page_annotated_b64 and pending_slices[idx].get("page_annotated_b64"):
                                page_annotated_b64 = pending_slices[idx].get("page_annotated_b64")
                            combined_d_map.update(pending_slices[idx].get("diagram_map", {}))

                    content_text, diagram = self._resolve_markers_and_extract_diagrams(content_text, combined_d_map)

                    item = {
                        "content": content_text,
                        "logic": q.get("LogicDescriptor", ""),
                        "tags": q.get("Tags", []),
                        "diagram": diagram,
                        "image_b64": image_b64,
                        "page_annotated_b64": page_annotated_b64
                    }
                    def _safe_append(i=item):
                        self.staging_questions.append(i)
                    self.after(0, _safe_append)

                self.after(0, self.refresh_staging_tree)
                current_idx = next_index

            except Exception as e:
                from utils import logger
                logger.error(f"AI 处理异常: {e}")
                if self.ask_api_retry_sync(str(e)):
                    continue
                else:
                    # 降级：放弃批次，保存源数据
                    fallback_end = min(current_idx + batch_size, len(pending_slices))
                    if fallback_end == current_idx: fallback_end += 1
                    for i in range(current_idx, fallback_end):
                        raw_text = pending_slices[i]["text"]
                        clean_text, fallback_diagram = self._resolve_markers_and_extract_diagrams(raw_text, pending_slices[i].get("diagram_map", {}))

                        item = {
                            "content": clean_text,
                            "logic": "API 失败，未解析",
                            "tags": ["API错误", "需人工校对"],
                            "diagram": fallback_diagram,
                            "page_annotated_b64": pending_slices[i].get("page_annotated_b64")
                        }
                        def _safe_append_f(itm=item):
                            self.staging_questions.append(itm)
                        self.after(0, _safe_append_f)
                    self.after(0, self.refresh_staging_tree)
                    current_idx = fallback_end

        # 如果结束时还有没处理完的 fragment，尝试把它作为一个单独题目保存
        if pending_fragment and pending_fragment.strip():
            clean_frag, diag_frag = self._resolve_markers_and_extract_diagrams(pending_fragment, cumulative_d_map)
            item = {
                "content": clean_frag,
                "logic": "跨页未完结残段 (合并结束仍遗留)",
                "tags": ["需人工校对"],
                "diagram": diag_frag,
                "image_b64": ""
            }
            def _safe_append_rem(itm=item):
                self.staging_questions.append(itm)
            self.after(0, _safe_append_rem)
            self.after(0, self.refresh_staging_tree)
"""

if old_ai_loop in content:
    content = content.replace(old_ai_loop, new_ai_loop)


# Fix on_staging_select
old_staging_select = """        # Determine what to display (diagram if present, else layout image)
        display_img_b64 = q.get("diagram")
        if not display_img_b64 and q.get("image_b64"):
            display_img_b64 = q.get("image_b64")

        if display_img_b64:
            try:
                img = Image.open(io.BytesIO(base64.b64decode(display_img_b64))).copy()
                img.thumbnail((400, 300))
                photo = ImageTk.PhotoImage(img)
                self.lbl_stg_diagram.config(image=photo, text="")
                self.lbl_stg_diagram.image = photo
            except Exception as e:
                self.lbl_stg_diagram.config(image='', text=f"图片加载失败: {e}")
        else:
            self.lbl_stg_diagram.config(image='', text="无图样附图或切片原图")"""

new_staging_select = """        # Determine what to display (diagram if present)
        display_img_b64 = q.get("diagram")
        self.stg_current_diags = self._parse_diagram_json(display_img_b64)
        self.current_img_index = 0
        self._render_stg_diagram()

    def _render_stg_diagram(self):
        if not hasattr(self, 'stg_current_diags') or not self.stg_current_diags:
            self.lbl_stg_diagram.config(image='', text="无图样")
            if hasattr(self.lbl_stg_diagram, 'image'):
                del self.lbl_stg_diagram.image
            self.lbl_stg_diag_info.config(text="")
            return

        display_img_b64 = self.stg_current_diags[self.current_img_index]
        if display_img_b64:
            try:
                img = Image.open(io.BytesIO(base64.b64decode(display_img_b64))).copy()
                img.thumbnail((400, 300))
                photo = ImageTk.PhotoImage(img)
                self.lbl_stg_diagram.config(image=photo, text="")
                self.lbl_stg_diagram.image = photo

                info_text = f"图样 {self.current_img_index + 1} / {len(self.stg_current_diags)}"
                self.lbl_stg_diag_info.config(text=info_text)
            except Exception as e:
                self.lbl_stg_diagram.config(image='', text=f"图片加载失败: {e}")
                self.lbl_stg_diag_info.config(text="")
        else:
            self.lbl_stg_diagram.config(image='', text="无图样")
            self.lbl_stg_diag_info.config(text="")

    def stg_prev_diagram(self):
        if hasattr(self, 'stg_current_diags') and self.stg_current_diags:
            self.current_img_index = (self.current_img_index - 1) % len(self.stg_current_diags)
            self._render_stg_diagram()

    def stg_next_diagram(self):
        if hasattr(self, 'stg_current_diags') and self.stg_current_diags:
            self.current_img_index = (self.current_img_index + 1) % len(self.stg_current_diags)
            self._render_stg_diagram()

    def stg_delete_diagram(self):
        sel = self.tree_staging.selection()
        if not sel: return
        idx = int(sel[0])

        if hasattr(self, 'stg_current_diags') and self.stg_current_diags:
            del self.stg_current_diags[self.current_img_index]

            q = self.staging_questions[idx]
            if not self.stg_current_diags:
                q["diagram"] = None
            elif len(self.stg_current_diags) == 1:
                q["diagram"] = self.stg_current_diags[0]
            else:
                q["diagram"] = json.dumps(self.stg_current_diags)

            self.current_img_index = max(0, min(self.current_img_index, len(self.stg_current_diags) - 1))
            self._render_stg_diagram()
"""

if old_staging_select in content:
    content = content.replace(old_staging_select, new_staging_select)


# Delete staging item logic refactor
old_delete_staging = """    def delete_staging_item(self):
        sel = self.tree_staging.selection()
        if not sel: return
        if messagebox.askyesno("警告", f"确定要彻底删除选中的 {len(sel)} 道题目吗？"):
            # Delete in reverse order to keep indices valid
            indices = sorted([int(s) for s in sel], reverse=True)
            for idx in indices:
                item = self.staging_questions.pop(idx)
                # Cleanup heavy images
                item.pop('diagram', None)
                item.pop('image_b64', None)
                item.pop('page_annotated_b64', None)
            self.refresh_staging_tree()
            self.txt_stg_content.delete("1.0", tk.END)
            self.ent_stg_tags.delete(0, tk.END)
            if hasattr(self, 'lbl_vector_info'):
                self.lbl_vector_info.config(text="未生成向量")
            self.lbl_stg_diagram.config(image='', text="图样显示区")
            if hasattr(self.lbl_stg_diagram, 'image'):
                del self.lbl_stg_diagram.image
            gc.collect()"""

new_delete_staging = """    def delete_staging_item(self):
        sel = self.tree_staging.selection()
        if not sel: return
        if messagebox.askyesno("警告", f"确定要彻底删除选中的 {len(sel)} 道题目吗？"):
            # Delete in reverse order to keep indices valid
            indices = sorted([int(s) for s in sel], reverse=True)
            for idx in indices:
                item = self.staging_questions.pop(idx)
                # Cleanup heavy images
                item.pop('diagram', None)
                item.pop('image_b64', None)
                item.pop('page_annotated_b64', None)
            self.refresh_staging_tree()
            self._clear_staging_ui()"""

if old_delete_staging in content:
    content = content.replace(old_delete_staging, new_delete_staging)

# Save staging to db refactor
old_save_staging = """    def save_staging_to_db(self):
        if not self.staging_questions: return
        self.update_status("正在检查 LaTeX 编译并准备入库...")
        logger.info("Starting LaTeX check and DB insertion for staged questions...")

        # We need to run this in background thread because compilation takes time
        import threading

        def task():
            from utils import logger
            import tempfile, os, subprocess
            from db_adapter import LanceDBAdapter

            failed_indices = []
            successful_questions = []

            # 1. LaTeX check & Auto Fix
            for idx, q in enumerate(self.staging_questions):
                self.after(0, lambda i=idx: self.update_status(f"正在编译检查第 {i+1}/{len(self.staging_questions)} 题..."))

                content_text = q["content"]

                # Create a minimal tex document to test compilation
                tex_code = f'''\\documentclass{{article}}\\n\\usepackage{{ctex}}\\n\\usepackage{{amsmath}}\\n\\usepackage{{amssymb}}\\n\\begin{{document}}\\n{content_text}\\n\\end{{document}}'''

                def test_compile(code):
                    with tempfile.TemporaryDirectory() as td:
                        tex_file = os.path.join(td, "test.tex")
                        with open(tex_file, "w", encoding="utf-8") as f_tex:
                            f_tex.write(code)
                        try:
                            res = subprocess.run(["xelatex", "-interaction=nonstopmode", "--no-shell-escape", "test.tex"],
                                                 cwd=td, capture_output=True, text=True, timeout=15)
                            if res.returncode == 0:
                                return True, ""
                            else:
                                return False, res.stdout
                        except Exception as e:
                            return False, str(e)

                success, err_msg = test_compile(tex_code)

                if not success:
                    self.after(0, lambda i=idx: self.update_status(f"第 {i+1} 题编译失败，AI 正在尝试修复..."))
                    fixed_content = self.ai_service.ai_fix_latex(content_text, err_msg)
                    if fixed_content:
                        # Test again
                        new_tex_code = f'''\\documentclass{{article}}\\n\\usepackage{{ctex}}\\n\\usepackage{{amsmath}}\\n\\usepackage{{amssymb}}\\n\\begin{{document}}\\n{fixed_content}\\n\\end{{document}}'''
                        success2, err_msg2 = test_compile(new_tex_code)
                        if success2:
                            q["content"] = fixed_content # accept fix
                            successful_questions.append((idx, q))
                        else:
                            failed_indices.append(idx)
                    else:
                        failed_indices.append(idx)
                else:
                    successful_questions.append((idx, q))

            # 2. Save successful questions to DB
            self.after(0, lambda: self.update_status("编译检查完成，正在生成向量并保存..."))
            try:
                adapter = LanceDBAdapter()
                for _, q in successful_questions:
                    vec = q.get("embedding") or self.ai_service.get_embedding(q["logic"] or q["content"])
                    q_id = adapter.execute_insert_question(q["content"], q["logic"], vec, q["diagram"])
                    for t in q["tags"]:
                        if not t: continue
                        t_id = adapter.execute_insert_tag(t)
                        adapter.execute_insert_question_tag(q_id, t_id)
            except Exception as e:
                logger.error(f"DB Insert Error: {e}", exc_info=True)
                self.after(0, lambda err=e: messagebox.showerror("错误", f"数据库保存失败: {err}"))
                return

            # 3. Update UI
            def update_ui():
                import gc
                if not failed_indices:
                    for q in self.staging_questions:
                        q.pop('diagram', None)
                        q.pop('image_b64', None)
                        q.pop('page_annotated_b64', None)
                    self.staging_questions.clear()
                    self.txt_stg_content.delete("1.0", tk.END)
                    self.ent_stg_tags.delete(0, tk.END)
                    self.lbl_stg_diagram.config(image='', text="图样显示区")
                    if hasattr(self.lbl_stg_diagram, 'image'):
                        del self.lbl_stg_diagram.image
                    gc.collect()
                    self.refresh_staging_tree()
                    self.update_status("入库成功！您可以前往题库查看。")
                    logger.info("All staged questions saved to DB successfully.")
                    messagebox.showinfo("成功", "已全部保存至题库！")
                else:
                    # Remove successful ones from staging, keep failed ones
                    for idx, q in reversed(successful_questions):
                        q.pop('diagram', None)
                        q.pop('image_b64', None)
                        q.pop('page_annotated_b64', None)
                        self.staging_questions.pop(idx)

                    self.refresh_staging_tree()
                    self.update_status(f"部分入库完成。保留了 {len(failed_indices)} 道编译失败的题目。")
                    messagebox.showwarning("部分完成", f"已入库成功 {len(successful_questions)} 题。有 {len(failed_indices)} 题由于 LaTeX 编译错误（AI 修复仍失败）未能入库，请手动检查列表中的剩余项。")

            self.after(0, update_ui)

        threading.Thread(target=task, daemon=True).start()"""

new_save_staging = """    def save_staging_to_db(self):
        if not self.staging_questions: return
        self.update_status("正在保存入库...")

        import threading
        def task():
            from utils import logger
            from db_adapter import LanceDBAdapter

            successful_count = 0
            try:
                adapter = LanceDBAdapter()
                for q in self.staging_questions:
                    vec = q.get("embedding") or self.ai_service.get_embedding(q["logic"] or q["content"])
                    q_id = adapter.execute_insert_question(q["content"], q["logic"], vec, q["diagram"])
                    for t in q["tags"]:
                        if not t: continue
                        t_id = adapter.execute_insert_tag(t)
                        adapter.execute_insert_question_tag(q_id, t_id)
                    successful_count += 1
            except Exception as e:
                logger.error(f"DB Insert Error: {e}", exc_info=True)
                self.after(0, lambda err=e: messagebox.showerror("错误", f"数据库保存失败: {err}"))
                return

            def update_ui():
                self._clear_staging_ui()
                self.refresh_staging_tree()
                self.update_status(f"成功直接入库 {successful_count} 题！您可以前往题库查看。")
                messagebox.showinfo("成功", f"已直接保存 {successful_count} 题至题库！")

            self.after(0, update_ui)

        threading.Thread(target=task, daemon=True).start()"""

if old_save_staging in content:
    content = content.replace(old_save_staging, new_save_staging)


# UI buttons
old_buttons = """        ttk.Label(bottom_frame, text="为整个试卷批量追加标签:").pack(side=tk.LEFT)
        self.ent_batch_tag = ttk.Entry(bottom_frame, width=20)
        self.ent_batch_tag.pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="应用批量标签", command=self.apply_batch_tags).pack(side=tk.LEFT)

        ttk.Button(bottom_frame, text="✅ 确认暂存区无误，全部保存入库", command=self.save_staging_to_db).pack(side=tk.RIGHT)"""

new_buttons = """        ttk.Label(bottom_frame, text="为整个试卷批量追加标签:").pack(side=tk.LEFT)
        self.ent_batch_tag = ttk.Entry(bottom_frame, width=20)
        self.ent_batch_tag.pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="应用批量标签", command=self.apply_batch_tags).pack(side=tk.LEFT)

        ttk.Button(bottom_frame, text="💾 全部直接入库 (跳过编译检查)", command=self.save_staging_to_db).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="🛠️ 检查并修复选中题目的 LaTeX", command=self.check_and_fix_latex).pack(side=tk.RIGHT, padx=5)"""

if old_buttons in content:
    content = content.replace(old_buttons, new_buttons)

old_diag_btn = """        self.lbl_stg_diagram = ttk.Label(right_frame, text="图样显示区", background="#e0e0e0", anchor=tk.CENTER)
        self.lbl_stg_diagram.pack(fill=tk.BOTH, expand=True, pady=5)

        diag_btn_frame = ttk.Frame(right_frame)
        diag_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(diag_btn_frame, text="⬆️ 将图样移至上一题", command=self.move_diagram_up).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(diag_btn_frame, text="⬇️ 将图样移至下一题", command=self.move_diagram_down).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)"""

new_diag_btn = """        self.lbl_stg_diagram = ttk.Label(right_frame, text="无图样", background="#e0e0e0", anchor=tk.CENTER)
        self.lbl_stg_diagram.pack(fill=tk.BOTH, expand=True, pady=5)

        self.lbl_stg_diag_info = ttk.Label(right_frame, text="", anchor=tk.CENTER)
        self.lbl_stg_diag_info.pack(fill=tk.X)

        diag_btn_frame = ttk.Frame(right_frame)
        diag_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(diag_btn_frame, text="⬅️ 上一图", command=self.stg_prev_diagram).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(diag_btn_frame, text="❌ 删除当前图", command=self.stg_delete_diagram).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(diag_btn_frame, text="下一图 ➡️", command=self.stg_next_diagram).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        move_btn_frame = ttk.Frame(right_frame)
        move_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(move_btn_frame, text="⬆️ 将当前图样移至上一题", command=self.move_diagram_up).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(move_btn_frame, text="⬇️ 将当前图样移至下一题", command=self.move_diagram_down).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)"""

if old_diag_btn in content:
    content = content.replace(old_diag_btn, new_diag_btn)

# Move diagram methods
old_move_up = """    def move_diagram_up(self):
        sel = self.tree_staging.selection()
        if not sel: return
        idx = int(sel[0])
        if idx == 0:
            messagebox.showinfo("提示", "已经是第一题，无法上移。")
            return

        current_q = self.staging_questions[idx]
        prev_q = self.staging_questions[idx - 1]

        # Check if the target already has a diagram to avoid losing it, ask user if they want to swap
        if prev_q.get("diagram") or prev_q.get("image_b64"):
            if not messagebox.askyesno("警告", "上一题已有图样或图片。确定要与当前题目的图样进行交换吗？"):
                return

        cur_diagram = current_q.get("diagram")
        cur_image_b64 = current_q.get("image_b64") or ""
        prev_diagram = prev_q.get("diagram")
        prev_image_b64 = prev_q.get("image_b64") or ""

        prev_q["diagram"], current_q["diagram"] = cur_diagram, prev_diagram
        prev_q["image_b64"], current_q["image_b64"] = cur_image_b64, prev_image_b64

        self.refresh_staging_tree()
        self.tree_staging.selection_set(str(idx - 1))
        self.on_staging_select(None)
        self.update_status(f"图样已与第 {idx} 题交换")"""

new_move_up = """    def move_diagram_up(self):
        sel = self.tree_staging.selection()
        if not sel: return
        idx = int(sel[0])
        if idx == 0:
            messagebox.showinfo("提示", "已经是第一题，无法上移。")
            return

        if not hasattr(self, 'stg_current_diags') or not self.stg_current_diags:
            messagebox.showinfo("提示", "当前题目没有图样。")
            return

        current_q = self.staging_questions[idx]
        prev_q = self.staging_questions[idx - 1]

        diag_to_move = self.stg_current_diags.pop(self.current_img_index)

        # update current
        if not self.stg_current_diags:
            current_q["diagram"] = None
        elif len(self.stg_current_diags) == 1:
            current_q["diagram"] = self.stg_current_diags[0]
        else:
            current_q["diagram"] = json.dumps(self.stg_current_diags)

        self.current_img_index = max(0, min(self.current_img_index, len(self.stg_current_diags) - 1))

        # update prev
        prev_diags = self._parse_diagram_json(prev_q.get("diagram"))
        prev_diags.append(diag_to_move)
        if len(prev_diags) == 1:
            prev_q["diagram"] = prev_diags[0]
        else:
            prev_q["diagram"] = json.dumps(prev_diags)

        self.refresh_staging_tree()
        self.tree_staging.selection_set(str(idx - 1))
        self.on_staging_select(None)
        self.update_status(f"图样已移至第 {idx} 题")"""

if old_move_up in content:
    content = content.replace(old_move_up, new_move_up)

old_move_down = """    def move_diagram_down(self):
        sel = self.tree_staging.selection()
        if not sel: return
        idx = int(sel[0])
        if idx == len(self.staging_questions) - 1:
            messagebox.showinfo("提示", "已经是最后一题，无法下移。")
            return

        current_q = self.staging_questions[idx]
        next_q = self.staging_questions[idx + 1]

        # Check if the target already has a diagram
        if next_q.get("diagram") or next_q.get("image_b64"):
            if not messagebox.askyesno("警告", "下一题已有图样或图片。确定要与当前题目的图样进行交换吗？"):
                return

        cur_diagram = current_q.get("diagram")
        cur_image_b64 = current_q.get("image_b64") or ""
        next_diagram = next_q.get("diagram")
        next_image_b64 = next_q.get("image_b64") or ""

        next_q["diagram"], current_q["diagram"] = cur_diagram, next_diagram
        next_q["image_b64"], current_q["image_b64"] = cur_image_b64, next_image_b64

        self.refresh_staging_tree()
        self.tree_staging.selection_set(str(idx + 1))
        self.on_staging_select(None)
        self.update_status(f"图样已与第 {idx + 2} 题交换")"""

new_move_down = """    def move_diagram_down(self):
        sel = self.tree_staging.selection()
        if not sel: return
        idx = int(sel[0])
        if idx == len(self.staging_questions) - 1:
            messagebox.showinfo("提示", "已经是最后一题，无法下移。")
            return

        if not hasattr(self, 'stg_current_diags') or not self.stg_current_diags:
            messagebox.showinfo("提示", "当前题目没有图样。")
            return

        current_q = self.staging_questions[idx]
        next_q = self.staging_questions[idx + 1]

        diag_to_move = self.stg_current_diags.pop(self.current_img_index)

        # update current
        if not self.stg_current_diags:
            current_q["diagram"] = None
        elif len(self.stg_current_diags) == 1:
            current_q["diagram"] = self.stg_current_diags[0]
        else:
            current_q["diagram"] = json.dumps(self.stg_current_diags)

        self.current_img_index = max(0, min(self.current_img_index, len(self.stg_current_diags) - 1))

        # update next
        next_diags = self._parse_diagram_json(next_q.get("diagram"))
        next_diags.append(diag_to_move)
        if len(next_diags) == 1:
            next_q["diagram"] = next_diags[0]
        else:
            next_q["diagram"] = json.dumps(next_diags)

        self.refresh_staging_tree()
        self.tree_staging.selection_set(str(idx + 1))
        self.on_staging_select(None)
        self.update_status(f"图样已移至第 {idx + 2} 题")"""

if old_move_down in content:
    content = content.replace(old_move_down, new_move_down)

# Update on_lib_select
old_lib_select = """            if hasattr(self, 'lbl_lib_diagram'):
                if diagram_base64:
                    import io, base64
                    from PIL import Image, ImageTk
                    try:
                        img_data = base64.b64decode(diagram_base64.split(",")[-1] if "," in diagram_base64 else diagram_base64)
                        img = Image.open(io.BytesIO(img_data)).copy()
                        img.thumbnail((400, 200))
                        photo = ImageTk.PhotoImage(img)
                        self.lbl_lib_diagram.config(image=photo, text="")
                        self.lbl_lib_diagram.image = photo
                    except Exception as e:
                        self.lbl_lib_diagram.config(image='', text=f"图样加载失败: {e}")
                else:
                    self.lbl_lib_diagram.config(image='', text="无图样")"""

new_lib_select = """            if hasattr(self, 'lbl_lib_diagram'):
                self.lib_current_diags = self._parse_diagram_json(diagram_base64)
                self.lib_img_index = 0
                self._render_lib_diagram()"""

lib_methods = """    def _render_lib_diagram(self):
        if not hasattr(self, 'lib_current_diags') or not self.lib_current_diags:
            self.lbl_lib_diagram.config(image='', text="无图样")
            if hasattr(self.lbl_lib_diagram, 'image'):
                del self.lbl_lib_diagram.image
            self.lbl_lib_diag_info.config(text="")
            return

        display_img_b64 = self.lib_current_diags[self.lib_img_index]
        if display_img_b64:
            import io, base64
            from PIL import Image, ImageTk
            try:
                img_data = base64.b64decode(display_img_b64.split(",")[-1] if "," in display_img_b64 else display_img_b64)
                img = Image.open(io.BytesIO(img_data)).copy()
                img.thumbnail((400, 200))
                photo = ImageTk.PhotoImage(img)
                self.lbl_lib_diagram.config(image=photo, text="")
                self.lbl_lib_diagram.image = photo
                info_text = f"图样 {self.lib_img_index + 1} / {len(self.lib_current_diags)}"
                self.lbl_lib_diag_info.config(text=info_text)
            except Exception as e:
                self.lbl_lib_diagram.config(image='', text=f"图样加载失败: {e}")
                self.lbl_lib_diag_info.config(text="")
        else:
            self.lbl_lib_diagram.config(image='', text="无图样")
            self.lbl_lib_diag_info.config(text="")

    def lib_prev_diagram(self):
        if hasattr(self, 'lib_current_diags') and self.lib_current_diags:
            self.lib_img_index = (self.lib_img_index - 1) % len(self.lib_current_diags)
            self._render_lib_diagram()

    def lib_next_diagram(self):
        if hasattr(self, 'lib_current_diags') and self.lib_current_diags:
            self.lib_img_index = (self.lib_img_index + 1) % len(self.lib_current_diags)
            self._render_lib_diagram()"""

if old_lib_select in content:
    content = content.replace(old_lib_select, new_lib_select)
    content = content.replace("    def update_lib_tags(self):", lib_methods + "\n    def update_lib_tags(self):")


old_lib_ui = """        self.lbl_lib_diagram = ttk.Label(det_frame, text="无图样", background="#e0e0e0", anchor=tk.CENTER)
        self.lbl_lib_diagram.pack(fill=tk.BOTH, expand=True, pady=5)"""

new_lib_ui = """        self.lbl_lib_diagram = ttk.Label(det_frame, text="无图样", background="#e0e0e0", anchor=tk.CENTER)
        self.lbl_lib_diagram.pack(fill=tk.BOTH, expand=True, pady=5)

        self.lbl_lib_diag_info = ttk.Label(det_frame, text="", anchor=tk.CENTER)
        self.lbl_lib_diag_info.pack(fill=tk.X)

        lib_btn_frame = ttk.Frame(det_frame)
        lib_btn_frame.pack(fill=tk.X, pady=2)
        ttk.Button(lib_btn_frame, text="⬅️ 上一图", command=self.lib_prev_diagram).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)
        ttk.Button(lib_btn_frame, text="下一图 ➡️", command=self.lib_next_diagram).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)"""

if old_lib_ui in content:
    content = content.replace(old_lib_ui, new_lib_ui)


# export_paper
old_export_img = """            if q.get("diagram"):
                img_data = base64.b64decode(q["diagram"])
                img_filename = f"diagram_{q['id']}.png"
                img_filepath = os.path.join(img_dir, img_filename)
                with open(img_filepath, "wb") as f:
                    f.write(img_data)

                rel_img_path = f"{img_dir_name}/{img_filename}".replace("\\\\", "/")
                tex.append(r"\\begin{center}")
                tex.append(rf"\\includegraphics[width=0.6\\textwidth]{{{rel_img_path}}}")
                tex.append(r"\\end{center}")"""

new_export_img = """            if q.get("diagram"):
                diags = self._parse_diagram_json(q.get("diagram"))
                for i, d in enumerate(diags):
                    try:
                        img_data = base64.b64decode(d)
                        img_filename = f"diagram_{q['id']}_{i}.png"
                        img_filepath = os.path.join(img_dir, img_filename)
                        with open(img_filepath, "wb") as f:
                            f.write(img_data)

                        rel_img_path = f"{img_dir_name}/{img_filename}".replace("\\\\", "/")
                        tex.append(r"\\begin{center}")
                        tex.append(rf"\\includegraphics[width=0.6\\textwidth]{{{rel_img_path}}}")
                        tex.append(r"\\end{center}")
                    except Exception as e:
                        from utils import logger
                        logger.error(f"Failed to export diagram {i} for Q {q['id']}: {e}")"""

if old_export_img in content:
    content = content.replace(old_export_img, new_export_img)

old_compile = """            try:
                result = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "--no-shell-escape", f"-output-directory={export_dir}", export_tex_path],
                    cwd=export_dir,
                    capture_output=True,
                    check=False
                )
                if result.returncode != 0:
                    try:
                        out_str = result.stdout.decode('utf-8', errors='replace')
                    except Exception:
                        out_str = str(result.stdout)
                    error_msg = f"LaTeX 编译错误，部分符号未被 AI 成功转义导致中断。\\n日志片段: {out_str[-500:]}"
                    raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
                pdf_success = True
            except FileNotFoundError:"""

new_compile = """            try:
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
                    error_msg = f"LaTeX 编译错误，部分符号未被 AI 成功转义导致中断。\\n日志片段: {out_str[-500:]}"
                    raise subprocess.CalledProcessError(result.returncode, result.args, output=result.stdout, stderr=result.stderr)
                pdf_success = True
            except FileNotFoundError:"""

if old_compile in content:
    content = content.replace(old_compile, new_compile)

# Replace 1024 defaults in settings
content = content.replace("getattr(self.settings, 'embedding_dimension', 1024)", "getattr(self.settings, 'embedding_dimension', 1536)")
content = content.replace("self.settings.embedding_dimension = 1024", "self.settings.embedding_dimension = 1536")

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("gui_app.py patched.")
