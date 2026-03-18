import re

with open('gui_app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = '''        logger.info("正在加载 Surya Layout 版面分析引擎 (必选)...")
        if LayoutPredictor:
            try:
                self.surya_layout = LayoutPredictor()
                logger.info("Surya Layout 引擎加载完成！")
            except Exception as e:
                logger.error(f"Failed to load Surya Layout: {e}", exc_info=True)
                self.surya_layout = None
        else:
            logger.error("无法导入 surya.layout，文档版面分析不可用。")
            raise RuntimeError("Missing required dependency: surya.layout")

        logger.info("正在加载 Surya OCR 引擎 (可选)...")
        if RecognitionPredictor and FoundationPredictor:
            try:
                foundation_predictor = FoundationPredictor()
                self.surya_ocr = RecognitionPredictor(foundation_predictor)
                logger.info("Surya OCR 引擎加载完成！")
            except Exception as e:
                logger.error(f"Failed to load Surya OCR: {e}", exc_info=True)
                self.surya_ocr = None
        else:
            self.surya_ocr = None'''

new_logic = '''        logger.info("正在加载 Surya 基础引擎 (FoundationPredictor)...")
        foundation_predictor = None
        if FoundationPredictor:
            try:
                foundation_predictor = FoundationPredictor()
            except Exception as e:
                logger.error(f"Failed to load FoundationPredictor: {e}", exc_info=True)

        logger.info("正在加载 Surya Layout 版面分析引擎 (必选)...")
        if LayoutPredictor and foundation_predictor:
            try:
                self.surya_layout = LayoutPredictor(foundation_predictor)
                logger.info("Surya Layout 引擎加载完成！")
            except Exception as e:
                logger.error(f"Failed to load Surya Layout: {e}", exc_info=True)
                self.surya_layout = None
        else:
            logger.error("缺少基础模型或 surya.layout，文档版面分析不可用。")
            self.surya_layout = None

        logger.info("正在加载 Surya OCR 引擎 (可选)...")
        if RecognitionPredictor and foundation_predictor:
            try:
                self.surya_ocr = RecognitionPredictor(foundation_predictor)
                logger.info("Surya OCR 引擎加载完成！")
            except Exception as e:
                logger.error(f"Failed to load Surya OCR: {e}", exc_info=True)
                self.surya_ocr = None
        else:
            self.surya_ocr = None'''

new_content = content.replace(old_logic, new_logic)

with open('gui_app.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("Updated gui_app.py successfully" if content != new_content else "No changes made to gui_app.py")
