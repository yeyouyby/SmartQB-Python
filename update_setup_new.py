with open('setup_new.bat', 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = '''echo     print("[INFO] Initializing Surya Layout and OCR models...") >> init_models.py
echo     lp = LayoutPredictor() >> init_models.py
echo     fp = FoundationPredictor() >> init_models.py
echo     op = RecognitionPredictor(fp) >> init_models.py'''

new_logic = '''echo     print("[INFO] Initializing Surya Layout and OCR models...") >> init_models.py
echo     fp = FoundationPredictor() >> init_models.py
echo     lp = LayoutPredictor(fp) >> init_models.py
echo     op = RecognitionPredictor(fp) >> init_models.py'''

new_content = content.replace(old_logic, new_logic)

with open('setup_new.bat', 'w', encoding='utf-8') as f:
    f.write(new_content)
print("Updated setup_new.bat successfully" if content != new_content else "No changes made to setup_new.bat")
