# 회사 실행과 업데이트

## 이번 버전의 핵심 변경

환산은 원본 실적과 독립적으로 처리합니다.

- Splunk 자재키: `MATNR`
- Oracle 자재키: `SCM_INFO.SCM_FABIN_CONV_FAM6_MST_M.ITEM`
- 분리키: `CONV_CODE`
- 계수: `CONVEQQTY`
- 환산식: `QTY × CONVEQQTY`
- K4*/PD*=DRAM, K9*=FLASH
- DRAM+FLASH 복합제품도 EA/QTY·BOX·USD는 한 번만 집계

## 가장 안전한 로컬 실행 순서

1. Release의 `SCMRealtimeDB_portable.zip`을 **새 폴더**에 해제합니다.
2. 기존 `%LOCALAPPDATA%\SCMRealtimeDB\live\scm_live.sqlite`가 남아 있다면 먼저 복사 보관하거나, 기존 실행본이 있으면 `BACKUP.cmd`로 백업합니다.
3. `SETUP.cmd`를 실행합니다. 이 단계는 Python 선택, `.env` 준비, DB 스키마 준비까지만 합니다.
4. 새 폴더의 `.env`에 승인된 Splunk/Oracle 정보를 입력합니다.
5. `CHECK.cmd`를 실행합니다. Oracle Thick 준비 오류가 있으면 START 전에 해결합니다.
6. **`SYNC_ORACLE.cmd`를 1회 실행합니다.** 이번 환산 변경은 새 `CONV_CODE / CONVEQQTY` 기준정보가 반드시 필요합니다.
7. `VERIFY_CONVERSION.cmd`를 실행하고 실제 MATNR 하나를 입력합니다.
8. 출력된 CONV_CODE, DRAM/FLASH, CONVEQQTY와 업무 기준값을 확인합니다.
9. `START.cmd`를 실행합니다. 기본 주소는 `http://127.0.0.1:8765/`입니다.

Python 3.11 이상이 필요합니다. Oracle은 승인된 `oracledb` 또는 `cx_Oracle`과 호환 Instant Client를 Thick 모드로 사용합니다.
회사 망에서 자동 pip 설치나 외부 다운로드를 시도하지 않습니다.

## 기존 DB를 이어 쓸 때

기본 DB는 코드 폴더 밖 `%LOCALAPPDATA%\SCMRealtimeDB\live\scm_live.sqlite`입니다.
따라서 예전 소스 폴더를 지웠더라도 이 DB가 남아 있으면 새 ZIP이 이어서 사용할 수 있습니다.

이번 버전은 기존 입고 DB가 예전 `P_CODE` 연결키로 수집되어 있으면 원문 JSON의 `MATNR`를 이용해 한 번 이관합니다.
모든 기존 행에 MATNR가 있을 때만 자동 이관하며, 이관 전 백업을 만듭니다.
MATNR 누락 행이 있으면 중단합니다. 이 경우 DB를 지우거나 reset-source를 하지 말고 오류 메시지를 보존하세요.

기존 EQQTY 기반 환산 결과는 새 버전에서 무효화되며 `SYNC_ORACLE.cmd`가 성공해야 새 환산값이 다시 계산됩니다.

## 화면만 먼저 확인

- `site/index.html`: Python 없이 합성 데이터 화면
- `DEMO.cmd`: 별도 합성 SQLite + 실제 Python API. 회사 `.env`, Splunk, Oracle을 사용하지 않음

## 확인 명령

- `STATUS.cmd`: 수집/기준정보 상태
- `CHECK.cmd`: Python, SQLite, Oracle Thick 준비상태
- `SYNC_ORACLE.cmd`: Oracle 기준정보/목표 수동 동기화
- `VERIFY_CONVERSION.cmd`: MATNR별 환산 구성과 최근 fact 환산값 확인
- `SELFTEST.cmd`: 외부 연결 없는 자동 테스트
- `BACKUP.cmd`: SQLite 일관성 백업

## 운영 전 검증

실제 Splunk/Oracle 인증, SAP 대비 수치, CARTON 의미, 원천 취소/삭제 의미와 수집 누락은 회사 환경에서 최종 확인해야 합니다.
`SHIPMENT_BOX_CONFIRMED=false`가 기본입니다. 검증 없이 true로 바꾸지 마세요.
