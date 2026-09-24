# 참고 코드와 공식 문서

## 실제 의존성

- TradingView / Lightweight Charts: https://github.com/tradingview/lightweight-charts
- 사용 버전: 5.2.1. https://tradingview.github.io/lightweight-charts/docs/release-notes
- v5 공식 사용 가이드: https://github.com/tradingview/lightweight-charts/blob/master/.github/skills/lightweight-charts/SKILL.md
- `createSeriesMarkers`: https://tradingview.github.io/lightweight-charts/docs/api/functions/createSeriesMarkers
- 차트 pane: https://tradingview.github.io/lightweight-charts/docs/panes

주요 반영 사항: UTC seconds와 ms 구분, 단조 증가 timestamp, 1개 chart 안의 price/volume panes, 존재하는 bar time으로 marker mapping, datetime formatter만으로 시간대 변경, `createSeriesMarkers` v5 API, 로컬 버전 고정 자산, attribution.

## 구조 참고 (코드 복사/의존성 없음)

- louisnw01 / lightweight-charts-python: https://github.com/louisnw01/lightweight-charts-python
  - CSV 데이터의 차트 표시, timeframe selector, marker, table interaction 흐름 참고.
  - 로컬 앱에서 별도 Qt/WebView 패키지 설치를 줄이기 위해 해당 Python wrapper 대신 표준 HTTP 서버 + 공식 JS API를 선택.

## 공개 시장 보완

- Binance Spot API market-data-only: https://developers.binance.com/docs/binance-spot-api-docs/faqs/market_data_only
- Binance public dataset: https://github.com/binance/binance-public-data
- API는 전체 거래량/가격 맥락용. 실제 BitMEX 체결과 다른 시장이며 비용 포함 전략 성과가 아니다.

## 테스트/CI

- https://github.com/microsoft/playwright-python
- https://github.com/actions/checkout
- https://github.com/actions/setup-python
- https://github.com/actions/upload-artifact

과거 대화의 가격·통계는 라이브러리의 예제 가격으로 대체하지 않는다. 이 참고 목록은 실제 트레이더가 사용한 매매법의 근거 목록이 아니다.
