import re

with open("document_service.py", "r", encoding="utf-8") as f:
    code = f.read()

# Modify Pix2Text image handling in process_doc_with_layout
old_figure = """                        if b_type in ['figure', 'table']:
                            if b_box is not None:
                                try:
                                    box_arr = np.array(b_box).reshape(-1, 2)
                                    x_min, y_min = np.min(box_arr, axis=0)
                                    x_max, y_max = np.max(box_arr, axis=0)
                                    cropped = img.crop((max(0, int(x_min)-5), max(0, int(y_min)-5), min(img.width, int(x_max)+5), min(img.height, int(y_max)+5)))
                                    buf = io.BytesIO()
                                    cropped.save(buf, format='PNG')
                                    new_diagram = base64.b64encode(buf.getvalue()).decode('utf-8')

                                    package_current_slice()
                                    current_diagram = new_diagram
                                except Exception:
                                    pass"""

# Allow image extraction for standalone formulas or isolated equations since they are often figures with text
new_figure = """                        if b_type in ['figure', 'table', 'isolated_equation', 'image']:
                            if b_box is not None:
                                try:
                                    box_arr = np.array(b_box).reshape(-1, 2)
                                    x_min, y_min = np.min(box_arr, axis=0)
                                    x_max, y_max = np.max(box_arr, axis=0)
                                    # Relax crop bounds slightly to capture edges
                                    crop_box = (
                                        max(0, int(x_min)-10),
                                        max(0, int(y_min)-10),
                                        min(img.width, int(x_max)+10),
                                        min(img.height, int(y_max)+10)
                                    )
                                    if crop_box[2] > crop_box[0] and crop_box[3] > crop_box[1]:
                                        cropped = img.crop(crop_box)
                                        buf = io.BytesIO()
                                        cropped.save(buf, format='PNG')
                                        new_diagram = base64.b64encode(buf.getvalue()).decode('utf-8')

                                        package_current_slice()
                                        current_diagram = new_diagram
                                except Exception as e:
                                    logger.warning(f"Image crop failed: {e}")"""

code = code.replace(old_figure, new_figure)

with open("document_service.py", "w", encoding="utf-8") as f:
    f.write(code)
