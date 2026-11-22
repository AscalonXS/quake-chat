import io, time
import requests
import pandas as pd

BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"
BBOX = dict(minlatitude=30, maxlatitude=45, minlongitude=120, maxlongitude=135)  # CHANGE
MIN_MAG = 4.0
YEARS = range(2000, 2026)

print("boo")
frames = []
for year in YEARS:
    params = dict(format="csv", starttime=f"{year}-01-01", endtime=f"{year + 1}-01-01",
                  minmagnitude=MIN_MAG, orderby="time-asc", **BBOX)
    r = requests.get(BASE, params=params, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    print(year, len(df))
    if len(df) >= 19000:
        print("  WARNING: close to the request limit, split this year into months")
    frames.append(df)
    time.sleep(1)          # be polite to the server

raw = pd.concat(frames, ignore_index=True)
raw.to_csv("data/catalog_raw.csv", index=False)
print("total rows:", len(raw))