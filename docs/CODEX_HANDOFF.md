# Codex 인수인계 — main v0.2

사용자 목적은 실제 캔들+거래량 위에서 실제 주문을 보고 복기하는 것입니다. 지침의 사실/추론, 그룹 끝점/개별체결, BitMEX/Binance, 사후정보를 구분하세요.

실행: run.py -> aoa.server.AppServer -> aoa.review.ReviewStore(Store). 기존 local-data/viewer.sqlite3 유지. 프런트 web/app.mjs, 순수 함수 core.mjs + review-core.mjs, UI index.html + style.css + review.css.

수정한 오류와 계산 정의는 UPDATE_0_2.md가 기준입니다. 재생 기준은 `S.anchor`, `S.cutoff`를 혼동하지 않아야 합니다. `S.bars`에는 whitespace가 있고 슬라이더 인덱스는 validBars만 셉니다. 현재 bar-open과 cutoff가 같으면 그 봉과 그 시각 주문을 공개하지 마세요.

누락 다운로드는 aoa.market.fetch_window / review.missing_plan. HTTP 요청 대기 중 DB 쓰기 잠금을 유지하지 마세요. 가격을 보간/자동 수정하지 말고 충돌은 격리합니다. 자동 다운로드를 거절/실패하면 매 렌더마다 재시도하지 마세요. 사용자 주문이나 파일을 외부에 업로드하지 마세요.

성과는 그룹 참고 근사값, 원장 BTC 순손익, 입력 증거금 참고 ROI를 분리합니다. price_return_pct를 전체 계좌 ROI로 바꾸거나 5배를 임의로 곱하지 마세요. 정확한 증거금 자료 없이는 실제 ROI 미확보가 맞습니다.

검증: unittest discover, node --check web/app.mjs, node --test tests/test_frontend.mjs tests/test_review_frontend.mjs, tests.browser_test. 브라우저 테스트는 Playwright와 Chromium이 필요합니다. scripts.verify_public_market는 별도 외부 공개 시세 검증이며 네트워크 불가를 구분합니다. tests/seed_ci.py와 테스트 주문은 합성입니다.

향후 원장 전체를 테스트하려면 로컬 원본만 읽고 집계 결과를 사용자에게 제시하세요. 사용자 원본을 공개 저장소/CI fixtures로 커밋하지 마세요. 별도 feat/whale-viewer-v1의 data/aoa.sqlite3를 main DB에 이름만 바꿔 연결하지 마세요.
