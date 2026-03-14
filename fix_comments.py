import re

# 1. Fix document_service.py multiple identical equation wrappers and bad newlines
with open("document_service.py", "r", encoding="utf-8") as f:
    doc_code = f.read()

# Remove duplicated equation wrapping logic blocks
pattern = r"(\s*if b_type in \['equation', 'isolated_equation', 'formula'\]:\s*if b_text\.strip\(\) and not b_text\.startswith\('\$'\):\s*b_text = '\$' \+ b_text \+ '\$')+"
doc_code = re.sub(pattern, r"\1", doc_code)

# Fix the broken list comprehension string line that has literal newlines in it (if it still exists)
doc_code = doc_code.replace("row_data = [cell.text.strip().replace(\"\n\", \" \") for cell in row.cells]",
                            "row_data = [cell.text.strip().replace(\"\\\\n\", \" \") for cell in row.cells]")

# Fix any instances of literal newlines splitting the row_data line
doc_code = re.sub(r'row_data = \[cell\.text\.strip\(\)\.replace\("\n", " "\) for cell in row\.cells\]',
                  'row_data = [cell.text.strip().replace("\\\\n", " ") for cell in row.cells]', doc_code)

with open("document_service.py", "w", encoding="utf-8") as f:
    f.write(doc_code)
