"""
quake_impact.py - scenario impact and cost calculator

    from quake_impact import get_impact
    result = get_impact(lat=35.76, lon=129.19, magnitude=6.5, depth_km=10)

Python calculates every number. The "text" part of the result is already rounded and worded, so Llama can
describe it without calculating anything.

Needs these files in data/ (created by the notebook):
    population_cities.csv   vulnerability.csv   value_per_person.csv
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

DATA = "data"
MAX_KM = 300          # shaking model range: distances up to 300 km

# ------------------------------------------------------------------ load tables once
pop = pd.read_csv(f"{DATA}/population_cities.csv", keep_default_na=False, na_values=[""])
vul = pd.read_csv(f"{DATA}/vulnerability.csv", keep_default_na=False, na_values=[""])
vpp = pd.read_csv(f"{DATA}/value_per_person.csv", keep_default_na=False, na_values=[""])
for need, df in [({"iso2", "theta", "beta", "zeta"}, vul), ({"iso2", "value_pc"}, vpp)]:
    if not need.issubset(df.columns):
        raise ValueError(f"missing columns {sorted(need - set(df.columns))}: run the notebook parts C and D first")

DEFAULT = {"theta": float(vul["theta"].median()), "beta": float(vul["beta"].median()),
           "zeta": float(vul["zeta"].median())}

def _place_array(df, col, default):
    s = pop["country"].map(dict(zip(df["iso2"], df[col])))
    return s.fillna(default).values.astype(float)

LAT = np.radians(pop["lat"].values)
LON = np.radians(pop["lon"].values)
P = pop["population"].values.astype(float)
COUNTRY = pop["country"].values
NAMES = pop["name"].values
THETA = _place_array(vul, "theta", DEFAULT["theta"])
BETA = _place_array(vul, "beta", DEFAULT["beta"])
ZETA = _place_array(vul, "zeta", DEFAULT["zeta"])
VALUE_PC = _place_array(vpp, "value_pc", float(vpp["value_pc"].median()))
_dem = pd.to_numeric(pop["dem"], errors="coerce") if "dem" in pop.columns else pd.Series(np.nan, index=pop.index)
DEM = np.where(_dem > -500, _dem, np.nan)

# California has its own parameters in Table 4 of the USGS report (theta 9.60, beta 0.10, zeta 2.27);
# the Appendix I row "United States" is the report's "without California" row. Rough California outline:
_east_limit = np.where(pop["lat"].values >= 39.0, -120.0,
                       np.where(pop["lat"].values >= 35.0, -120.0 + (39.0 - pop["lat"].values) * (5.4 / 4.0), -114.6))
IN_CALIFORNIA = ((COUNTRY == "US") & (pop["lat"].values >= 32.5) & (pop["lat"].values <= 42.0)
                 & (pop["lon"].values >= -124.6) & (pop["lon"].values <= _east_limit))
THETA = np.where(IN_CALIFORNIA, 9.60, THETA)
BETA = np.where(IN_CALIFORNIA, 0.10, BETA)
ZETA = np.where(IN_CALIFORNIA, 2.27, ZETA)               # GeoNames uses large negative numbers for "no data"

# ------------------------------------------------------------------ shaking (intensity) model
# Allen, Wald and Worden (2012), Modified Mercalli Intensity, active crustal regions, hypocentral distance.
# Coefficients as published in the OpenQuake implementation (AllenEtAl2012Rhypo).
# Stated range: Mw 5.0-7.9, distances under 300 km, shallow crustal earthquakes.
IPE = dict(c0=2.085, c1=1.428, c2=-1.402, c4=0.078, m1=-0.209, m2=2.042, s1=0.82, s2=0.37, s3=22.9)

def mmi_from_hypo_distance(mag, r_hyp_km):
    r = np.maximum(np.asarray(r_hyp_km, dtype=float), 1.0)
    r_m = IPE["m1"] + IPE["m2"] * np.exp(mag - 5.0)
    f = IPE["c2"] * np.log(np.sqrt(r ** 2 + r_m ** 2))
    f = f + np.where(r > 50.0, IPE["c4"] * np.log(r / 50.0), 0.0)
    return np.clip(IPE["c0"] + IPE["c1"] * mag + f, 1.0, 10.0)

def mmi_sigma(r_hyp_km):
    return IPE["s1"] + IPE["s2"] / (1.0 + (np.asarray(r_hyp_km, dtype=float) / IPE["s3"]) ** 2)

BANDS = [(5.0, 6.0, "moderate (MMI V)"), (6.0, 7.0, "strong (MMI VI)"), (7.0, 8.0, "very strong (MMI VII)"),
         (8.0, 9.0, "severe (MMI VIII)"), (9.0, 99.0, "violent or extreme (MMI IX and above)")]
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}

def distance_km(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    a = np.sin((LAT - la) / 2) ** 2 + np.cos(la) * np.cos(LAT) * np.sin((LON - lo) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))

# ------------------------------------------------------------------ wording helpers
def say_people(n):
    n = float(n)
    if n < 1000: return "fewer than 1,000"
    if n < 1e6: return f"about {int(round(n, -3)):,}"
    return f"about {n / 1e6:.1f} million"

def _money_part(usd):
    usd = float(usd)
    if usd < 1e9: return f"{usd / 1e6:.0f} million"
    if usd < 1e12: return f"{usd / 1e9:.1f} billion"
    return f"{usd / 1e12:.1f} trillion"

def say_money(usd):
    if float(usd) < 1e6: return "less than 1 million US dollars"
    return f"about {_money_part(usd)} US dollars"

def say_money_range(low, base, high):
    if float(high) < 1e6:
        return "less than 1 million US dollars"
    lo = "under 1 million" if float(low) < 1e6 else _money_part(low)
    return f"between about {lo} and {_money_part(high)} US dollars (middle estimate {say_money(base)})"

def alert_level(loss_usd):
    m = loss_usd / 1e6
    return "green" if m < 1 else "yellow" if m < 100 else "orange" if m < 1000 else "red"

# ------------------------------------------------------------------ environmental screening rules
# These are screening labels built from published rules of thumb, not site assessments.
def tsunami_label(mag, depth, offshore):
    if mag < 6.5:
        return "very unlikely", "magnitude is below 6.5 (USGS guideline)"
    if depth >= 100:
        return "very unlikely", "the earthquake is deep (tsunamis need a shallow event; warning centers use under 100 km)"
    if offshore is False:
        return "very unlikely", "the epicenter is inland"
    if mag < 7.1:
        return "low", "magnitude 6.5 to 7.1 and shallow: a small local tsunami is possible only if the epicenter is under the sea near a coast"
    if offshore is True:
        return "possible", "magnitude 7.1 or more, shallow and offshore: warning centers would issue a tsunami threat message"
    return "possible if offshore", "magnitude 7.1 or more and shallow: a tsunami is possible if the epicenter is under or near the sea"

def landslide_label(mag, mmi, dem, pop_w, max_mmi):
    if mag < 5.0 or max_mmi < 6.0:
        return "low", "shaking is below the levels at which landsliding is usually observed (about magnitude 5 and intensity VI)"
    strong = (mmi >= 6.0) & (pop_w > 0)
    hilly = strong & (DEM_NAN_FILTER(dem) >= 300)
    share = pop_w[hilly].sum() / max(pop_w[strong].sum(), 1.0)
    if max_mmi >= 7.0 and share >= 0.3:
        return "moderate to high", "strong shaking (VII or more) and hilly terrain in about {:.0f}% of the exposed places (rough proxy)".format(100 * share)
    return "possible", "shaking of VI or more can trigger landslides on susceptible slopes; slope data is not used, only a rough hilliness proxy"

def DEM_NAN_FILTER(dem):
    return np.where(np.isnan(dem), -9999, dem)

def liquefaction_label(mag, mmi, dem, pop_w):
    if mag < 5.0:
        return "low", "magnitude is below about 5, the usual minimum for liquefaction"
    low = (mmi >= 7.0) & (DEM_NAN_FILTER(dem) <= 30) & (DEM_NAN_FILTER(dem) > -500)
    n = pop_w[low].sum()
    if low.any() and n > 0:
        return "possible", f"intensity VII or more reaches low-lying places (elevation 30 m or less) with {say_people(n)} people; soil type is not known"
    return "low", "no low-lying listed places reach intensity VII (soil type is not known)"

# ------------------------------------------------------------------ the calculator
def get_impact(lat, lon, magnitude, depth_km, region_name=None, offshore=None):
    """Impact and cost estimate for ONE scenario earthquake. Returns a dict (numbers + worded text)."""
    mag, depth = float(magnitude), float(depth_km)
    if offshore is None and region_name:
        up = str(region_name).upper()
        if up.startswith("OFF") or any(w in up for w in ("OFFSHORE", "SEA", "OCEAN", "TRENCH")):
            offshore = True

    d = distance_km(lat, lon)
    near = d <= MAX_KM
    r_hyp = np.sqrt(d ** 2 + depth ** 2)
    mmi = np.where(near, mmi_from_hypo_distance(mag, r_hyp), 1.0)

    # loss per place: people x value per person x loss ratio at that place's shaking (USGS PAGER-style model)
    shaken = near & (mmi >= 5.0)
    ratio = np.where(shaken, norm.cdf(np.log(np.minimum(mmi, 9.0) / THETA) / BETA), 0.0)
    loss_i = P * VALUE_PC * ratio
    total = float(loss_i.sum())
    zeta = float((loss_i * ZETA).sum() / total) if total > 0 else float(DEFAULT["zeta"])

    # the intensity equation has a standard deviation of about 0.8 intensity units, and the loss curve is very steep,
    # so also compute the loss if shaking is one standard deviation stronger than the median estimate
    mmi_hi = np.where(near, np.clip(mmi + mmi_sigma(r_hyp), 1.0, 10.0), 1.0)
    ratio_hi = np.where(near & (mmi_hi >= 5.0), norm.cdf(np.log(np.minimum(mmi_hi, 9.0) / THETA) / BETA), 0.0)
    total_hi = float((P * VALUE_PC * ratio_hi).sum())

    bands = []
    for lo, hi, name in BANDS:
        m = shaken & (mmi >= lo) & (mmi < hi)
        bands.append({"band": name, "people": int(P[m].sum()), "places": int(m.sum()), "loss_usd": float(loss_i[m].sum())})

    max_mmi = float(mmi[near].max()) if near.any() else 0.0
    epi_mmi = float(mmi_from_hypo_distance(mag, depth))          # shaking right above the epicenter
    people_vi = float(P[near & (mmi >= 6.0)].sum())
    people_v = float(P[shaken].sum())
    nearest = int(np.argmin(d))
    top = np.argsort(loss_i)[::-1][:3]
    biggest = [{"place": str(NAMES[i]), "country": str(COUNTRY[i]), "distance_km": round(float(d[i])), "mmi": round(float(mmi[i]), 1),
                "people": int(P[i])} for i in top if loss_i[i] > 0]

    ts, ts_why = tsunami_label(mag, depth, offshore)
    ls, ls_why = landslide_label(mag, mmi, DEM, P, max_mmi)
    lq, lq_why = liquefaction_label(mag, mmi, DEM, P)

    assumptions = [
        "Shaking from the Allen, Wald and Worden (2012) intensity equation (active crustal regions, hypocentral distance)",
        "Loss ratio and uncertainty from Jaiswal and Wald (2011), USGS Open-File Report 2011-1116",
        "Exposed value = GDP per person x exposure factor alpha (same report); GDP from the World Bank",
        "People counted only in listed towns and cities (GeoNames), so counts are a minimum",
        "Shaking uncertainty (about 0.8 intensity units) is shown separately as the 'stronger shaking' case",
        "Soil, slope and building types are not modeled"]
    warnings = []
    if not 5.0 <= mag <= 7.9:
        warnings.append("magnitude is outside 5.0 to 7.9, the range of the shaking model: treat shaking as less reliable")
    if depth > 40:
        warnings.append("depth is over 40 km: the shaking model was built for shallow crustal earthquakes")
    if not near.any() or float(d.min()) > 100:
        warnings.append("no listed place within 100 km: the epicenter is remote or offshore, so counts are very low")

    sigma_mmi = float(mmi_sigma(r_hyp[nearest]))
    result = {
        "scenario": {"lat": lat, "lon": lon, "magnitude": mag, "depth_km": depth, "nearest_place": str(NAMES[nearest]),
                     "nearest_country": str(COUNTRY[nearest]), "nearest_km": round(float(d[nearest]))},
        "shaking": {"mmi_at_epicenter": round(epi_mmi, 1), "max_mmi_listed_places": round(max_mmi, 1), "sigma_mmi": round(sigma_mmi, 2), "bands": bands},
        "people": {"exposed_mmi_5_plus": int(people_v), "exposed_mmi_6_plus": int(people_vi)},
        "loss_usd": {"low": total * np.exp(-zeta), "base": total, "high": total * np.exp(zeta), "zeta": round(zeta, 2),
                     "base_stronger_shaking": total_hi, "high_stronger_shaking": total_hi * np.exp(zeta)},
        "alert": alert_level(total),
        "largest_contributors": biggest,
        "environment": {"tsunami": {"level": ts, "why": ts_why}, "landslide": {"level": ls, "why": ls_why},
                        "liquefaction": {"level": lq, "why": lq_why}},
        "confidence": "low: simplified scenario estimate" if not warnings else "very low: " + "; ".join(warnings),
        "warnings": warnings, "assumptions": assumptions,
    }
    mm = ROMAN.get(int(round(epi_mmi)), str(round(epi_mmi, 1)))
    result["text"] = {
        "scenario": f"Magnitude {mag:g} earthquake at {depth:g} km depth near {NAMES[nearest]} ({COUNTRY[nearest]}).",
        "strongest_shaking": f"intensity {mm} directly above the epicenter ({epi_mmi:.1f} on the Modified Mercalli scale)",
        "people_strong_shaking": say_people(people_vi) + " people in listed places with strong shaking (intensity VI or more)",
        "cost_range": say_money_range(total * np.exp(-zeta), total, total * np.exp(zeta)),
        "cost_if_shaking_stronger": f"if shaking is one standard deviation stronger than the median estimate: middle estimate {say_money(total_hi)}",
        "alert_level": f"{result['alert']} on the USGS economic loss scale",
        "tsunami": f"{ts}: {ts_why}", "landslide": f"{ls}: {ls_why}", "liquefaction": f"{lq}: {lq_why}",
        "confidence": result["confidence"],
    }
    return result

if __name__ == "__main__":
    import json
    r = get_impact(35.76, 129.19, 6.5, 10)
    print(json.dumps(r["text"], indent=2))