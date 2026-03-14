import cv2
import numpy as np
import onnxruntime as ort
import os
from utils import logger

class DocLayoutYOLO:
    def __init__(self, model_path="models/doclayout_yolo.onnx", conf_thres=0.4, iou_thres=0.45):
        self.model_path = model_path
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.session = None
        self.input_name = None
        self.output_names = None
        self.classes = {
            0: 'title', 1: 'plain text', 2: 'abandon', 3: 'figure', 4: 'figure_caption',
            5: 'table', 6: 'table_caption', 7: 'table_footnote', 8: 'isolate_formula', 9: 'formula_caption'
        }

        if os.path.exists(self.model_path):
            self._init_session()
        else:
            logger.warning(f"DocLayout-YOLO model not found at {self.model_path}. Visual layout extraction will be disabled.")

    def _init_session(self):
        try:
            logger.info(f"Loading ONNX model from {self.model_path} with CPUExecutionProvider...")
            self.session = ort.InferenceSession(self.model_path, providers=['CPUExecutionProvider'])
            self.input_name = self.session.get_inputs()[0].name
            self.output_names = [output.name for output in self.session.get_outputs()]
            logger.info("DocLayout-YOLO ONNX model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load DocLayout-YOLO ONNX model: {e}", exc_info=True)
            self.session = None

    def _letterbox(self, img, new_shape=(1024, 1024), color=(114, 114, 114)):
        shape = img.shape[:2]
        r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
        new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
        dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]

        dw /= 2
        dh /= 2

        if shape[::-1] != new_unpad:
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)

        top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
        left, right = int(round(dw - 0.1)), int(round(dw + 0.1))

        img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
        return img, r, (dw, dh)

    def _nms(self, boxes, scores, iou_threshold):
        if len(boxes) == 0:
            return []

        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            w = np.maximum(0.0, xx2 - xx1)
            h = np.maximum(0.0, yy2 - yy1)
            inter = w * h
            ovr = inter / (areas[i] + areas[order[1:]] - inter)

            inds = np.where(ovr <= iou_threshold)[0]
            order = order[inds + 1]

        return keep

    def predict(self, pil_img):
        """
        Takes a PIL Image, returns a list of dictionaries:
        [{'box': [x_min, y_min, x_max, y_max], 'conf': float, 'class_id': int, 'class_name': str}, ...]
        """
        if self.session is None:
            return []

        try:
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            h, w = img.shape[:2]

            img_padded, r, (dw, dh) = self._letterbox(img, new_shape=(1024, 1024))
            blob = cv2.dnn.blobFromImage(img_padded, 1/255.0, (1024, 1024), swapRB=True, crop=False)

            outputs = self.session.run(self.output_names, {self.input_name: blob})

            predictions = outputs[0]
            predictions = np.squeeze(predictions)
            if predictions.shape[0] < predictions.shape[1]:
                 predictions = predictions.T
            # After transpose, expected shape: (8400, 14) for 10 classes + 4 coords

            boxes = predictions[:, :4]
            scores = predictions[:, 4:]
            class_ids = np.argmax(scores, axis=1)
            confidences = np.max(scores, axis=1)

            mask = confidences > self.conf_thres
            boxes = boxes[mask]
            confidences = confidences[mask]
            class_ids = class_ids[mask]

            if len(boxes) == 0:
                return []

            # xywh to xyxy
            x_c, y_c, w_b, h_b = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
            boxes_xyxy = np.zeros_like(boxes)
            boxes_xyxy[:, 0] = x_c - w_b / 2
            boxes_xyxy[:, 1] = y_c - h_b / 2
            boxes_xyxy[:, 2] = x_c + w_b / 2
            boxes_xyxy[:, 3] = y_c + h_b / 2
            boxes = boxes_xyxy

            # Rescale
            boxes[:, 0] -= dw
            boxes[:, 2] -= dw
            boxes[:, 1] -= dh
            boxes[:, 3] -= dh
            boxes /= r

            boxes[:, 0] = np.clip(boxes[:, 0], 0, w)
            boxes[:, 1] = np.clip(boxes[:, 1], 0, h)
            boxes[:, 2] = np.clip(boxes[:, 2], 0, w)
            boxes[:, 3] = np.clip(boxes[:, 3], 0, h)

            results = []
            for c in np.unique(class_ids):
                c_mask = class_ids == c
                c_boxes = boxes[c_mask]
                c_confs = confidences[c_mask]

                keep = self._nms(c_boxes, c_confs, self.iou_thres)
                for k in keep:
                    results.append({
                        'box': c_boxes[k].tolist(),
                        'conf': float(c_confs[k]),
                        'class_id': int(c),
                        'class_name': self.classes.get(int(c), 'unknown')
                    })

            return results
        except Exception as e:
            logger.error(f"Error during DocLayout-YOLO prediction: {e}", exc_info=True)
            return []

_doclayout_yolo_instance = None

def get_doclayout_yolo():
    global _doclayout_yolo_instance
    if _doclayout_yolo_instance is None:
        _doclayout_yolo_instance = DocLayoutYOLO()
    return _doclayout_yolo_instance
