"""Turn solver output into chart data + a question pool for the Daily GTO page.
usage: python3 build_questions.py out/Ks7d2c.json [...more] > out/data.js
"""
import json, sys, random

RANKS = "AKQJT98765432"


def hand_class(c):
    a, b = c[0], c[2]
    if a == b:
        return a + b
    hi, lo = sorted([a, b], key=RANKS.index)
    return hi + lo + ("s" if c[1] == c[3] else "o")


def label(act, node):
    pot = node["pot"]
    code, amt = act[0], act[1:]
    if code == "X": return {"k": "check", "t": "Check"}
    if code == "C": return {"k": "call", "t": "Call"}
    if code == "F": return {"k": "fold", "t": "Fold"}
    v = int(amt) / 10
    if code == "B":
        pct = round(v / pot * 100)
        return {"k": "bet_s" if pct < 50 else "bet_l", "t": f"Bet {pct}%", "amt": v}
    if code == "R":
        return {"k": "raise", "t": f"Raise {v:g}", "amt": v}
    if code == "A":
        return {"k": "allin", "t": "All-in", "amt": v}
    return {"k": "other", "t": act}


def chart(node):
    agg = {}
    combos = {}
    tot_w = 0
    na = len(node["actions"])
    tot = [0.0] * na
    for h in node["hands"]:
        k = hand_class(h["c"])
        e = agg.setdefault(k, {"w": 0.0, "s": [0.0] * na, "n": 0})
        e["w"] += h["w"]; e["n"] += 1
        combos.setdefault(k, []).append([h["c"], round(h["w"], 2)] + h["s"])
        for i, s in enumerate(h["s"]):
            e["s"][i] += s * h["w"]; tot[i] += s * h["w"]
        tot_w += h["w"]
    out = {}
    for k, e in agg.items():
        if e["w"] <= 0: continue
        maxw = 6 if len(k) == 2 else 4 if k[2] == "s" else 12
        out[k] = [round(min(e["w"] / maxw, 1), 3)] + [round(x / e["w"], 3) for x in e["s"]]
    return out, [round(x / tot_w, 3) for x in tot], [round(x, 1) for x in tot], combos


def grade_info(h):
    best_ev = max(h["evs"])
    return [round(best_ev - e, 3) for e in h["evs"]]


def main():
    spots, pool = [], []
    for path in sys.argv[1:]:
        d = json.load(open(path))
        si = len(spots)
        nodes = []
        for ni, n in enumerate(d["nodes"]):
            acts = [label(a, n) for a in n["actions"]]
            mx = max(h["w"] for h in n["hands"])
            for h in n["hands"]: h["w"] = h["w"] / mx
            ch, tot, cmb, combos = chart(n)
            nodes.append({"id": n["id"], "path": n["path"], "player": n["player"], "pot": n["pot"],
                          "bets": n["bets"], "acts": acts, "chart": ch, "tot": tot, "cmb": cmb, "combos": combos})
            # question candidates (skip near-pure nodes: every answer would be the same)
            if max(tot) > 0.97: continue
            rng = random.Random(f"{d['flop']}-{n['id']}")
            by_best = {}
            seen = set()
            hands = sorted(n["hands"], key=lambda h: -h["w"])
            for h in hands:
                if h["w"] < 0.3: continue
                cls = hand_class(h["c"])
                if cls in seen: continue
                loss = grade_info(h)
                s = h["s"]
                order = sorted(range(len(s)), key=lambda i: -s[i])
                top, second = order[0], order[1]
                gap = sorted(loss)[1]  # EV cost of the 2nd-best choice
                if s[top] >= 0.8 and gap >= 0.08:
                    kind = "pure"
                elif s[top] >= 0.35 and s[second] >= 0.35:
                    kind = "mix"
                else:
                    continue
                # answer must match the hand class majority (skip suit/blocker quirks)
                cv = ch.get(cls)
                if not cv or cv[1 + top] < 0.5:
                    continue
                seen.add(cls)
                by_best.setdefault((top, kind), []).append(
                    {"s": si, "n": ni, "c": h["c"], "f": s, "l": loss, "eq": h["eq"], "kind": kind})
            for (top, kind), lst in by_best.items():
                rng.shuffle(lst)
                cap = 6 if kind == "pure" else 2
                pool.extend(lst[:cap])
        spots.append({"flop": d["flop"], "turn": d["turn"], "spot": d["spot"],
                      "expl": d["exploitability_pct_pot"], "nodes": nodes})
    # round-robin across nodes so each day mixes situations
    rng = random.Random(7)
    buckets = {}
    for q in pool:
        buckets.setdefault((q["s"], q["n"]), []).append(q)
    for b in buckets.values(): rng.shuffle(b)
    keys = list(buckets)
    ordered = []
    while any(buckets.values()):
        rng.shuffle(keys)
        for k in keys:
            if buckets[k]: ordered.append(buckets[k].pop())
    sys.stderr.write(f"{len(ordered)} questions, nodes: " + ", ".join(f"{k}:{sum(1 for q in pool if (q['s'],q['n'])==k)}" for k in keys) + "\n")
    print("const DATA=" + json.dumps({"spots": spots, "pool": ordered}, separators=(",", ":")) + ";")


main()
