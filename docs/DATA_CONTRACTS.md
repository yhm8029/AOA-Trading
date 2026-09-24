# 데이터 계약과 해석 규칙

## 우선순위

원본 거래 기록이 분석의 기준이지만 이 뷰어가 새로 실행 조각을 재정산하지는 않는다. 현재 입력은 기존 가공 CSV다. 사용자의 원본 파일은 손대지 않는다. 정규화 이벤트는 우선순위 100, 주문 컨텍스트/특징은 50으로 병합한다. 원본 사실과 기존 연구 분류가 서로 다르면 후자를 사실로 격상하지 않는다.

## 주문 키

`symbol | episode_id | source_orderid | raw_role`의 SHA-256 앞 28자리. `Entry`와 `Exit`를 별도 키로 두어 같은 주문 ID가 포지션을 반대로 넘길 때 데이터가 소실되지 않게 한다. `first/last`를 두 번의 독립 거래로 세지 않는다.

## 지원 이벤트 CSV

`episode_id,event_time_utc,event,direction,qty,bitmex_vwap,bitmex_first_fill,qty_before,qty_after,avg_basis_before,episode_max_qty,stop_trigger,episode_net_pnl_btc,classification_reason,source_orderid`

`symbol`이 없는 기존 XBTUSD 이벤트 파일은 `bitmex_vwap` 스키마에서만 XBTUSD로 해석한다. 새 데이터에서는 symbol을 명시하는 것이 원칙이다. `event_time_kst`는 기준 timestamp로 사용하지 않는다. `directional_dev_from_basis`처럼 미리 계산한 수익률을 실제 BTC 손익으로 해석하지 않는다.

## 지원 컨텍스트 CSV

`ep_id,symbol,role,direction,orderid,phase,event_time_assumed_utc,execution_price,qty,reference_pair,pre_*`

`qty`가 없는 특징 파일은 `order_group_qty_audit_only`를 사용한다. `pre_*`만 사전 특징으로 보관하며 `post_*`는 진입 설명에 자동 투입하지 않는다. first/last 끝점 파일은 first가 먼저 오는 기존 추출기 순서를 전제로 한다. last만 단독으로 제공한 파일은 완전한 주문 소스가 아니다.

## 지원 캔들 CSV

`reference_pair,candle_open_utc,minute_utc,open,high,low,close,volume`

- `minute_utc`: Unix epoch 이후 **분** 개수.
- 내부 `candles.time`: Unix UTC **초**.
- 내부 주문 `time_us`: Unix UTC **마이크로초**. 소수초를 보존한다.
- 차트 마커: `floor(time_us / 1e6 / (tf*60)) * (tf*60)`.
- 캔들이 실제 존재하는 시각에만 마커를 붙인다. 가장 가까운 캔들로 옮기지 않는다.

## Binance 월별 원본

공식 12열 kline CSV를 인식한다. 13자리 ms 또는 16자리 µs의 시작·종료 시각을 검증하고, OHLC·음수 거래량·유효 범위를 확인한다. header가 없는 `PAIR-1m-YYYY-MM.csv`를 지원한다. 이 버전에서 모든 비표준 거래소 CSV를 지원하지 않는다.

## 검증 정책

- 원본 파일별 SHA-256 중복 검사, ZIP CRC, UTF-8-sig, 행 수·크기 상한.
- ZIP 경로 탈출, 심볼릭 링크, 암호화 파일, 중복 member 이름 거부.
- 유효하지 않은 행은 격리. identifiable minute이 있으면 그 분은 제외.
- 같은 pair/time에 같은 OHLCV는 중복 제거; 다른 OHLCV는 충돌로 양쪽 모두 제외.
- 로컬 SHA는 내려받은 원본과 공식 거래소의 동일성까지 입증하지 않는다.
- 새로운 파일 가져오기는 한 트랜잭션. 실패하면 기존 정상 데이터는 유지.
- 상위봉은 UTC 고정 경계에서 모든 1분이 존재하는 경우만 생성. 부분봉 보간 없음.

## 분류 보수성

- `CLOSE_*` + `qty_after > 0` → UI는 `NEAR_CLOSE_*`(대부분 정리). 원래명은 별도 보존.
- `TACTICAL_CUT_*`, `FLIP_*`는 기존 연구의 사후 해석 후보. 단순 수량 일치가 동기 증거는 아님.
- 컨텍스트 `Entry`에 before 정보가 없으면 `INCREASE_*`; `Exit`에 근거가 없으면 `REDUCE_*`.
- `qty_before + signed(qty) != qty_after`는 interleaved endpoint 경고. 값을 임의로 맞추지 않음.
- `episode_max_qty`, `episode_net_pnl_btc`는 사후 메타데이터. 실시간 신호나 바 리플레이 입력으로 쓰지 않음.

## 거래량

상세의 직전 완성 1분은 주문이 포함된 분보다 바로 이전 분이다. 상대 거래량은 해당 이전 분보다 앞선 연속 20분 평균을 분모로 한다. 체결 분 최종 거래량은 사후 값이며 분모는 체결 분 이전 20분이다. 연속 자료가 부족하면 공란이다. 1분 전체 거래량을 특정 초의 체결 시점 거래량으로 위장하지 않는다.

## 아직 구현하지 않은 것

원본 실행·펀딩·정산 재회계, 역계약 수량 변화의 정확한 체결별 순서 복원, 계좌 전역 순노출/레버리지, 전체 승패 재계산, 주문 제출·취소·미체결 복원, 실시간/틱 리플레이. 기존 이벤트의 최종 수량을 첫 체결 때 모두 보유한 것으로 표시하지 않는다.
