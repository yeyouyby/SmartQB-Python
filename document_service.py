import re
import io
import base64
import numpy as np
import fitz  # PyMuPDF
import docx
from PIL import Image, ImageDraw
from utils import logger

# ==========================================
# 文档解析服务 (PDF / Word / Image)
# ==========================================


class DocumentService:
    @staticmethod
    def process_doc_with_layout(
        file_path, file_type, layout_predictor, update_status=None, on_slice_ready=None
    ):
        """
        使用 PP-StructureV3 进行版面分析与 Markdown 提取
        返回: pending_slices 列表，元素结构为 {"text": str, "image_b64": str, "diagram_map": dict}
        """
        pending_slices = []

        doc = None
        try:
            total_pages = 1
            if file_type == "pdf":
                doc = fitz.open(file_path)
                total_pages = len(doc)

            for page_index in range(total_pages):
                if update_status:
                    update_status(
                        f"🚀 PP-StructureV3 分析与提取中: 第 {page_index + 1}/{total_pages} 页..."
                    )

                img = None
                if file_type == "pdf":
                    pix = doc[page_index].get_pixmap(dpi=150)
                    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                else:
                    img = Image.open(file_path).convert("RGB")

                try:
                    full_page_markdown = ""
                    diagram_map = {}

                    if layout_predictor is not None:
                        # --- PP-StructureV3 逻辑 ---
                        cv_img = np.array(img.convert("RGB"))[:, :, ::-1]  # RGB to BGR
                        output = layout_predictor(cv_img)

                        md_info = ""
                        md_images = {}

                        if output and isinstance(output, list):
                            for res in output:
                                if "markdown" in res:
                                    md_info += res["markdown"] + "\n"
                                if res.get("markdown_images"):
                                    md_images.update(res["markdown_images"])

                        full_page_markdown = md_info

                        annotated_img = img.copy()
                        if output and isinstance(output, list):
                            draw = ImageDraw.Draw(annotated_img)
                            for res in output:
                                if "text_region" in res:
                                    pts = res["text_region"]
                                    if len(pts) == 4:
                                        draw.polygon(
                                            [tuple(p) for p in pts],
                                            outline="red",
                                            width=2,
                                        )
                                elif "bbox" in res:
                                    box = res["bbox"]
                                    if len(box) == 4:
                                        draw.rectangle(box, outline="red", width=2)

                        d_idx = 0
                        for img_name, img_data in md_images.items():
                            global_marker = f"{page_index}_{d_idx}"

                            buf = io.BytesIO()
                            if isinstance(img_data, np.ndarray):
                                with Image.fromarray(img_data) as pil_img:
                                    pil_img.save(buf, format="PNG")
                            else:
                                img_data.save(buf, format="PNG")
                            d_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

                            diagram_map[global_marker] = d_b64

                            marker_str = f"\n\n[[{{ima_dont_del_{global_marker}}}]]\n\n"

                            escaped_name = re.escape(img_name)
                            pattern = (
                                r"!\[.*?\]\(" + escaped_name + r"\)|"
                                r'<img[^>]*?src=["\']' + escaped_name + r'["\'][^>]*?>|'
                                r"\b" + escaped_name + r"\b"
                            )
                            full_page_markdown = re.sub(
                                pattern,
                                marker_str,
                                full_page_markdown,
                            )

                            d_idx += 1

                    # Save the full page image for vision model
                    buf_page = io.BytesIO()
                    img.save(buf_page, format="PNG")
                    page_image_b64 = base64.b64encode(buf_page.getvalue()).decode(
                        "utf-8"
                    )

                    # Package the entire page as ONE slice
                    annotated_buf = io.BytesIO()
                    if "annotated_img" in locals() and annotated_img is not None:
                        annotated_img.save(annotated_buf, format="PNG")
                    else:
                        img.save(annotated_buf, format="PNG")
                    page_annotated_b64 = base64.b64encode(
                        annotated_buf.getvalue()
                    ).decode("utf-8")

                    slice_obj = {
                        "text": full_page_markdown,
                        "image_b64": page_image_b64,
                        "diagram": next(iter(diagram_map.values()), None),
                        "diagram_map": diagram_map,
                        "page_annotated_b64": page_annotated_b64,
                    }

                    pending_slices.append(slice_obj)
                    if on_slice_ready:
                        try:
                            on_slice_ready(slice_obj)
                        except Exception as e:
                            logger.error(
                                f"Error in on_slice_ready callback: {e}", exc_info=True
                            )

                finally:
                    if img:
                        img.close()

        finally:
            if doc:
                doc.close()

        return pending_slices

    @staticmethod
    def extract_from_word(docx_path):
        doc = docx.Document(docx_path)
        chunks = []
        current_text = []
        current_images = []

        def extract_image(embed_id):
            if embed_id:
                try:
                    part = doc.part.related_parts[embed_id]
                    if "image" in part.content_type:
                        img_data = part.blob
                        return base64.b64encode(img_data).decode("utf-8")
                except Exception as e:
                    logger.error(
                        f"Error extracting image from docx: {e}", exc_info=True
                    )
            return None

        for element in doc.element.body:
            try:
                if element.tag.endswith("p"):
                    para = docx.text.paragraph.Paragraph(element, doc)
                    if para.text.strip():
                        prefix = ""
                        if para.style.name.startswith("Heading"):
                            prefix = "# "
                        elif element.xpath(".//w:numPr"):
                            prefix = "- "
                        current_text.append(prefix + para.text.strip())

                elif element.tag.endswith("tbl"):
                    table = docx.table.Table(element, doc)
                    for i, row in enumerate(table.rows):
                        row_data = [
                            cell.text.strip().replace("\n", " ") for cell in row.cells
                        ]
                        if row_data:
                            current_text.append("| " + " | ".join(row_data) + " |")
                            if i == 0:
                                current_text.append(
                                    "|" + "|".join(["---"] * len(row_data)) + "|"
                                )

                for blip in element.xpath(".//a:blip"):
                    embed_id = None
                    for key in blip.keys():
                        if key.endswith("embed"):
                            embed_id = blip.get(key)
                            break
                    img_b64 = extract_image(embed_id)
                    if img_b64:
                        current_images.append(img_b64)

                for imagedata in element.xpath(".//v:imagedata"):
                    embed_id = None
                    for key in imagedata.keys():
                        if key.endswith("id"):
                            embed_id = imagedata.get(key)
                            break
                    img_b64 = extract_image(embed_id)
                    if img_b64:
                        current_images.append(img_b64)

            except Exception as e:
                logger.error(f"Error processing word element: {e}", exc_info=True)
                continue

            if len(current_text) >= 10 or current_images:
                chunks.append(
                    {
                        "text": "\n".join(current_text),
                        "image_b64": "",
                        "diagram": current_images[0] if current_images else None,
                    }
                )
                current_text = []
                if len(current_images) > 1:
                    for extra_img in current_images[1:]:
                        chunks.append(
                            {"text": "", "image_b64": "", "diagram": extra_img}
                        )
                current_images = []

        if current_text or current_images:
            chunks.append(
                {
                    "text": "\n".join(current_text) if current_text else "",
                    "image_b64": "",
                    "diagram": current_images[0] if current_images else None,
                }
            )
            if len(current_images) > 1:
                for extra_img in current_images[1:]:
                    chunks.append({"text": "", "image_b64": "", "diagram": extra_img})

        if not chunks:
            full_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            text_chunks = [chunk for chunk in full_text.split("\n\n") if chunk.strip()]
            chunks = [
                {"text": t.replace("\n", " "), "image_b64": "", "diagram": None}
                for t in text_chunks
            ]

        return chunks
