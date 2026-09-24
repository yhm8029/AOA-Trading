# 설계 및 데이터 계약

## 구성
- `run.py`: Python 3.10+ 실행. 첫 실행에 차트 패키지 고정 버전 준비.
- `aoa/model.py`: timestamp/숫자 검증, 입력 어댑터, 끝점 병합, 보수적 행동 라벨, 엄격한 OHLCV 집계.
- `aoa/importer.py`: CSV/gzip/ZIP 스트림, 트랜잭션, 무결성·중복·거부 기록.
- `aoa/store.py`: SQLite WAL. 주문 JSON과 에피소드/시간 인덱스, 분봉 `(pair,t)` PK, conflict 격리, notes.
- `aoa/market.py`: 사용자 요청 공개 API 다운로드만 담당.
- `aoa/server.py`: 표준 라이브러리 loopback HTTP API와 정적 파일.
- `web/core.mjs`: 마커 봉 정렬, 같은 봉 그룹화, 복기 마스킹 등 순수 함수.
- `web/app.mjs`: 차트/목록/필터/메모 UI.

## 원장 우선순위와 병합
키는 `episode + raw role + original order ID` 해시다. 동일 주문의 first/last는 병합한다. 다른 역할 또는 에피소드로 나뉜 동일 주문ID는 별개다.
끝점의 시간은 microseconds 정수로 저장한다. 화면 차트 시각만 seconds로 변환한다. 원문 timezone 미기재는 잠정 UTC.
CSV에 값이 없으면 `None`이며 0으로 대체하지 않는다. 컨텍스트와 캔들특징의 `pre_*`만 별도 딕셔너리로 보존한다. `post_*`를 예측 입력에 자동 편입하지 않는다.
원본이 `first/last fill endpoints`인 경우 주문량은 전체 그룹 수량이다. 보유량의 endpoint 차이가 qty와 다르면 **중간 다른 주문 가능성**을 경고한다. 이를 기반으로 정확한 틱별 보유량·평균단가 곡선을 생성하지 않는다.

## 캔들
시간은 UTC UNIX seconds, 봉은 [open_time, open_time + timeframe) 반개구간이다.
상위 봉은 UTC 시계 경계에 맞춘 정확히 N개의 1분봉이 있어야 생성한다. 누락·중복·잘못된 OHLCV는 0값이나 forward-fill로 보간하지 않는다.
같은 `(pair,time)` 값이 다시 들어오면 같을 때 중복 제외, 다르면 기존값 제거와 conflicts 테이블 등록. 이후 동일 시각 재유입도 차단하여 조용한 값 교체를 방지한다.
화면 범위는 최대4000봉이며 날짜점프/주문점프/구간버튼을 사용한다. 계좌·보유기간 제한이 아니다.

## API
- GET `/api/status`: 로컬 세션 token, 적재 건수와 market coverage, 최근 가져오기 이력.
- GET `/api/episodes?symbol=XBTUSD&year=2021&direction=Short&result=Win&search=3086`
- GET `/api/events?episode=3086`
- GET `/api/candles?pair=BTCUSDT&tf=5m&start=...&end=...`
- GET `/api/note?episode=3086`; POST `/api/note` JSON.
- POST `/api/import?name=...`: raw file body. multipart 아님.
- POST `/api/fetch`: pair/start/end JSON; 사용자 요청 시에만 실행.
- GET `/api/job`: 1개의 로컬 worker 작업 진행도.
- GET `/api/issues`: 최근500개 검증 오류.
- GET `/api/export?episode=3086`: CSV (formula injection 방어).
모든 POST는 `X-AOA-Token` 필요. API token은 외부 계정 credential이 아닌 해당 실행 세션의 CSRF 방어 수단이다.

## 재생의 정확한 의미
완성 봉 이후까지의 시장 자료만 화면에 노출하는 복기다. 미체결 주문·주문 제출시각·시장 틱 흐름은 없다. 서버의 전체 원본을 지우는 보안 기능이나 실시간 백테스트 엔진은 아니다. CSV 분류의 미래 최대수량·최종손익 의존은 replay 마커에서 제거한다.

## 개인 데이터 경계
`local-data`, imports/exports 및 CSV/ZIP 원본은 Git 제외. 어떤 원장도 기본 저장소·CI에 포함하지 않는다. CI는 별도로 표시한 합성 구조 테스트만 사용한다.
