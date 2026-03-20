import re

with open("gui_app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update handle_slice_ready to pass diagram_map safely and accommodate new structure
old_handle_slice_ready = """        def handle_slice_ready(s):
            if mode == 1:
                item = {
                    "content": s["text"], "logic": "无 (本地OCR模式)", "tags": ["本地提取"], "diagram": s.get("diagram"), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            else:
                item = {
                    "content": s["text"], "logic": "等待 AI 处理...", "tags": ["本地提取中"], "diagram": s.get("diagram"), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }"""

new_handle_slice_ready = """        def handle_slice_ready(s):
            if mode == 1:
                item = {
                    "content": s["text"], "logic": "无 (本地OCR模式)", "tags": ["本地提取"], "diagram": s.get("diagram"), "diagram_map": s.get("diagram_map", {}), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }
            else:
                item = {
                    "content": s["text"], "logic": "等待 AI 处理...", "tags": ["本地提取中"], "diagram": s.get("diagram"), "diagram_map": s.get("diagram_map", {}), "page_annotated_b64": s.get("page_annotated_b64"), "image_b64": s.get("image_b64")
                }"""
content = content.replace(old_handle_slice_ready, new_handle_slice_ready)


# 2. Update processing loop to handle diagram mapping
old_processing_loop = """                for q in questions:
                    status = q.get("Status", "Complete")
                    if status == "NotQuestion":
                        continue

                    source_indices = q.get("SourceSliceIndices", [])
                    diagram = None
                    image_b64 = ""
                    page_annotated_b64 = ""

                    for idx in source_indices:
                        if 0 <= idx < len(pending_slices):
                            if not image_b64 and pending_slices[idx].get("image_b64"):
                                image_b64 = pending_slices[idx]["image_b64"]
                            if not diagram and pending_slices[idx].get("diagram"):
                                diagram = pending_slices[idx]["diagram"]
                            if not page_annotated_b64 and pending_slices[idx].get("page_annotated_b64"):
                                page_annotated_b64 = pending_slices[idx].get("page_annotated_b64")

                        if diagram and image_b64 and page_annotated_b64:
                            break

                    item = {
                        "content": q.get("Content", ""),
                        "logic": q.get("LogicDescriptor", ""),
                        "tags": q.get("Tags", []),
                        "diagram": diagram,
                        "image_b64": image_b64,
                        "page_annotated_b64": page_annotated_b64
                    }"""

new_processing_loop = """                for q in questions:
                    status = q.get("Status", "Complete")
                    if status == "NotQuestion":
                        continue

                    source_indices = q.get("SourceSliceIndices", [])
                    diagram = None
                    image_b64 = ""
                    page_annotated_b64 = ""
                    content_text = q.get("Content", "")

                    # Combine all diagram maps from source slices into one big dict for this question
                    merged_diagram_map = {}
                    for idx in source_indices:
                        if 0 <= idx < len(pending_slices):
                            if not image_b64 and pending_slices[idx].get("image_b64"):
                                image_b64 = pending_slices[idx]["image_b64"]
                            if not page_annotated_b64 and pending_slices[idx].get("page_annotated_b64"):
                                page_annotated_b64 = pending_slices[idx].get("page_annotated_b64")

                            d_map = pending_slices[idx].get("diagram_map", {})
                            if d_map:
                                # Prepend the slice index to make the key unique if cross-slice diagrams exist
                                # However, our markers are just [[{ima_dont_del_X}]] so we search the text
                                # We'll just merge them directly if the page has isolated diagram indices 0,1,2...
                                # In a real cross-page scenario, it might collide, so let's rely on finding the marker in text.
                                # Let's find any [[{ima_dont_del_X}]] in content_text and replace it.
                                pass

                    # Resolve diagram markers within the content text
                    # We will scan the source_indices again to map the markers correctly.
                    # Since markers are [[{ima_dont_del_X}]], we search the text for them.
                    import re
                    marker_pattern = re.compile(r'\[\[\{ima_dont_del_(\d+)\}\]\]')
                    matches = marker_pattern.findall(content_text)

                    if matches:
                        # Grab the first match to set as diagram
                        first_d_idx = int(matches[0])

                        # Find the corresponding diagram b64 from the source slices
                        for idx in source_indices:
                            if 0 <= idx < len(pending_slices):
                                d_map = pending_slices[idx].get("diagram_map", {})
                                # Note: keys might be stored as strings if parsed from json elsewhere, but here they are ints
                                if first_d_idx in d_map:
                                    diagram = d_map[first_d_idx]
                                    break
                                elif str(first_d_idx) in d_map:
                                    diagram = d_map[str(first_d_idx)]
                                    break

                        # Clean up ALL markers from the content text to keep LaTeX pure
                        content_text = marker_pattern.sub('', content_text).strip()

                    item = {
                        "content": content_text,
                        "logic": q.get("LogicDescriptor", ""),
                        "tags": q.get("Tags", []),
                        "diagram": diagram,
                        "image_b64": image_b64,
                        "page_annotated_b64": page_annotated_b64
                    }"""

content = content.replace(old_processing_loop, new_processing_loop)

# Save
with open("gui_app.py", "w", encoding="utf-8") as f:
    f.write(content)
