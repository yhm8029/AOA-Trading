# AOA Whale Viewer

**고래의 과거 거래를 실제 캔들 위에서 복기하는 로컬 연구 앱.**

포지션을 고르면 해당 기간으로 바로 이동합니다. 1분·5분·15분·1시간·4시간·일봉, 거래량, 진입/추가/감량 마커를 한 화면에서 확인합니다. TradingView.com 계정이나 유료 구독은 필요하지 않습니다. 차트 엔진은 공식 **TradingView Lightweight Charts 5.2.1**이며, TradingView.com 사이트 자체는 아닙니다.

> 이 앱은 과거 거래 **표시·복기 도구**입니다. 새로운 매수/매도 신호, 고래의 생각을 복제한 전략, 자동매매 프로그램이 아닙니다. 가짜 캔들과 샘플 매매를 실제 기록처럼 채워 넣지 않습니다.

## 가장 빠른 시작 — Windows

1. 저장소의 **Code → Download ZIP**으로 받거나, [Actions](https://github.com/yhm8029/AOA-Trading/actions)에서 성공한 실행의 `AOA-Whale-Viewer-...` 아티팩트를 받습니다. 아티팩트 안의 `dist/AOA-Whale-Viewer.zip`에는 차트 라이브러리도 포함됩니다.
2. ZIP을 **완전히 압축 해제**합니다. **Python 3.10 이상**이 설치되어 있어야 합니다.
3. `start_windows.bat`를 더블클릭합니다. 브라우저가 `http://127.0.0.1:8765`로 열립니다. 포트가 사용 중이면 다음 포트를 선택합니다.
4. **데이터 가져오기**에서 아래 두 파일을 선택합니다. 파일명 뒤의 `(1)`은 상관없습니다.
   - `AOA_TradingView_2021_Package.zip` 또는 `AOA_XBTUSD_2021_events.csv`
   - `AOA_candle_analysis.zip`
5. 가져오기가 끝나면 창을 닫고 포지션을 선택합니다. **#3086 / #3099** 빠른 선택 버튼은 해당 실제 데이터가 있을 때만 작동합니다.

GitHub 소스 ZIP은 **처음 한 번** 공식 차트 라이브러리 다운로드에 인터넷이 필요합니다. 이후 기존 로컬 데이터로 오프라인 사용 가능합니다. Python 패키지 설치, Node.js, API 키는 앱 실행에 필요하지 않습니다. Python 자체까지 포함된 설치형 EXE는 아닙니다.

macOS / Linux:

```sh
python3 app.py --open
```

수동 실행 / 포트 변경:

```sh
python app.py --open
python app.py --port 8870 --open
python app.py --import-file "C:\\Downloads\\AOA_candle_analysis(1).zip" --open
```

종료는 실행 터미널에서 **Ctrl+C**입니다. 실행 중인 터미널을 닫으면 서버도 종료됩니다.

## 화면과 사용법

| 위치 | 기능 |
|---|---|
| 왼쪽 | 계약·연도·롱/숏·최종 손익 필터, Episode 검색, 이전/다음 포지션 |
| 가운데 | 캔들 + 거래량, 시간봉 전환, 날짜 점프, 앞/뒤 구간 이동, 전체 포지션 보기 |
| 캔들 위/아래 | 실제 주문 시각이 포함된 캔들의 진입·추가·감량 마커. 한 봉에 겹치는 주문은 묶음 표시 |
| 오른쪽 | 주문 타임라인, 첫 체결가와 그룹 VWAP, 그룹 수량, 수량 관측치, 스톱 발동 가격, 출처·분류 근거 |
| 연구 메모 | 포지션별 관측 사실 / 가설 / 반례 저장. 다른 창에서 동시 수정하면 충돌 감지 |
| 내보내기 | 현재 차트 PNG, 선택 포지션의 표시 이벤트 CSV |

**주문을 클릭하면 해당 캔들로 바로 점프합니다.** 옛 날짜까지 마우스로 수천 번 스크롤할 필요가 없습니다. 긴 포지션은 작은 구간부터 읽고, ‘전체 포지션’은 필요한 경우 시간봉을 올려 보여줍니다. 요청당 최대 10,000봉은 브라우저 부하를 위한 **창 크기 제한**이며 과거 특정 연도를 못 보는 제한이 아닙니다.

표시 색: 롱 증가 초록 / 숏 증가 빨강 / 익절 파랑 / 추가분 철회 후보 보라 / STOP 진한 빨강 / 종료 회색 / 방향 전환 후보 주황.

## 가지고 있는 파일 그대로 사용

| 입력 | 처리 |
|---|---|
| 연간/월별 AOA 이벤트 CSV, TradingView 패키지 ZIP | 기존 분류·수량·첫 가격·VWAP·Episode 정보를 가져옴. 연간/월별 중복은 동일 주문 ID로 합침 |
| `AOA_candle_analysis.zip` | 실제 `candles_1m.csv.gz`, 끝점 이벤트, 내부 `order_context.csv` 등을 스트리밍 처리 |
| `order_context.csv` | first/last 끝점을 같은 주문 그룹으로 연결. 평균단가나 방향 전환 근거가 없는 경우 **증가/감량**으로만 표시 |
| `order_candle_features.csv` | 주문의 사전 특징을 보충. 특징값으로 원본 캔들을 만들어 내지 않음 |
| `candles_1m.csv.gz` / 동일 스키마 CSV | 실제 OHLCV를 로컬 SQLite에 저장 |
| `AOA_market_data.zip` / Binance 월별 1분 ZIP | 한 단계 중첩된 월별 ZIP의 원시 12열 CSV 지원 |

**직접 지원하지 않는 입력:** 원본 `aoa_public_...zip` 안의 140만 개 실행 조각을 신규 재정산하는 기능, `orders_deep.csv`/`episodes_deep.csv`의 미확인 변종, 한국어 타임라인만으로 방향을 추측하는 기능, XLSX 가져오기. 해당 자료는 연구 근거로 별도 보관합니다. v0.1은 이미 만든 주문 컨텍스트와 이벤트 파일을 사용합니다.

2018~2021 주문 위치는 컨텍스트에 기록된 범위에서 읽을 수 있습니다. **상세 TP/CUT/FLIP 명칭은 분류 이벤트를 제공한 연도/포지션에 한해서만 표시합니다.** 2021 전체 데이터 또는 모든 원본 파일에 대한 이 세션의 재정산을 완료했다고 주장하지 않습니다.

## 데이터가 없는 구간

분봉이 없는 구간은 빈 공간으로 표시합니다. 상위 시간봉은 해당 구간의 1분봉이 **전부** 있어야 표시합니다. 예를 들어 5개 중 1개가 없는 5분봉을 나머지 4개로 그리지 않습니다. 동일 시각의 OHLCV가 충돌하면 임의로 한쪽을 택하지 않고 그 분을 제외합니다.

선택한 범위가 비어 있으면:

- 로컬 월별 원본 ZIP을 추가하거나,
- **‘이 구간 공개 분봉 보완’**을 누릅니다. 확인 후 Binance 공개 API에 **거래쌍과 시간 범위만** 요청합니다. 주문·계좌·메모는 전송하지 않습니다.

공개 API 요청은 한 번에 32일 이내입니다. 거래소의 데이터 공백·상장 전 기간·지역 제한·요청 제한은 임의 우회하지 않습니다. 로컬 자료와 새로 받은 자료가 충돌하면 충돌 분은 계속 제외됩니다.

## 반드시 알아야 할 해석상의 구분

1. **차트는 Binance 현물, 체결은 BitMEX입니다.** 마커는 시각을 맞추고 캔들 위/아래에 표시합니다. BitMEX 체결가를 Binance 가격처럼 강제로 맞추지 않습니다. 실제 가격 참고선은 선택 사항이며 기본적으로 꺼져 있습니다.
2. **그룹 총량은 첫 체결 순간의 수량이 아닙니다.** 한 주문이 여러 분에 걸쳐 체결되거나 다른 주문과 섞일 수 있습니다. 첫/마지막 관측 수량 차이로 임의의 완전한 계좌 수량 경로를 만들지 않습니다.
3. **CLOSE에 잔량이 남으면 ‘대부분 정리’로 표시합니다.** 원본 분류는 상세 화면에 보존합니다. CUT·FLIP도 기존 연구의 가설임을 표시합니다.
4. **평균단가 대비 가격 차이 ≠ 실현 BTC 손익.** 수수료·펀딩·역계약 손익을 재계산한 값이 아닙니다. 포지션 최종 손익은 입력 파일에 일관되게 제공된 경우에만 사용합니다.
5. **직전 완성 분봉과 체결 분 최종 거래량을 분리합니다.** 체결 분 전체 거래량·OHLC는 사후 정보입니다. 메모나 차트 복기에서 당시에 전부 알았던 것처럼 사용하지 않습니다.
6. **원문 시각은 잠정 UTC**입니다. 한국시간 옵션은 라벨만 바꾸며 데이터의 timestamp를 변조하지 않습니다.
7. 기존 Pine의 ‘최대 수량의 5%’ 등은 **미래 최대값을 이용한 사후 라벨**입니다. 앱은 이를 실시간 예측 신호로 사용하지 않습니다.

더 자세한 정의: [데이터 계약](docs/DATA_CONTRACTS.md), [설계와 구현 현황](docs/ARCHITECTURE.md), [검증 범위](docs/VERIFICATION.md).

## 개인정보와 저장 위치

모든 거래·캔들·메모·업로드는 기본 `data/`에 저장합니다. **이 폴더 전체를 백업**하면 됩니다. 앱을 완전히 종료한 뒤 복사하세요.

- `data/aoa.sqlite3`: 주문, 캔들, 메모, 데이터 검사 기록
- `data/inbox`: 업로드한 파일 사본. 원본 업로드 파일을 수정하지 않음
- `data/market-downloads`: 사용자가 요청한 공개 시장 API 응답
- `web/vendor`: 공식 차트 라이브러리 캐시

GitHub에는 앱 코드와 **합성 테스트**만 저장합니다. 자동 업로드·원격 분석·추적 스크립트·거래소 로그인은 없습니다. 서버는 `127.0.0.1`에만 바인딩하며 Host/Origin 검사와 쓰기 토큰을 사용합니다. 인터넷에 공개 배포하는 서버로 설계하지 않았습니다.

## 개발 및 테스트

```sh
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/core.test.mjs
python prepare_assets.py
python -m pip install playwright==1.63.0
python -m playwright install chromium
python tests/browser_smoke.py
python scripts/package.py
```

Node와 Playwright는 **개발 테스트용**이며 일반 앱 실행 의존성이 아닙니다. CI는 Ubuntu/Windows의 Python 3.10·3.13, 실제 Chromium 화면, ZIP 가져오기·캔들/거래량·마커·시간봉·메모·내보내기를 검사합니다. 합성 테스트 통과와 사용자의 전체 데이터 검증은 별개입니다. Actions의 실제 성공 여부를 확인하세요.

## 참고한 GitHub 코드

- [tradingview/lightweight-charts](https://github.com/tradingview/lightweight-charts): 실제 차트 엔진. v5 시리즈, pane, markers, 날짜/좌표 처리와 공식 예제 참고.
- [louisnw01/lightweight-charts-python](https://github.com/louisnw01/lightweight-charts-python): CSV 차트, 시간봉 선택, marker/table UI 흐름 참고. Python 데스크톱 래퍼를 복사하지 않고 가벼운 로컬 HTTP + 공식 JS 라이브러리로 구현.

자체 작성 코드는 MIT, Lightweight Charts는 Apache-2.0과 NOTICE를 따릅니다. [제3자 고지](THIRD_PARTY_NOTICES.md)를 확인하세요.
