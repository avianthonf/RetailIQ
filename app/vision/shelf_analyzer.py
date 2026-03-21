import logging
import os

from PIL import Image

try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover - optional dependency
    YOLO = None

logger = logging.getLogger(__name__)


class ShelfAnalyzer:
    """
    Analyzes retail shelf images using YOLOv8 to detect products and gaps.
    """

    def __init__(self, model_path="yolov8n.pt"):
        """
        Initializes the YOLOv8 model.
        """
        self.model_path = model_path
        self.model = None
        if YOLO is None:
            logger.warning("ultralytics is not installed. Shelf analysis will return a graceful fallback.")
            return
        try:
            if os.path.exists(model_path):
                self.model = YOLO(model_path)
                logger.info("YOLOv8 model loaded from %s", model_path)
            else:
                logger.warning("YOLOv8 model file %s not found. Inference will fail.", model_path)
        except Exception as e:
            logger.error("Failed to load YOLOv8 model: %s", str(e))

    def analyze_image(self, image_path: str) -> dict:
        """
        Performs inference on the image and returns detected products and gaps.
        """
        if not self.model:
            return {
                "error": "Model not loaded",
                "detected_products": [],
                "out_of_stock_slots": [],
                "compliance_score": 0,
            }

        try:
            results = self.model(image_path)
            detections = []

            # YOLOv8 returns a list of Results objects
            for r in results:
                boxes = r.boxes
                for box in boxes:
                    # bgr -> x1, y1, x2, y2
                    coords = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    label = self.model.names[cls]

                    detections.append({"label": label, "confidence": conf, "box": coords})

            # Identify gaps (out-of-stock slots)
            gaps = self.detect_gaps(detections)

            # Calculate compliance score (simplified: percentage of shelf filled)
            total_slots = len(detections) + len(gaps)
            compliance_score = (len(detections) / total_slots * 100) if total_slots > 0 else 100

            return {
                "detected_products": detections,
                "out_of_stock_slots": gaps,
                "compliance_score": round(compliance_score, 2),
                "model_info": f"YOLOv8 ({self.model_path})",
            }

        except Exception as e:
            logger.error("Inference failed: %s", str(e))
            return {"error": str(e), "detected_products": [], "out_of_stock_slots": []}

    def detect_gaps(self, detections: list) -> list:
        """
        Simple spatial analysis to find gaps between detected products.
        This is a heuristic-based approach.
        """
        if not detections:
            return []

        # Sort detections by y1 (vertical rows) and then x1 (horizontal position)
        sorted_dets = sorted(detections, key=lambda d: (d["box"][1], d["box"][0]))

        gaps = []
        # Group detections into rows (simplified: items with similar y-coordinates)
        rows = []
        current_row = []
        last_y = -1
        threshold_y = 50  # Heuristic for row height overlap

        for det in sorted_dets:
            y1 = det["box"][1]
            if last_y == -1 or abs(y1 - last_y) < threshold_y:
                current_row.append(det)
            else:
                rows.append(current_row)
                current_row = [det]
            last_y = y1
        if current_row:
            rows.append(current_row)

        # Analyze each row for horizontal gaps
        for row in rows:
            row = sorted(row, key=lambda d: d["box"][0])  # Sort by x
            for i in range(len(row) - 1):
                box1 = row[i]["box"]
                box2 = row[i + 1]["box"]

                # Gap between x2 of box1 and x1 of box2
                horizontal_gap = box2[0] - box1[2]
                avg_width = ((box1[2] - box1[0]) + (box2[2] - box2[0])) / 2

                # If gap is larger than 50% of average product width, mark it as a gap
                if horizontal_gap > (avg_width * 0.5):
                    gap_box = [box1[2], box1[1], box2[0], box2[3]]
                    gaps.append(
                        {"label": "gap", "box": gap_box, "estimated_missing": max(1, round(horizontal_gap / avg_width))}
                    )

        return gaps
