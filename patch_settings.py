with open("settings_manager.py", "r", encoding="utf-8") as f:
    content = f.read()

if "self.ocr_engine_type" not in content:
    content = content.replace("self.recognition_mode = 2", "self.recognition_mode = 2\n        self.ocr_engine_type = 'Pix2Text'")

    # Save/Load
    content = content.replace("self.recognition_mode = d.get(\"recognition_mode\", 2)", "self.recognition_mode = d.get(\"recognition_mode\", 2)\n                self.ocr_engine_type = d.get(\"ocr_engine_type\", \"Pix2Text\")")

    content = content.replace("\"recognition_mode\": self.recognition_mode,", "\"recognition_mode\": self.recognition_mode,\n                \"ocr_engine_type\": self.ocr_engine_type,")

with open("settings_manager.py", "w", encoding="utf-8") as f:
    f.write(content)
