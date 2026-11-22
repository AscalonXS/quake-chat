# import io, os, time
# import requests
# import pandas as pd

# URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
# LIMIT = 20000
# MIN_MAG = 4.5            # use 5.0 if it is too slow or too large
# FMT = "%Y-%m-%dT%H:%M:%S"
# os.makedirs("data/emsc_raw", exist_ok=True)

# def fetch(start, end):
#     params = dict(start=start, end=end, minmag=MIN_MAG,
#                   format="text", orderby="time-asc", limit=LIMIT)     # no lat/lon box
#     r = requests.get(URL, params=params, timeout=180)
#     if r.status_code == 204 or not r.text.strip():
#         return pd.DataFrame()
#     if r.status_code != 200:
#         print("ERROR", r.status_code, r.text[:300])
#         r.raise_for_status()
#     df = pd.read_csv(io.StringIO(r.text), sep="|")
#     df.columns = [c.lstrip("# ").strip() for c in df.columns]
#     return df

# def fetch_split(start, end):
#     df = fetch(start, end)
#     if len(df) >= LIMIT:                      # hit the limit: split the window in two
#         t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
#         mid = t0 + (t1 - t0) / 2
#         a = fetch_split(t0.strftime(FMT), mid.strftime(FMT))
#         b = fetch_split(mid.strftime(FMT), t1.strftime(FMT))
#         return pd.concat([a, b], ignore_index=True)
#     return df

# for year in range(2000, 2027):
#     for month in range(1, 13):
#         first = pd.Timestamp(year=year, month=month, day=1)
#         if first > pd.Timestamp.now():
#             break
#         nxt = first + pd.offsets.MonthBegin(1)
#         path = f"data/emsc_raw/{year}-{month:02d}.csv"
#         if os.path.exists(path):              # resume if the script stopped
#             continue
#         df = fetch_split(first.strftime(FMT), nxt.strftime(FMT))
#         df.to_csv(path, index=False)
#         print(year, month, len(df))
#         time.sleep(1)

import glob
import os
import pandas as pd 

files = sorted(glob.glob("data/emsc_raw/*.csv"))
frames = [pd.read_csv(f) for f in files if os.path.getsize(f) > 5]
emsc = pd.concat(frames, ignore_index=True).drop_duplicates(subset="EventID")
emsc.to_csv("data/emsc_raw.csv", index=False)
print(len(emsc), "events")