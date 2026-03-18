with open("document_service.py", "r", encoding="utf-8") as f:
    content = f.read()

# Update the if condition for layout types to match Surya documentation exactly
# Old: if p_type in ['Figure', 'Table', 'Equation']:
# New: if p_type in ['Picture', 'Figure', 'Table', 'Formula', 'Text-inline-math', 'Form']:
old_str = "if p_type in ['Figure', 'Table', 'Equation']:"
new_str = "if p_type in ['Picture', 'Figure', 'Table', 'Formula', 'Text-inline-math', 'Form']:"

content = content.replace(old_str, new_str)

with open("document_service.py", "w", encoding="utf-8") as f:
    f.write(content)
