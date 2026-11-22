"""Solver hand playthroughs -> per-hand JSON files for the site, with data-only explanations.
usage: python3 tools/build_hands.py raw/*.hands.json --out data/hands
"""
import json, os, sys
from collections import defaultdict

RANKS = "23456789TJQKA"
RV = {r: i + 2 for i, r in enumerate(RANKS)}
ORDER = "AKQJT98765432"
START_POT = 55  # chips, 10 chips = 1bb


def cls_of(c):
    a, b = c[0], c[2]
    if a == b:
        return a + b
    hi, lo = sorted([a, b], key=ORDER.index)
    return hi + lo + ("s" if c[1] == c[3] else "o")


def has_straight(vals):
    s = set(vals)
    if 14 in s:
        s.add(1)
    return any(all(v - k in s for k in range(5)) for v in range(5, 15))


def category(hole, board):
    """(made, draw) for a 2-card hand on a 3-5 card board. Plain facts only."""
    h = [(RV[c[0]], c[1]) for c in (hole[:2], hole[2:])]
    b = [(RV[c[0]], c[1]) for c in board]
    allc = h + b
    suits = defaultdict(int)
    for _, s in allc:
        suits[s] += 1
    bsuits = defaultdict(int)
    for _, s in b:
        bsuits[s] += 1
    flush = any(n >= 5 and any(s == hs for _, hs in h) and bsuits[s] < 5 for s, n in suits.items())
    straight = has_straight([v for v, _ in allc]) and not has_straight([v for v, _ in b])
    bcount = defaultdict(int)
    for v, _ in b:
        bcount[v] += 1
    uniq = sorted(set(v for v, _ in b), reverse=True)
    a, c2 = h[0][0], h[1][0]
    made = None
    if flush:
        made = "플러시"
    elif straight:
        made = "스트레이트"
    elif a == c2:
        n = bcount[a]
        if n >= 2:
            made = "포카드"
        elif n == 1:
            made = "풀하우스" if any(k != a and m >= 2 for k, m in bcount.items()) else "세트"
        elif a > uniq[0]:
            made = "오버페어"
        elif len(uniq) > 1 and a > uniq[1]:
            made = "미들 포켓페어"
        else:
            made = "로우 포켓페어"
    else:
        ma, mb = bcount[a], bcount[c2]
        if ma == 3 or mb == 3:
            made = "포카드"
        elif (ma >= 1 and mb >= 1) and (ma == 2 or mb == 2):
            made = "풀하우스"
        elif ma >= 1 and mb >= 1:
            made = "투페어"
        elif ma == 2 or mb == 2:
            made = "트립스"
        elif ma == 1 or mb == 1:
            r = a if ma == 1 else c2
            i = uniq.index(r)
            made = "탑페어" if i == 0 else "세컨드 페어" if i == 1 else "로우 페어"
        else:
            made = "노페어"
    draw = None
    if len(board) < 5 and made not in ("플러시", "스트레이트", "풀하우스", "포카드"):
        fd = any(n == 4 and any(s == hs for _, hs in h) and bsuits[s] < 4 for s, n in suits.items())
        outs = 0
        vals = [v for v, _ in allc]
        bvals = [v for v, _ in b]
        for r in range(2, 15):
            if has_straight(vals + [r]) and not has_straight(vals) and not has_straight(bvals + [r]):
                outs += 1
        sd = "오픈엔드" if outs >= 2 else "거트샷" if outs == 1 else None
        if fd and sd:
            draw = "플러시 드로우 + " + sd
        elif fd:
            draw = "플러시 드로우"
        elif sd:
            draw = sd + " 스트레이트 드로우"
    return made, draw


def group_key(made, draw):
    if made in ("노페어",):
        return "노페어 + 드로우" if draw else "노페어"
    return made


def act_label(code, pot_before, street_bets, p):
    c, v = code[0], code[1:]
    if c == "X": return {"k": "check", "t": "Check"}
    if c == "C": return {"k": "call", "t": "Call"}
    if c == "F": return {"k": "fold", "t": "Fold"}
    amt = int(v) / 10
    if c == "B":
        pct = round(int(v) / pot_before * 100)
        return {"k": "bet_s" if pct < 50 else "bet_l", "t": f"Bet {pct}%", "amt": amt}
    if c == "R": return {"k": "raise", "t": f"Raise {amt:g}", "amt": amt}
    if c == "A": return {"k": "allin", "t": "All-in", "amt": amt}
    return {"k": "other", "t": code}


def replay(path):
    """pot (chips, before current street bets) and current street bets [BB, BTN]."""
    pot, bets, p = START_POT, [0, 0], 0
    for t in path:
        if len(t) == 2 and t[0] in RANKS and t[1] in "shdc":
            pot += sum(bets); bets = [0, 0]; p = 0; continue
        c = t[0]
        if c == "C": bets[p] = bets[1 - p]
        elif c in "BRA": bets[p] = int(t[1:])
        p = 1 - p
    return pot, bets


def pct(x): return f"{round(x * 100)}%"


def explain(node, hero, hc, board, acts):
    lines = []
    made, draw = category(hc, board)
    lines.append("핸드: " + made + (" + " + draw if draw else ""))
    pot, bets = replay(node["path"])
    hp = 0 if hero == "BB" else 1
    to_call = bets[1 - hp] - bets[hp]
    if to_call > 0:
        need = to_call / (pot + sum(bets) + to_call)
        lines.append(f"Call에 필요한 승률 {pct(need)} · 지금 승률 {pct(node['eq'])} (상대 레인지 기준)")
    # same-group aggregate over hero's range at this node
    gk = group_key(made, draw)
    k = len(acts)
    agg, tw = [0.0] * k, 0.0
    for c, w, s in node["range"]:
        m, d = category(c, board)
        if group_key(m, d) != gk:
            continue
        tw += w
        for i in range(k):
            agg[i] += w * s[i]
    if tw > 0:
        parts = [f"{acts[i]['t']} {pct(agg[i] / tw)}" for i in sorted(range(k), key=lambda i: -agg[i]) if agg[i] / tw >= 0.01]
        lines.append(f"같은 그룹({gk}) 전체: " + " · ".join(parts))
    # EV gap between the top two choices
    ev = node["evs"]
    order = sorted(range(k), key=lambda i: -ev[i])
    gap = ev[order[0]] - ev[order[1]] if k > 1 else 1
    if gap < 0.05:
        lines.append(f"{acts[order[0]]['t']}와 {acts[order[1]]['t']}의 EV 차이 {gap:.2f}bb: 거의 같은 선택")
    return lines


def chart(node, k):
    agg = {}
    for c, w, s in node["range"]:
        key = cls_of(c)
        e = agg.setdefault(key, [0.0, [0.0] * k])
        e[0] += w
        for i in range(k):
            e[1][i] += w * s[i]
    mx = max(w for _, w, _ in node["range"])
    out, tot, totw = {}, [0.0] * k, 0.0
    for key, (w, s) in agg.items():
        if w <= 0:
            continue
        cap = (6 if len(key) == 2 else 4 if key[2] == "s" else 12) * mx
        out[key] = [round(min(w / cap, 1), 3)] + [round(x / w, 3) for x in s]
        for i in range(k):
            tot[i] += s[i]
        totw += w
    return out, [round(x / totw, 3) for x in tot], [round(x / mx, 1) for x in tot]


def main():
    args = sys.argv[1:]
    out_dir = args[args.index("--out") + 1]
    files = [a for a in args if a.endswith(".hands.json")]
    os.makedirs(out_dir, exist_ok=True)
    index = []
    for f in files:
        d = json.load(open(f))
        flop = [d["flop"][i:i + 2] for i in (0, 2, 4)]
        for hi, h in enumerate(d["hands"]):
            # keep only the main line: after every hero decision the hand continues with the best action
            raw, keep, i = h["nodes"], [], 0
            while True:
                keep.append(i)
                if raw[i].get("end"):
                    break
                i = raw[i]["next"][str(raw[i]["best"])]
            # nodes with a single legal action (e.g. BB must check on the flop) are not questions
            keep = [i for i in keep if raw[i].get("end") or len(raw[i]["acts"]) > 1]
            if len(keep) < 2:
                continue
            nodes = []
            for j, n in enumerate(raw[i] for i in keep):
                if n.get("end"):
                    nodes.append({"end": 1, "p": n["path"]})
                    continue
                board = flop + [t for t in n["path"] if len(t) == 2 and t[0] in RANKS and t[1] in "shdc"]
                pot, bets = replay(n["path"])
                acts = [act_label(a, pot + sum(bets), bets, 0) for a in n["acts"]]
                k = len(acts)
                ch, tot, cmb = chart(n, k)
                best_ev = max(n["evs"])
                mine = cls_of(h["hc"])
                nodes.append({
                    "p": n["path"], "a": acts, "s": n["s"], "l": [round(best_ev - e, 3) for e in n["evs"]],
                    "eq": n["eq"], "b": n["best"], "nx": j + 1, "ch": ch, "tot": tot, "cmb": cmb,
                    "hcls": [[c] + s for c, w, s in n["range"] if cls_of(c) == mine],
                    "x": explain(n, h["hero"], h["hc"], board, acts),
                })
            hid = f"{d['flop']}-{hi:03d}"
            json.dump({"id": hid, "hero": h["hero"], "hc": h["hc"], "vc": h["vc"], "flop": d["flop"],
                       "nodes": nodes}, open(os.path.join(out_dir, hid + ".json"), "w"), separators=(",", ":"), ensure_ascii=False)
            index.append(hid)
    json.dump({"hands": index}, open(os.path.join(out_dir, "index.json"), "w"))
    print(f"{len(index)} hands -> {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
