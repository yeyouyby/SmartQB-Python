import threading


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

    def emit_started(self, *args, **kwargs):
        for callback in self.started:
            callback(*args, **kwargs)

    def emit_progress(self, *args, **kwargs):
        for callback in self.progress:
            callback(*args, **kwargs)

    def emit_finished(self, *args, **kwargs):
        for callback in self.finished:
            callback(*args, **kwargs)

    def emit_error(self, *args, **kwargs):
        for callback in self.error:
            callback(*args, **kwargs)


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
