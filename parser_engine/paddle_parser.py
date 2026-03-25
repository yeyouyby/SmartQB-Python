from typing import List, Dict
import os
import multiprocessing as mp
import logging
import queue
import time
import traceback
from .base import BaseParser

logger = logging.getLogger(__name__)

# This process runs isolated to avoid GIL block and memory leaks in the main PySide6 process.
# We intentionally spin up and tear down the PaddleOCR engine per parse call for total stability.
def pp_structure_worker(file_path: str, result_queue: mp.Queue):
    try:
        from paddleocr import PPStructure

        # Initialize engine (takes time)
        # Using MKLDNN for CPU optimization if available. Do not pass file_path to image_dir.
        engine = PPStructure(show_log=True)

        # Execute OCR/layout analysis
        result = engine(file_path)

        # Process real results into standard format. For brevity in this mock, we map the output.
        # In a real full implementation, `result` from PPStructure needs detailed markdown construction.
        # Here we just dump the repr of the result for the user's content and keep the structure.
        markdown_content = f"Parsed content from {os.path.basename(file_path)}:\n\n{repr(result)}"

        res_data = [{
            "markdown_content": markdown_content,
            "images": {},
            "page_num": 1
        }]

        result_queue.put({"status": "success", "data": res_data})
    except Exception as e:
        # Pass traceback back through IPC so main process can log it
        tb = traceback.format_exc()
        result_queue.put({"status": "error", "message": str(e), "traceback": tb})

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
                except queue.Empty:
                    if not p.is_alive():
                        # Subprocess died unexpectedly before returning anything
                        raise RuntimeError(f"PaddleOCR worker process terminated unexpectedly with exit code {p.exitcode}.")
                    if time.time() - start_time > timeout:
                        raise TimeoutError("PaddleOCR worker process timed out.")
        finally:
            # Always ensure cleanup
            if p.is_alive():
                p.terminate()
            p.join(timeout=1)

        if res and res["status"] == "success":
            return res["data"]
        else:
            tb = res.get("traceback", "") if res else ""
            if tb:
                logger.error(f"PaddleOCR Worker failed:\n{tb}")
            raise RuntimeError(f"Parse failed: {res.get('message') if res else 'Unknown Error'}")
