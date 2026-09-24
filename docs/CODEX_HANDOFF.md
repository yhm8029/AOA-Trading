# Codex 인수인계

## 사용자 목표
TradingView의 오래된 1분/5분봉 조회 제한 없이 실제 고래 포지션을 클릭해 캔들 위 진입/감량과 하단 거래량을 연구한다. 가짜 그림, 텍스트만의 보고서, 사용자가 수년치를 스크롤하는 UX는 금지.

## 먼저 할 일
1. README와 `docs/ARCHITECTURE.md`, `docs/RESEARCH.md`를 읽는다.
2. CI 결과와 테스트를 확인한다. `python -m unittest discover -v`, `node --test tests/test_frontend.mjs`.
3. 사용자 PC의 `AOA_candle_analysis.zip`과 `AOA_XBTUSD_2021_events.csv`를 **로컬에서만** 가져온다.
4. 실제 포지션 3086,3099와 CSV 원장 첫/마지막 시각을 수동 대조한다. 2018~2020도 전체 context가 적재된 경우만 지원된다고 말한다.
5. 스크린샷/집계 기반으로 통과 근거를 추가한다. CI 합성 데이터와 실제 데이터 검사를 혼동하지 않는다.

## 우선 개선
- `order_candle_features.csv` 현재 헤더 차이를 실제 파일과 대조하여 alias 추가.
- 원본 `orders_deep.csv` / `episodes_deep.csv`의 실제 헤더 확인 후 엄격한 별도 adapter 작성.
- 주문 그룹의 구간 중첩을 해소하는 정확한 개별 execution 기반 보유량 곡선.
- 마커가 많은 시간봉에서 위치별 요약/툴팁 UX.
- 무한 스크롤과 분봉 range cache; 동시에 요청한 결과의 역전 방지 유지.
- 독립 Windows EXE 포장 (서버 loopback·보안 검사 유지).

## 변경 금지 원칙
원본/메모를 GitHub에 커밋하지 않는다. 누락 캔들을 만들어 채우지 않는다. 손실 Exit를 전부 Stop으로 바꾸지 않는다. 그룹 최종수량을 first fill 순간값으로 보지 않는다. 실제로 없는 자동매매·검증완료 기능을 문서에 추가하지 않는다.
