with open("gui_app.py", "r", encoding="utf-8") as f:
    c = f.read()

# Verify save_manual bug fix
if "        if getattr(self, \"_manual_save_inflight\"" in c:
    print("save_manual indentation fixed")

# Verify lib diagram UI
if "self.lbl_lib_diagram = ttk.Label(det_frame" in c:
    print("lib diagram UI added")
