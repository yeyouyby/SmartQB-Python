from typing import List, Dict
import os
import multiprocessing as mp
import logging
import queue
from .base import BaseParser

logger = logging.getLogger(__name__)

# This process runs isolated to avoid GIL block
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
        # Catch all here to ensure worker doesn't silently die without notifying the queue
        result_queue.put({"status": "error", "message": str(e)})

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

        try:
            # Add reasonable timeout to avoid infinite blocking if worker dies
            res = result_queue.get(timeout=300)
        except queue.Empty:
            if p.is_alive():
                p.terminate()
            p.join()
            raise TimeoutError("PaddleOCR worker process timed out.")

        p.join(timeout=5)
        if p.is_alive():
            p.terminate()
            p.join()

        if res["status"] == "success":
            return res["data"]
        else:
            raise RuntimeError(f"Parse failed: {res.get('message')}")
