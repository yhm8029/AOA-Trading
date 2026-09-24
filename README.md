# AOA Whale Viewer

**고래가 진입하고 청산한 바로 그 캔들을, 거래량과 함께 보는 로컬 연구 앱입니다.**

[![CI](https://github.com/yhm8029/AOA-Trading/actions/workflows/ci.yml/badge.svg)](https://github.com/yhm8029/AOA-Trading/actions/workflows/ci.yml)

TradingView 계정이나 유료 요금제 없이 사용합니다. Lightweight Charts™로 실제 OHLCV를 표시하고, 기존 AOA 데이터의 주문 끝점을 해당 캔들에 연결합니다. 가짜 캔들·생성형 이미지·자동매매 기능은 없습니다.

## 빠른 시작 — Windows

1. 이 저장소에서 **Code → Download ZIP**으로 내려받고 압축을 풉니다.
2. **`start_windows.bat`를 실행**합니다. Python 3.10 이상이 필요합니다. 기존 AOA 수집기를 돌린 PC라면 같은 Python을 사용할 수 있습니다.
3. 첫 실행에만 고정 버전 차트 라이브러리를 받아 무결성을 확인합니다. 이후 브라우저가 `http://127.0.0.1:8765`로 열립니다.
4. **데이터 가져오기 → `AOA_candle_analysis.zip`**을 선택합니다. `(1)`이 붙은 파일도 동일하게 지원합니다. ZIP을 수동으로 풀 필요 없습니다.
5. **`AOA_XBTUSD_2021_events.csv`**를 추가하면 기존 연구 분류·수량·평균단가·순손익을 함께 확인할 수 있습니다. 기존 `order_context.csv`, 대표사례 타임라인, 캔들 특징 CSV도 보완 입력입니다.
6. 왼쪽 **포지션 `3086` 또는 `3099`**을 검색해서 클릭하고, **1분/5분/15분/1시간/4시간/일봉**을 바꿔 봅니다. 오른쪽 주문을 클릭하면 그 캔들로 바로 이동합니다.

> Python이 없으면 [공식 Python 설치 페이지](https://www.python.org/downloads/windows/)에서 설치하세요. 이 앱 자체의 Python 패키지 설치는 없습니다. 콘솔을 닫으면 서버도 종료됩니다. 독립 실행형 EXE는 현재 포함하지 않습니다.

macOS/Linux: `./start_unix.sh` 또는 `python3 run.py`.
포트 충돌: `python run.py --port 8766`.
다른 데이터 폴더: `python run.py --data-dir "D:\\AOA-local"`.

## 화면 구성

- **왼쪽**: 계약/연도/롱·숏/승패/포지션 ID 검색, 이전·다음 포지션.
- **가운데**: 실제 캔들 + 같은 시간축의 거래량, 마우스 확대·이동, 날짜 점프, 구간 이동, PNG 저장.
- **캔들 위**: 숏 진입·추가 / 롱 감량. **캔들 아래**: 롱 진입·추가 / 숏 감량. 동일 캔들의 같은 종류 주문은 묶고 수량 합계를 표시합니다.
- **오른쪽**: 주문 첫·마지막 체결시각, 실제 첫 가격, 산술/역수가중 평균가격, 주문 구간 전후 수량, 평균단가 대비 가격 변화, 사전 시장 특징, 출처.
- **메모**: 포지션별 연구 태그와 메모를 SQLite에 저장합니다. 브라우저 새로고침 후에도 유지됩니다.
- **봉 단위 복기**: 다음 봉으로 진행하거나 재생. 미래 OHLCV·주문·최종 손익·주문 전체 수량·사후 CUT/FLIP 분류를 숨깁니다. 개별 틱/미체결 주문을 재생하는 기능은 아닙니다.

## 중요한 데이터 구분

**BitMEX 실제 체결가격과 Binance 현물 캔들은 다른 데이터입니다.** 시점으로 마커를 연결하며 가격을 강제로 일치시키지 않습니다. 캔들 밑 거래량은 Binance 해당 현물 거래쌍의 기준자산 거래량입니다. 고래 본인의 체결량이나 BitMEX 거래량이 아닙니다.

- 원문 거래시각을 **잠정 UTC**로 해석합니다. KST 스위치는 표시만 +9시간 합니다.
- 주문별 첫·마지막 끝점은 하나의 주문입니다. 두 번 세지 않습니다.
- 표시 수량과 평균가격은 **분할체결 주문 전체의 사후 합계**일 수 있습니다.
- 첫 체결 전 수량과 마지막 체결 뒤 수량 사이에는 다른 주문이 섞일 수 있습니다. 따라서 이 데이터를 누적해서 정확한 실시간 보유량 그래프로 만들지 않습니다.
- 기본 분류는 원장 역할·확인된 수량·평균단가·명시 주문유형을 씁니다. 이전 Pine의 `TACTICAL_CUT`/`FLIP`은 **가설 옵션**으로 별도 보존합니다. 미래 최대 수량 5%/3% 기준을 실시간 신호에 쓰지 않습니다.
- `익절*`, `손실감량*`은 **당시 평균단가 대비 가격** 기준입니다. 수수료·펀딩을 차감한 주문 순손익이 아닙니다. 실제 Stop 주문유형이 없으면 손실 감량을 Stop이라고 부르지 않습니다.
- 현재 제공된 표에 없는 PnL·수량·가격·캔들은 **미확보**로 표시합니다. 0이나 가상 값으로 채우지 않습니다.

## 캔들 데이터가 비어 있을 때

`AOA_candle_analysis.zip`의 원본 분봉은 **주문 주변을 잘라 모은 데이터**이므로 긴 보유 구간 전체가 연속적이라고 보장하지 않습니다.

1. 이미 보관한 `AOA_market_data.zip`이나 Binance 월별 `BTCUSDT-1m-YYYY-MM.zip`을 가져옵니다. 앱이 실제 로컬 분봉을 읽습니다.
2. 또는 원하는 기간으로 이동한 뒤 **데이터 가져오기 → 현재 차트 구간의 실제 1분봉 받기**를 누릅니다. 클릭할 때만 Binance 공개 API에서 받으며, 주문 정보는 전송하지 않습니다.
3. 수동 다운로드 범위는 한 번에 **20,000분 이내**입니다. 더 넓으면 시간대를 낮추거나 월별 ZIP을 사용하세요. 418/451 등 접근 제한은 우회하지 않고 중단합니다.

누락된 1분이 있는 5분/1시간봉은 부분 합계로 만들지 않습니다. **전체 상위 봉을 빈칸**으로 두고 누락 개수를 알립니다. 중복 분봉이 서로 다르면 양쪽 모두 격리합니다.

차트 한 화면의 요청은 성능상 **4,000봉**으로 제한하지만 전체 과거 보관 기간은 제한하지 않습니다. 날짜·주문 클릭으로 2018~2021 어느 시점이나 바로 요청합니다. 자동 무한 스크롤은 없고 **◀ 구간 / 구간 ▶**로 추가 구간을 요청합니다.

## 어떤 파일을 넣는가

| 입력 | 용도 |
|---|---|
| `AOA_candle_analysis.zip` | 정규화된 1분봉 + 주문 끝점. 가장 먼저 권장 |
| `order_context.csv` | 첫/마지막 주문 시각·방향·주문 ID와 사전 시장 특징 |
| `AOA_XBTUSD_2021_events.csv` 또는 월별 CSV | 기존 연구 분류, 평균단가·순손익 보완 |
| `AOA_대표사례_주문타임라인.csv` | 주문 구간, 실제 평균가격, 전후 수량, Stop 조건 보완 |
| `order_candle_features.csv` | 캔들 모양·사전 거래량 특징 보완. post_*는 적재하지 않음 |
| `AOA_market_data.zip` / 월별 1분 ZIP | 더 넓은 실제 시장 분봉 |

`aoa_public_...zip` 원본 개별 execution 행을 새 포지션 원장으로 복원하는 엔진은 **이번 버전에 포함하지 않았습니다.** 기존에 검산된 가공 주문 끝점을 입력합니다. 처음 보는 CSV는 지원 헤더인지 검증하고, 모르는 형식을 임의 추측해서 매매로 만들지 않습니다. ZIP 안에서 지원하지 않는 보조파일은 목록에 기록하고 건너뜁니다.

## 로컬 데이터와 보안

기본 저장소는 `local-data/viewer.sqlite3`입니다. 원본은 수정하지 않고 읽으며, 업로드 임시 복사본은 가져오기 이후 제거합니다. SHA-256으로 동일 파일 재가져오기를 막습니다. 메모까지 백업하려면 앱을 종료한 뒤 `local-data/` 폴더 전체를 복사하세요.

서버는 **127.0.0.1에만 바인딩**, Host/Origin 검사와 변경 요청 토큰을 사용합니다. 원장·시장 ZIP·개인 메모는 `.gitignore` 대상이며 GitHub에 포함하지 않습니다. 외부 계정/API 키, 매매 주문, 광고·분석 추적, 임시 파일 공유 사이트 업로드는 없습니다. 처음 실행할 때 차트 패키지를 받는 네트워크와 사용자 요청 공개 시세 다운로드만 있습니다.

## 검증과 배포

```bash
python -m unittest discover -v
node --test tests/test_frontend.mjs
python scripts/prepare_vendor.py
python -m pip install playwright==1.55.0
python -m playwright install chromium
python -m tests.browser_test
python scripts/build_package.py
```

GitHub Actions는 Windows/Linux × Python 3.11/3.13, 프런트 로직, Chromium에서 차트/마커/시간봉/메모/복기/PNG 저장을 검사합니다. `tests/seed_ci.py`는 **합성 테스트 전용**이고 실제 고래 거래로 표시하지 않습니다. CI 성공 후 Actions의 `AOA-Viewer-runtime-and-test-evidence` 아티팩트에서 차트 라이브러리가 포함된 실행 ZIP과 테스트 화면 PNG를 받을 수 있습니다. 소스 ZIP과 달리 이 실행 ZIP은 라이브러리 최초 다운로드도 이미 포함합니다.

CI 통과는 제공된 4년 전체 원장을 다시 검산했다는 뜻이 아닙니다. 실제 파일 전수 가져오기 결과는 사용자 PC의 **검증 기록**에서 확인하세요.

## 문서

- [기능명세](docs/FEATURES.md)
- [설계·데이터 계약](docs/ARCHITECTURE.md)
- [구현 상태와 후속 작업](docs/STATUS.md)
- [연구 원칙](docs/RESEARCH.md)
- [Codex 인수인계](docs/CODEX_HANDOFF.md)

## 출처 / 라이선스

차트: [TradingView Lightweight Charts™ 5.0](https://tradingview.github.io/lightweight-charts/docs/5.0), [pane API](https://tradingview.github.io/lightweight-charts/tutorials/how_to/panes).
시세: [Binance Market Data Only API](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md).

앱 코드는 MIT. 차트 라이브러리는 Apache 2.0이며 별도 저작권·NOTICE를 보존합니다. AOA 원본 거래자료와 시장자료의 권리는 이 저장소의 MIT 라이선스로 재허가되지 않습니다. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)를 참고하세요.
