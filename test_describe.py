"""
Offline test of the number check and the fallback. It does NOT need Ollama: a fake model stands in for Llama.
Run:  python test_describe.py
"""
import re
import quake_describe as qd
from impacts import get_impact

result = get_impact(35.76, 129.19, 6.5, 10)
t = result["text"]
print("RESULT TEXT:"); [print("  ", k, "=", v) for k, v in t.items()]

GOOD = (f"{t['scenario']} People would feel {t['strongest_shaking']}, and {t['people_strong_shaking']}. "
        f"The cost is a rough estimate: {t['cost_range']}. Alert: {t['alert_level']}. "
        f"Tsunami: {t['tsunami']}. Confidence: {t['confidence']}. What to do: 1. Drop, cover and hold on. "
        "2. Stay away from windows. 3. Follow your local authorities.")

# Dynamically replace the first number in cost_range with 999.9 so it is always an invented number
bad_cost = re.sub(r"\d+(?:\.\d+)?", "999.9", t["cost_range"], count=1)
INVENTED = GOOD.replace(t["cost_range"], bad_cost)
OMITS_COST = "A strong earthquake would shake the area. What to do: 1. Drop. 2. Cover. 3. Hold on."

def run(responses, label):
    calls = {"n": 0, "prompts": []}
    def fake(prompt):
        calls["prompts"].append(prompt); r = responses[min(calls["n"], len(responses) - 1)]; calls["n"] += 1; return r
    qd.call_llm = fake
    text, fb, hist = qd.describe(result, guidance="", retries=1)
    print(f"\n[{label}] used_fallback={fb} attempts={len(hist)}")
    for h in hist: print("   ", h)
    return text, fb, hist, calls

text, fb, hist, _ = run([GOOD], "1. good answer")
assert not fb and len(hist) == 1 and not hist[0]["unknown_numbers"], "good answer should pass first time"

text, fb, hist, calls = run([INVENTED, GOOD], "2. invented number, then a good retry")
assert not fb and len(hist) == 2 and hist[0]["unknown_numbers"], "invented number must be caught and retried"
assert "not in RESULT" in calls["prompts"][1], "retry prompt must list the bad numbers"

text, fb, hist, _ = run([INVENTED, INVENTED], "3. invented number twice -> fallback")
assert fb and "999.9" not in text and t["cost_range"] in text, "fallback must use only result text"

text, fb, hist, _ = run([OMITS_COST, GOOD], "4. leaves out the cost, then a good retry")
assert not fb and hist[0]["missing_cost_numbers"], "missing cost numbers must be caught"

# the number checker on its own
allowed = qd.allowed_numbers(result, "")
assert qd.unknown_numbers("about 1,300,000 people", {1300000.0}) == []
assert qd.unknown_numbers("cost 9.9 billion", allowed) == [9.9]
print("\nALL OFFLINE TESTS PASSED")
print("\nFallback text example:\n", qd.fallback_description(result))