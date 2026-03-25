import os
from utils import logger

try:
    from ultralytics import YOLO
    import torch
except ImportError:
    YOLO = None


import sys


def get_base_path():
    """获取程序当前运行的目录，完美兼容 .py 和 .exe 两种情况"""
    if getattr(sys, "frozen", False):
        # 如果是打包后的 .exe 运行，返回 .exe 所在的当前目录
        return os.path.dirname(sys.executable)
    else:
        # 如果是开发环境下的 .py 运行，返回脚本所在目录
        return os.path.dirname(os.path.abspath(__file__))


class DummyBoundingBox:
    def __init__(self, bbox, label):
        self.bbox = bbox
        self.label = label


class DummyLayoutResult:
    def __init__(self, bboxes):
        self.bboxes = bboxes


class DocLayoutYOLO:
    """
    A wrapper for DocLayout-YOLO (onnx model) that mimics Surya's LayoutPredictor interface
    so it can drop-in replace it in document_service.py.
    """

    def __init__(
        self, model_path="model/doclayoutyolo/DocLayout-YOLO-DocStructBench.onnx"
    ):
        if YOLO is None:
            logger.warning("ultralytics library is missing for DocLayout-YOLO.")
            self.model_path = None
            self.model = None
            return

        base_dir = get_base_path()
        self.model_path = (
            model_path
            if os.path.isabs(model_path)
            else os.path.join(base_dir, model_path)
        )
        self.model = None  # Lazy load in __call__

    def __call__(self, images):
        """
        Accepts a list of PIL Images (like Surya does).
        Returns a list of LayoutResult objects.
        """
        if YOLO is None:
            raise ImportError(
                "ultralytics library is required for DocLayout-YOLO. Please install it."
            )

        if self.model is None:
            if not self.model_path or not os.path.exists(self.model_path):
                raise FileNotFoundError(
                    f"DocLayout-YOLO model not found at '{self.model_path}'. Please place the onnx model there."
                )
            logger.info(f"Lazy loading DocLayout-YOLO model from {self.model_path}...")
            self.model = YOLO(self.model_path)
            logger.info("DocLayout-YOLO model loaded.")

        results = []
        for img in images:
            # Run inference
            # imgsz can be adjusted based on model requirements (e.g. 1024)

            # Use half precision only on compatible non-ONNX CUDA backends
            use_half = bool(
                "torch" in globals()
                and torch is not None
                and torch.cuda.is_available()
                and str(self.model_path).lower().endswith((".pt", ".engine"))
            )

            preds = self.model(img, verbose=False, half=use_half)

            # Map predictions to Surya format
            # Each prediction contains boxes
            surya_bboxes = []
            if preds and len(preds) > 0:
                pred = preds[0]
                if pred.boxes is not None and len(pred.boxes) > 0:
                    for box in pred.boxes:
                        # Extract xyxy and label
                        xyxy = (
                            box.xyxy[0].cpu().numpy().tolist()
                        )  # [x_min, y_min, x_max, y_max]
                        cls_id = int(box.cls[0].item())

                        # Get label name, default to original if unknown mapping
                        names = pred.names if hasattr(pred, "names") else None
                        if not names:
                            names = getattr(self.model, "names", None)
                        if isinstance(names, dict):
                            label_name = names.get(cls_id, f"Class_{cls_id}")
                        elif isinstance(names, (list, tuple)) and 0 <= cls_id < len(
                            names
                        ):
                            label_name = names[cls_id]
                        else:
                            label_name = f"Class_{cls_id}"

                        # Normalize label to Match Surya's expected strings if possible
                        # Surya expects things like 'Picture', 'Figure', 'Table', 'Formula', 'Text-inline-math', 'Form' for extraction
                        normalized_label = self._normalize_label(label_name)

                        surya_bboxes.append(DummyBoundingBox(xyxy, normalized_label))

            results.append(DummyLayoutResult(surya_bboxes))

        return results

    def _normalize_label(self, label):
        """Map YOLO classes to Surya-like classes used in document_service.py."""
        label_lower = label.lower()
        if "table" in label_lower:
            return "Table"
        elif (
            "figure" in label_lower
            or "picture" in label_lower
            or "image" in label_lower
        ):
            return "Figure"
        elif (
            "formula" in label_lower
            or "math" in label_lower
            or "equation" in label_lower
        ):
            return "Formula"
        elif "form" in label_lower:
            return "Form"
        return "Text"  # Default to text for other regions
