from PySide6.QtCore import QThread, Signal
from utils import logger

class WorkerThread(QThread):
    finished_signal = Signal(object)
    error_signal = Signal(str)
    progress_signal = Signal(str)

    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.task_func(*self.args, **self.kwargs)
            self.finished_signal.emit(result)
        except Exception as e:
            logger.error(f"WorkerThread Error: {e}", exc_info=True)
            self.error_signal.emit(str(e))
