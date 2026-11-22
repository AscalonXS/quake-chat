"""
quake_simulate.py - Storytelling-style area simulation connecting impacts.py,
area_gatherer.py, your ChromaDB RAG guidance, and Ollama (quake-bot).

Run:  python quake_simulate.py 37.57 126.98 7.5 10 --hour 18
"""
from datetime import datetime
import sys
import ollama

from area_gather import build_area_profile
from impacts import get_impact, ROMAN
from quake_describe import (
    DISCLAIMER,
    MODEL,
    allowed_numbers,
    get_guidance,
    unknown_numbers,
)

MMI_PERCEPTION = {
    1: "Barely noticeable—only a few people sitting still on upper floors feel a faint sway.",
    2: "A gentle, dizzying sway felt by people resting on upper floors.",
    3: "Indoors, it feels like a heavy delivery truck rumbling past the building; hanging lights sway.",
    4: "Windows, dishes, and doors rattle loudly; parked cars rock on their suspension.",
    5: "Everyone feels it—sleepers jolt awake, glasses clatter off shelves, and unstable items topple.",
    6: "Frightening jolt felt by everyone; people stumble as they walk, heavy furniture slides, and plaster cracks.",
    7: "Hard to stay on your feet; drivers feel their cars swerving, hanging fixtures shake violently, and older walls crack.",
    8: "Steering a car becomes a struggle; violent jolts throw heavy furniture over and crack or topple tall walls and monuments.",
    9: "Widespread panic; violent ground waves make standing almost impossible, underground pipes snap, and cracks split the ground.",
    10: "Extreme, rolling ground waves throw people off balance, bend rails, and trigger severe ground and slope failures.",
}

def describe_time_context(hour):
    h = int(hour) % 24
    if 7 <= h <= 9:
        period = f"{h:02d}:00 (Morning Rush Hour)"
        traffic = ("Gridlock hits almost instantly—highways, arterial roads, and bridges are already packed with commuters. "
                   "Subway and train stations are crowded, and sudden braking plus debris quickly choke off emergency lanes.")
        population_loc = "Hundreds of thousands of commuters are packed onto trains, buses, school routes, and inbound roads."
    elif 17 <= h <= 20:
        period = f"{h:02d}:00 (Evening Rush Hour)"
        traffic = ("Bumper-to-bumper chaos—drivers trying to rush home or reach family jam up highway interchanges, "
                   "bridges, and tunnel entrances within minutes.")
        population_loc = "Crowds are concentrated in downtown offices, restaurants, shopping streets, transit hubs, and outbound roads."
    elif 10 <= h <= 16:
        period = f"{h:02d}:00 (Midday Work & School Hours)"
        traffic = ("Steady daytime traffic with buses and delivery trucks filling main avenues; "
                   "waves of people evacuating buildings spill onto sidewalks and block intersections.")
        population_loc = "Most people are inside office towers, schools, hospitals, and commercial districts rather than at home."
    else:
        period = f"{h:02d}:00 (Late Night / Sleeping Hours)"
        traffic = ("Roads start out nearly empty, but sudden power outages, dark streets, and scattered debris create "
                   "serious crash hazards as startled residents drive out into the night.")
        population_loc = "Most people are asleep indoors across city apartments and quiet rural villages, slowing reaction times."
    return {"period": period, "traffic": traffic, "population_loc": population_loc}

SIM_PROMPT = """You are an engaging storyteller and disaster-dynamics narrator explaining what unfolds during a simulated earthquake.
Tell the story of what happens across this area in a vivid, human, easy-to-read tone—not overly stiff or robotic—while keeping the response cleanly organized with the headings and bullet points below (around 320 to 420 words).

Use this exact structure:

### The First Seconds: What People Feel
- Paint a clear picture of the shock hitting at {time_period}. Contrast what people experience in the listed cities versus the smaller towns/villages using their exact distances, MMI levels, and sensory cues from SIMULATION DATA.

### Where the Crowds Run: Safe Spots & Danger Zones
- Tell the story of where people pour out once the shaking stops—heading toward the listed open parks, plazas, or assembly points—and point out the high-pressure danger spots (crowded stations, hospitals, narrow glass-lined streets) where panic or falling debris is highest.

### On the Roads: Traffic & Chokepoints
- Describe how the streets and traffic react at this specific hour, naming the exact highways, roads, bridges, or tunnels from SIMULATION DATA that turn into bottlenecks.

### How the Land Reacts ({env_class})
- Explain what the surrounding environment does to the area:
  * If mountainous or hilly: describe rockfalls, landslides cutting off valley roads or mountain passes, and how small villages risk getting isolated.
  * If coastal or low-lying: describe people moving inland toward higher ground and soft-soil liquefaction risks.
  * If dense urban: describe falling glass/facades, utility blackouts, and emergency crews fighting through blocked avenues.

### Staying Safe: What To Do Right Now
- Give 3 short, practical bullet points grounded in the RAG SAFETY GUIDANCE below.

Important Grounding Rules:
- Tell the story using ONLY the place names, road/bridge/tunnel names, distances, elevations, MMI values, and facts in SIMULATION DATA and RAG SAFETY GUIDANCE. Copy every number exactly as written.
- Do NOT invent extra numbers, casualty counts, or percentages.
- NEVER claim any specific building, bridge, or shelter is structurally "safe" or "unsafe" (always note that qualified engineers or local authorities must inspect structures).
- Frame this as a hypothetical simulation ("would feel", "would rush"), never as a prediction or official warning.
{extra}
SIMULATION DATA:
{sim_block}

RAG SAFETY GUIDANCE (from embedded documents):
{guidance}
"""

def _format_sim_block(base_result, profile, time_ctx):
    s = profile["settlements"]
    osm = profile["osm"]
    env = base_result["environment"]

    lines = [
        f"- Scenario: {base_result['text']['scenario']}",
        f"- Epicenter shaking: {base_result['text']['strongest_shaking']}",
        f"- People in strong shaking (MMI VI+): {base_result['text']['people_strong_shaking']}",
        f"- Rough cost estimate: {base_result['text']['cost_range']}",
        f"- Environment Type: {profile['environment_classification']}",
        f"- Time of Day: {time_ctx['period']}",
        f"- Where People Are Right Now: {time_ctx['population_loc']}",
        f"- Road & Traffic Behavior: {time_ctx['traffic']}",
        f"- Secondary Hazards -> Tsunami: {env['tsunami']['level']} ({env['tsunami']['why']}); "
        f"Landslide: {env['landslide']['level']} ({env['landslide']['why']}); "
        f"Liquefaction: {env['liquefaction']['level']} ({env['liquefaction']['why']})",
    ]

    lines.append("\nCITIES IN THE AREA:")
    if s["cities"]:
        for c in s["cities"]:
            m_int = max(1, min(10, int(round(c["mmi"]))))
            elev_txt = f", elevation {c['elevation_m']} m" if c["elevation_m"] is not None else ""
            lines.append(
                f"- {c['name']} (pop. {c['population']:,}, {c['distance_km']} km away{elev_txt}): "
                f"MMI {c['mmi_roman']} ({c['mmi']}) -> {MMI_PERCEPTION[m_int]}"
            )
    else:
        lines.append("- No major city (>50,000 pop) within 30 km.")

    lines.append("\nTOWNS & VILLAGES IN THE AREA:")
    if s["villages"]:
        for v in s["villages"]:
            m_int = max(1, min(10, int(round(v["mmi"]))))
            elev_txt = f", elevation {v['elevation_m']} m" if v["elevation_m"] is not None else ""
            lines.append(
                f"- {v['name']} (pop. {v['population']:,}, {v['distance_km']} km away{elev_txt}): "
                f"MMI {v['mmi_roman']} ({v['mmi']}) -> {MMI_PERCEPTION[m_int]}"
            )
    else:
        lines.append("- No listed smaller towns/villages within 30 km.")

    lines.append("\nMAJOR ROADS & CORRIDORS:")
    lines.extend(
        [f"- {r['name']} ({r['type']}, {r['distance_km']} km away)" for r in osm["major_roads"]]
        or ["- Local arterial roads around the epicenter."]
    )

    lines.append("\nBRIDGES & TUNNELS (Chokepoints):")
    lines.extend(
        [f"- {b['name']} ({b['type']}, {b['distance_km']} km away)" for b in osm["bridges_tunnels"]]
        or ["- Local river crossings and road overpasses."]
    )

    lines.append("\nOPEN PARKS & ASSEMBLY SPOTS:")
    lines.extend(
        [f"- {p['name']} ({p['type']}, {p['distance_km']} km away)" for p in osm["open_assembly_spots"]]
        or ["- Open schoolyards, wide plazas, and municipal assembly areas."]
    )

    lines.append("\nCROWDED HUBS & HOSPITALS:")
    lines.extend(
        [f"- {h['name']} ({h['type']}, {h['distance_km']} km away)" for h in osm["high_density_hubs"]]
        or ["- Local clinics and transit stops."]
    )

    lines.append("\nTERRAIN & LANDMARKS:")
    lines.extend(
        [f"- {t['label']} ({t['distance_km']} km away)" for t in osm["terrain_markers"]]
        or ["- Surrounding hills, valleys, and local waterways."]
    )

    return "\n".join(lines)

def simulate_area(lat, lon, magnitude, depth_km, hour=None, use_rag=True, retries=1):
    mag, dep = float(magnitude), float(depth_km)
    if hour is None:
        hour = datetime.now().hour

    base_result = get_impact(lat, lon, mag, dep)
    profile = build_area_profile(lat, lon, mag, dep)
    time_ctx = describe_time_context(hour)
    guidance, sources = get_guidance(base_result) if use_rag else ("", [])

    sim_block = _format_sim_block(base_result, profile, time_ctx)

    # Allow numbers from impact results, gathered area places, and embedded RAG chunks
    allowed = allowed_numbers(base_result, sim_block + "\n" + guidance)
    allowed.add(float(int(hour) % 24))

    problems = []
    used_fallback = False
    text = ""

    for _ in range(retries + 1):
        extra = ("\nFix these issues from your previous draft: " + " ".join(problems) + "\n") if problems else ""
        prompt = SIM_PROMPT.format(
            extra=extra,
            time_period=time_ctx["period"],
            env_class=profile["environment_classification"],
            sim_block=sim_block,
            guidance=guidance if guidance else "(No matching RAG chunks found; use standard earthquake safety steps.)",
        )
        r = ollama.chat(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.35, "num_predict": 950},
        )
        text = r["message"]["content"].strip()
        bad = unknown_numbers(text, allowed)
        if not bad:
            break
        problems = [f"Remove numbers not found in SIMULATION DATA or RAG SAFETY GUIDANCE: {', '.join(f'{n:g}' for n in bad)}."]
    else:
        used_fallback = True
        text = (
            "### Area Simulation Summary\n\n"
            f"{sim_block}\n\n"
            "### Staying Safe: What To Do Right Now\n"
            "- Drop, cover, and hold on until the shaking stops.\n"
            "- Move calmly to open spaces away from glass, slopes, and power lines.\n"
            "- Follow official instructions from local authorities and wait for qualified engineers to inspect structures."
        )

    return {
        "simulation": text + "\n\n" + DISCLAIMER,
        "profile": profile,
        "time_context": time_ctx,
        "guidance_sources": sources,
        "used_fallback": used_fallback,
        "result": base_result,
    }

if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit("usage: python quake_simulate.py LAT LON MAGNITUDE DEPTH_KM [--hour 18]")
    lat, lon, mag, dep = map(float, sys.argv[1:5])
    hour = None
    if "--hour" in sys.argv:
        idx = sys.argv.index("--hour")
        hour = int(sys.argv[idx + 1])
    out = simulate_area(lat, lon, mag, dep, hour=hour)
    print(out["simulation"])
    if out["guidance_sources"]:
        print("\nRAG Sources:", ", ".join(out["guidance_sources"]))
    print("Used fallback:", out["used_fallback"])