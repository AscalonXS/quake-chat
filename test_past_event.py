"""
Compare the calculator with recorded losses of past earthquakes.
The epicenters below are APPROXIMATE (typed from memory): check each one on the USGS event page before you trust it.
Recorded losses: Jaiswal and Wald (2011), Open-File Report 2011-1116, Table 2 (check the numbers there too).
Population and GDP are today's values, not those of the event year, so expect rough agreement at best.

Columns: "standard range" = median shaking, loss uncertainty only (low to high).
         "wide range"     = from the standard low to the high of the case with shaking one standard deviation stronger.
"""
from impacts import get_impact

EVENTS = [  # name, lat, lon, magnitude, depth_km, recorded loss in million USD (from the report's Table 2)
    ("Northridge 1994", 34.21, -118.54, 6.7, 18, 44000),
    ("Kobe 1995", 34.60, 135.00, 6.9, 17, 100000),
    ("Chi-Chi 1999", 23.85, 120.82, 7.6, 20, 14000),
    ("Sichuan 2008", 31.00, 103.32, 7.9, 19, 85000),
    ("Izmit 1999", 40.75, 29.86, 7.6, 15, 12000),
]

print(f"{'event':<17}{'low':>9}{'base':>9}{'high':>9}{'wide high':>11}{'recorded':>10}{'base/rec':>9}  {'standard':<9}{'wide':<5}")
inside_std = inside_wide = 0
for name, lat, lon, m, dep, rec in EVENTS:
    r = get_impact(lat, lon, m, dep)["loss_usd"]
    lo, ba, hi, wh = r["low"] / 1e6, r["base"] / 1e6, r["high"] / 1e6, r["high_stronger_shaking"] / 1e6
    a, b = lo <= rec <= hi, lo <= rec <= wh
    inside_std += a; inside_wide += b
    print(f"{name:<17}{lo:>9,.0f}{ba:>9,.0f}{hi:>9,.0f}{wh:>11,.0f}{rec:>10,.0f}{ba / rec:>9.2f}  {'yes' if a else 'no':<9}{'yes' if b else 'no':<5}")
print(f"\nrecorded loss inside the standard range: {inside_std} of {len(EVENTS)}; inside the wide range: {inside_wide} of {len(EVENTS)}")
print("All amounts in million US dollars. A ratio within a factor of about 3 either way is normal for this kind of model.")
