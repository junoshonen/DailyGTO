// Solve one BTN vs BB single-raised-pot flop and dump selected decision nodes as JSON.
// usage: dgsolve <flop e.g. Ks7d2c> <out.json> <estimate|solve> [turn card for turn nodes]
use postflop_solver::*;
use serde_json::{json, Value};

const BB: f32 = 10.0; // chips per big blind

fn action_label(a: &Action) -> String {
    match a {
        Action::Fold => "F".into(),
        Action::Check => "X".into(),
        Action::Call => "C".into(),
        Action::Bet(n) => format!("B{}", n),
        Action::Raise(n) => format!("R{}", n),
        Action::AllIn(n) => format!("A{}", n),
        other => format!("{:?}", other),
    }
}

// token: X, C, F, B1/B2 (nth bet), R1 (nth raise/allin), or a card like 4h
fn resolve(game: &PostFlopGame, tok: &str) -> usize {
    if game.is_chance_node() {
        return card_from_str(tok).unwrap() as usize;
    }
    let acts = game.available_actions();
    let pick = |pred: &dyn Fn(&Action) -> bool, n: usize| -> usize {
        acts.iter().enumerate().filter(|(_, a)| pred(a)).nth(n - 1)
            .unwrap_or_else(|| panic!("token {} not in {:?}", tok, acts)).0
    };
    match tok {
        "X" => pick(&|a| matches!(a, Action::Check), 1),
        "C" => pick(&|a| matches!(a, Action::Call), 1),
        "F" => pick(&|a| matches!(a, Action::Fold), 1),
        t if t.starts_with('B') => pick(&|a| matches!(a, Action::Bet(_)), t[1..].parse().unwrap()),
        t if t.starts_with('R') => pick(&|a| matches!(a, Action::Raise(_) | Action::AllIn(_)), t[1..].parse().unwrap()),
        _ => panic!("bad token {}", tok),
    }
}

fn r3(x: f32) -> f64 { ((x as f64) * 1000.0).round() / 1000.0 }

fn dump(game: &mut PostFlopGame, id: &str, path: &[&str], start_pot: i32) -> Value {
    game.back_to_root();
    let mut hist = vec![];
    for t in path {
        let i = resolve(game, t);
        if game.is_chance_node() { hist.push(t.to_string()); } else { hist.push(action_label(&game.available_actions()[i])); }
        game.play(i);
    }
    game.cache_normalized_weights();
    let p = game.current_player();
    let acts: Vec<String> = game.available_actions().iter().map(action_label).collect();
    let tb = game.total_bet_amount();
    let pot = start_pot + tb[0] + tb[1];
    let cards = holes_to_strings(game.private_cards(p)).unwrap();
    let n = cards.len();
    let strat = game.strategy();
    let evd = game.expected_values_detail(p);
    let ev = game.expected_values(p);
    let eq = game.equity(p);
    let w = game.normalized_weights(p).to_vec();
    let mut hands = vec![];
    for h in 0..n {
        if w[h] < 1e-4 { continue; }
        let s: Vec<f64> = (0..acts.len()).map(|a| r3(strat[a * n + h])).collect();
        let e: Vec<f64> = (0..acts.len()).map(|a| r3(evd[a * n + h] / BB)).collect();
        hands.push(json!({"c": cards[h], "w": r3(w[h]), "eq": r3(eq[h]), "ev": r3(ev[h] / BB), "s": s, "evs": e}));
    }
    json!({"id": id, "path": hist, "player": if p == 0 {"BB"} else {"BTN"},
           "pot": pot as f32 / BB, "bets": [tb[0] as f32 / BB, tb[1] as f32 / BB],
           "actions": acts, "hands": hands})
}


struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 { let mut x = self.0; x ^= x << 13; x ^= x >> 7; x ^= x << 17; self.0 = x; x }
    fn f(&mut self) -> f64 { (self.next() >> 11) as f64 / (1u64 << 53) as f64 }
}
fn cstr(c: u8) -> String { card_to_string(c).unwrap() }

// Walk forward from the current state until the hero must act (or the hand ends).
// Villain acts by sampling its own combo's GTO strategy; chance nodes take the fixed runout.
// At hero nodes we branch on every action the hero uses >= 10% plus the best one.
fn walk(game: &mut PostFlopGame, hero: usize, hi: usize, vi: usize, run: &[u8],
        nodes: &mut Vec<Value>, rng: &mut Rng, mut labels: Vec<String>) -> usize {
    loop {
        if game.is_terminal_node() {
            let id = nodes.len();
            nodes.push(json!({"end": true, "path": labels}));
            return id;
        }
        if game.is_chance_node() {
            let c = run[game.current_board().len() - 3];
            labels.push(cstr(c));
            game.play(c as usize);
            continue;
        }
        let p = game.current_player();
        let acts = game.available_actions();
        if p != hero {
            let n = game.private_cards(p).len();
            let st = game.strategy();
            let mut r = rng.f();
            let mut a = acts.len() - 1;
            for k in 0..acts.len() { r -= st[k * n + vi] as f64; if r <= 0.0 { a = k; break; } }
            labels.push(action_label(&acts[a]));
            game.play(a);
            continue;
        }
        game.cache_normalized_weights();
        let cards = holes_to_strings(game.private_cards(hero)).unwrap();
        let n = cards.len();
        let st = game.strategy();
        let evd = game.expected_values_detail(hero);
        let eq = game.equity(hero);
        let w = game.normalized_weights(hero).to_vec();
        let k = acts.len();
        let s: Vec<f64> = (0..k).map(|a| r3(st[a * n + hi])).collect();
        let e: Vec<f64> = (0..k).map(|a| r3(evd[a * n + hi] / BB)).collect();
        let mut range = vec![];
        for h in 0..n {
            if w[h] < 1e-4 { continue; }
            let hs: Vec<f64> = (0..k).map(|a| r3(st[a * n + h])).collect();
            range.push(json!([cards[h], r3(w[h]), hs]));
        }
        let best = (0..k).max_by(|&a, &b| s[a].partial_cmp(&s[b]).unwrap()).unwrap();
        let id = nodes.len();
        nodes.push(json!({"path": labels.clone(), "acts": acts.iter().map(action_label).collect::<Vec<_>>(),
                          "s": s, "evs": e, "eq": r3(eq[hi]), "best": best, "range": range}));
        let hist = game.history().to_vec();
        let mut next = serde_json::Map::new();
        for a in 0..k {
            if a == best {
                game.apply_history(&hist);
                game.play(a);
                let mut l = labels.clone();
                l.push(action_label(&acts[a]));
                let cid = walk(game, hero, hi, vi, run, nodes, rng, l);
                next.insert(a.to_string(), json!(cid));
            }
        }
        nodes[id]["next"] = Value::Object(next);
        return id;
    }
}

fn hand_scripts(game: &mut PostFlopGame, count: usize, seed: u64) -> Vec<Value> {
    let mut rng = Rng(seed | 1);
    let flop = game.card_config().flop;
    let mut out = vec![];
    for s in 0..count {
        let hero = s % 2;
        let vil = 1 - hero;
        game.back_to_root();
        let hc = game.private_cards(hero).to_vec();
        let vc = game.private_cards(vil).to_vec();
        let hw = game.weights(hero).to_vec();
        let vw = game.weights(vil).to_vec();
        let cand: Vec<usize> = (0..hc.len()).filter(|&i| hw[i] > 0.2).collect();
        let hi = cand[(rng.next() as usize) % cand.len()];
        let (h1, h2) = hc[hi];
        let ok = |i: usize| { let (a, b) = vc[i]; a != h1 && a != h2 && b != h1 && b != h2 };
        let tot: f64 = (0..vc.len()).filter(|&i| ok(i)).map(|i| vw[i] as f64).sum();
        let mut r = rng.f() * tot;
        let mut vi = 0;
        for i in 0..vc.len() { if !ok(i) { continue; } vi = i; r -= vw[i] as f64; if r <= 0.0 { break; } }
        let (v1, v2) = vc[vi];
        let used = [flop[0], flop[1], flop[2], h1, h2, v1, v2];
        let mut run: Vec<u8> = vec![];
        while run.len() < 2 { let c = (rng.next() % 52) as u8; if !used.contains(&c) && !run.contains(&c) { run.push(c); } }
        let mut nodes = vec![];
        walk(game, hero, hi, vi, &run, &mut nodes, &mut rng, vec![]);
        out.push(json!({"hero": if hero == 0 {"BB"} else {"BTN"},
            "hc": holes_to_strings(&[(h1, h2)]).unwrap()[0], "vc": holes_to_strings(&[(v1, v2)]).unwrap()[0],
            "run": [cstr(run[0]), cstr(run[1])], "nodes": nodes}));
        eprintln!("hand {} done ({} nodes)", s, out.last().unwrap()["nodes"].as_array().unwrap().len());
    }
    out
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let (flop, out, mode) = (&a[1], &a[2], &a[3]);
    let turn = a.get(4).cloned().unwrap_or("4h".into());
    let base = std::env::var("RANGES_DIR").unwrap_or("tools/ranges/".into());
    let oop = std::fs::read_to_string(format!("{base}bb_call_vs_btn.txt")).unwrap();
    let ip = std::fs::read_to_string(format!("{base}btn_open.txt")).unwrap();
    let card_config = CardConfig {
        range: [oop.trim().parse().unwrap(), ip.trim().parse().unwrap()],
        flop: flop_from_str(flop).unwrap(),
        turn: NOT_DEALT,
        river: NOT_DEALT,
    };
    let fl_oop = BetSizeOptions::try_from((std::env::var("FL_OOP").unwrap_or("".into()).as_str(), std::env::var("FL_R").unwrap_or("3x".into()).as_str())).unwrap();
    let fl_ip = BetSizeOptions::try_from((std::env::var("FL_IP").unwrap_or("33%, 75%".into()).as_str(), std::env::var("FL_R").unwrap_or("3x".into()).as_str())).unwrap();
    let tu = BetSizeOptions::try_from((std::env::var("TU").unwrap_or("75%".into()).as_str(), std::env::var("TU_R").unwrap_or("a".into()).as_str())).unwrap();
    let ri = BetSizeOptions::try_from((std::env::var("RI").unwrap_or("75%".into()).as_str(), std::env::var("RI_R").unwrap_or("a".into()).as_str())).unwrap();
    let start_pot = 55; // 2.5 + 2.5 + 0.5 SB
    let tree_config = TreeConfig {
        initial_state: BoardState::Flop,
        starting_pot: start_pot,
        effective_stack: 975,
        rake_rate: 0.0,
        rake_cap: 0.0,
        flop_bet_sizes: [fl_oop, fl_ip],
        turn_bet_sizes: [tu.clone(), tu],
        river_bet_sizes: [ri.clone(), ri],
        turn_donk_sizes: None,
        river_donk_sizes: None,
        add_allin_threshold: 1.5,
        force_allin_threshold: 0.15,
        merging_threshold: 0.1,
    };
    let tree = ActionTree::new(tree_config).unwrap();
    let mut game = PostFlopGame::with_config(card_config, tree).unwrap();
    let (m, mc) = game.memory_usage();
    eprintln!("mem: {:.2}GB raw, {:.2}GB compressed", m as f64 / 1073741824.0, mc as f64 / 1073741824.0);
    if mode == "estimate" { return; }
    game.allocate_memory(true);
    let target = start_pot as f32 * 0.003; // 0.3% of pot
    let t0 = std::time::Instant::now();
    let expl = solve(&mut game, 2000, target, true);
    eprintln!("exploitability {:.4} chips ({:.3}% pot), {:.0}s", expl, 100.0 * expl / start_pot as f32, t0.elapsed().as_secs_f32());

    let t = turn.as_str();
    let specs: Vec<(&str, Vec<&str>)> = vec![
        ("f_btn_vs_check", vec!["X"]),
        ("f_bb_vs_small", vec!["X", "B1"]),
        ("f_bb_vs_big", vec!["X", "B2"]),
        ("t_bb_first", vec!["X", "B1", "C", t]),
        ("t_btn_vs_check", vec!["X", "B1", "C", t, "X"]),
        ("t_bb_vs_bet", vec!["X", "B1", "C", t, "X", "B1"]),
    ];
    let nodes: Vec<Value> = specs.iter().map(|(id, p)| dump(&mut game, id, p, start_pot)).collect();
    let res = json!({"flop": flop, "turn": turn, "spot": "BTN vs BB SRP 100bb",
                     "exploitability_pct_pot": r3(100.0 * expl / start_pot as f32), "nodes": nodes});
    std::fs::write(out, serde_json::to_string(&res).unwrap()).unwrap();
    eprintln!("wrote {}", out);
    let nh: usize = std::env::var("HANDS").unwrap_or("0".into()).parse().unwrap();
    if nh > 0 {
        let seed = flop.bytes().fold(1469598103934665603u64, |h, b| (h ^ b as u64).wrapping_mul(1099511628211));
        let hands = hand_scripts(&mut game, nh, seed);
        let hout = out.replace(".json", ".hands.json");
        std::fs::write(&hout, serde_json::to_string(&json!({"flop": flop, "spot": "BTN vs BB SRP 100bb",
            "exploitability_pct_pot": r3(100.0 * expl / start_pot as f32), "hands": hands})).unwrap()).unwrap();
        eprintln!("wrote {}", hout);
    }
}
