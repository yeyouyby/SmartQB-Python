import glob
for file in glob.glob("**/*.py", recursive=True):
    try:
        with open(file, 'r', encoding='utf-8') as f:
            pass
    except UnicodeDecodeError:
        print(f"fixing {file}")
        with open(file, 'r', encoding='latin-1') as f:
            content = f.read()
        with open(file, 'w', encoding='utf-8') as f:
            f.write(content)
print("done")
