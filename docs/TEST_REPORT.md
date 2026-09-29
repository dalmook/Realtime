# Portable 1.2.0 실제 검증 결과

검증일: 2026-09-29. 환경: Linux / Python 3.13 / SQLite 3.46.1 / Chromium.
회사 네트워크, Oracle, Splunk에 접속하지 않았습니다.

## Python: 132개 통과

```text
python -S -m unittest discover -s tests -v
Ran 132 tests in 10.928s
OK
```

기존 98개 코어·모의 커넥터 테스트와 신규 34개 대시보드/설정 테스트입니다.
임시 합성 DB와 loopback HTTP만 사용했습니다. 테스트 데이터를 실제 DB에 쓰지 않습니다.

확인한 내용:
- 동일 조건의 KPI 금일 = 시간별 합계, 월 누적 = 일별 합계 (EA / USD / 개별 EQ / 지원 BOX)
- 거래선 Top N + 기타 = 전체, 품목 합집합 전체와 KPI 일치
- 거래선/ITEM/창고 필터, 과거 기준일 상한, 달력상 잘못된 날짜 거절
- KZWI3 연속 수집 우선, legacy KZWI3 보조, 미매칭 금액의 NETWR fallback 금지
- EQ 이중 계수로 EA 증폭 없음, 월 계수의 상시 계수 우선 적용
- scope_ok 이탈 제외, 미수집 값과 실제0 구분, 미지원 BOX 필터 NULL
- 수기 목표 범위·우선순위, CRUD/복사/비활성/0목표/NaN 거절/필터 연산자/SQL injection
- 집중관리 CRUD/중복/일괄 원자성 및 동일 ITEM KPI 일치
- HTTP 읽기/쓰기 정상, 잘못된 Origin/Host·.env 노출·잘못된 날짜 차단
- 중복 초기화 데이터 보존, demo의 비데모 DB 접근 거절

전체 출력: TEST_OUTPUT.txt. 테스트 성공은 회사 원천 필드 의미와 숫자의 검증을 대신하지 않습니다.

## 브라우저: 33개 통과

생성된 독립 HTML을 Chromium 문서에 로드하고 실제 DOM 이벤트를 실행했습니다.
이 실행 환경의 브라우저 정책이 localhost/file URL 직접 탐색을 차단하여,
브라우저 검사는 인메모리 문서에서 수행했습니다. HTTP API는 위 Python 테스트에서 별도로 검증했습니다.
따라서 Windows에서 HTML 더블클릭/START.cmd 실행이나 브라우저→HTTP 통합 검증 완료로 표현하지 않습니다.

확인한 내용:
- 다섯 화면 전환, 화면 중복 표시 없음
- 목표 미리보기 / 생성 / 복사 / 수정 / 비활성 / 삭제
- 집중관리 등록 / 삭제 (중복 이벤트 호출 없음)
- EA / EQ_DRAM / EQ_FLASH / BOX / USD 전환과 시간 합계 일치
- ITEM 텍스트 입력 필터, 차트/수치 조건 일치
- 누적/확대/표, UTF-8 BOM CSV 다운로드
- 1440px 화면 및 390px 모바일 가로 넘침 없음
- 라이트/다크 전환, JavaScript 예외0
- 정적 데모에서 HTTP/HTTPS API 또는 외부 네트워크 요청0

브라우저 저장소가 차단된 문서에서는 세션 메모리로 작동합니다.
일반 브라우저 localStorage 영구 보존의 실제 재시작 검사는 이번 제한 환경에서 수행하지 못했습니다.
로컬 API의 SQLite 목표/집중관리 저장은 Python에서 검증했습니다.

## 배포 검사

- JavaScript 문법 검사 통과.
- 공개 사이트 생성은 합성 fixtures.js만 사용, DB/.env 읽기 없음.
- GitHub 게시 스크립트는 --dry-run 실행 성공. 실제 gh 생성/push/Pages workflow는 미실행.
- ZIP은 허용된 코드 경로만 포함하며 .env/DB/로그/venv/인증키/실행 바이너리는 제외.

## 미검증

실제 Windows .cmd/Oracle Thick 조합, 사내 Splunk/Oracle 접속, SAP 정합성,
원천 취소/삭제/스냅샷 계약, 대량 데이터 성능, GitHub 권한/Actions/Pages 배포,
기존 운영 DB의 회사별 추가 스키마 및 외부 SQL 소비자 호환성은 검증하지 못했습니다.
