with open("document_service.py", "r", encoding="utf-8") as f:
    text = f.read()

# Clean all the literal \n strings that are splitting lines
text = text.replace('"text": "\n".join(current_text),', '"text": "\\\\n".join(current_text),')
text = text.replace('"text": "\n".join(current_text) if current_text else "",', '"text": "\\\\n".join(current_text) if current_text else "",')
text = text.replace('full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])', 'full_text = "\\\\n".join([p.text for p in doc.paragraphs if p.text.strip()])')
text = text.replace('text_chunks = [chunk for chunk in full_text.split("\n\n") if chunk.strip()]', 'text_chunks = [chunk for chunk in full_text.split("\\\\n\\\\n") if chunk.strip()]')
text = text.replace('chunks = [{"text": t.replace("\n", " "), "image_b64": "", "diagram": None} for t in text_chunks]', 'chunks = [{"text": t.replace("\\\\n", " "), "image_b64": "", "diagram": None} for t in text_chunks]')

with open("document_service.py", "w", encoding="utf-8") as f:
    f.write(text)
