# 복원 범위와 변경 이력

## 입력과 보존

이번 대화의 PART 1–16 텍스트가 기준입니다. 이전 Library의 DBOnly / Executive UI ZIP은
변하지 않은 파일의 원형을 복구하는 데 사용했습니다. 별도 SCMRealtimeV1 제품으로 대체하지 않았습니다.
분할된 server.py / target_manager.py / focus_manager.py와 KZWI3 수집기를 연결해 보존했습니다.
PART 8의 Markdown 이스케이프와 HTML 공백 표기는 코드 문법에 맞게 복원했습니다.
`token=MASKED`는 전송 마스킹으로 실행 변수까지 가려진 것으로 판단해 실행판에서 세대 카운터로 수정했습니다.

다음 비교 원문은 `restoration/*.txt`에 있습니다: 서버 1,517줄, 목표 관리자 872줄,
집중관리 관리자 458줄, 과거 KZWI3 수집기 4개.
JSON은 UTF-8로 다시 기록했고 문서/테스트/일부 UI는 현재 실행 계약에 맞춰 재작성했습니다.
구버전 MANIFEST는 현재 소스와 맞지 않아 새 SHA-256 MANIFEST를 생성합니다.
따라서 바이트 단위 원본 검증이나 전체 81개 파일의 동일 복제를 주장하지 않습니다.

## 실제 적용한 수정

| 영역 | 변경 |
|---|---|
| 실행 | run.py → launcher.py; START가 API+수집을 실행; 경로는 프로젝트 상대 경로 |
| 데이터 위치 | API/목표/집중관리/수집기가 같은 Settings/DB를 사용 |
| 기존 데이터 | 초기화 전 SQLite backup, 컬럼 추가만 허용, 실행 데이터는 ZIP 밖 |
| 수집 잠금 | run_collector도 ProcessLock 적용. 임의 우회 제거 |
| KZWI3 | 연속 수집 테이블 우선, 기존 KZWI3 스냅샷은 보조, NETWR fallback 없음 |
| 필터 | c_id/i_type은 payload_json에서 추출; scope_ok 준수 |
| 공통 집계 | reporting.py에서 KPI/시간/월/거래선/ITEM/목표/집중관리 공통 계약 |
| 환산 | 월별 계수 우선, 단위별 1행 선택, 다중 환산 행으로 EA가 중복되지 않음 |
| 목표 | UI/Python 필드·연산자·응답명 통일, 동일 조건만 우선 적용, 오류를0으로 숨기지 않음 |
| 집중관리 | 날짜·지표 연동, 초기 등록 버튼 접근 가능, 중복 삭제 요청 제거 |
| BOX | 모호한 CARTON 의미 확인 플래그. 미매핑 차원 합계를 임의 표시하지 않음 |
| Web | localhost 기본, JSON 크기/형식 검사, Origin/Host 검사, .env 정적 노출 차단 |
| 데모 | 합성 SQLite와 브라우저 전용 데모 분리, 정적 데모는 network CSP 차단 |
| 공개 배포 | 코드 비공개 + 합성 HTML 공개 저장소로 분리하는 최초 게시 도구 |

## 호환성과 달라진 점

외부 API URL과 기본 응답 필드는 유지했습니다. aliases `/api/targets/list`, `/api/focus/list` 등도 지원합니다.
원본에서 하드코딩된 회사 PC 경로나 실제 DB에 쓰는 테스트는 제거하고 임시 DB 테스트로 교체했습니다.
`collect_kzwi3_v2.py`의 DROP TABLE은 실행 경로에서 제거했습니다. 동일 파일명은 안전한 수집 CLI 래퍼입니다.
`v_inbound_plan_progress`와 `v_shipment_plan_progress`는 현재 v_monthly_progress 기반 호환 뷰입니다.
이 두 뷰의 일부 구형 컬럼과 일할 목표 산식은 동일하지 않습니다. 외부 SQL 소비자는 검토해야 합니다.
기존 문서의 “DB only”, 이전 테스트 결과 등은 historical/로 이동해 현재 안내와 구분합니다.

## 회사에서 확인해야 하는 계약

CARTON의 식별자/수량 의미, I_DATE='00000000'의 예정/완료 의미, 청구 생성일과 수정 버전의 관계,
KUNAG와 입고 GC_CODE/Oracle SITE 계층 관계, 목표 PLANID/FWEEK/PLAN_VERSION과 적용 범위,
삭제·취소 이벤트, 초기 백필 범위, 실제 KZWI3 마스터 조인 결과는 회사 확인이 필요합니다.
미연동 재고를 합성 재고로 대체하거나 입고-출하로 현재고를 추정하지 않습니다.

## 실제 GitHub 상태

인증 계정 dalmook 확인과 저장소 검색은 수행했습니다. 새 SCM 저장소 검색 결과는 없었습니다.
사용 가능한 GitHub 액션에는 신규 저장소 생성/Pages 설정 액션이 없었고, 원격 실행기는 계정 연결 오류를 반환했습니다.
신규 저장소 생성·커밋 push·Pages URL 정상 접속은 **미완료**입니다.
게시 스크립트 및 workflow 파일을 준비했지만 실제 GitHub Actions 성공으로 표시하지 않습니다.
