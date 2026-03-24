from typing import List, Dict
import os
import multiprocessing as mp
from .base import BaseParser

# This process runs isolated to avoid GIL block
def pp_structure_worker(file_path: str, result_queue: mp.Queue):
    try:
        # Import Paddle inside the worker to avoid polluting main process
        # and to make sure it loads correctly in a separate process space
        from paddleocr import PPStructure

        # Initialize engine (takes time)
        # Using MKLDNN for CPU optimization if available
        engine = PPStructure(show_log=True, image_dir=file_path)

        # In a real scenario, handle PDF vs Image. For now, assume single image for brevity.
        # result = engine(file_path)
        #
        # Simulated parsing for structure map:
        simulated_res = [{
            "markdown_content": f"Mock parsed content from {os.basename(file_path)}",
            "images": {},
            "page_num": 1
        }]

        result_queue.put({"status": "success", "data": simulated_res})
    except Exception as e:
        result_queue.put({"status": "error", "message": str(e)})

class PPStructureParser(BaseParser):
    def __init__(self):
        # We don't initialize paddle here to avoid slow startup.
        # It's done inside the worker.
        pass

    def parse(self, file_path: str) -> List[Dict]:
        """
        Parses a file synchronously for API simplicity, but uses multiprocessing
        internally to bypass GIL and prevent blocking.
        If async/non-blocking is needed for GUI, this should be called inside a QThread.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        result_queue = mp.Queue()
        p = mp.Process(target=pp_structure_worker, args=(file_path, result_queue))
        p.start()

        # This will block until the worker finishes.
        # In the actual GUI, we will wrap this `parse` call in a QThread
        # so this block doesn't freeze the main event loop.
        res = result_queue.get()
        p.join()

        if res["status"] == "success":
            return res["data"]
        else:
            raise RuntimeError(f"Parse failed: {res.get('message')}")
