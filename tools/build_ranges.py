"""Preflop input ranges (PioSolver format) -> data/ranges.json for the range viewer."""
import json, sys
R = "AKQJT98765432"

def expand(tok):
    h, _, w = tok.partition(":")
    w = float(w) if w else 1.0
    out = []
    if "-" in h:
        a, b = h.split("-")
        if len(a) == 2:  # pairs JJ-22
            for i in range(R.index(a[0]), R.index(b[0]) + 1):
                out.append(R[i] * 2)
        else:  # AQs-A6s
            for i in range(R.index(a[1]), R.index(b[1]) + 1):
                out.append(a[0] + R[i] + a[2])
    elif h.endswith("+"):
        h = h[:-1]
        if len(h) == 2:  # 22+
            for i in range(0, R.index(h[0]) + 1):
                out.append(R[i] * 2)
        else:  # A2s+
            for i in range(R.index(h[0]) + 1, R.index(h[1]) + 1):
                out.append(h[0] + R[i] + h[2])
    else:
        out.append(h)
    return [(c, w) for c in out]

def parse(path):
    m = {}
    for tok in open(path).read().strip().split(","):
        for c, w in expand(tok.strip()):
            m[c] = w
    combos = sum(w * (6 if len(c) == 2 else 4 if c[2] == "s" else 12) for c, w in m.items())
    return {"w": m, "pct": round(combos / 1326 * 100, 1)}

d = {"BTN": {"label": "BTN Open 2.5bb", **parse("tools/ranges/btn_open.txt")},
     "BB": {"label": "BB Call vs BTN", **parse("tools/ranges/bb_call_vs_btn.txt")}}
json.dump(d, open("data/ranges.json", "w"), separators=(",", ":"))
print({k: (v["pct"], len(v["w"])) for k, v in d.items()})
