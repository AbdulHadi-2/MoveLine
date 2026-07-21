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

HEAVY_ITEMS = {
    "Sofa",
    "Bed",
    "Wardrobe",
    "Refrigerator",
    "Washing Machine",
    "Oven",
}

VEHICLE_BASE_WORKERS = {
    "small": 1,
    "medium": 2,
    "large": 3,
}


def _safe_int(value, default=0):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(value, default)


def estimate_items_volume_m3(items):
    total = 0.0
    for item in items or []:
        label = item.get("label")
        quantity = _safe_int(item.get("quantity", 1), default=1)
        total += ITEM_VOLUMES_M3.get(label, 0.0) * quantity
    return total


def estimate_minimum_workers(
    items,
    vehicle_type=None,
    pickup_floor=0,
    pickup_has_elevator=False,
    dropoff_floor=0,
    dropoff_has_elevator=False,
    assembly=False,
    disassembly=False,
):
    has_items = bool(items)
    total_volume = estimate_items_volume_m3(items)
    if has_items:
        if total_volume <= 6:
            workers = 1
        elif total_volume <= 12:
            workers = 2
        elif total_volume <= 20:
            workers = 3
        else:
            workers = 4
    else:
        workers = VEHICLE_BASE_WORKERS.get(vehicle_type, 1)

    heavy_quantity = 0
    for item in items or []:
        if item.get("label") in HEAVY_ITEMS:
            heavy_quantity += _safe_int(item.get("quantity", 1), default=1)

    if heavy_quantity > 0 and workers < 2:
        workers = 2
    if heavy_quantity >= 3:
        workers += 1

    pickup_stairs = _safe_int(pickup_floor) if not pickup_has_elevator else 0
    dropoff_stairs = _safe_int(dropoff_floor) if not dropoff_has_elevator else 0
    highest_stairs_floor = max(pickup_stairs, dropoff_stairs)

    if highest_stairs_floor >= 4 and (workers >= 2 or total_volume >= 6):
        workers += 1
    if highest_stairs_floor >= 7:
        workers += 1

    if assembly and disassembly and (total_volume > 8 or workers >= 4):
        workers += 1
    elif (assembly or disassembly) and total_volume > 12:
        workers += 1

    return min(max(workers, 1), 6)
