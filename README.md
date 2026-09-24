# AOA Whale Viewer v0.2

**고래의 실제 진입·추가·감량을 실제 캔들과 거래량 위에서 보는 로컬 연구 앱.**

[![CI](https://github.com/yhm8029/AOA-Trading/actions/workflows/ci.yml/badge.svg)](https://github.com/yhm8029/AOA-Trading/actions/workflows/ci.yml)

TradingView 계정 없이 과거 차트를 탐색합니다. 차트 엔진은 공식 Lightweight Charts이며 TradingView.com 사이트 자체가 아닙니다. 가짜 캔들·생성형 가격 이미지·거래소 로그인·자동매매는 없습니다.

## 기존 사용자 — 반드시 먼저 읽기

이번 버전은 **main의 `run.py` / `local-data/viewer.sqlite3`**를 유지하는 수정판입니다. 별도 `feat/whale-viewer-v1`의 다른 DB를 덮어쓰지 않습니다.

1. **기존 실행 콘솔에서 Ctrl+C로 앱을 종료**하고 브라우저 탭을 닫습니다.
2. 새 실행 ZIP을 풉니다. 프로그램 파일을 기존 앱 폴더에 덮어써도 됩니다.
3. **`local-data/` 폴더는 지우지 마세요.** 새 폴더에 설치했다면 종료 상태에서 기존 `local-data/` 전체를 새 앱 폴더로 복사합니다. 원본/메모 DB는 자동으로 유지됩니다.
4. `start_windows.bat` 실행 → 화면 상단 **v0.2.0** 확인. 여전히 v0.1이면 옛 서버가 실행 중입니다.
5. 기존 데이터는 다시 가져오지 않아도 됩니다. **누락 시세 자동 보완**이 켜져 있으면 현재 차트에 없는 분봉만 Binance 공개 API에서 받습니다. 개인 주문·메모는 외부로 보내지 않습니다.

[변경 내역과 계산 정의](docs/UPDATE_0_2.md)

## 처음 시작 — Windows

- Code → Download ZIP 또는 성공한 Actions의 `AOA-Viewer-v0.2-runtime-and-tests` 실행 패키지를 받습니다. Actions ZIP의 **`dist/AOA-Whale-Viewer.zip`**을 한 번 더 풉니다.
- **Python 3.10 이상**이 필요합니다. `start_windows.bat`를 더블클릭하면 로컬 브라우저 앱이 열립니다. Node.js나 Python 추가 패키지는 실행에 필요 없습니다. Python까지 포함한 독립 EXE는 아닙니다.
- 데이터 가져오기에서 `AOA_candle_analysis.zip`과 `AOA_XBTUSD_2021_events.csv`를 선택합니다. 파일명에 `(1)`이 붙어도 됩니다. 기존 월별 시장 ZIP, 컨텍스트 CSV, 대표사례 타임라인, 캔들 특징 CSV도 지원합니다.
- 포지션 ID를 선택한 뒤 오른쪽 주문을 클릭하면 해당 캔들로 바로 이동합니다.

소스 ZIP은 첫 실행에만 고정 버전 차트 라이브러리 다운로드가 필요합니다. Actions 실행 패키지는 라이브러리를 포함합니다.

```sh
python run.py
python run.py --port 8766
python run.py --data-dir "D:\\AOA-local"
```

macOS/Linux: `./start_unix.sh` 또는 `python3 run.py`. 종료: Ctrl+C.

## 화면에서 할 수 있는 것

| 기능 | 사용법 |
|---|---|
| 연도 선택 | 기본은 **첫 관측 진입 연도**. 전년도 이월 포함은 별도 체크. 목록과 차트가 함께 변경됨 |
| 시간봉 | 1m/5m/15m/1h/4h/1d. 같은 주문/날짜 anchor를 유지 |
| 캔들·거래량 | 같은 시간축. 확대/축소·드래그·날짜 이동·포지션 전체 보기 |
| 주문 마커 | 숏 증가 위/감량 아래, 롱은 반대. 같은 봉의 같은 종류는 묶음 |
| 마우스 호버 | 시가/고가/저가/종가, **봉 등락률 %, 전봉 대비 %, 고저폭 %, 거래량·RV20** |
| 주문 타임라인 | 선택 주문으로 이동, 이전/다음 주문, 감량 가격변화율 표시 |
| 복기 | 진입/선택 주문 직전 시작, 실제 완성 봉만 재생, 속도·이전/다음 봉·슬라이더 |
| 미래정보 차단 | 복기 시 미래 봉·최종 손익·집계수량·주문 종료시각·사후 분류 숨김 |
| 포지션 성과 | 감량 가격성과 참고 %, 원장 BTC 순손익, 입력 증거금 기준 참고 ROI |
| 시세 공백 보완 | 없는 1분봉만 요청·검증·캐시. 진행상황·중단·남은 공백 표시 |
| 연구 기록 | 포지션별 메모·태그 영속 저장, CSV/PNG 내보내기 |

## 퍼센트의 의미 — 혼동하지 마세요

**봉 등락률**: `(C/O−1)×100`. **전봉 대비**: `(C/직전 종가−1)×100`, 직전 봉이 없으면 미확보. **고저폭**: `(H−L)/O×100`.

**감량 가격성과***는 제공된 Exit 주문의 수량가중 방향환산 가격변화입니다. 그룹 평균/첫 가격과 주문 직전 평균단가를 비교하는 **참고 근사값**입니다. 분할체결 동안 평균단가가 변할 수 있고 제공된 주문이 일부일 수 있으므로 실제 전체 실현수익률이라고 부르지 않습니다. 사용된 감량 주문 수·수량 커버리지를 표시합니다.

**원장 순손익**은 입력 파일에 제공된 BTC 값만 사용합니다. **증거금 참고 ROI**는 사용자가 확인한 참고 증거금을 입력한 경우에만 계산합니다. 근거가 없으면 미확보이며 레버리지를 임의로 곱하지 않습니다. 변동 증거금·입출금·복리 계좌 수익률과 다릅니다.

XBTUSD 역계약의 손익을 선형 USDT 계약처럼 계산하지 않습니다. BitMEX 체결가와 Binance 시세를 섞어 정확한 체결손익을 만들지 않습니다.

## 차트가 비어 있거나 일부 구간이 없을 때

주문 주변만 추출한 캔들 ZIP에는 보유기간 전체가 없을 수 있습니다. 기본 **누락 시세 자동 보완**은 현재 요청한 구간에 없는 분만 공개 API에서 받습니다. 끄면 인터넷 요청 없이 기존 로컬 자료만 사용합니다. 수동 **이 구간 다시 보완**도 있습니다.

- 한 작업 최대 180일, 1,000분 이하 요청으로 나누고 이미 있는 분봉은 다시 받지 않습니다.
- 네트워크 대기 중 SQLite 쓰기 잠금을 잡지 않으며, 받은 페이지는 검증 후 저장합니다. 중단 후 재요청하면 남은 구간만 받습니다.
- API가 비어 있거나 거래소 장애/상장 전 기간/지역 제한이면 그대로 알립니다. 접근 제한을 우회하지 않습니다.
- 충돌 자료는 격리하며 자동으로 임의의 가격을 선택하지 않습니다.
- 빠진 분이 있는 상위 봉은 부분 봉으로 그리지 않습니다. 누락/불완전 개수와 보완 후 남은 공백을 표시합니다.
- 재생은 존재하는 실제 봉만 넘기고 건너뛴 시간 구간을 표시합니다. **건너뛰기 ≠ 누락 가격 복원**입니다.

## 입력과 보존

| 입력 | 역할 |
|---|---|
| `AOA_candle_analysis.zip` | 정규화 1분봉 + 주문 첫/마지막 끝점 |
| `order_context.csv` | 주문 ID·역할·시각·사전 특징 |
| `AOA_XBTUSD_2021_events.csv` / TradingView 패키지 | 기존 분류·수량·평균단가·포지션 순손익 보완 |
| `AOA_대표사례_주문타임라인.csv` | 평균체결가·전후 수량·Stop 조건 |
| `order_candle_features.csv` | 사전 캔들 특징 보완. post_*는 예측 입력으로 적재하지 않음 |
| `AOA_market_data.zip` / Binance 월별 1분 ZIP | 연속 원본 시장 시세 |

원본 `aoa_public_...zip` 개별 executions를 새로 전수 회계처리하는 엔진이나 XLSX 직접 가져오기는 이 버전 범위가 아닙니다. 그룹 끝점은 두 체결이 아니라 하나의 주문이며, 그 사이 타 주문이 섞일 수 있습니다. 이 끝점만으로 초 단위 보유량 경로를 만들지 않습니다.

기본 DB: `local-data/viewer.sqlite3`. 원본을 수정하지 않습니다. 백업은 앱을 종료한 뒤 **local-data 폴더 전체**를 복사하세요. 기존 메모와 주문을 유지하며 참고 증거금 테이블만 추가합니다.

서버는 127.0.0.1만 사용하고 Host/Origin·쓰기 토큰·엄격한 CSP를 적용합니다. 외부 계정 연결·추적·자동 업로드는 없습니다. 거래 파일과 메모는 GitHub/CI에 넣지 않습니다.

## 테스트

```sh
python -m unittest discover -v
node --check web/app.mjs
node --test tests/test_frontend.mjs tests/test_review_frontend.mjs
python scripts/prepare_vendor.py
python -m pip install playwright==1.55.0
python -m playwright install chromium
python -m tests.browser_test
python -m scripts.verify_public_market
python scripts/build_package.py
```

Windows/Linux Python 3.10/3.13, JS 회귀, Chromium 실제 클릭·호버·재생·시세 보완·메모·PNG 저장을 검사합니다. **거래 테스트는 합성 데이터**입니다. 별도 공개 시장 probe는 실제 Binance 2021-01-03 캔들의 작업 사본 공백을 API로 복원합니다. 이 검증과 사용자의 전체 ZIP 전수 가져오기는 다릅니다. 최신 CI 결과와 `public-market-probe.json`을 확인하세요.

## 문서 / 라이선스

- [v0.2 업데이트 및 계산 정의](docs/UPDATE_0_2.md)
- [기능과 현재 범위](docs/FEATURES.md)
- [설계](docs/ARCHITECTURE.md)
- [구현 상태](docs/STATUS.md)
- [연구 원칙](docs/RESEARCH.md)
- [Codex 인수인계](docs/CODEX_HANDOFF.md)

차트: [tradingview/lightweight-charts](https://github.com/tradingview/lightweight-charts). 공개 시세: [Binance market-data-only API](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md). UI 흐름 참고: [lightweight-charts-python](https://github.com/louisnw01/lightweight-charts-python).

앱 MIT, 차트 Apache-2.0. 저작권·NOTICE를 보존합니다. 원본 거래/시세자료를 이 저장소의 MIT로 재허가하지 않습니다. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
