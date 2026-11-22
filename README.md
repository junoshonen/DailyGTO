# DailyGTO

하루 10핸드 포커 GTO 트레이너. 한 핸드를 플랍→턴→리버까지 플레이하고 매 결정을 채점. 6max Cash 100bb, 솔버 계산 데이터 기반.

## 구조
- `index.html` — 사이트
- `data/hands/` — 핸드별 데이터 (보드를 추가하면 이 폴더만 바뀜)
- `tools/solver` — 솔버 실행기 ([postflop-solver](https://github.com/b-inary/postflop-solver), AGPL-3.0)
- `tools/ranges` — 프리플랍 레인지 (BTN open, BB call vs BTN)
- `tools/build_hands.py` — 솔버 결과 → 핸드·차트·해설 데이터

## 데이터 만들기
```
cargo build --release --manifest-path tools/solver/Cargo.toml
HANDS=120 FL_R="2.5x,4x,a" TU_R="3x,a" RI_R="a" tools/solver/target/release/dgsolve Ks7d2c raw/Ks7d2c.json solve
python3 tools/build_hands.py raw/*.hands.json --out data/hands
```
