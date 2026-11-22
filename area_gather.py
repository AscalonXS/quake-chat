"""
area_gatherer.py - Gather settlements (cities & villages), terrain features, major roads/chokepoints,
and open evacuation areas around an epicenter using local GeoNames data + fast Photon OSM search.
"""
import hashlib
import json
import math
import os
import numpy as np
import requests

from impacts import pop, LAT, LON, P, NAMES, COUNTRY, DEM, distance_km, mmi_from_hypo_distance, ROMAN

CACHE_DIR = "data/area_cache"
PHOTON_URL = "https://photon.komoot.io/api/"
HEADERS = {"User-Agent": "QuakeChatStudentProject/1.0 (educational-simulation)"}

def _haversine_km(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return float(2 * 6371 * np.arcsin(np.sqrt(a)))

def gather_settlements(lat, lon, mag, depth_km, radius_km=30):
    """Pulls nearby cities and smaller towns/villages from population_cities.csv with local MMI & elevation."""
    d = distance_km(lat, lon)
    mask = d <= radius_km
    idxs = np.where(mask)[0]
    if len(idxs) == 0:
        return {"cities": [], "villages": [], "avg_elevation_m": None}

    items = []
    for i in idxs:
        dist = float(d[i])
        r_hyp = math.sqrt(dist ** 2 + depth_km ** 2)
        mmi_val = round(float(mmi_from_hypo_distance(mag, r_hyp)), 1)
        mmi_int = max(1, min(10, int(round(mmi_val))))
        elev = None if np.isnan(DEM[i]) else int(round(float(DEM[i])))
        items.append({
            "name": str(NAMES[i]),
            "country": str(COUNTRY[i]),
            "population": int(P[i]),
            "distance_km": round(dist, 1),
            "elevation_m": elev,
            "mmi": mmi_val,
            "mmi_roman": ROMAN[mmi_int],
        })

    cities = sorted([x for x in items if x["population"] >= 50000], key=lambda x: x["distance_km"])[:4]
    villages = sorted([x for x in items if x["population"] < 50000], key=lambda x: x["distance_km"])[:5]

    valid_elevs = [x["elevation_m"] for x in items if x["elevation_m"] is not None]
    avg_elev = round(float(np.mean(valid_elevs)), 1) if valid_elevs else None
    return {"cities": cities, "villages": villages, "avg_elevation_m": avg_elev}

def _search_photon(query_term, lat, lon, radius_km=15, limit=8):
    """Fast location-biased OpenStreetMap search via Photon (~0.3s per call)."""
    try:
        r = requests.get(
            PHOTON_URL,
            params={"q": query_term, "lat": lat, "lon": lon, "limit": limit},
            headers=HEADERS,
            timeout=8,
        )
        if r.status_code != 200:
            return []
        results = []
        for feat in r.json().get("features", []):
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [])
            name = props.get("name")
            if not name or len(coords) < 2:
                continue
            plon, plat = float(coords[0]), float(coords[1])
            dist = round(_haversine_km(lat, lon, plat, plon), 1)
            if dist <= radius_km:
                results.append({
                    "name": name,
                    "osm_key": props.get("osm_key", ""),
                    "osm_value": props.get("osm_value", ""),
                    "distance_km": dist,
                })
        return results
    except Exception:
        return []

def gather_osm_features(lat, lon, radius_km=15):
    """Fetches roads/chokepoints, terrain features, high-density zones, and open assembly spots."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = hashlib.md5(f"photon_{round(lat, 3)}_{round(lon, 3)}_{radius_km}".encode()).hexdigest()[:12]
    cache_path = os.path.join(CACHE_DIR, f"area_{key}.json")

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    out = {
        "major_roads": [],
        "bridges_tunnels": [],
        "open_assembly_spots": [],
        "high_density_hubs": [],
        "terrain_markers": [],
    }

    # 1. Major roads & highways
    seen = set()
    for term in ("expressway", "highway", "avenue", "road"):
        for item in _search_photon(term, lat, lon, radius_km=radius_km, limit=6):
            if item["osm_key"] == "highway" and item["name"].lower() not in seen:
                seen.add(item["name"].lower())
                out["major_roads"].append({
                    "name": item["name"],
                    "type": item["osm_value"].replace("_", " "),
                    "distance_km": item["distance_km"],
                })

    # 2. Bridges & tunnels
    seen.clear()
    for term in ("bridge", "tunnel"):
        for item in _search_photon(term, lat, lon, radius_km=radius_km, limit=6):
            if (item["osm_key"] in ("bridge", "tunnel", "highway") or term in item["name"].lower()) and item["name"].lower() not in seen:
                seen.add(item["name"].lower())
                out["bridges_tunnels"].append({
                    "name": item["name"],
                    "type": term,
                    "distance_km": item["distance_km"],
                })

    # 3. Open parks & assembly spots
    seen.clear()
    for term in ("park", "plaza", "stadium", "shelter"):
        for item in _search_photon(term, lat, lon, radius_km=radius_km, limit=6):
            if item["osm_key"] in ("leisure", "amenity", "emergency", "tourism") and item["name"].lower() not in seen:
                seen.add(item["name"].lower())
                out["open_assembly_spots"].append({
                    "name": item["name"],
                    "type": item["osm_value"].replace("_", " "),
                    "distance_km": item["distance_km"],
                })

    # 4. High-density hubs (hospitals & major transit stations)
    seen.clear()
    for term in ("hospital", "station"):
        for item in _search_photon(term, lat, lon, radius_km=radius_km, limit=6):
            if item["osm_value"] in ("hospital", "clinic", "station", "halt", "subway_entrance") and item["name"].lower() not in seen:
                seen.add(item["name"].lower())
                out["high_density_hubs"].append({
                    "name": item["name"],
                    "type": item["osm_value"].replace("_", " "),
                    "distance_km": item["distance_km"],
                })

    # 5. Terrain markers (mountains, peaks, rivers, beaches/coasts)
    seen.clear()
    for term in ("mountain", "peak", "river", "beach"):
        for item in _search_photon(term, lat, lon, radius_km=radius_km, limit=5):
            if item["osm_key"] in ("natural", "waterway") and item["name"].lower() not in seen:
                seen.add(item["name"].lower())
                t_type = item["osm_value"].replace("_", " ")
                out["terrain_markers"].append({
                    "label": f"{item['name']} ({t_type})",
                    "type": t_type,
                    "distance_km": item["distance_km"],
                })

    for k in out:
        out[k].sort(key=lambda x: x["distance_km"])
        out[k] = out[k][:4]

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return out

def build_area_profile(lat, lon, mag, depth_km):
    settlements = gather_settlements(lat, lon, mag, depth_km, radius_km=30)
    osm = gather_osm_features(lat, lon, radius_km=15)

    avg_elev = settlements["avg_elevation_m"]
    terrain_types = [t["type"] for t in osm["terrain_markers"]]
    has_peaks = any(t in terrain_types for t in ("peak", "volcano", "ridge", "mountain pass")) or (avg_elev is not None and avg_elev >= 300)
    has_coast = any(t in terrain_types for t in ("coastline", "beach", "bay")) or (avg_elev is not None and avg_elev <= 25)
    total_city_pop = sum(c["population"] for c in settlements["cities"])

    env_tags = []
    if has_peaks:
        env_tags.append("Mountainous / Hilly Terrain")
    if has_coast:
        env_tags.append("Coastal / Low-Lying Basin")
    if total_city_pop >= 200000:
        env_tags.append("High-Density Urban Area")
    if not env_tags:
        env_tags.append("Mixed Town & Rural Area")

    return {
        "environment_classification": ", ".join(env_tags),
        "settlements": settlements,
        "osm": osm,
    }

if __name__ == "__main__":
    import pprint
    pprint.pprint(build_area_profile(37.57, 126.98, 7.5, 10))