import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add surya imports
if "surya.layout" not in content:
    imports_to_add = """
try:
    from surya.layout import LayoutPredictor
    from surya.ocr import OCRPredictor
except ImportError:
    LayoutPredictor = None
    OCRPredictor = None
from utils import logger
"""
    content = content.replace("from config import DB_NAME", imports_to_add + "from config import DB_NAME")

# 2. Add surya initialization to __init__
init_code_search = 'print("Pix2Text 引擎加载完成！")'
surya_init_code = """        print("正在加载 Surya Layout 版面分析引擎 (必选)...")
        if LayoutPredictor:
            try:
                self.surya_layout = LayoutPredictor()
                print("Surya Layout 引擎加载完成！")
            except Exception as e:
                logger.error(f"Failed to load Surya Layout: {e}", exc_info=True)
                self.surya_layout = None
        else:
            self.surya_layout = None
            print("警告: 无法导入 surya，请检查依赖！")

        print("正在加载 Surya OCR 引擎 (可选)...")
        if OCRPredictor:
            try:
                self.surya_ocr = OCRPredictor()
                print("Surya OCR 引擎加载完成！")
            except Exception as e:
                logger.error(f"Failed to load Surya OCR: {e}", exc_info=True)
                self.surya_ocr = None
        else:
            self.surya_ocr = None"""

if "Surya Layout 版面分析引擎" not in content:
    content = content.replace(init_code_search, init_code_search + "\n" + surya_init_code)

# 3. Add OCR Engine toggle to build_settings_tab
ocr_toggle_ui = """        ttk.Label(container, text="📝 核心图像与文字识别模式:").pack(anchor=tk.W, pady=(20, 5))

        # --- NEW OCR TOGGLE ---
        ocr_frame = ttk.Frame(container)
        ocr_frame.pack(anchor=tk.W, padx=20, fill=tk.X, pady=2)
        ttk.Label(ocr_frame, text="使用的 OCR 识别引擎 (版面分析已固定使用 Surya):").pack(side=tk.LEFT)
        self.cbo_ocr_engine = ttk.Combobox(ocr_frame, values=["Pix2Text", "Surya"], width=15, state="readonly")
        self.cbo_ocr_engine.set(self.settings.ocr_engine_type if hasattr(self.settings, 'ocr_engine_type') else 'Pix2Text')
        self.cbo_ocr_engine.pack(side=tk.LEFT, padx=10)
        # ----------------------
"""
content = re.sub(r'        ttk\.Label\(container, text="📝 核心图像与文字识别模式:"\)\.pack\(anchor=tk\.W, pady=\(20, 5\)\)', ocr_toggle_ui, content)

# 4. Save the OCR engine toggle in save_settings
save_settings_code = """        self.settings.use_prm_optimization = self.var_use_prm.get()
        if hasattr(self, 'cbo_ocr_engine'):
            self.settings.ocr_engine_type = self.cbo_ocr_engine.get()"""
content = content.replace("self.settings.use_prm_optimization = self.var_use_prm.get()", save_settings_code)


# 5. Pass surya_layout and the chosen OCR engine to process_doc_with_layout
run_pipeline_replace = """                pending_slices = DocumentService.process_doc_with_layout(
                    file_path, file_type,
                    self.surya_layout,
                    self.ocr_engine if getattr(self.settings, 'ocr_engine_type', 'Pix2Text') == 'Pix2Text' else self.surya_ocr,
                    getattr(self.settings, 'ocr_engine_type', 'Pix2Text'),
                    self.update_status, handle_slice_ready
                )"""
content = re.sub(
    r'pending_slices = DocumentService\.process_doc_with_layout\(\s*file_path,\s*file_type,\s*self\.ocr_engine,\s*self\.update_status,\s*handle_slice_ready\s*\)',
    run_pipeline_replace,
    content
)

with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
