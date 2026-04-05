with open("gui/components/question_block.py", "r") as f:
    lines = f.readlines()
with open("gui/components/question_block.py", "w") as f:
    for line in lines:
        if "import markdown" in line:
            f.write("import markdown  # type: ignore\n")
        else:
            f.write(line)
print("done")
