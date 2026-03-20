import os
from utils import logger
try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

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
    def __init__(self, model_path="models/doclayout_yolo.onnx"):
        if YOLO is None:
            raise ImportError("ultralytics library is required for DocLayout-YOLO. Please install it.")

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_path = model_path if os.path.isabs(model_path) else os.path.join(base_dir, model_path)
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"DocLayout-YOLO model not found at '{self.model_path}'. Please place the onnx model there.")

        logger.info(f"Loading DocLayout-YOLO model from {self.model_path}...")
        self.model = YOLO(self.model_path)
        logger.info("DocLayout-YOLO model loaded.")



    def __call__(self, images):
        """
        Accepts a list of PIL Images (like Surya does).
        Returns a list of LayoutResult objects.
        """
        results = []
        for img in images:
            # Run inference
            # imgsz can be adjusted based on model requirements (e.g. 1024)
            preds = self.model(img, verbose=False)

            # Map predictions to Surya format
            # Each prediction contains boxes
            surya_bboxes = []
            if preds and len(preds) > 0:
                pred = preds[0]
                if pred.boxes:
                    for box in pred.boxes:
                        # Extract xyxy and label
                        xyxy = box.xyxy[0].cpu().numpy().tolist() # [x_min, y_min, x_max, y_max]
                        cls_id = int(box.cls[0].item())

                        # Get label name, default to original if unknown mapping
                        names = pred.names if hasattr(pred, "names") else None
                        if not names:
                            names = getattr(self.model, "names", None)
                        if isinstance(names, dict):
                            label_name = names.get(cls_id, f"Class_{cls_id}")
                        elif isinstance(names, (list, tuple)) and 0 <= cls_id < len(names):
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
        elif "figure" in label_lower or "picture" in label_lower or "image" in label_lower:
            return "Figure"
        elif "formula" in label_lower or "math" in label_lower or "equation" in label_lower:
            return "Formula"
        elif "form" in label_lower:
            return "Form"
        return "Text" # Default to text for other regions
