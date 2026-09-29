# 운영 안내

## .env 기본값

- Splunk: 기존 host:8089, sessionKey 인증, **인증서 검증 false / CA 공란 / proxy 공란**.
- Oracle: 활성 true, 기존 DSN, `C:\instantclient`, Thick 필수.
- 비밀번호는 배포 ZIP에 없음. `.env`는 평문 설정이므로 사용자 계정과 NTFS 권한으로 보호하고 Git/메일에 공유하지 않음.
- 기존 LogisticsLiveHub .env를 **연결값만 복사**하며 원본 DB·설정·소스코드는 수정하지 않음.
- 웹 포트/APP_HOST/APP_MODE/회원등록/Knox 발송 기능 없음. 이번 프로젝트는 DB 전용.

## 설치/Oracle 오류를 반복하지 않기

기본 실행에는 `pip install -r requirements.txt`가 없습니다. 버전을 고정해서 다시 다운로드하지 않습니다. `SETUP.cmd`는 기존 Python을 검색하고 Oracle 드라이버가 있는 Python을 우선 선택합니다. 선택 경로는 `.python_path`에 저장합니다. `PYTHON_EXE` 환경값을 지정한 경우 그 값을 우선합니다.

```bat
set "PYTHON_EXE=C:\Users\<USER>\AppData\Local\Programs\Python\Python314\python.exe"
SETUP.cmd
```

Python 선택은 **패키지 존재 여부** 검사이며 실제 Oracle 로그인 성공 검사와 다릅니다. `CHECK.cmd`는 OCI 초기화까지, 실제 로그인/권한 검사는 `DISCOVER_ORACLE.cmd` 또는 `SYNC_ORACLE.cmd`에서 수행합니다.

어느 Python에도 드라이버가 없다면 IT 승인 경로로 해당 Python/Windows에 맞는 드라이버 및 의존성을 준비해야 합니다. ZIP에 Oracle 드라이버/Instant Client를 포함하지 않았습니다. `offline_wheels`에 승인 파일을 넣은 후 `INSTALL_ORACLE_OFFLINE.cmd`를 수동 실행할 수 있으며, 이 스크립트는 --no-index로 동작하고 다운로드하지 않습니다. 사내 pip.ini와 보안정책을 바꾸지 않습니다.

## 09시 운영 규칙

한국시간 09:00에 활성화된 Oracle 5개 원천을 한 번 읽습니다. 프로세스가 켜져 있어야 합니다. 09시가 지나서 실행되면 **당일 예약 기록이 없을 때** 1회 보충합니다. 전날 누락을 여러 번 몰아서 실행하지 않습니다. 하루 한 번은 간격 86400초와 다르므로 `ORACLE_REFRESH_SECONDS`를 사용하지 않습니다.

예약 실패도 그날의 1회 시도로 기록됩니다. 무한 재시도하지 않습니다. 실패 후 즉시 다시 필요하면 START를 종료하고 SYNC_ORACLE.cmd로 명시적 수동 조회합니다. 수동 조회는 사용자가 요청한 예외이므로 하루 여러 번 가능하며, 자동 예약 횟수와는 별개입니다.

Oracle은 별도 스레드에서 조회하고 읽은 결과를 로컬에 교체합니다. 원격 Oracle 조회 중 Splunk 수집을 기다리게 하지 않습니다. 다만 로컬 스냅샷 교체와 전체 환산 재계산 트랜잭션 동안에는 SQLite 쓰기/읽기 잠금 대기가 생길 수 있습니다. 대규모 데이터일 때는 실제 실행시간을 측정하고 SQL 범위/DB 엔진을 조정하세요.

## 초기 수집과 정합성

기본 입고의 초기 커버리지는 **현재 월 1일의 인덱싱 구간부터 현재까지**입니다. 날짜가 오래된 월 목표를 비교하려면 해당 월초부터 재수집해야 합니다.

```bat
python run.py collect --source inbound_dep --from-date 2026-01-01
```

실제 Splunk 보관 이력·수집 누락까지 자동 증명하지는 않습니다. `coverage_from`은 성공적으로 검색한 구간이며 원천 SAP 전체와의 숫자 대조를 대체하지 않습니다. 원천에서 삭제된 행/권한 밖 이벤트/이미 만료된 Splunk 데이터는 복구할 수 없습니다.

입고 상세와 SAP의 같은 범위/날짜 숫자를 대조하세요. 현재 고유키와 취소 플래그 의미는 추가 확인 대상입니다. 정합성 미확인 상태를 일괄 0으로 만들지 않습니다.

## 장애가 나면

먼저 STATUS.cmd에서 source_id, last_error, watermark, coverage_from을 확인합니다.

| 상태/오류 | 조치 |
|---|---|
| 인증서 검증 | 새 프로젝트 .env의 SPLUNK_VERIFY_SSL=false 확인. 다른 복사본 실행 여부 확인 |
| 401/403 | 원천 계정/API 권한 확인. sessionKey는 자동 재로그인 1회만 시도 |
| Oracle driver 없음 | SELECT_PYTHON.cmd로 설치된 드라이버가 있는 Python 선택 |
| oci.dll 없음 / DPI-1047 | C:\instantclient 및 Python/Client 아키텍처 확인 |
| ORA-01017 | Oracle 계정 확인. 오류창에 비밀번호 붙여넣지 않음 |
| ORA-00942 | 테이블/동의어 조회 권한 확인. 다른 테이블로 조용히 대체하지 않음 |
| max_rows 초과 | query_file로 필요한 기간/컬럼을 제한하거나 승인 후 상한 조정 |
| MAPPING_REQUIRED | 원본 복제는 완료, 컬럼 매핑 도우미 실행 |
| MAPPING_ERROR | 동일키 충돌/없는 컬럼/단위 확인. MAX로 임의 수정 금지 |
| 수집기가 이미 실행 중 | START 창 중복 실행 중지. STATUS/읽기 SQL은 가능 |
| PARTIAL_HISTORY | 월초부터 백필 완료 후 다시 월 진척 조회 |
| SOURCE_LAG_OR_BACKFILL | 수집 커서가 현재를 따라잡는지 확인 |

`data_issue`에서 문제 행을 확인할 수 있습니다. 한 구간에 잘못된 키/수량/시각이 있으면 현재 테이블/체크포인트를 전진시키지 않고 원본을 보존합니다. 불완전한 일시/삭제 전용 이벤트가 실제 원천 계약에 포함된다면, 해당 계약을 확인한 후 매핑/정규화 규칙을 조정해야 합니다.

로그에는 계정 토큰/비밀번호/원격 응답 원문을 출력하지 않습니다. 세부 DBA 오류가 필요하면 별도 사내 진단 환경에서 확인하세요.

## 백업/보관

BACKUP.cmd는 sqlite backup API로 읽는 동안 일관된 백업을 만들고 quick_check를 수행합니다. 상시 수집에서는 09시 이후 로컬 백업을 실행하며 기본 최근 7개를 유지합니다. raw_splunk_event/실행 로그/오류 기록은 기본 30일 정리합니다. 최신 실적·월 목표는 이 정리에서 삭제하지 않습니다.

동시 실행은 OS 잠금으로 방지합니다. 프로세스 종료 시 잠금은 풀립니다. 강제 종료 중인 RUNNING 기록은 다음 시작에 INTERRUPTED로 표시됩니다. 기존 성공 데이터를 없애거나 체크포인트만 앞당기지 않습니다.

복원은 수집을 종료하고 현재 파일을 별도 보관한 다음, 무결성이 확인된 백업을 원래 DB 경로로 복사합니다. 실행 중 sqlite 파일을 탐색기로 덮어쓰지 마세요. DB 엔진이 WAL을 사용하는 경우 단순 본체 파일 복사 대신 BACKUP.cmd를 사용합니다.

## 향후 UI/서버 확장

현재 DB는 로컬 단일 수집기용입니다. 다른 직원이 직접 파일을 열거나 TCP로 접속할 수 있는 DB 서버가 아닙니다. 나중에 같은 PC/사내 서버의 API가 읽기 전용 SQL VIEW를 제공하도록 연결합니다. UI에서 Splunk/Oracle을 다시 조회하지 않도록 합니다.

업무 규모가 커지면 source adapters/표준 테이블/매핑 계약은 유지하고 저장소를 PostgreSQL/SQL Server 등으로 이전할 수 있습니다. 이 ZIP에 원격 DB 서버를 설치하거나 방화벽을 열지는 않습니다.
