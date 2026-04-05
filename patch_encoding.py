import glob
for file in ['ui_calibration.py', 'gui/components/question_block.py']:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)
print("done")
