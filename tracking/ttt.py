import asyncio
import json
import websockets

WS_URL = "ws://127.0.0.1:8000/ws/tracking/104/"
INTERVAL_SEC = 0.5
SPEED_KMH = 25
HEADING = 254

ROUTE_POINTS = [
    (33.552516, 36.388156),
    (33.552016, 36.388158),
    (33.551911, 36.387848),
    (33.551907, 36.387335),
    (33.551983, 36.386852),
    (33.552068, 36.386406),
    (33.552168, 36.386075),
    (33.552199, 36.385806),
    (33.552339, 36.385901),
    (33.552540, 36.386065),
    (33.552754, 36.386216),
    (33.552987, 36.386346),
    (33.553159, 36.386428),
    (33.553294, 36.386482),
    (33.553351, 36.386308),
    (33.553425, 36.386108),
    (33.553579, 36.385658),
]

def densify(points, step_count_between=4):
    dense = []
    for i in range(len(points) - 1):
        lat1, lon1 = points[i]
        lat2, lon2 = points[i + 1]
        dense.append((lat1, lon1))
        for s in range(1, step_count_between + 1):
            t = s / (step_count_between + 1)
            dense.append((lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t))
    dense.append(points[-1])
    return dense

DENSE_POINTS = densify(ROUTE_POINTS, 4)

async def main():
    # ping_interval=None => تعطيل keepalive ping
    async with websockets.connect(WS_URL, ping_interval=None) as ws:
        print(f"Connected to {WS_URL}")
        print(f"Original points: {len(ROUTE_POINTS)} | Dense points: {len(DENSE_POINTS)}")

        for i, (lat, lon) in enumerate(DENSE_POINTS, start=1):
            payload = {
                "current_latitude": lat,
                "current_longitude": lon,
                "speed_kmh": SPEED_KMH,
                "heading": HEADING,
                "is_active": True
            }
            await ws.send(json.dumps(payload))
            if i % 20 == 0 or i in (1, len(DENSE_POINTS)):
                print(f"Sent {i}/{len(DENSE_POINTS)}")
            await asyncio.sleep(INTERVAL_SEC)

        print("Done sending route points.")

if __name__ == "__main__":
    asyncio.run(main())
