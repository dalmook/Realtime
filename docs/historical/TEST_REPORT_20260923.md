# 검증 보고서 · SCMRealtimeDB 1.0

검증일: 2026-09-23. 제작 환경: Linux x86_64 / Python 3.13. 실제 Windows/Python 3.14 호환성은 아래 미검증 범위와 구분합니다.

## 실제 수행

```text
python -S -m unittest discover -s tests -v
Ran 98 tests in 5.751s
OK
```

`-S`로 site-packages를 불러오지 않은 상태에서 통과했습니다. 로컬 모의 HTTP 서버만 사용하며 실제 Splunk/Oracle에 접속하거나 회사 데이터를 발송하지 않았습니다. 테스트는 임시 DB와 가상 데이터만 씁니다.

검증 범위:

- 최신 전체행 유지, 과거 수정본의 역전 방지, 같은 이벤트 재수집의 멱등성
- 동일 시각 충돌 거절, 키/수량/일시 오류 시 현재값·체크포인트 보존
- P1M1/CO·GO 최신 상태 범위 및 범위 밖으로 변경된 행의 집계 제외
- 고유 BOX와 최신행 개수 구분, PC 원본 보존/EA 표시, 이종 단위 혼합 방지
- 실제 입고시각과 수정시각 분리, 코드 선행 0 보존, UTC/KST 변환
- 원천별로 다른 입고/재고/출하 매핑
- 재고 완전 스냅샷 교체, 불완전/빈 스냅샷 차단, 수정된 잔량을 이력처럼 합산하지 않음
- Oracle 원본 5개 테이블 복제/원자 교체, 실패 시 이전 원본 스냅샷 유지
- 제품 동일값 중복 병합, 서로 다른 제품명/그룹 충돌 거절, 매핑 미확정 상태 표시
- 환산 revision 반영/정확한 숫자 처리/미매핑 상태 표시
- 월 목표 일할 배분 없음, 목표-실적 JOIN 증폭 방지, 계획 버전 분리
- 중복 목표 상세행 합산은 명시적 원천키가 있을 때만 허용
- 과거 수집 미완료/수집 지연/미등록 출하/누락된 차원 매핑의 진척률 보류
- 목표가 0이면 비율 NULL, 단위가 다르면 비율 보류
- Oracle 09:00 실행/09시 전 미실행/재시작 중복 방지/같은 날 자동 재시도 금지/다음 날 실행
- Splunk 세션키 인증과 401 재로그인 1회
- loopback 모의 서버에서 2,505행 페이지네이션, 페이지 누락/조기종료/경고/preview/건수초과 거절
- 환경변수의 HTTP_PROXY/HTTPS_PROXY를 Splunk 직결에 사용하지 않음
- Oracle Strict Thick, read-only transaction 필수, fetchmany 전체 페이지 처리 및 상한 실패 시 스테이징 미반영
- 로컬 조회가 Oracle 재조회를 발생시키지 않음
- read-only SQL, 백업 무결성, raw 이력 정리가 현재 실적을 지우지 않음, 날짜 인덱스 사용

## 별도 스모크 검사

```text
CLI init: PASS
CLI status: PASS
CLI query examples/source_health.sql: PASS
CLI query examples/today_inbound.sql: PASS
CLI query examples/month_progress.sql: PASS
CLI backup and PRAGMA quick_check: PASS
Fresh schema: 19 tables + 13 views
Oracle raw tables: first successful capture creates 5 additional raw tables
Python AST / JSON parse: PASS
Windows CMD files: ASCII + CRLF / control-character checks PASS
```

DEMO.cmd의 실제 Python 엔트리포인트도 실행했습니다. 가상 최신 입고 3행, 고유 BOX 3개, EA 1,250개와 재고/출하·월 목표 진척 뷰를 확인했습니다. 이 값은 회사 실적이 아닙니다.

EXPLAIN QUERY PLAN에서 날짜를 지정한 입고 상세 뷰 조회가 원천 날짜 인덱스를 사용하는 것도 확인했습니다. 실제 데이터 규모에서의 지연시간/SLA를 측정했다는 의미는 아닙니다.

## 아직 검증하지 못한 것

- 실제 Windows .cmd 실행, Python 3.14와 사용자 설치 패키지 조합
- 사용자의 oci.dll 로딩과 Oracle 드라이버/Instant Client 버전 조합
- 실제 Splunk 서버 인증/검색 동작 및 사내 Oracle 접근 권한/속도
- 실제 GUI_SITEORGHRCY/환산/목표 4개 테이블의 컬럼·고유키·단위·적용월
- 실제 재고·출하 Splunk의 테이블·삭제/스냅샷 계약
- SAP 수치와의 종합 대조 및 데이터 지연 SLA

원천 접속/미확정 업무 매핑은 테스트 성공만으로 완료됐다고 주장하지 않습니다. 실제 연결은 사용자 환경에서 수행해야 합니다. 핵심 코드의 self-test가 Oracle 드라이버를 함께 설치해 주지는 않습니다.
