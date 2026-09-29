# 회사 실행과 업데이트

## 화면부터 보기

`site/index.html`을 다운로드해 브라우저에서 열면 합성 데이터 화면을 확인할 수 있습니다.
`DEMO.cmd`는 별도 합성 SQLite와 실제 Python API를 실행합니다. 회사 연결 정보는 필요하지 않습니다.

## 최초 회사 실행

1. Release의 `SCMRealtimeDB_portable.zip`을 새 폴더에 해제합니다.
2. `SETUP.cmd`를 실행해 `.env`를 준비합니다. 기존 `.env`는 덮어쓰지 않습니다.
3. `.env`에 회사 승인 Splunk/Oracle 연결 정보를 입력합니다. 이 파일은 로컬에만 둡니다.
4. `CHECK.cmd`로 Python·DB·Oracle Thick 준비 상태를 확인합니다.
5. `START.cmd`를 실행합니다. 기본 접속 주소는 `http://127.0.0.1:8765/`입니다.

Python 3.11 이상이 필요합니다. Oracle을 사용하는 Python에는 승인된 `oracledb` 또는 `cx_Oracle`과 호환 Instant Client가 미리 설치되어 있어야 합니다.
회사 망에서 자동 pip 설치나 외부 다운로드를 시도하지 않습니다.

## 새 ZIP으로 교체

수집기를 먼저 종료하고 `BACKUP.cmd`로 백업합니다. 새 ZIP은 새 폴더에 해제합니다.
기존 `.env`는 회사 PC 안에서만 새 폴더로 복사합니다. 직접 수정한 `config/pipeline.json`/SQL은 새 버전과 비교 후 반영합니다.
기본 실제 DB는 `%LOCALAPPDATA%\SCMRealtimeDB\live\scm_live.sqlite`이므로 코드 폴더 밖에 유지됩니다.
`DATA_DIR`을 바꿨다면 같은 로컬 DB 경로를 지정해야 합니다.

소스 키/매핑 지문 오류가 나면 DB 삭제로 해결하지 마세요. 이전 폴더/백업을 보존하고 매핑 차이를 확인합니다.
GitHub의 공개 화면은 합성 데이터 전용이며 회사 API를 외부에 노출하지 않습니다.

## 운영 전 검증

실제 Splunk/Oracle 인증, SAP 대비 수치, CARTON 의미, 원천별 취소/삭제 의미와 수집 누락은 회사 환경에서 확인해야 합니다.
`SHIPMENT_BOX_CONFIRMED=false`가 기본입니다. 검증 없이 true로 바꾸지 마세요.
기존 수기 목표와 집중관리는 운영 DB에 저장됩니다. 정적 HTML 데모의 입력값은 해당 브라우저의 저장소에만 저장됩니다.
