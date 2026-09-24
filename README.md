# AOA Whale Viewer v0.3.1

**고래의 주문을 캔들·거래량 위에서 보고, 진입·추가·감량의 근거를 복기하는 로컬 연구 앱.**

[실행 ZIP](https://github.com/yhm8029/AOA-Trading/releases/download/v0.3.1/AOA-Whale-Viewer.zip) · [배포 안내](docs/RELEASE_v0.3.1.md) · [CI](https://github.com/yhm8029/AOA-Trading/actions/workflows/ci.yml)

## 기존 화면이 계속 나오던 문제

v0.3.1은 기존 서버가 8765 포트를 점유해도 다른 로컬 포트로 새 앱을 실행합니다. 브라우저를 열기 전에 버전·프로세스·실행 ID를 확인합니다. 새 탭에 `v0.3.1`과 `실행 확인 v0.3.1`이 보여야 합니다. **이전 탭의 주소를 재사용하지 마세요.** 이전 프로세스는 강제 종료하지 않습니다.

## Windows — 기존 사용자

1. 실행 ZIP을 **새 빈 폴더**에 풉니다. 프로그램 파일을 섞어 덮어쓰지 않습니다.
2. `start_windows.bat`를 실행합니다. **Python 3.10 이상**이 필요합니다.
3. 기존 데이터 선택 창에서 **기존 앱 폴더 또는 local-data**를 선택합니다. 새 local-data에 SQLite 일관성 사본을 만들며 원본은 지우지 않습니다. **주문·캔들·메모를 파일별로 다시 넣을 필요가 없습니다.** 이미 새 폴더에 local-data가 있으면 선택 창 없이 시작합니다.
4. 자동으로 열린 새 탭에서 `실행 확인 v0.3.1` 확인 → 포지션 선택 → 오른쪽 주문 클릭.

폴더 선택을 취소하면 새 빈 데이터로 시작합니다. 나중에 데이터 사본을 만들 때는 `start_with_existing_data.bat`를 사용하세요. 새 폴더에 DB가 이미 있으면 덮어쓰기하지 않습니다. 원본 DB와 사본은 이후 자동 동기화되지 않습니다.

복사 직전 옛 앱의 가져오기·메모 저장 작업을 마치는 것이 좋습니다. 기존 폴더는 백업으로 보관하세요. NTFS 등 하드링크를 지원하는 로컬 디스크에 새 폴더를 만들어야 합니다. 독립 EXE/Python 포함 설치판은 아닙니다.

## 화면에서 할 수 있는 것

- 1m/5m/15m/1h/4h/일봉 캔들과 같은 시간축 거래량. 확대·이동·날짜 점프.
- 포지션 선택 시 첫 관측 진입을 포함한 범위로 이동. 첫 진입/마지막 감량/전체 보기.
- 숏 증가 위·감량 아래, 롱은 반대. 같은 봉의 주문 요약, 전체 주문 타임라인 유지.
- 최소 수량 기본값 0. 최초 진입·마지막 관측 감량·선택 주문은 수량 필터 보호.
- 주문별 **관측 사실 → 가능한 해석 → 반대 근거 → 한계** 해설. 1·5·15·60·240·1440분 배경과 근거 봉 보기.
- 완성 봉 재생, 배속, 이전/다음 봉. 주문에서 멈추고 해설 옵션. 미래 주문·사후 집계 숨김.
- 호버 시 봉 등락률·전봉 대비·고저폭·거래량·상대거래량.
- 없는 실제 1분봉만 다운로드한 뒤 상위 시간봉 재집계. 해설용 48시간 시세 보완.
- 포지션 메모/태그, PNG·CSV·해설 JSON 내보내기.
- 원장 BTC 순손익, 감량 가격성과 참고값, 직접 입력 증거금 기준 참고 ROI.

`주문이 나오면 멈추고 해설`이 켜져 있으면 주문에서 멈추는 것이 정상입니다. 체크를 끄면 계속 재생합니다. 주문 마커는 체결을 포함한 봉이 완성된 시점에 나타납니다.

## 데이터

| 파일 | 역할 |
|---|---|
| AOA_candle_analysis.zip | 정규화 1분봉과 주문 첫/마지막 끝점 |
| order_context.csv / order_candle_features.csv | 사전 가격·거래량 특징 |
| AOA_XBTUSD_2021_events.csv / TradingView 패키지 | 기존 이벤트 분류·평균단가·성과 보완 |
| AOA_대표사례_주문타임라인.csv | 평균가격·보유량·스톱 조건 보완 |
| AOA_market_data.zip / Binance 월별 1분 ZIP | 넓은 구간의 연속 시장 자료 |

파일명에 `(1)`이 있어도 됩니다. CSV/CSV.GZ/ZIP 가져오기, 파일당 512MB. 원본 개별 execution ZIP/XLSX를 새로 전수 회계처리하는 엔진은 포함하지 않습니다. 원본 파일은 수정하지 않습니다.

캔들·거래량은 **Binance 현물 대체자료**, 실제 주문 가격은 **BitMEX**입니다. 가격과 거래량을 동일시하지 않습니다. 원문 시각은 잠정 UTC이며 KST 표시를 선택할 수 있습니다. 해설은 체결 이전 완성 봉을 사용하나 주문 제출·의사결정 시각과 체결 시각은 다를 수 있습니다.

### 15분봉 등의 공백

`누락 시세 자동 보완`이 켜져 있으면 현재 구간에서 없는 1분봉을 요청합니다. 존재하는 자료를 다시 받지 않습니다. 받은 분봉은 검증 후 페이지별로 저장하므로 중단 후 재개할 수 있습니다. 거래소 원본 공백·상장 전·접근 제한·충돌 격리 구간을 가짜 가격으로 메우지 않습니다. 부분 봉은 정상 봉처럼 표시하지 않습니다.

### 수익률 정의

봉 등락률=(C/O−1)×100, 전봉 대비=(C/직전 C−1)×100, 고저폭=(H−L)/O×100.

감량 가격성과*는 입력 감량 주문의 수량가중 방향환산 가격변화 **참고 근사값**입니다. 전체 개별체결 회계·수수료·펀딩 포함 순수익률이 아닙니다. 원장 순손익은 입력 BTC 값만 사용합니다. 증거금 참고 ROI는 확인한 증거금을 직접 입력한 경우만 계산합니다. XBTUSD 역계약을 선형 USDT 계약처럼 임의 계산하지 않습니다.

## 실행과 보존

```
python run.py
python run.py --data-dir "D:\AOA-data"
python run.py --copy-data-from "D:\old AOA" --no-browser
python run.py --port 8766 --strict-port
python run.py --self-check
```

macOS/Linux는 `python3 run.py`. 종료 Ctrl+C. 기본 DB는 `local-data/viewer.sqlite3`. `--data-dir`은 지정한 폴더를 직접 사용하고, `--copy-data-from`은 빈 폴더에만 사본을 생성합니다. 현재 URL은 `local-data/last-launch.json`에서도 확인할 수 있습니다. 실행 ZIP은 manifest의 모든 파일 해시를 검사하고, 소스 체크아웃은 필수 파일과 버전을 점검합니다.

127.0.0.1 전용, Host/Origin 검증, 쓰기 토큰, CSP, 캐시 금지. 주문·메모·DB는 GitHub나 외부 LLM에 전송하지 않습니다. 시세 보완은 공개 거래쌍·기간만 전송합니다. 차트 엔진은 TradingView Lightweight Charts이며 TradingView.com 계정은 필요하지 않습니다.

## 검사와 한계

Windows/Linux Python 3.10/3.13, JavaScript 회귀, Chromium 4종을 병렬 실행합니다. ZIP을 풀어 **한글·공백 경로에서 실행**, 옛 포트 점유·새 프로세스 연결·SQLite WAL 사본·마커·해설·재생까지 검사한 후 배포합니다.

거래 회귀 테스트는 합성 자료입니다. 실제 Binance 과거 시세 보완 검사는 별도이며 **사용자 전체 ZIP 전수검산이 아닙니다.** 해설은 연구 초기 규칙을 사용하는 로컬 해석기이며 본인 의도/승률 검증/자동매매 신호를 확정하지 않습니다. 엄밀한 체결별 회계·전략 전체 검증은 미완료입니다.

```
python -m unittest discover -v
node --test tests/test_frontend.mjs tests/test_review_frontend.mjs tests/test_study_frontend.mjs
python scripts/prepare_vendor.py
python -m pip install playwright==1.55.0
python -m playwright install chromium
python -m tests.browser_launch_test
python scripts/build_package.py
python scripts/test_packaged_runtime.py
```

[설계](docs/ARCHITECTURE.md) · [기능](docs/FEATURES.md) · [연구 원칙](docs/RESEARCH.md) · [인수인계](docs/CODEX_HANDOFF.md) · [v0.3 해설 범위](docs/RELEASE_v0.3.0.md)

차트: [tradingview/lightweight-charts](https://github.com/tradingview/lightweight-charts). UI 흐름 참고: [lightweight-charts-python](https://github.com/louisnw01/lightweight-charts-python). 앱 MIT, 차트 Apache-2.0, 원본 거래/시세는 앱 MIT로 재허가하지 않습니다. [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
