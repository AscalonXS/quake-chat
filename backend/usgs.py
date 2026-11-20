import json, os, time
from pathlib import Path
import httpx

FEED_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
TTL = int(os.getenv("USGS_CACHE_SECONDS", "300"))
SAMPLE = json.loads((Path(__file__).parent / "sample_quake.json").read_text())

_cache = {"events": None, "fetched_at": 0.0}

def _parse(data: dict) -> list[dict]:
    events = []
    for f in data.get("features", []):
        p, g = f["properties"], f["geometry"]["coordinates"]
        if p.get("mag") is None:
            continue
        events.append({
            "id": f["id"], "mag": p["mag"], "place": p.get("place") or "Unknown",
            "depth_km": g[2], "time": p["time"], "url": p.get("url"),
        })
    events.sort(key=lambda e: e["time"], reverse=True)
    return events

def get_earthquakes() -> dict:
    """Return cached events; refresh if older than TTL. Falls back to stale cache, then sample."""
    now = time.time()
    fresh = _cache["events"] is not None and now - _cache["fetched_at"] < TTL
    if not fresh:
        try:
            r = httpx.get(FEED_URL, timeout=8)
            r.raise_for_status()
            _cache["events"] = _parse(r.json())
            _cache["fetched_at"] = now
        except Exception as e:
            print("USGS error:", e)
            if _cache["events"] is None:
                return {"events": [SAMPLE], "updated_at": None, "source": "sample", "stale": True}
            return {"events": _cache["events"], "updated_at": _cache["fetched_at"],
                    "source": "usgs", "stale": True}
    return {"events": _cache["events"], "updated_at": _cache["fetched_at"],
            "source": "usgs", "stale": False}
