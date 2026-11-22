import numpy as np
import pandas as pd

pop = pd.read_csv("data/population_cities.csv", keep_default_na=False, na_values=[""])
LAT = np.radians(pop["lat"].values)
LON = np.radians(pop["lon"].values)
P = pop["population"].values
NAMES = pop["name"].values

def distance_km(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    a = np.sin((LAT - la) / 2) ** 2 + np.cos(la) * np.cos(LAT) * np.sin((LON - lo) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))              # haversine formula, km

RINGS = [(0, 20), (20, 50), (50, 100), (100, 200)]       # km from the epicenter

def population_by_ring(lat, lon, rings=RINGS):
    d = distance_km(lat, lon)
    out = []
    for lo_km, hi_km in rings:
        m = (d >= lo_km) & (d < hi_km)
        largest = NAMES[m][np.argmax(P[m])] if m.any() else None
        out.append({"from_km": lo_km, "to_km": hi_km,
                    "population": int(P[m].sum()), "places": int(m.sum()),
                    "largest_place": largest})
    return out

if __name__ == "__main__":
    for row in population_by_ring(35.76, 129.19):        # near Gyeongju, as a test
        print(row)