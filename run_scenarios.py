"""
Run 10 scenarios through the whole pipeline, save every description, and flag numbers that are not in the result.
Output: eval/scenario_descriptions.csv   (read every description yourself, the check only catches numbers)
Needs Ollama running, the quake-bot model, and the document database (python ingest.py).
"""
import csv, os
from quake_describe import explain_scenario

SCENARIOS = [  # name, lat, lon, magnitude, depth_km
    ("Gyeongju-type, M6.5", 35.76, 129.19, 6.5, 10),
    ("Pohang-type, M5.4", 36.11, 129.37, 5.4, 10),
    ("Near Seoul, M6.0", 37.57, 126.98, 6.0, 12),
    ("Busan area, M6.8", 35.10, 129.04, 6.8, 15),
    ("Tokyo area, M7.0", 35.68, 139.69, 7.0, 30),
    ("Offshore Japan, M7.6", 38.3, 142.4, 7.6, 25),
    ("Istanbul area, M7.2", 40.98, 28.98, 7.2, 12),
    ("Lima area, M7.5", -12.05, -77.04, 7.5, 40),
    ("Remote, M6.5", 0.0, -150.0, 6.5, 10),
    ("Small, M4.5", 35.76, 129.19, 4.5, 8),
]
os.makedirs("eval", exist_ok=True)
rows = []
for name, lat, lon, m, d in SCENARIOS:
    print("running", name)
    out = explain_scenario(lat, lon, m, d)
    last = out["checks"][-1]
    rows.append({"scenario": name, "used_fallback": out["used_fallback"], "attempts": len(out["checks"]),
                 "unknown_numbers": last["unknown_numbers"], "missing_cost_numbers": last["missing_cost_numbers"],
                 "alert": out["result"]["alert"], "description": out["description"].replace("\n", " ")})
with open("eval/scenario_descriptions.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader(); w.writerows(rows)

print("\nscenario                     fallback  attempts  unknown numbers")
for r in rows:
    print(f"{r['scenario']:<28} {str(r['used_fallback']):<9} {r['attempts']:<9} {r['unknown_numbers']}")
print("\nSaved eval/scenario_descriptions.csv")