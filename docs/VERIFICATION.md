# 검증 범위

검증 결과는 저장소의 **Actions 실행 결과**가 기준이다. 코드에 테스트가 있다는 사실만으로 통과를 주장하지 않는다.

## 자동 검사

- Python unittest: timestamp 단위, KST/UTC, 필수 방향, 원시 OHLCV 검증, 그룹 끝점 경고, 잔량 보존, first/last 연결, 우선순위 병합, 누락 분봉·상위봉 집계, 거래량의 시간 구분, 충돌 격리, 중복 ZIP 멱등성, ZIP 경로 보안, 메모 version 충돌, 서버 Host/Origin/CSRF, 공개 API 지역제한·범위·응답 정렬.
- Node native test: UTC containing-bar mapping, same-bar aggregation, marker placement, missing candles, filters, price deviations, display timezone, CSV safety.
- Playwright Chromium: 실제 서버 실행 → 합성 ZIP을 화면에서 가져오기 → 캔들/거래량 pane → 마커 → 주문 점프 → 시간봉 → UTC/KST → 최소 수량 → 메모 저장/새로고침 → 테마 → PNG/CSV 저장 → 다음 Episode → 모바일 레이아웃.
- 배포 ZIP: 실제 ZIP CRC, 소스/공식 차트 포함 여부, 사용자 data 폴더 제외.

## 해석 경계

테스트의 가격·주문은 **합성값**이다. `artifacts/ui-synthetic-*.png`와 test PNG는 테스트 UI 증거이지 실제 AOA 차트가 아니다. 앱은 사용자 데이터를 가져오기 전 합성값을 표시하지 않는다.

개발 대화의 로컬 실행 도구가 ClientError를 반환해 전체 사용자 ZIP/CSV를 실행 환경에서 직접 분석하지 못했다. 프로젝트의 실제 이벤트·컨텍스트 CSV 스키마와 표본을 Files 도구로 확인하고 어댑터를 작성했다. 따라서 CI 통과는 해당 어댑터·로직·브라우저 동작에 대한 검증이며, 사용자 파일 전체의 처리 완료나 기존 모든 통계의 재검산을 의미하지 않는다.

Windows CI는 Python 서버/데이터 로직을 검사한다. 실제 Windows 데스크톱에서 배치파일을 더블클릭하고 브라우저를 여는 사용성 검사는 사용자의 PC에서 별도로 확인해야 한다.
