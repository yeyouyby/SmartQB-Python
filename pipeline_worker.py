import threading
import logging

logger = logging.getLogger("SmartQB")

class WorkerSignals:
    """
    A pseudo-signal class mimicking PySide6's Signal mechanism.
    When moving to PySide, this can simply inherit QObject and define actual pyqtSignals.
    """

    def __init__(self):
        self.started = []
        self.progress = []
        self.finished = []
        self.error = []

    def _emit(self, callbacks, signal_name, *args, **kwargs):
        for callback in callbacks:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {signal_name} callback: {e}", exc_info=True)

    def emit_started(self, *args, **kwargs):
        for callback in self.started:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                import logging
                logging.getLogger("SmartQB").error(f"Error in emit_started callback: {e}", exc_info=True)

    def emit_progress(self, *args, **kwargs):
        for callback in self.progress:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                import logging
                logging.getLogger("SmartQB").error(f"Error in emit_progress callback: {e}", exc_info=True)

    def emit_finished(self, *args, **kwargs):
        for callback in self.finished:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                import logging
                logging.getLogger("SmartQB").error(f"Error in emit_finished callback: {e}", exc_info=True)

    def emit_error(self, *args, **kwargs):
        for callback in self.error:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                import logging
                logging.getLogger("SmartQB").error(f"Error in emit_error callback: {e}", exc_info=True)


class GenericWorker(threading.Thread):
    """
    A generic background worker thread that uses pseudo-signals to report status.
    Easily convertible to QThread in PySide.
    """

    def __init__(self, task_func, *args, **kwargs):
        super().__init__(daemon=True)
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        self.signals.emit_started()
        try:
            result = self.task_func(
                self.signals.emit_progress, *self.args, **self.kwargs
            )
            self.signals.emit_finished(result)
        except Exception as e:
            self.signals.emit_error(e)