"""
Finish the data step:
  1. build data/catalog.csv from the downloaded EMSC (and optional USGS) files, if it is missing
  2. create / update data/sources.csv (link, date accessed, terms) for every dataset
  3. check the "done when" list and print PASS / FAIL

Run from your project folder:   python finish_data_step.py
(add --skip-sources to ignore sources.csv completely)
(or in a notebook cell:         %run finish_data_step.py)
Safe to run again: it never deletes your edits in sources.csv.
"""
import glob, os, sys
from datetime import datetime
import numpy as np
import pandas as pd

DATA = "data"
MIN_CATALOG_ROWS = 2000      # "thousands of rows"
MIN_COUNTRIES = 150          # value-per-person and damage-ratio tables
MATCH_SECONDS, MATCH_KM = 60, 50

# ---------------------------------------------------------------- helpers
def col(df, *names, required=True):
    low = {c.lower().strip(): c for c in df.columns}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    for c in df.columns:                                   # prefix match, e.g. "Depth/km"
        if any(c.lower().startswith(n.lower()) for n in names):
            return c
    if required:
        sys.exit(f"Could not find a column like {names} in {df.columns.tolist()}.\n"
                 "Send me this list and I will adjust the mapping.")
    return None

def haversine_km(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))

def file_date(path):
    return datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d") if os.path.exists(path) else ""

# ---------------------------------------------------------------- 1. catalog
def load_emsc(path):
    df = pd.read_csv(path)
    df.columns = [str(c).lstrip("# ").strip() for c in df.columns]
    out = pd.DataFrame({
        "time_utc": pd.to_datetime(df[col(df, "Time")], utc=True, errors="coerce"),
        "lat": pd.to_numeric(df[col(df, "Latitude")], errors="coerce"),
        "lon": pd.to_numeric(df[col(df, "Longitude")], errors="coerce"),
        "depth_km": pd.to_numeric(df[col(df, "Depth/km", "Depth")], errors="coerce"),
        "mag": pd.to_numeric(df[col(df, "Magnitude")], errors="coerce"),
        "mag_type": df[col(df, "MagType", required=False)] if col(df, "MagType", required=False) else "",
        "region": df[col(df, "EventLocationName", required=False)] if col(df, "EventLocationName", required=False) else "",
    })
    out["source"] = "EMSC"
    return out

def load_usgs(path):
    df = pd.read_csv(path)
    tcol = col(df, "type", required=False)
    if tcol:
        df = df[df[tcol] == "earthquake"]
    out = pd.DataFrame({
        "time_utc": pd.to_datetime(df[col(df, "time")], utc=True, errors="coerce"),
        "lat": pd.to_numeric(df[col(df, "latitude")], errors="coerce"),
        "lon": pd.to_numeric(df[col(df, "longitude")], errors="coerce"),
        "depth_km": pd.to_numeric(df[col(df, "depth")], errors="coerce"),
        "mag": pd.to_numeric(df[col(df, "mag")], errors="coerce"),
        "mag_type": df[col(df, "magType", required=False)] if col(df, "magType", required=False) else "",
        "region": df[col(df, "place", required=False)] if col(df, "place", required=False) else "",
    })
    out["source"] = "USGS"
    return out

def clean(df):
    n0 = len(df)
    df = df.dropna(subset=["time_utc", "lat", "lon", "mag"])
    df = df[df["lat"].between(-90, 90) & df["lon"].between(-180, 180) & df["mag"].between(-1, 10)]
    df = df.copy()
    df["depth_missing"] = df["depth_km"].isna()
    df["depth_km"] = df["depth_km"].fillna(df["depth_km"].median())
    df = df[df["depth_km"].between(-5, 800)]
    df = df.drop_duplicates(subset=["time_utc", "lat", "lon", "mag"])
    print(f"  cleaned: kept {len(df)} of {n0}")
    return df.sort_values("time_utc").reset_index(drop=True)

def drop_matches(primary, secondary):
    """Remove events of `secondary` that also appear in `primary` (within 60 s and 50 km)."""
    pt = primary["time_utc"].astype("int64").values // 10**9
    order = np.argsort(pt)
    pt = pt[order]
    plat, plon = primary["lat"].values[order], primary["lon"].values[order]
    keep = []
    for t, la, lo in zip(secondary["time_utc"].astype("int64").values // 10**9,
                         secondary["lat"].values, secondary["lon"].values):
        i0, i1 = np.searchsorted(pt, t - MATCH_SECONDS), np.searchsorted(pt, t + MATCH_SECONDS, side="right")
        dup = i1 > i0 and (haversine_km(la, lo, plat[i0:i1], plon[i0:i1]) <= MATCH_KM).any()
        keep.append(not dup)
    return secondary[np.array(keep, dtype=bool)]

def build_catalog():
    path = f"{DATA}/catalog.csv"
    if os.path.exists(path):
        print("catalog.csv already exists, not rebuilding")
        return
    parts = []
    if os.path.exists(f"{DATA}/emsc_raw.csv"):
        print("reading emsc_raw.csv"); parts.append(clean(load_emsc(f"{DATA}/emsc_raw.csv")))
    if os.path.exists(f"{DATA}/usgs_raw.csv"):
        print("reading usgs_raw.csv"); parts.append(clean(load_usgs(f"{DATA}/usgs_raw.csv")))
    if not parts:
        print("No emsc_raw.csv or usgs_raw.csv found, so catalog.csv cannot be built yet.")
        return
    cat = parts[0]
    if len(parts) == 2:
        extra = drop_matches(parts[0], parts[1])
        print(f"  USGS events not already in EMSC: {len(extra)} of {len(parts[1])}")
        cat = pd.concat([parts[0], extra], ignore_index=True)
    cat = cat.sort_values("time_utc").reset_index(drop=True)
    cat.to_csv(path, index=False)
    print("saved", path, len(cat), "rows")

# ---------------------------------------------------------------- 2. sources.csv
COLUMNS = ["dataset", "file", "publisher", "url", "date_accessed", "license_terms", "used_for", "notes"]

def source_rows():
    return [
        ["Earthquake catalog (EMSC)", f"{DATA}/emsc_raw.csv", "EMSC-CSEM SeismicPortal",
         "https://www.seismicportal.eu/fdsnws/event/1/query", file_date(f"{DATA}/emsc_raw.csv"),
         "CC BY 4.0, credit EMSC. A third-party description says copying the whole catalogue needs EMSC's written permission: confirm on the seismicportal.eu terms page",
         "Worldwide earthquake history", "Downloaded month by month, no region filter; magnitude threshold used in the download script"],
        ["Earthquake catalog (USGS)", f"{DATA}/usgs_raw.csv", "U.S. Geological Survey",
         "https://earthquake.usgs.gov/fdsnws/event/1/query", file_date(f"{DATA}/usgs_raw.csv"),
         "TO CHECK: read the USGS data policy on usgs.gov and write the exact terms here",
         "Optional second catalog", "Delete this row if you did not use USGS"],
        ["Merged earthquake catalog", f"{DATA}/catalog.csv", "Derived (built by finish_data_step.py)",
         "see rows above", file_date(f"{DATA}/catalog.csv"),
         "Inherits the terms of the catalogs it is built from", "Hazard model and examples",
         "Duplicates removed (60 s and 50 km rule); time in UTC; magnitude types differ between sources"],
        ["City population table", f"{DATA}/population_cities.csv", "GeoNames",
         "https://download.geonames.org/export/dump/cities1000.zip", file_date(f"{DATA}/population_cities.csv"),
         "CC BY 4.0, credit GeoNames", "People near the epicenter",
         "Only places with a listed population, so counts are a minimum"],
        ["GDP per capita", f"{DATA}/gdp_per_capita.csv", "World Bank",
         "https://data.worldbank.org/indicator/NY.GDP.PCAP.CD", file_date(f"{DATA}/gdp_per_capita.csv"),
         "CC BY 4.0, credit World Bank", "Value per person",
         "Indicator NY.GDP.PCAP.CD (current US dollars), latest year per country; gaps filled with the income-group median"],
        ["Vulnerability / loss-ratio parameters (theta, beta, zeta) and exposure factor alpha", f"{DATA}/vulnerability.csv",
         "U.S. Geological Survey (Jaiswal and Wald, 2011)",
         "https://pubs.usgs.gov/of/2011/1116 (Appendix I: http://pubs.usgs.gov/of/2011/1116/downloads/Appendix-1.csv)",
         file_date(f"{DATA}/vulnerability.csv"),
         "USGS report states it is in the public domain; permission is needed for any copyrighted material inside it. Cite: Open-File Report 2011-1116, DOI 10.3133/ofr20111116",
         "Damage ratio and value per person", "Cleaned from Appendix I (212 countries); fallback medians used for missing countries"],
        ["Value per person", f"{DATA}/value_per_person.csv", "Derived",
         "see GDP per capita and vulnerability rows", file_date(f"{DATA}/value_per_person.csv"),
         "Inherits the terms of its inputs", "Cost estimate",
         "value_pc = GDP per capita x alpha (method of Jaiswal and Wald 2011)"],
    ]

def doc_rows():
    rows = []
    for p in sorted(glob.glob("docs/*.txt")):
        rows.append([f"Safety document: {os.path.basename(p)}", p, "TODO: publisher", "TODO: link",
                     file_date(p), "TODO: terms of use", "Chatbot answers (RAG)", "Fill in the TODO fields"])
    return rows

def update_sources():
    path = f"{DATA}/sources.csv"
    old = pd.read_csv(path, keep_default_na=False) if os.path.exists(path) else pd.DataFrame(columns=COLUMNS)
    have = set(old["file"]) if "file" in old.columns else set()
    rows = [r for r in source_rows() if os.path.exists(r[1])] + doc_rows()     # only datasets you actually have
    for r in source_rows():
        if not os.path.exists(r[1]):
            print("  (no row added, file not found:", r[1] + ")")
    new = [r for r in rows if r[1] not in have]
    out = pd.concat([old, pd.DataFrame(new, columns=COLUMNS)], ignore_index=True) if new else old
    out.to_csv(path, index=False)
    print(f"sources.csv: {len(out)} rows ({len(new)} added)")
    return out

# ---------------------------------------------------------------- 3. checks
def check(skip_sources=False):
    results = []
    def add(name, ok, detail):
        results.append(ok); print(("PASS  " if ok else "FAIL  ") + name + " - " + detail)

    def rd(p, **kw):
        return pd.read_csv(p, keep_default_na=False, na_values=[""], **kw) if os.path.exists(p) else None

    cat = rd(f"{DATA}/catalog.csv")
    if cat is None:
        add("catalog.csv", False, "file missing (run the EMSC download first)")
    else:
        t = pd.to_datetime(cat["time_utc"], utc=True, errors="coerce")
        add("catalog.csv", len(cat) >= MIN_CATALOG_ROWS,
            f"{len(cat):,} rows, {t.min():%Y-%m-%d} to {t.max():%Y-%m-%d}, sources {cat['source'].value_counts().to_dict()}")
        add("catalog covers the world", cat["lat"].min() < -40 and cat["lat"].max() > 40,
            f"latitude {cat['lat'].min():.0f} to {cat['lat'].max():.0f}, longitude {cat['lon'].min():.0f} to {cat['lon'].max():.0f}")

    city = rd(f"{DATA}/population_cities.csv")
    if city is None:
        add("city table", False, "file missing")
    else:
        kr = int(city.loc[city["country"] == "KR", "population"].sum())
        add("city table", len(city) > 10000 and kr > 0, f"{len(city):,} places, South Korea total {kr:,}")

    vpp = rd(f"{DATA}/value_per_person.csv")
    if vpp is None or "value_pc" not in vpp.columns:
        add("value per person", False, "file missing or no value_pc column (re-run Part C of the notebook)")
    else:
        add("value per person", len(vpp) >= MIN_COUNTRIES and vpp["value_pc"].notna().all(),
            f"{len(vpp)} countries, median {vpp['value_pc'].median():,.0f} USD per person")

    vul = rd(f"{DATA}/vulnerability.csv")
    need = {"iso2", "theta", "beta", "zeta", "alpha"}
    if vul is None or not need.issubset(vul.columns):
        add("damage-ratio table", False, "file missing or not the cleaned version")
    else:
        from scipy.stats import norm
        j = vul[vul["iso2"] == "JP"].iloc[0]
        r9 = float(norm.cdf(np.log(9 / j["theta"]) / j["beta"]))
        add("damage-ratio table", len(vul) >= MIN_COUNTRIES and abs(r9 - 0.09) < 0.01,
            f"{len(vul)} countries, Japan loss ratio at MMI IX = {r9:.3f} (report: almost 10 percent)")

    src = None if skip_sources else rd(f"{DATA}/sources.csv")
    if skip_sources:
        print("SKIP  sources.csv checks (run without --skip-sources to include them)")
    elif src is None:
        add("sources.csv", False, "file missing")
    else:
        todo = src[(src[["url", "date_accessed", "license_terms"]] == "").any(axis=1) |
                   src.apply(lambda r: ("TODO" in " ".join(map(str, r.values))) or ("TO CHECK" in " ".join(map(str, r.values))), axis=1)]
        add("sources.csv complete", len(todo) == 0,
            "every row has a link, date and terms" if len(todo) == 0 else
            f"{len(todo)} rows still need work: " + ", ".join(todo["dataset"].str.slice(0, 40)))
        for need_file in ["catalog.csv", "population_cities.csv", "gdp_per_capita.csv", "value_per_person.csv", "vulnerability.csv"]:
            if f"{DATA}/{need_file}" not in set(src["file"]):
                add(f"sources.csv has a row for {need_file}", False, "missing row")

    print("\nOVERALL:", "ALL DONE" if all(results) else "NOT DONE YET - fix the FAIL lines above")

if __name__ == "__main__":
    skip = "--skip-sources" in sys.argv
    build_catalog()
    if not skip:
        update_sources()
    print()
    check(skip_sources=skip)
