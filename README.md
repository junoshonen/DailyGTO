# DailyGTO

하루 5문제 포커 GTO 퀴즈. 6max Cash 100bb, 솔버 계산 데이터 기반.

## 구조
- `index.html` — 사이트
- `data/questions.js` — 문제·차트 데이터 (보드를 추가하면 이 파일만 바뀜)
- `tools/solver` — 솔버 실행기 ([postflop-solver](https://github.com/b-inary/postflop-solver), AGPL-3.0)
- `tools/ranges` — 프리플랍 레인지 (BTN open, BB call vs BTN)
- `tools/build_questions.py` — 솔버 결과 → 문제·차트 데이터

## 데이터 만들기
```
cargo build --release --manifest-path tools/solver/Cargo.toml
FL_R="2.5x,4x,a" TU_R="3x,a" RI_R="a" tools/solver/target/release/dgsolve Ks7d2c raw/Ks7d2c.json solve 4h
python3 tools/build_questions.py raw/*.json > data/questions.js
```
