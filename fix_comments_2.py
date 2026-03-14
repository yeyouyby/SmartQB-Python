with open("document_service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

out = []
skip_next = False
for line in lines:
    if skip_next:
        skip_next = False
        continue

    if "row_data = [cell.text.strip().replace(" in line and line.strip().endswith('('):
        pass # this doesn't match the current error format
    if 'row_data = [cell.text.strip().replace("' in line and not line.strip().endswith(']'):
        # Found the split line.
        out.append('                        row_data = [cell.text.strip().replace("\\\\n", " ") for cell in row.cells]\n')
        skip_next = True
    elif '", " ") for cell in row.cells]' in line:
        pass # Should have been skipped
    else:
        out.append(line)

with open("document_service.py", "w", encoding="utf-8") as f:
    f.writelines(out)
