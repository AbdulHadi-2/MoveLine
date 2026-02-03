import os
import tempfile
from collections import Counter

# import torch
from PIL import Image
from ultralytics import YOLO

YOLO_WEIGHTS = "yolov8n##.pt"

YOLO_CONF = 0.25

ALLOWED_ITEMS = {
    "Sofa",
    "Bed",
    "Wardrobe",
    "Table",
    "Chair",
    "Desk",
    "TV Stand",
    "Refrigerator",
    "Washing Machine",
    "Oven",
    "Air Conditioner",
    "TV",
    "Moving Box",
    "Large Box",
    "Fragile Box",
}

ITEM_VOLUMES_M3 = {
    "Sofa": 2.5,
    "Bed": 3.0,
    "Wardrobe": 3.5,
    "Table": 1.0,
    "Chair": 0.3,
    "Desk": 1.2,
    "TV Stand": 0.8,
    "Refrigerator": 1.8,
    "Washing Machine": 0.9,
    "Oven": 0.7,
    "Air Conditioner": 0.6,
    "TV": 0.4,
    "Moving Box": 0.1,
    "Large Box": 0.2,
    "Fragile Box": 0.12,
}

VEHICLE_CAPACITY_M3 = {
    "small": 8.0,
    "medium": 16.0,
    "large": 9999.0,
}

POST_FILTER_MAP = {
    "couch": "Sofa",
    "Couch": "Sofa",
    "sofa": "Sofa",
    "Sofa": "Sofa",
    "bed": "Bed",
    "Bed": "Bed",
    "wardrobe": "Wardrobe",
    "Wardrobe": "Wardrobe",
    "closet": "Wardrobe",
    "Closet": "Wardrobe",
    "dining table": "Table",
    "Dining Table": "Table",
    "coffee table": "Table",
    "Coffee Table": "Table",
    "table": "Table",
    "Table": "Table",
    "chair": "Chair",
    "Chair": "Chair",
    "armchair": "Chair",
    "Armchair": "Chair",
    "desk": "Desk",
    "Desk": "Desk",
    "tv stand": "TV Stand",
    "TV stand": "TV Stand",
    "Tv Stand": "TV Stand",
    "TV Stand": "TV Stand",
    "tv": "TV",
    "Tv": "TV",
    "TV": "TV",
    "television": "TV",
    "Television": "TV",
    "refrigerator": "Refrigerator",
    "Refrigerator": "Refrigerator",
    "fridge": "Refrigerator",
    "Fridge": "Refrigerator",
    "washing machine": "Washing Machine",
    "Washing Machine": "Washing Machine",
    "washer": "Washing Machine",
    "Washer": "Washing Machine",
    "oven": "Oven",
    "Oven": "Oven",
    "air conditioner": "Air Conditioner",
    "Air Conditioner": "Air Conditioner",
    "ac": "Air Conditioner",
    "AC": "Air Conditioner",
    "box": "Moving Box",
    "Box": "Moving Box",
    "boxes": "Moving Box",
    "Boxes": "Moving Box",
}


def _is_fragile(label: str) -> bool:
    return label in {"TV", "TV Stand", "Fragile Box", "Air Conditioner"}


def _post_filter_items(raw_items):
    merged = {}
    for item in raw_items or []:
        raw_label = item.get("label", "")
        qty = item.get("quantity", 1)
        try:
            qty = int(qty)
        except Exception:
            qty = 1
        if qty < 1:
            qty = 1

        label = POST_FILTER_MAP.get(raw_label, raw_label)
        if label not in ALLOWED_ITEMS:
            continue

        if label not in merged:
            merged[label] = {
                "label": label,
                "quantity": 0,
                "is_fragile": _is_fragile(label),
            }
        merged[label]["quantity"] += qty

    return sorted(merged.values(), key=lambda x: x["label"])

def estimate_total_volume_m3(items):
    total = 0.0
    for item in items or []:
        label = item.get("label")
        qty = item.get("quantity", 1)
        try:
            qty = int(qty)
        except Exception:
            qty = 1
        if qty < 1:
            qty = 1
        volume = ITEM_VOLUMES_M3.get(label, 0.0)
        total += volume * qty
    return total


def recommend_vehicle_type(total_volume_m3):
    # Add a safety margin to avoid tight packing.
    required = total_volume_m3 * 1.2
    if required <= VEHICLE_CAPACITY_M3["small"]:
        return "small"
    if required <= VEHICLE_CAPACITY_M3["medium"]:
        return "medium"
    return "large"


class HybridMoveLineDetector:
    def __init__(self):
        # self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.yolo = YOLO(YOLO_WEIGHTS)

    # @torch.no_grad()
    # def _detect_with_yolo(self, image_path: str):
    #     results = self.yolo(image_path, conf=YOLO_CONF, verbose=False)
    #     r = results[0]
    #     names = r.names

    #     labels = []
    #     if r.boxes is not None and r.boxes.cls is not None:
    #         for c in r.boxes.cls.tolist():
    #             labels.append(names[int(c)])
    #     return Counter(labels)

    def predict(self, image_path: str):
        yolo_counts = self._detect_with_yolo(image_path)
        raw_items = []
        for label, qty in yolo_counts.items():
            raw_items.append(
                {
                    "label": label,
                    "quantity": int(qty),
                    "is_fragile": False,
                }
            )
        return raw_items


_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        _detector = HybridMoveLineDetector()
    return _detector


def analyze_image(pil_image: Image.Image) -> dict:
    detector = _get_detector()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        pil_image.save(tmp_path, format="JPEG")
        raw_items = detector.predict(tmp_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    items = _post_filter_items(raw_items)
    total_volume = estimate_total_volume_m3(items)
    return {
        "items": items,
        "estimated_total_volume_m3": round(total_volume, 2),
        "recommended_vehicle_type": recommend_vehicle_type(total_volume),
    }
