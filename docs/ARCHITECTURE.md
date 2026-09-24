# 설계 및 기능 명세 v0.1

## 목적

TradingView 구독의 과거 인트라데이 열람 제약 대신, 사용자가 가진 과거 OHLCV와 거래 이벤트를 날짜 범위로 읽는 **로컬 매매 복기 도구**를 제공한다. 기존 ChatGPT 프로젝트는 연구 지침·원본 보관 공간이고, 이 저장소는 해당 연구를 위한 실행 앱이다.

## 구성

```text
local CSV / ZIP / CSV.GZ
        ↓ streaming parse + validation
local SQLite (events, candles, aggregate bars, provenance, notes)
        ↓ HTTP on 127.0.0.1 only
native HTML / CSS / JS
        ↓ official Lightweight Charts 5.2.1
candles + volume panes + grouped event markers
```

표준 라이브러리만으로 서버·DB·압축파일을 다루어 Python 환경 의존성을 줄였다. 프런트는 번들러/React 의존성 없이 ES modules를 사용한다. 차트 JS만 버전을 고정하고 npm 공식 배포 tarball의 integrity를 검증한다. 다운로드는 라이브러리 초기 준비와 사용자가 확인한 공개 시장 보완에만 필요하다.

## 구현 범위

- 연도·계약·방향·손익·Episode 필터, 이전/다음 선택
- UTC / 한국시간 표시 전환
- 1m / 5m / 15m / 1h / 4h / 1d
- 거래량 하단 pane, crosshair OHLCV, 줌·드래그
- 동일 bar/위·아래 위치별 주문 마커 집계
- 개별 주문 목록/선택, 주문 시각으로 범위 점프
- 첫 가격/그룹 VWAP/수량/평균단가/stop별 정보
- 전후 이벤트 탐색, 날짜 이동, 구간 전후 이동, 전체 포지션 fit
- 원시 캔들 부족 및 제외 분봉 개수 표시
- 사전 거래량과 체결 분 최종 거래량 분리
- 이벤트 CSV/캔들 PNG 저장
- 포지션별 연구 노트, 버전 충돌 감지
- ZIP/CSV/GZ 로컬 업로드, inbox, 진행 표시
- 선택 범위 공개시장 보완 및 로컬 캐시
- local-only 데이터, 보수적인 입력 검증과 보안 경계

## 명확히 미구현

설치형 EXE/Tauri 배포, 주문/계좌 API, 자동매매, 원본 140만 실행행 재회계, 새로운 예측전략, 서버 배포·멀티유저, 시각별 포지션 사이즈와 평균단가 선의 완전 복원, 틱 단위 혹은 미래 정보 차단형 리플레이, 자동 유사패턴 탐색. 현재 '이전/다음 주문'은 복기 탐색이지 엄밀한 바 리플레이가 아니다.

## 보유기간·수량 표현

Episode 목록의 기간은 가져온 표시 주문의 처음/마지막 끝점이다. 원장상 수량0 경계와 동일하다고 단정하지 않는다. 기존파일의 episode 최대수량/손익은 입력값으로 표시하며 새로 검산했다고 쓰지 않는다. interleaving이 가능한 주문 그룹에서 완전한 수량 step graph를 그리지 않는다.

## UI 원칙

넓은 가격 차트와 같은 축의 거래량을 우선한다. 마커는 짧은 한국어 이름, 수량은 선택 옵션이다. 주문 내용을 긴 글로 캔들 위에 전부 겹쳐 쓰지 않는다. 반대 방향과 감량을 구분하며 손절/익절을 색 하나만으로 판단하지 않는다. 데이터가 없는 초기 화면을 가짜 데모로 대체하지 않는다.

## API

읽기: `/api/bootstrap`, `/api/status`, `/api/episodes`, `/api/events`, `/api/chart`, `/api/event-volume`, `/api/note`, `/api/inbox`, `/api/health`.

쓰기: `/api/upload`, `/api/import-inbox`, `/api/fetch-market`, `/api/note`.

전체 API는 Host 및 Origin allowlist를 사용하고 쓰기 요청에는 세션 토큰을 요구한다. 임의 경로 읽기, 임의 URL 프록시, 파일 삭제, 거래 실행 endpoint는 제공하지 않는다. HTTP 서버를 외부 네트워크에 노출하지 않는다.

## 확장 순서

1. 실제 사용자 데이터 통합 검수와 추가 schema adapter.
2. 체결 조각 기반의 정확한 수량/평균단가 history.
3. 미래 데이터 제거형 bar replay와 실제 미청산 상태.
4. 비교 차트·태그·가설 검증 및 casebook.

사용자 데이터나 원본을 공개 저장소에 넣는 변경은 별도 동의 없이 진행하지 않는다.
