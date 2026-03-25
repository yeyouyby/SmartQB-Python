from typing import List, Dict
import os
import multiprocessing as mp
import logging
import queue as queue_module
import time
import traceback
import base64
from .base import BaseParser

logger = logging.getLogger(__name__)

def parse_single_image(img, engine, idx_offset=0):
    """Helper to parse a single image array with the initialized PPStructure engine."""
    import cv2
    raw_result = engine(img)
    md_lines = []
    images_map = {}

    for idx, block in enumerate(raw_result, start=idx_offset):
        block_type = block.get("type", "").strip().lower()
        res = block.get("res")

        if block_type in ("text", "title"):
            if isinstance(res, (list, tuple)):
                texts = []
                for item in res:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        text_info = item[1]
                        if isinstance(text_info, (list, tuple)) and text_info:
                            texts.append(str(text_info[0]))
                if texts:
                    md_lines.append(" ".join(texts))

        elif block_type == "table":
            if isinstance(res, dict) and "html" in res:
                md_lines.append(res["html"])
            elif isinstance(res, str):
                md_lines.append(res)

        elif block_type in ("figure", "figure_caption", "image"):
            img_array = block.get("img")
            if img_array is not None:
                _, buf = cv2.imencode(".png", img_array)
                b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
                img_id = f"fig_{idx}"
                images_map[img_id] = b64
                md_lines.append(f"![{img_id}]({img_id})")

    return md_lines, images_map, idx_offset + len(raw_result)

# This process runs isolated to avoid GIL block and memory leaks in the main PySide6 process.
def pp_structure_worker(file_path: str, result_queue: mp.Queue):
    try:
        import cv2
        import numpy as _np
        from paddleocr import PPStructure

        # Determine file type
        is_pdf = file_path.lower().endswith(".pdf")
        images_to_parse = []

        if is_pdf:
            import fitz
            doc = fitz.open(file_path)
            for page in doc:
                pix = page.get_pixmap(dpi=150)
                img_data = pix.tobytes("png")
                nparr = _np.frombuffer(img_data, _np.uint8)
                cv_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                images_to_parse.append(cv_img)
            doc.close()
        else:
            # Assume it's a multi-page tiff or single image
            ret, imgs = cv2.imreadmulti(file_path)
            if ret and len(imgs) > 0:
                images_to_parse = imgs
            else:
                img = cv2.imread(file_path)
                if img is None:
                    raise FileNotFoundError(f"cv2 could not read image file: {file_path}")
                images_to_parse = [img]

        engine = PPStructure(show_log=True)
        pages = []
        global_idx = 0

        for page_idx, img_mat in enumerate(images_to_parse, start=1):
            md_lines, images_map, global_idx = parse_single_image(img_mat, engine, global_idx)

            pages.append({
                "markdown_content": "\n\n".join(md_lines),
                "images": images_map,
                "page_num": page_idx
            })

        result_queue.put({"status": "success", "data": pages})
    except Exception as e:
        result_queue.put({
            "status": "error",
            "message": str(e),
            "traceback": traceback.format_exc()
        })

class PPStructureParser(BaseParser):
    def __init__(self):
        pass

    def parse(self, file_path: str) -> List[Dict]:
        """
        Parses a file synchronously for API simplicity, but uses multiprocessing
        internally to bypass GIL and prevent blocking.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        result_queue = mp.Queue()
        p = mp.Process(target=pp_structure_worker, args=(file_path, result_queue))
        p.start()

        res = None
        timeout = 300
        start_time = time.time()

        try:
            while True:
                try:
                    res = result_queue.get(timeout=0.5)
                    break
                except queue_module.Empty:
                    if not p.is_alive():
                        retry_deadline = time.time() + 0.5
                        while time.time() < retry_deadline:
                            try:
                                res = result_queue.get(timeout=0.1)
                                break
                            except queue_module.Empty:
                                time.sleep(0.05)

                        if res is None:
                            raise RuntimeError(
                                f"PaddleOCR worker process terminated unexpectedly with exit code {p.exitcode}."
                            )
                        break

                    if time.time() - start_time > timeout:
                        raise TimeoutError("PaddleOCR worker process timed out after 300s.")
        finally:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
                p.join()

            try:
                result_queue.close()
                result_queue.join_thread()
            except Exception as e:
                logger.warning(f"Failed to close result_queue: {e}", exc_info=True)

        if res and res["status"] == "success":
            return res["data"]
        else:
            tb = res.get("traceback", "") if res else ""
            if tb:
                logger.error(f"PaddleOCR Worker failed:\n{tb}")
            raise RuntimeError(f"Parse failed: {res.get('message') if res else 'Unknown Error'}\n{tb}")
