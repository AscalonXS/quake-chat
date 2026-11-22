"""
realtime_pipeline.py - End-to-End Real-Time Seismic Pipeline:
  1. Live USGS Seismicity + Live Open-Meteo Weather + Spatial/Road/Village Profile
  2. Trained AI Historical Analog Model (M4+, M5+, M6+, M7+ conditional rates + 1h/6h/24h next-shock windows)
  3. Physics Impact Calculator (impacts.py)
  4. Chain-of-Thought (CoT) LLM Simulation + RAG Safety Guidance + Number & Anti-Prediction Guardrails

Run:
  python realtime_pipeline.py 37.57 126.98 --hypothetical-mag 7.5
  python realtime_pipeline.py 35.68 139.69
"""
from datetime import datetime, timedelta, timezone
import math
import os
import pickle
import re
import sys
import numpy as np
import ollama
import requests

from area_gather import build_area_profile
from impacts import get_impact
from quake_describe import MODEL, allowed_numbers, get_guidance, unknown_numbers
from quake_simulate import MMI_PERCEPTION, describe_time_context

USGS_QUERY_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
AI_MODEL_PATH = "models/aftershock_ai.pkl"

REASONING_MODEL = os.getenv("QUAKE_COT_MODEL", MODEL)

SAFE_DISCLAIMER = (
    "DISCLAIMER: Earthquakes and aftershocks cannot be predicted. "
    "All shaking, impact, and aftershock figures above are hypothetical simulations and "
    "historical statistical estimates—not a prediction or an official warning. "
    "In an emergency, follow official instructions and call your local emergency number."
)

FORBIDDEN_WORDS = (
    "predict", "prediction", "predicting", "predicted",
    "will happen", "will strike", "will occur", "will hit",
    "is going to hit", "is going to strike", "guaranteed",
)

def forbidden_claims(text):
    low = text.lower()
    return [w for w in FORBIDDEN_WORDS if w in low]

def _haversine_km(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return float(2 * 6371 * np.arcsin(np.sqrt(a)))

# ------------------------------------------------------------------ Stage 1: Real-Time Collectors
def fetch_realtime_seismicity(lat, lon, radius_km=250, days=30):
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    params = {
        "format": "geojson",
        "starttime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "latitude": lat,
        "longitude": lon,
        "maxradiuskm": radius_km,
        "minmagnitude": 2.5,
        "orderby": "time",
    }
    try:
        r = requests.get(USGS_QUERY_URL, params=params, timeout=15)
        r.raise_for_status()
        features = r.json().get("features", [])
    except Exception as e:
        print(f"WARNING: USGS live feed unavailable ({e}); proceeding with empty live feed.")
        features = []

    events = []
    for f in features:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [])
        if len(coords) < 3 or props.get("mag") is None:
            continue
        ev_time = datetime.fromtimestamp(props.get("time", 0) / 1000.0, tz=timezone.utc)
        hours_ago = max(0.05, (end_dt - ev_time).total_seconds() / 3600.0)
        events.append({
            "place": props.get("place", "Unknown"),
            "mag": float(props["mag"]),
            "lon": float(coords[0]),
            "lat": float(coords[1]),
            "depth_km": max(1.0, float(coords[2])),
            "hours_ago": round(hours_ago, 1),
        })

    last_24h = [e for e in events if e["hours_ago"] <= 24.0]
    largest = max(events, key=lambda x: x["mag"]) if events else None
    return {
        "count_30d": len(events),
        "count_24h": len(last_24h),
        "largest_recent": largest,
        "events": events,
    }

def fetch_realtime_weather(lat, lon):
    try:
        r = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,precipitation",
                "daily": "precipitation_sum",
                "past_days": 1,
                "forecast_days": 1,
            },
            timeout=10,
        )
        r.raise_for_status()
        js = r.json()
        rain_24h = round(float(js.get("daily", {}).get("precipitation_sum", [0.0])[0] or 0.0), 1)
        return {
            "temp_c": js.get("current", {}).get("temperature_2m"),
            "rain_24h_mm": rain_24h,
            "soil_saturated": rain_24h >= 20.0,
        }
    except Exception:
        return {"temp_c": None, "rain_24h_mm": 0.0, "soil_saturated": False}

# ------------------------------------------------------------------ Stage 2: Conditional Historical Analog Estimator
def _omori_decay_ratio(hours_since_main, duration_days):
    p, c = 1.08, 0.05
    t1 = max(hours_since_main / 24.0, 0.0)
    if t1 == 0.0:
        return 1.0
    int_now = ((t1 + duration_days + c) ** (1 - p) - (t1 + c) ** (1 - p)) / (1 - p)
    int_zero = ((duration_days + c) ** (1 - p) - (c) ** (1 - p)) / (1 - p)
    return max(0.05, min(1.0, int_now / int_zero))

def _poisson_pct(lam):
    return round((1.0 - math.exp(-max(0.0, lam))) * 100.0, 1)

def estimate_next_shock_window(expected_24h_m4, expected_24h_m5):
    """
    Converts 24h expected rates into short-term probabilities (1h, 6h, 24h)
    and average waiting time until the next M4+ / M5+ tremor (conditional on an active sequence).
    """
    def _window_stats(rate_24h):
        if rate_24h <= 0.01:
            return {"prob_1h_pct": 0.0, "prob_6h_pct": 0.0, "prob_24h_pct": 0.0, "avg_wait_hours": None}
        hourly_rate = rate_24h / 24.0
        return {
            "prob_1h_pct": round((1.0 - math.exp(-hourly_rate * 1.0)) * 100.0, 1),
            "prob_6h_pct": round((1.0 - math.exp(-hourly_rate * 6.0)) * 100.0, 1),
            "prob_24h_pct": round((1.0 - math.exp(-hourly_rate * 24.0)) * 100.0, 1),
            "avg_wait_hours": round(24.0 / rate_24h, 1),
        }

    return {
        "next_M4_plus": _window_stats(expected_24h_m4),
        "next_M5_plus": _window_stats(expected_24h_m5),
    }

def estimate_conditional_aftershocks(main_mag, depth_km, lat, bg_30d, bg_24h, has_larger_7d=0.0, hours_since_main=0.1):
    """Estimates historical analog aftershock rates (M4+, M5+, M6+, M7+) and next-shock windows conditional on a mainshock."""
    if os.path.exists(AI_MODEL_PATH):
        with open(AI_MODEL_PATH, "rb") as f:
            bundle = pickle.load(f)

        feats = np.array(
            [[main_mag, depth_km, abs(lat), np.log1p(bg_30d), np.log1p(bg_24h), float(has_larger_7d)]],
            dtype=float,
        )
        raw_preds = []
        for gbdt, mlp in zip(bundle["gbdt"], bundle["mlp"]):
            log_pred = 0.5 * float(gbdt.predict(feats)[0]) + 0.5 * float(mlp.predict(feats)[0])
            raw_preds.append(max(0.0, math.expm1(log_pred)))

        scale_24h = _omori_decay_ratio(hours_since_main, 1.0)
        scale_7d = _omori_decay_ratio(hours_since_main, 7.0)
        gr_m4 = 10.0 ** (0.91 * (4.5 - 4.0))

        m4_24 = raw_preds[0] * gr_m4 * scale_24h
        m5_24 = raw_preds[1] * scale_24h
        m6_24 = raw_preds[2] * scale_24h
        m7_24 = raw_preds[3] * scale_24h

        m4_7d = raw_preds[4] * gr_m4 * scale_7d
        m5_7d = raw_preds[5] * scale_7d
        m6_7d = raw_preds[6] * scale_7d
        m7_7d = raw_preds[7] * scale_7d
        engine = "AI Historical Analog Ensemble (GBDT + Neural Network trained on past catalog sequences)"
    else:
        a, b, p, c = -1.67, 0.91, 1.08, 0.05
        t1 = max(hours_since_main / 24.0, 0.01)
        def _rj(m_min, days):
            t2 = t1 + days
            omori = ((t2 + c) ** (1 - p) - (t1 + c) ** (1 - p)) / (1 - p)
            return (10 ** (a + b * (main_mag - m_min))) * omori
        m4_24, m5_24, m6_24, m7_24 = _rj(4.0, 1.0), _rj(5.0, 1.0), _rj(6.0, 1.0), _rj(7.0, 1.0)
        m4_7d, m5_7d, m6_7d, m7_7d = _rj(4.0, 7.0), _rj(5.0, 7.0), _rj(6.0, 7.0), _rj(7.0, 7.0)
        engine = "Reasenberg-Jones Empirical Baseline"

    return {
        "engine": engine,
        "next_shock_windows": estimate_next_shock_window(m4_24, m5_24),
        "next_24h": {
            "expected_M4_plus": round(m4_24, 1),
            "expected_M5_plus": round(m5_24, 1),
            "prob_M5_plus_pct": _poisson_pct(m5_24),
            "prob_M6_plus_pct": _poisson_pct(m6_24),
            "prob_M7_plus_pct": _poisson_pct(m7_24),
        },
        "next_7d": {
            "expected_M4_plus": round(m4_7d, 1),
            "expected_M5_plus": round(m5_7d, 1),
            "prob_M5_plus_pct": _poisson_pct(m5_7d),
            "prob_M6_plus_pct": _poisson_pct(m6_7d),
            "prob_M7_plus_pct": _poisson_pct(m7_7d),
        },
    }

# ------------------------------------------------------------------ Stage 4: Chain-of-Thought Prompt
COT_PROMPT = """You are a technical data-to-text assistant summarizing pre-computed seismic engineering metrics and public safety guidelines for a university civil-engineering readiness exercise.

Transform the structured ENGINEERING DATA and SAFETY GUIDELINES below into a clear, engaging, well-organized briefing using the exact XML tags <thought> and <simulation>.

<thought>
1. Data Review: Note the scenario parameters, live USGS background counts, and historical analog statistics (1h/6h/24h windows and 7d rates).
2. Terrain & Weather Context: Connect the terrain classification and 24h rainfall metrics to slope and road accessibility.
3. Spatial & Traffic Mapping: Connect the local hour's traffic context to the listed cities, towns/villages, roads, bridges, tunnels, and open parks.
4. Verification: Confirm every number comes strictly from ENGINEERING DATA or SAFETY GUIDELINES.
</thought>

<simulation>
### 1. Seismic Context & Historical Analog Statistics (M4+ to M7+)
- Summarize the live USGS background activity and the historical analog rates (1-hour, 6-hour, and 24-hour windows plus 7-day rates across M4+, M5+, M6+, and M7+), noting that these are historical statistical averages for similar-sized events.

### 2. Ground Shaking & Community Experience (Cities vs. Villages)
- Describe what residents in the listed cities and smaller towns/villages would experience based on the exact MMI levels, distances, and sensory descriptions in the data.

### 3. Crowd Movement, Road Chokepoints & Weather Factors
- Explain where people would gather (listed parks/assembly areas vs. busy stations/hospitals), which named roads, bridges, or tunnels would experience congestion at this hour, and how terrain plus rainfall affect local routes.

### 4. Recommended Preparedness & Safety Actions
- List 3 practical safety actions directly from SAFETY GUIDELINES.
</simulation>

Rules:
- Use ONLY the numbers, place names, road/bridge names, and percentages provided in ENGINEERING DATA or SAFETY GUIDELINES. Copy numbers verbatim.
- Use conditional phrasing ("would experience", "historical averages indicate", "in this exercise").
- Do not certify any specific building or bridge as structurally sound or unsound.
{extra}
ENGINEERING DATA:
{data_block}

SAFETY GUIDELINES:
{guidance}
"""

REFUSAL_PHRASES = ("i cannot", "i can't", "i am unable", "cannot create a simulation", "is there anything else")

def is_refusal(text):
    low = text.lower()
    return any(p in low for p in REFUSAL_PHRASES)

def run_pipeline(lat, lon, hypothetical_mag=None, hypothetical_depth=10.0, use_rag=True, retries=2):
    print("[1/4] Fetching live USGS seismicity & Open-Meteo weather...")
    live_seis = fetch_realtime_seismicity(lat, lon, radius_km=250, days=30)
    weather = fetch_realtime_weather(lat, lon)

    largest = live_seis["largest_recent"]
    if hypothetical_mag is not None:
        mode = "Hypothetical Stress-Test Conditioned on Live Environment"
        ev_lat, ev_lon = float(lat), float(lon)
        mag, dep, hours_since = float(hypothetical_mag), float(hypothetical_depth), 0.1
    elif largest and largest["mag"] >= 4.5:
        mode = f"Live Recent Earthquake ({largest['place']}, {largest['hours_ago']}h ago)"
        ev_lat, ev_lon = largest["lat"], largest["lon"]
        mag, dep, hours_since = largest["mag"], largest["depth_km"], largest["hours_ago"]
    else:
        mode = "Quiet Live Seismicity -> Hypothetical M6.5 Regional Stress-Test"
        ev_lat, ev_lon = float(lat), float(lon)
        mag, dep, hours_since = 6.5, float(hypothetical_depth), 0.1

    has_larger_7d = 0.0
    for ev in live_seis.get("events", []):
        if ev["hours_ago"] <= 168.0 and ev["mag"] > mag:
            if _haversine_km(ev_lat, ev_lon, ev["lat"], ev["lon"]) <= 100.0:
                has_larger_7d = 1.0
                break

    print("[2/4] Estimating conditional historical aftershock rates & next-shock windows...")
    aftershocks = estimate_conditional_aftershocks(
        mag,
        dep,
        ev_lat,
        live_seis["count_30d"],
        live_seis["count_24h"],
        has_larger_7d=has_larger_7d,
        hours_since_main=hours_since,
    )

    print("[3/4] Computing shaking intensity, exposure & local road/terrain profile...")
    base_result = get_impact(ev_lat, ev_lon, mag, dep)
    profile = build_area_profile(ev_lat, ev_lon, mag, dep)
    local_hour = int((datetime.now(timezone.utc).hour + round(ev_lon / 15.0)) % 24)
    time_ctx = describe_time_context(local_hour)
    guidance, sources = get_guidance(base_result) if use_rag else ("", [])

    s = profile["settlements"]
    osm = profile["osm"]
    a24, a7 = aftershocks["next_24h"], aftershocks["next_7d"]
    w_m4 = aftershocks["next_shock_windows"]["next_M4_plus"]
    w_m5 = aftershocks["next_shock_windows"]["next_M5_plus"]

    wait_m4_txt = f"average spacing ~{w_m4['avg_wait_hours']} hours" if w_m4["avg_wait_hours"] else "low frequency"
    wait_m5_txt = f"average spacing ~{w_m5['avg_wait_hours']} hours" if w_m5["avg_wait_hours"] else "low frequency"

    lines = [
        f"- Mode: {mode}",
        f"- Scenario: {base_result['text']['scenario']}",
        f"- Epicenter Shaking: {base_result['text']['strongest_shaking']}",
        f"- People in Strong Shaking (MMI VI+): {base_result['text']['people_strong_shaking']}",
        f"- Rough Economic Cost Range: {base_result['text']['cost_range']}",
        f"- Live USGS Activity (250 km): {live_seis['count_30d']} quakes (M2.5+) in past 30 days; {live_seis['count_24h']} in past 24 hours.",
        f"- Estimation Engine: {aftershocks['engine']}",
        f"- Short-Term Next M4+ Tremor Window (conditional on mainshock): {w_m4['prob_1h_pct']}% within 1h, "
        f"{w_m4['prob_6h_pct']}% within 6h, {w_m4['prob_24h_pct']}% within 24h ({wait_m4_txt}).",
        f"- Short-Term Next M5+ Tremor Window (conditional on mainshock): {w_m5['prob_1h_pct']}% within 1h, "
        f"{w_m5['prob_6h_pct']}% within 6h, {w_m5['prob_24h_pct']}% within 24h ({wait_m5_txt}).",
        f"- Historical Analog Aftershock Rates (Next 24h, conditional on mainshock): ~{a24['expected_M4_plus']} M4+ tremors, ~{a24['expected_M5_plus']} M5+ tremors "
        f"| Empirical occurrence rates: {a24['prob_M5_plus_pct']}% for M5+, {a24['prob_M6_plus_pct']}% for M6+, {a24['prob_M7_plus_pct']}% for M7+.",
        f"- Historical Analog Aftershock Rates (Next 7d, conditional on mainshock): ~{a7['expected_M4_plus']} M4+ tremors, ~{a7['expected_M5_plus']} M5+ tremors "
        f"| Empirical occurrence rates: {a7['prob_M5_plus_pct']}% for M5+, {a7['prob_M6_plus_pct']}% for M6+, {a7['prob_M7_plus_pct']}% for M7+.",
        f"- Live Weather at Epicenter: {weather['rain_24h_mm']} mm rain in past 24h "
        f"({'soil saturated — elevated landslide risk' if weather['soil_saturated'] else 'normal soil moisture'}).",
        f"- Terrain Classification: {profile['environment_classification']}",
        f"- Local Time & Traffic: {time_ctx['period']} — {time_ctx['traffic']}",
    ]

    for label, group in (("CITIES", s["cities"]), ("TOWNS & VILLAGES", s["villages"])):
        lines.append(f"\n{label}:")
        for item in group:
            m_int = max(1, min(10, int(round(item["mmi"]))))
            lines.append(
                f"- {item['name']} (pop. {item['population']:,}, {item['distance_km']} km away): "
                f"MMI {item['mmi_roman']} ({item['mmi']}) -> {MMI_PERCEPTION[m_int]}"
            )

    lines.append("\nROADS & CHOKEPOINTS:")
    for r in osm["major_roads"] + osm["bridges_tunnels"]:
        lines.append(f"- {r['name']} ({r['type']}, {r['distance_km']} km away)")

    lines.append("\nPARKS, ASSEMBLY SPOTS & CRITICAL HUBS:")
    for p in osm["open_assembly_spots"] + osm["high_density_hubs"]:
        lines.append(f"- {p['name']} ({p['type']}, {p['distance_km']} km away)")

    data_block = "\n".join(lines)
    allowed = allowed_numbers(base_result, data_block + "\n" + guidance)

    print(f"[4/4] Running Chain-of-Thought simulation via {REASONING_MODEL}...")
    problems = []
    used_fallback = False
    thought_text, sim_text = "", ""

    for _ in range(retries + 1):
        extra = ("\nFix these issues from your previous attempt: " + " ".join(problems) + "\n") if problems else ""
        prompt = COT_PROMPT.format(
            extra=extra,
            data_block=data_block,
            guidance=guidance if guidance else "(No matching RAG chunks found.)",
        )
        r = ollama.chat(
            model=REASONING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.25, "num_predict": 1350},
        )
        raw = r["message"]["content"].strip()

        t_match = re.search(r"<thought>(.*?)</thought>", raw, re.DOTALL)
        s_match = re.search(r"<simulation>(.*?)</simulation>", raw, re.DOTALL)
        thought_text = t_match.group(1).strip() if t_match else ""
        sim_text = s_match.group(1).strip() if s_match else raw

        probs = []
        bad_nums = unknown_numbers(sim_text, allowed)
        if bad_nums:
            probs.append(f"Remove numbers not in REAL-TIME DATA or RAG GUIDANCE: {', '.join(f'{n:g}' for n in bad_nums)}.")
        bad_words = forbidden_claims(sim_text)
        if bad_words:
            probs.append(
                f"Remove forbidden prediction phrasing ({', '.join(bad_words)}); "
                "describe as a hypothetical simulation or historical statistical estimate."
            )
        if not probs:
            break
        problems = probs
    else:
        used_fallback = True
        sim_text = f"### Real-Time Pipeline Data Summary\n\n{data_block}"

    return {
        "thought": thought_text,
        "simulation": sim_text + "\n\n" + SAFE_DISCLAIMER,
        "aftershocks": aftershocks,
        "live_seismicity": live_seis,
        "weather": weather,
        "guidance_sources": sources,
        "used_fallback": used_fallback,
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python realtime_pipeline.py LAT LON [--hypothetical-mag 7.5]")
    lat, lon = float(sys.argv[1]), float(sys.argv[2])
    h_mag = float(sys.argv[sys.argv.index("--hypothetical-mag") + 1]) if "--hypothetical-mag" in sys.argv else None

    out = run_pipeline(lat, lon, hypothetical_mag=h_mag)
    if out["thought"]:
        print("\n=== CHAIN OF THOUGHT ===")
        print(out["thought"])
    print("\n=== FINAL SIMULATION ===")
    print(out["simulation"])
    if out["guidance_sources"]:
        print("\nRAG Sources:", ", ".join(out["guidance_sources"]))
    print("Used fallback:", out["used_fallback"])