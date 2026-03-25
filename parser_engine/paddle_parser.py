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

# This process runs isolated to avoid GIL block and memory leaks in the main PySide6 process.
# We intentionally spin up and tear down the PaddleOCR engine per parse call for total stability.
def pp_structure_worker(file_path: str, result_queue: mp.Queue):
    try:
        import cv2
        from paddleocr import PPStructure

        engine = PPStructure(show_log=True)
        img = cv2.imread(file_path)
        if img is None:
            raise FileNotFoundError(f"cv2 could not read image file: {file_path}")

        raw_result = engine(img)

        md_lines = []
        images_map = {}

        for idx, block in enumerate(raw_result):
            block_type = block.get("type", "").strip().lower()
            res = block.get("res")

            if block_type in ("text", "title"):
                # res: list of (bbox, (text, confidence)) tuples
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
                # res: dict with 'html' key containing HTML string of the table
                if isinstance(res, dict) and "html" in res:
                    md_lines.append(res["html"])
                elif isinstance(res, str):
                    md_lines.append(res)

            elif block_type in ("figure", "figure_caption", "image"):
                # img: numpy array of the cropped region
                img_array = block.get("img")
                if img_array is not None:
                    import cv2 as _cv2
                    _, buf = _cv2.imencode(".png", img_array)
                    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
                    img_id = f"fig_{idx}"
                    images_map[img_id] = b64
                    md_lines.append(f"![{img_id}]({img_id})")

        pages = [{
            "markdown_content": "\n\n".join(md_lines),
            "images": images_map,
            "page_num": 1
        }]

        result_queue.put({"status": "success", "data": pages})
    except Exception as e:
        # Pass traceback back through IPC so main process can log it
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
            # Poll instead of a single blocking `get` to detect early crashes without hanging for 300s
            while True:
                try:
                    res = result_queue.get(timeout=0.5)
                    break
                except queue_module.Empty:
                    if not p.is_alive():
                        # Worker may have called result_queue.put() just before the OS
                        # marked it as dead; give the IPC pipe up to 500ms to deliver the data.
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
            # Always ensure cleanup
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
                p.join()

            # Explicitly close the queue to release background thread and OS handles
            try:
                result_queue.close()
                result_queue.join_thread()
            except Exception:
                pass

        if res and res["status"] == "success":
            return res["data"]
        else:
            tb = res.get("traceback", "") if res else ""
            if tb:
                logger.error(f"PaddleOCR Worker failed:\n{tb}")
            raise RuntimeError(f"Parse failed: {res.get('message') if res else 'Unknown Error'}\n{tb}")
