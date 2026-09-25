# v0.4.1 잔고 형식 수정

잘린 timestamp 때문에 시드가 미연결되던 문제를 수정했습니다. 새 폴더에서 실행 후 기존 wallet CSV를 한 번 다시 선택하세요. 원본 날짜와 금액·잔고 연결을 검산하여 이전 기록일 마감 잔고를 참고값으로 사용합니다. 정확한 주문 직전 시드로 표시하지 않습니다. 자세한 사용법: [v0.4.1 안내](docs/RELEASE_v0.4.1.md).

# v0.4.0 · 시드 비중 추가

[업데이트·잔고 연결·계산 한계](docs/RELEASE_v0.4.0.md)

# AOA Whale Viewer v0.3.2

실제 고래 주문을 캔들·거래량 위에 표시하고, 대응 근거와 포지션 최종 성과를 복기하는 로컬 연구 앱입니다. 차트 엔진은 TradingView 공식 Lightweight Charts이며 TradingView.com 사이트 자체가 아닙니다.

**[검증된 실행 ZIP](https://github.com/yhm8029/AOA-Trading/releases/download/v0.3.2/AOA-Whale-Viewer.zip)** · **[이번 업데이트 안내](docs/RELEASE_v0.3.2.md)**

## 실행 및 기존 데이터 유지

Python 3.10 이상이 필요합니다. 실행 ZIP을 새 빈 폴더에 풀고 `start_windows.bat`를 실행합니다. 처음 폴더 선택 창에서 기존 AOA 앱 또는 `local-data` 폴더를 고르면 SQLite backup으로 주문·캔들·메모 사본을 가져옵니다. 기존 데이터는 삭제하지 않습니다. 자동으로 열리는 **새 탭의 v0.3.2**를 사용합니다. 옛 포트가 점유되어도 다른 로컬 포트로 실행하며 실행 폴더·버전·프로세스를 확인합니다.

소스 Code ZIP은 첫 실행에만 차트 라이브러리 다운로드가 필요합니다. Releases 실행 ZIP에는 라이브러리가 포함됩니다. Node.js나 추가 Python 패키지는 일반 실행에 필요하지 않습니다. 독립 EXE가 아니라 로컬 웹앱입니다.

## 기존 주문은 있는데 손익만 미확보인 경우

앱의 **손익자료 연결 / 보완**에서 이미 가진 자료를 한 번 다시 선택합니다. 업데이트만으로 예전에 건너뛴 파일 내용을 복원할 수는 없습니다.

가장 명확한 연결:
1. **AOA_거래분석_2018-2021.xlsx**: `포지션` 시트의 순손익·수수료·펀딩·수량·종료시각을 연결합니다. 파일명에 `(1)`이 있어도 됩니다.
2. **AOA_XBTUSD_2021_events.csv** 또는 TradingView 패키지: 2021년 주문 평균가격·보고된 최종 손익을 기존 주문 ID에 연결합니다.
3. **AOA_candle_analysis.zip** / 기존 분석 ZIP: 안의 명시적 BTC 단위 `episodes.csv`, `orders.csv`를 다시 읽습니다. 주문의 역수가중가격이 있으면 분모를 정확하게 합산할 수 있습니다. 지원하지 않는 성과 열은 실제 헤더와 함께 검증 기록에 남깁니다.

이미 가져온 파일도 새 성과 파서로 재처리합니다. 기존 시세·메모는 보존하고 주문 ID 기준으로 중복을 합칩니다. 새 시세를 다시 수집할 필요는 없습니다. XLSX는 저장된 값만 읽으며 수식·매크로·외부 링크를 실행하지 않습니다.

## 주요 기능

| 기능 | 내용 |
|---|---|
| 차트 | 1m·5m·15m·1h·4h·일봉, 거래량, 등락률 호버, 시간대 UTC/KST |
| 주문 | 최초 진입·추가·감량·청산 마커, 주문으로 이동, 같은 봉 주문 그룹 |
| 해설 | 관측 사실·가능한 해석·반대 근거·자료 한계; 로컬 규칙 기반 |
| 복기 | 선택 주문 직전부터 재생, 배속, 주문 시 자동 정지, 미래 정보 숨김 |
| 최종 결과 | 순손익률 %·순손익 BTC·비용 구성, 좌측 목록과 마지막 청산 봉 표시 |
| 성과 공개 | 복기에서는 마지막 체결이 끝난 후에만 최종 성과를 공개 |
| 누락 시세 | 실제 공개 분봉을 보완하고 상위 봉 재집계; 보간 없음 |
| 기록 | 메모·태그, PNG·주문 CSV·성과/해설 JSON 저장 |

## 수익률은 무엇을 나눈 값인가

**최종 순손익 BTC ÷ 누적 진입 계약가치 BTC × 100**입니다. XBTUSD의 계약가치는 각 진입·추가 체결에 대한 `수량 / 가격`의 합이며, 역수가중 평균가격이 있으면 주문별 `수량 / inverse_vwap`를 합산합니다. 재진입도 다시 분모에 포함합니다.

**증거금 수익률이나 계좌 수익률이 아닙니다.** 레버리지를 임의로 곱하지 않습니다. 원장 수량과 분모가 검증된 계산과, 산술평균가격 등을 사용한 **≈ 참고값**을 구분합니다. 알려진 수량 누락·잘못된 계약/시각 연결·손익 충돌·미종료 상태에서는 최종 % 계산을 보류합니다.

가격손익 − 거래수수료 − 펀딩비 = 순손익. 음수 수수료/펀딩은 수취입니다. 비용이 없으면 0으로 꾸미지 않습니다. 명시적 BTC 분모가 없는 다른 계약에 XBTUSD 산식을 적용하지 않습니다.

## 자료와 개인정보

BitMEX 실제 체결가격과 Binance 현물 시세는 별도입니다. Binance 거래량은 BitMEX 거래량이 아닙니다. 원문 시각은 잠정 UTC입니다. 해설은 트레이더의 확인된 의도가 아닌 연구 가설입니다. RSI/MACD나 임의의 매매 신호를 붙이지 않습니다. 가짜 가격·주문·증거금은 생성하지 않습니다.

서버는 loopback만 사용합니다. 원본 거래·로컬 DB·메모·키는 GitHub에 올리지 않습니다. 공개 시세 요청에 개인 주문·메모를 전송하지 않습니다. 직접 원본 execution ZIP을 회계 처리하는 엔진은 아닙니다.

## 테스트

GitHub Actions: Windows/Linux Python 3.10·3.13, JavaScript 회귀, Chromium 5종, 배포 ZIP의 한글/공백 경로 실행과 기존 데이터 복사/포트 충돌 검사. 테스트 거래는 명시적인 **합성 자료**이며 사용자 전체 거래 ZIP 전수 검산과 다릅니다. 실제 공개 시세 보완 probe는 별도 보고됩니다.

```
python -m unittest discover -v
node --test tests/test_frontend.mjs tests/test_review_frontend.mjs tests/test_study_frontend.mjs tests/test_pnl_frontend.mjs
python scripts/prepare_vendor.py
python -m tests.browser_pnl_test
python scripts/build_package.py
```

## 문서 / 라이선스

[설계](docs/ARCHITECTURE.md) · [연구 원칙](docs/RESEARCH.md) · [v0.3.2 변경점](docs/RELEASE_v0.3.2.md) · [실행 확인/업데이트](docs/RELEASE_v0.3.1.md)

차트: [tradingview/lightweight-charts](https://github.com/tradingview/lightweight-charts). UI 흐름 참고: [lightweight-charts-python](https://github.com/louisnw01/lightweight-charts-python). 앱 MIT, 차트 Apache-2.0. 저작권·NOTICE 유지. 원본 거래/시세 자료를 앱 라이선스로 재허가하지 않습니다. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
